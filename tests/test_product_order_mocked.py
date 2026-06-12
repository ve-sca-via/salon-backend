"""
Mocked route tests for the product_order_service module (app/api/product_orders.py +
app/api/admin/product_orders.py + app/services/product_order_service.py).

These run WITHOUT a real Supabase stack or Razorpay account. The DB client is a
small in-memory fake; ProductOrderService._get_razorpay_creds is stubbed to force
"dev/simulation" mode for create_order, and app.services.payment.RazorpayService
is replaced with a fake whose signature check is controllable. They exercise the
full HTTP path:

    HTTP -> FastAPI (auth deps overridden, rate limiter disabled) -> route ->
    ProductOrderService -> FakeSupabase / FakeRazorpay.

Scope: every endpoint (customer create/verify/dev-verify/my-orders + admin
list/status), B2B price selection at order time, and the cleanup applied this
module — the verify_payment 400/404 fixes (were 500s) and the admin status enum.

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import get_current_user, require_admin, TokenData
from app.services.product_order_service import ProductOrderService

API = settings.API_PREFIX
ORDERS = f"{API}/product-orders"
ADMIN_ORDERS = f"{API}/admin/product-orders"


# =====================================================================
# In-memory fake Supabase client
# =====================================================================
class _Resp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, table):
        self._table = table
        self._filters = []          # list of (op, col, val)
        self._op = ("select", "*")
        self._single = False
        self._order = []

    def select(self, cols="*", count=None):
        self._op = ("select", cols)
        return self

    def insert(self, payload):
        self._op = ("insert", payload)
        return self

    def update(self, payload):
        self._op = ("update", payload)
        return self

    def delete(self):
        self._op = ("delete", None)
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def order(self, col, desc=False):
        self._order.append((col, desc))
        return self

    def single(self):
        self._single = True
        return self

    def _match(self, row):
        for op, c, v in self._filters:
            rv = row.get(c)
            if op == "eq" and rv != v:
                return False
            if op == "in" and rv not in v:
                return False
        return True

    def execute(self):
        op, payload = self._op
        rows = self._table.rows

        if op == "select":
            matched = [dict(r) for r in rows if self._match(r)]
            for col, desc in reversed(self._order):
                matched.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
            if self._single:
                if len(matched) != 1:
                    raise Exception("PGRST116: results contain 0 or multiple rows")
                return _Resp(matched[0])
            return _Resp(matched)

        if op == "insert":
            new_rows = payload if isinstance(payload, list) else [payload]
            added = []
            for nr in new_rows:
                row = dict(nr)
                row.setdefault("id", str(uuid.uuid4()))
                row.setdefault("created_at", datetime.utcnow().isoformat())
                rows.append(row)
                added.append(dict(row))
            return _Resp(added)

        if op == "update":
            updated = []
            for r in rows:
                if self._match(r):
                    r.update(payload)
                    updated.append(dict(r))
            return _Resp(updated)

        if op == "delete":
            removed = [dict(r) for r in rows if self._match(r)]
            rows[:] = [r for r in rows if not self._match(r)]
            return _Resp(removed)

        return _Resp(None)


class _Table:
    def __init__(self):
        self.rows = []

    def select(self, cols="*", count=None):
        return _Query(self).select(cols, count=count)

    def insert(self, payload):
        return _Query(self).insert(payload)

    def update(self, payload):
        return _Query(self).update(payload)

    def delete(self):
        return _Query(self).delete()


class FakeSupabase:
    def __init__(self):
        self._tables = {}

    def table(self, name):
        return self._tables.setdefault(name, _Table())


# =====================================================================
# Fake Razorpay (signature check is controllable per test)
# =====================================================================
class FakeRazorpay:
    valid = True  # class-level switch flipped by individual tests

    def __init__(self, *args, **kwargs):
        pass

    def create_order(self, amount, receipt, notes=None):
        return {"order_id": f"order_{uuid.uuid4().hex[:12]}", "amount": amount, "currency": "INR"}

    def verify_payment_signature(self, razorpay_order_id, razorpay_payment_id, razorpay_signature):
        return FakeRazorpay.valid


# =====================================================================
# Test handle + fixture
# =====================================================================
class Handle:
    def __init__(self, db, app):
        self.db = db
        self.app = app
        self.client = TestClient(app)

    def seed_profile(self, user_id, role="customer", **fields):
        row = {"id": user_id, "full_name": f"User {user_id}", "phone": "9999999999", "user_role": role}
        row.update(fields)
        self.db.table("profiles").rows.append(row)
        return row

    def seed_product(self, **fields):
        pid = fields.pop("id", str(uuid.uuid4()))
        row = {
            "id": pid, "name": "Hair Serum", "price": 1000.0,
            "discount_price": None, "b2b_discount_price": None,
            "image_urls": ["https://img/serum.jpg"],
        }
        row.update(fields)
        self.db.table("products").rows.append(row)
        return row

    def seed_order(self, user_id, **fields):
        row = {
            "id": fields.pop("id", str(uuid.uuid4())),
            "user_id": user_id,
            "order_number": f"ORD-{uuid.uuid4().hex[:6]}",
            "status": "pending",
            "payment_status": "pending",
            "subtotal": 1000.0, "total_amount": 1000.0,
            "created_at": datetime.utcnow().isoformat(),
        }
        row.update(fields)
        self.db.table("product_orders").rows.append(row)
        return row

    def seed_order_item(self, order_id, **fields):
        row = {
            "id": str(uuid.uuid4()), "order_id": order_id,
            "product_id": str(uuid.uuid4()), "product_name": "Hair Serum",
            "quantity": 1, "unit_price": 1000.0, "total_price": 1000.0,
        }
        row.update(fields)
        self.db.table("product_order_items").rows.append(row)
        return row

    def login_as(self, user_id="u1", role="customer"):
        td = TokenData(user_id=user_id, email=f"{role}@example.com", user_role=role,
                       jti="jti", exp=datetime.utcnow() + timedelta(hours=1))
        self.app.dependency_overrides[get_current_user] = lambda: td
        return td

    def login_admin(self):
        td = TokenData(user_id="admin-1", email="admin@example.com", user_role="admin",
                       jti="jti", exp=datetime.utcnow() + timedelta(hours=1))
        self.app.dependency_overrides[require_admin] = lambda: td
        return td

    def logout(self):
        self.app.dependency_overrides.pop(get_current_user, None)
        self.app.dependency_overrides.pop(require_admin, None)


@pytest.fixture()
def od(app, monkeypatch):
    db = FakeSupabase()
    handle = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db

    # Force dev/simulation mode for create_order (no real Razorpay network).
    async def _dev_creds(self):
        return "dev_key", "dev_secret", True
    monkeypatch.setattr(ProductOrderService, "_get_razorpay_creds", _dev_creds)

    # Replace the Razorpay client used by verify_payment.
    FakeRazorpay.valid = True
    monkeypatch.setattr("app.services.payment.RazorpayService", FakeRazorpay)

    yield handle

    handle.logout()
    app.dependency_overrides.pop(get_db_client, None)


def _order_payload(product_id, quantity=2, discount_total=0.0):
    return {
        "shipping_address": {"line1": "1 Test St", "city": "Testville", "pincode": "560001"},
        "discount_total": discount_total,
        "items": [{"product_id": product_id, "quantity": quantity}],
    }


# =====================================================================
# POST /product-orders/create
# =====================================================================
def test_create_order_happy_dev_mode(od):
    od.seed_profile("u1", role="customer")
    p = od.seed_product(price=1000.0)
    od.login_as("u1")

    r = od.client.post(f"{ORDERS}/create", json=_order_payload(p["id"], quantity=2))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dev_mode"] is True
    assert body["razorpay_order_id"].startswith("dev_order_")
    assert body["order"]["total_amount"] == 2000.0   # 1000 * 2, DB price
    # Order + items persisted
    assert len(od.db.table("product_orders").rows) == 1
    items = od.db.table("product_order_items").rows
    assert len(items) == 1 and items[0]["unit_price"] == 1000.0


def test_create_order_uses_db_price_not_client(od):
    # The schema only accepts product_id + quantity; price comes from the DB.
    od.seed_profile("u1")
    p = od.seed_product(price=500.0, discount_price=400.0)
    od.login_as("u1")

    r = od.client.post(f"{ORDERS}/create", json=_order_payload(p["id"], quantity=3))
    assert r.status_code == 200, r.text
    assert r.json()["order"]["total_amount"] == 1200.0   # discount_price 400 * 3


def test_create_order_b2b_price_for_vendor(od):
    od.seed_profile("v1", role="vendor")
    p = od.seed_product(price=1000.0, discount_price=900.0, b2b_discount_price=600.0)
    od.login_as("v1", role="vendor")

    r = od.client.post(f"{ORDERS}/create", json=_order_payload(p["id"], quantity=1))
    assert r.status_code == 200, r.text
    assert r.json()["order"]["total_amount"] == 600.0
    assert r.json()["order"]["user_type"] == "vendor"


def test_create_order_applies_discount_total(od):
    od.seed_profile("u1")
    p = od.seed_product(price=1000.0)
    od.login_as("u1")

    r = od.client.post(f"{ORDERS}/create", json=_order_payload(p["id"], quantity=1, discount_total=200.0))
    assert r.status_code == 200, r.text
    assert r.json()["order"]["total_amount"] == 800.0


def test_create_order_unknown_product_is_400(od):
    od.seed_profile("u1")
    od.login_as("u1")
    r = od.client.post(f"{ORDERS}/create", json=_order_payload(str(uuid.uuid4())))
    assert r.status_code == 400, r.text


def test_create_order_requires_auth(od):
    r = od.client.post(f"{ORDERS}/create", json=_order_payload(str(uuid.uuid4())))
    assert r.status_code in (401, 403), r.text


# =====================================================================
# POST /product-orders/verify
# =====================================================================
def _verify_payload(order_id="order_x"):
    return {"razorpay_order_id": order_id, "razorpay_payment_id": "pay_1", "razorpay_signature": "sig_1"}


def test_verify_payment_happy(od):
    od.seed_order("u1", razorpay_order_id="order_x")
    od.login_as("u1")
    FakeRazorpay.valid = True

    r = od.client.post(f"{ORDERS}/verify", json=_verify_payload("order_x"))
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    row = od.db.table("product_orders").rows[0]
    assert row["status"] == "paid"
    assert row["payment_status"] == "completed"
    assert row["razorpay_payment_id"] == "pay_1"


def test_verify_payment_invalid_signature_is_400(od):
    # Regression: this was swallowed into a 500 before the cleanup.
    od.seed_order("u1", razorpay_order_id="order_x")
    od.login_as("u1")
    FakeRazorpay.valid = False

    r = od.client.post(f"{ORDERS}/verify", json=_verify_payload("order_x"))
    assert r.status_code == 400, r.text


def test_verify_payment_order_not_found_is_404(od):
    # Valid signature but no matching order -> clean 404 (was a 500).
    od.login_as("u1")
    FakeRazorpay.valid = True
    r = od.client.post(f"{ORDERS}/verify", json=_verify_payload("order_missing"))
    assert r.status_code == 404, r.text


def test_verify_payment_requires_auth(od):
    r = od.client.post(f"{ORDERS}/verify", json=_verify_payload())
    assert r.status_code in (401, 403), r.text


# =====================================================================
# POST /product-orders/dev-verify/{order_id}
# =====================================================================
def test_dev_verify_happy(od):
    order = od.seed_order("u1")
    od.login_as("u1")

    r = od.client.post(f"{ORDERS}/dev-verify/{order['id']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dev_mode"] is True
    row = od.db.table("product_orders").rows[0]
    assert row["status"] == "paid"
    assert row["payment_status"] == "completed"


def test_dev_verify_not_found_is_404(od):
    od.login_as("u1")
    r = od.client.post(f"{ORDERS}/dev-verify/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


def test_dev_verify_blocked_in_production(od, monkeypatch):
    order = od.seed_order("u1")
    od.login_as("u1")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    r = od.client.post(f"{ORDERS}/dev-verify/{order['id']}")
    assert r.status_code == 403, r.text


def test_dev_verify_requires_auth(od):
    r = od.client.post(f"{ORDERS}/dev-verify/{uuid.uuid4()}")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# GET /product-orders/my-orders
# =====================================================================
def test_my_orders_returns_user_orders_with_items(od):
    o1 = od.seed_order("u1", created_at="2026-06-01T00:00:00")
    o2 = od.seed_order("u1", created_at="2026-06-02T00:00:00")
    od.seed_order("u2")  # another user's order
    od.seed_order_item(o1["id"], product_name="Serum A")
    od.seed_order_item(o2["id"], product_name="Serum B")
    od.login_as("u1")

    r = od.client.get(f"{ORDERS}/my-orders")
    assert r.status_code == 200, r.text
    orders = r.json()
    assert len(orders) == 2                       # only u1's
    assert orders[0]["id"] == o2["id"]            # newest first
    assert orders[0]["items"][0]["product_name"] == "Serum B"


def test_my_orders_empty(od):
    od.login_as("u1")
    r = od.client.get(f"{ORDERS}/my-orders")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_my_orders_requires_auth(od):
    r = od.client.get(f"{ORDERS}/my-orders")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# GET /admin/product-orders/  (admin list)
# =====================================================================
def test_admin_list_orders_with_profiles_and_items(od):
    od.seed_profile("u1", role="customer", full_name="Alice")
    od.seed_profile("u2", role="vendor", full_name="Bob")
    o1 = od.seed_order("u1")
    o2 = od.seed_order("u2")
    od.seed_order_item(o1["id"])
    od.login_admin()

    r = od.client.get(f"{ADMIN_ORDERS}/")
    assert r.status_code == 200, r.text
    orders = r.json()
    assert len(orders) == 2
    by_id = {o["id"]: o for o in orders}
    assert by_id[o1["id"]]["profiles"]["full_name"] == "Alice"
    assert len(by_id[o1["id"]]["items"]) == 1
    assert by_id[o2["id"]]["items"] == []


def test_admin_list_requires_admin(od):
    r = od.client.get(f"{ADMIN_ORDERS}/")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# PATCH /admin/product-orders/{order_id}/status
# =====================================================================
def test_admin_update_status_happy(od):
    order = od.seed_order("u1", status="paid")
    od.login_admin()

    r = od.client.patch(f"{ADMIN_ORDERS}/{order['id']}/status", json={"status": "shipped"})
    assert r.status_code == 200, r.text
    assert r.json()["order"]["status"] == "shipped"
    assert od.db.table("product_orders").rows[0]["status"] == "shipped"


def test_admin_update_status_invalid_value_is_422(od):
    order = od.seed_order("u1")
    od.login_admin()
    r = od.client.patch(f"{ADMIN_ORDERS}/{order['id']}/status", json={"status": "bogus"})
    assert r.status_code == 422, r.text   # Literal validation at the route


def test_admin_update_status_not_found_is_404(od):
    od.login_admin()
    r = od.client.patch(f"{ADMIN_ORDERS}/{uuid.uuid4()}/status", json={"status": "shipped"})
    assert r.status_code == 404, r.text


def test_admin_update_status_requires_admin(od):
    r = od.client.patch(f"{ADMIN_ORDERS}/{uuid.uuid4()}/status", json={"status": "shipped"})
    assert r.status_code in (401, 403), r.text
