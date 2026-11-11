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
        self._maybe_single = False
        self._order = []
        self._count = False

    def select(self, cols="*", count=None):
        self._op = ("select", cols)
        self._count = count == "exact"
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

    def neq(self, col, val):
        self._filters.append(("neq", col, val))
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

    def maybe_single(self):
        self._maybe_single = True
        return self

    def _match(self, row):
        for op, c, v in self._filters:
            rv = row.get(c)
            if op == "eq" and rv != v:
                return False
            if op == "neq" and rv == v:
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
            if self._maybe_single:
                if len(matched) > 1:
                    raise Exception("PGRST116: results contain multiple rows")
                return _Resp(matched[0] if matched else None)
            return _Resp(matched, count=len(matched) if self._count else None)

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


class _Rpc:
    """Understands `decrement_product_stock` and `redeem_product_coupon` — the
    two RPCs this module calls. Mirrors migrations 20261103000000 and
    20261104000000's behaviour against the fake's in-memory tables."""

    def __init__(self, db, fn_name, params):
        self.db = db
        self.fn_name = fn_name
        self.params = params

    def execute(self):
        if self.fn_name == "decrement_product_stock":
            return self._decrement_product_stock()
        if self.fn_name == "redeem_product_coupon":
            return self._redeem_product_coupon()
        raise Exception(f"FakeSupabase.rpc: unknown function {self.fn_name!r}")

    def _decrement_product_stock(self):
        order_id = self.params["p_order_id"]
        order = next(
            (o for o in self.db.table("product_orders").rows if o["id"] == order_id), None
        )
        if not order or order.get("stock_decremented"):
            return _Resp(False)

        items = [i for i in self.db.table("product_order_items").rows if i["order_id"] == order_id]
        products = self.db.table("products").rows

        # Validate everything before mutating anything, simulating the real
        # function's single transaction (raise rolls back the whole thing).
        for item in items:
            product = next((p for p in products if p["id"] == item["product_id"]), None)
            if not product or (product.get("stock_quantity") or 0) < item["quantity"]:
                raise Exception(f"insufficient_stock_for_product_{item['product_id']}")

        for item in items:
            product = next(p for p in products if p["id"] == item["product_id"])
            product["stock_quantity"] = product["stock_quantity"] - item["quantity"]

        order["stock_decremented"] = True
        return _Resp(True)

    def _redeem_product_coupon(self):
        import uuid as _uuid
        from datetime import datetime as _dt

        coupon_id = self.params["p_coupon_id"]
        user_id = self.params["p_user_id"]
        order_id = self.params["p_product_order_id"]
        discount_amount = self.params["p_discount_amount"]

        redemptions = self.db.table("coupon_redemptions").rows
        existing = next(
            (r for r in redemptions if r["coupon_id"] == coupon_id and r.get("product_order_id") == order_id),
            None,
        )
        if existing:
            return _Resp([{"success": True, "reason": "already_redeemed", "was_already_redeemed": True}])

        coupon = next((c for c in self.db.table("coupons").rows if c["id"] == coupon_id), None)
        if not coupon:
            return _Resp([{"success": False, "reason": "coupon_not_found", "was_already_redeemed": False}])
        if not coupon.get("is_active", True):
            return _Resp([{"success": False, "reason": "coupon_inactive", "was_already_redeemed": False}])
        if coupon.get("applies_to") != "product" or coupon.get("scope") != "platform":
            return _Resp([{"success": False, "reason": "not_applicable_to_products", "was_already_redeemed": False}])

        total_limit = coupon.get("usage_limit_total")
        if total_limit is not None and (coupon.get("used_count") or 0) >= total_limit:
            return _Resp([{"success": False, "reason": "total_limit_reached", "was_already_redeemed": False}])

        per_user_limit = coupon.get("usage_limit_per_user")
        if per_user_limit is not None:
            user_redemptions = len([r for r in redemptions if r["coupon_id"] == coupon_id and r["user_id"] == user_id])
            if user_redemptions >= per_user_limit:
                return _Resp([{"success": False, "reason": "per_user_limit_reached", "was_already_redeemed": False}])

        redemptions.append({
            "id": str(_uuid.uuid4()), "coupon_id": coupon_id, "user_id": user_id,
            "product_order_id": order_id, "discount_amount": discount_amount,
            "gross_discount": discount_amount, "coupon_code": coupon.get("code"),
            "funded_by": coupon.get("funded_by"), "scope": coupon.get("scope"),
            "redeemed_at": _dt.utcnow().isoformat(),
        })
        coupon["used_count"] = (coupon.get("used_count") or 0) + 1
        return _Resp([{"success": True, "reason": "redeemed", "was_already_redeemed": False}])


class FakeSupabase:
    def __init__(self):
        self._tables = {}

    def table(self, name):
        return self._tables.setdefault(name, _Table())

    def rpc(self, fn_name, params):
        return _Rpc(self, fn_name, params)


# =====================================================================
# Fake Razorpay (signature check is controllable per test)
# =====================================================================
class FakeRazorpay:
    valid = True  # class-level switch flipped by individual tests

    def __init__(self, *args, **kwargs):
        pass

    # Async to match the real RazorpayService (payment audit C-4).
    async def create_order(self, amount, receipt, notes=None):
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

    def seed_coupon(self, **fields):
        row = {
            "id": fields.pop("id", str(uuid.uuid4())),
            "code": "SAVE20",
            "title": "20% off products",
            "scope": "platform",
            "salon_id": None,
            "funded_by": "platform",
            "applies_to": "product",
            "discount_type": "percentage",
            "discount_value": 20,
            "max_discount_cap": None,
            "min_order_amount": None,
            "first_time_scope": None,
            "usage_limit_total": None,
            "usage_limit_per_user": 1,
            "used_count": 0,
            "valid_from": None,
            "valid_until": None,
            "is_active": True,
        }
        row.update(fields)
        self.db.table("coupons").rows.append(row)
        return row

    def seed_salon(self, vendor_id, **fields):
        row = {
            "id": str(uuid.uuid4()), "vendor_id": vendor_id,
            "registration_fee_paid": True, "registration_fee_amount": 5000.0,
        }
        row.update(fields)
        self.db.table("salons").rows.append(row)
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


def _order_payload(product_id, quantity=2, **extra):
    return {
        "shipping_address": {"line1": "1 Test St", "city": "Testville", "pincode": "560001"},
        "items": [{"product_id": product_id, "quantity": quantity}],
        **extra,
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


def test_create_order_ignores_client_supplied_discount(od):
    # Regression for audit C-5: `discount_total` used to be read off the request
    # and subtracted from the server-computed subtotal, with the result floored at
    # the ₹1 gateway minimum — so any caller could buy any order for ₹1. There is
    # no coupon flow for product orders, so the field is now ignored entirely.
    od.seed_profile("u1")
    p = od.seed_product(price=1000.0)
    od.login_as("u1")

    r = od.client.post(
        f"{ORDERS}/create",
        json=_order_payload(p["id"], quantity=1, discount_total=999999.0),
    )
    assert r.status_code == 200, r.text
    assert r.json()["order"]["total_amount"] == 1000.0
    assert r.json()["order"]["discount_total"] == 0.0

    # A negative "discount" must not inflate the charge either.
    r = od.client.post(
        f"{ORDERS}/create",
        json=_order_payload(p["id"], quantity=1, discount_total=-500.0),
    )
    assert r.status_code == 200, r.text
    assert r.json()["order"]["total_amount"] == 1000.0


def test_create_order_unknown_product_is_400(od):
    od.seed_profile("u1")
    od.login_as("u1")
    r = od.client.post(f"{ORDERS}/create", json=_order_payload(str(uuid.uuid4())))
    assert r.status_code == 400, r.text


def test_create_order_requires_auth(od):
    r = od.client.post(f"{ORDERS}/create", json=_order_payload(str(uuid.uuid4())))
    assert r.status_code in (401, 403), r.text


def test_create_order_insufficient_stock_is_400(od):
    od.seed_profile("u1")
    p = od.seed_product(price=1000.0, stock_quantity=1)
    od.login_as("u1")

    r = od.client.post(f"{ORDERS}/create", json=_order_payload(p["id"], quantity=2))
    assert r.status_code == 400, r.text
    assert "stock" in r.json()["message"].lower()
    # Rejected before any order row was created.
    assert od.db.table("product_orders").rows == []


def test_create_order_inactive_product_is_400(od):
    od.seed_profile("u1")
    p = od.seed_product(price=1000.0, stock_quantity=10, is_active=False)
    od.login_as("u1")

    r = od.client.post(f"{ORDERS}/create", json=_order_payload(p["id"], quantity=1))
    assert r.status_code == 400, r.text
    assert "no longer available" in r.json()["message"].lower()
    # Rejected before any order row was created.
    assert od.db.table("product_orders").rows == []


def test_create_order_allows_exact_remaining_stock(od):
    od.seed_profile("u1")
    p = od.seed_product(price=1000.0, stock_quantity=2)
    od.login_as("u1")

    r = od.client.post(f"{ORDERS}/create", json=_order_payload(p["id"], quantity=2))
    assert r.status_code == 200, r.text


def test_create_order_blocked_when_registration_fee_unpaid(od):
    od.seed_profile("v1", role="vendor")
    od.seed_salon("v1", registration_fee_paid=False, registration_fee_amount=2500.0)
    p = od.seed_product(price=1000.0)
    od.login_as("v1", role="vendor")

    r = od.client.post(f"{ORDERS}/create", json=_order_payload(p["id"], quantity=1))
    assert r.status_code == 403, r.text
    assert "registration payment" in r.json()["message"].lower()
    assert "2,500" in r.json()["message"]
    assert od.db.table("product_orders").rows == []


def test_create_order_allowed_when_registration_fee_paid(od):
    od.seed_profile("v1", role="vendor")
    od.seed_salon("v1", registration_fee_paid=True)
    p = od.seed_product(price=1000.0)
    od.login_as("v1", role="vendor")

    r = od.client.post(f"{ORDERS}/create", json=_order_payload(p["id"], quantity=1))
    assert r.status_code == 200, r.text


def test_create_order_allowed_when_b2b_user_has_no_salon_row(od):
    # Fail open: an inconsistent account state (B2B role, no salon row at all)
    # isn't a reason to block every order. Also covers regular_buyer, not just
    # vendor.
    od.seed_profile("b1", role="regular_buyer")
    p = od.seed_product(price=1000.0)
    od.login_as("b1", role="regular_buyer")

    r = od.client.post(f"{ORDERS}/create", json=_order_payload(p["id"], quantity=1))
    assert r.status_code == 200, r.text


def test_create_order_registration_fee_check_skipped_for_customers(od):
    # A plain customer role has no salon at all — the B2B gate must not run for it.
    od.seed_profile("u1", role="customer")
    p = od.seed_product(price=1000.0)
    od.login_as("u1", role="customer")

    r = od.client.post(f"{ORDERS}/create", json=_order_payload(p["id"], quantity=1))
    assert r.status_code == 200, r.text


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


def test_verify_payment_decrements_stock_exactly_once(od):
    order = od.seed_order("u1", razorpay_order_id="order_x")
    p = od.seed_product(stock_quantity=10)
    od.seed_order_item(order["id"], product_id=p["id"], quantity=3)
    od.login_as("u1")
    FakeRazorpay.valid = True

    r = od.client.post(f"{ORDERS}/verify", json=_verify_payload("order_x"))
    assert r.status_code == 200, r.text
    assert od.db.table("products").rows[0]["stock_quantity"] == 7
    assert od.db.table("product_orders").rows[0]["stock_decremented"] is True

    # A second confirmation of the same already-paid order (retry after a
    # dropped response, say) must not decrement a second time.
    r2 = od.client.post(f"{ORDERS}/verify", json=_verify_payload("order_x"))
    assert r2.status_code == 200, r2.text
    assert od.db.table("products").rows[0]["stock_quantity"] == 7


def test_verify_payment_oversell_race_still_confirms_order(od):
    # Payment is already captured by the time stock is checked, so a genuine
    # oversell race (stock changed between order creation and confirmation)
    # must not block marking the order paid — there's no way to un-charge the
    # buyer from here. It's logged, not raised.
    order = od.seed_order("u1", razorpay_order_id="order_x")
    p = od.seed_product(stock_quantity=1)
    od.seed_order_item(order["id"], product_id=p["id"], quantity=3)
    od.login_as("u1")
    FakeRazorpay.valid = True

    r = od.client.post(f"{ORDERS}/verify", json=_verify_payload("order_x"))
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    assert od.db.table("products").rows[0]["stock_quantity"] == 1  # untouched


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


def test_dev_verify_decrements_stock(od):
    order = od.seed_order("u1")
    p = od.seed_product(stock_quantity=5)
    od.seed_order_item(order["id"], product_id=p["id"], quantity=2)
    od.login_as("u1")

    r = od.client.post(f"{ORDERS}/dev-verify/{order['id']}")
    assert r.status_code == 200, r.text
    assert od.db.table("products").rows[0]["stock_quantity"] == 3


# =====================================================================
# GET /product-orders/{order_id}
# =====================================================================
def test_get_order_by_id_happy(od):
    order = od.seed_order("u1")
    od.seed_order_item(order["id"], product_name="Serum A")
    od.login_as("u1")

    r = od.client.get(f"{ORDERS}/{order['id']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == order["id"]
    assert body["items"][0]["product_name"] == "Serum A"


def test_get_order_by_id_404_for_another_users_order(od):
    order = od.seed_order("u1")
    od.login_as("u2")

    r = od.client.get(f"{ORDERS}/{order['id']}")
    assert r.status_code == 404, r.text


def test_get_order_by_id_404_when_missing(od):
    od.login_as("u1")
    r = od.client.get(f"{ORDERS}/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


def test_get_order_by_id_requires_auth(od):
    r = od.client.get(f"{ORDERS}/{uuid.uuid4()}")
    assert r.status_code in (401, 403), r.text


def test_get_order_by_id_does_not_shadow_my_orders(od):
    # /{order_id} is registered after /my-orders specifically so this keeps working.
    od.login_as("u1")
    r = od.client.get(f"{ORDERS}/my-orders")
    assert r.status_code == 200, r.text
    assert r.json() == []


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


# =====================================================================
# Coupon support (migration 20261104000000_add_product_order_coupon_support.sql)
# =====================================================================
def test_create_order_with_valid_coupon_applies_discount(od):
    od.seed_profile("u1")
    p = od.seed_product(price=1000.0)
    od.seed_coupon(code="SAVE20", discount_type="percentage", discount_value=20)
    od.login_as("u1")

    r = od.client.post(
        f"{ORDERS}/create",
        json=_order_payload(p["id"], quantity=1, coupon_code="save20"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["order"]["subtotal"] == 1000.0
    assert body["order"]["discount_total"] == 200.0
    assert body["order"]["total_amount"] == 800.0
    assert body["order"]["coupon_code"] == "SAVE20"
    assert body["coupon_reason"] is None


def test_create_order_with_unknown_coupon_proceeds_without_discount(od):
    od.seed_profile("u1")
    p = od.seed_product(price=1000.0)
    od.login_as("u1")

    r = od.client.post(
        f"{ORDERS}/create",
        json=_order_payload(p["id"], quantity=1, coupon_code="NOPE"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["order"]["discount_total"] == 0.0
    assert body["order"]["total_amount"] == 1000.0
    assert body["order"]["coupon_code"] is None
    assert body["coupon_reason"] is not None


def test_create_order_with_service_coupon_is_rejected_for_products(od):
    # A booking coupon (applies_to='service') must never discount a product
    # order, even if the code is otherwise valid.
    od.seed_profile("u1")
    p = od.seed_product(price=1000.0)
    od.seed_coupon(code="BOOKING10", applies_to="service")
    od.login_as("u1")

    r = od.client.post(
        f"{ORDERS}/create",
        json=_order_payload(p["id"], quantity=1, coupon_code="BOOKING10"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["order"]["total_amount"] == 1000.0
    assert r.json()["coupon_reason"] is not None


def test_create_order_coupon_respects_server_computed_subtotal(od):
    # The discount is computed against the server-priced subtotal (DB price),
    # not anything the client could influence.
    od.seed_profile("u1")
    p = od.seed_product(price=500.0, discount_price=400.0)
    od.seed_coupon(code="FLAT100", discount_type="flat_amount", discount_value=100)
    od.login_as("u1")

    r = od.client.post(
        f"{ORDERS}/create",
        json=_order_payload(p["id"], quantity=2, coupon_code="FLAT100"),
    )
    assert r.status_code == 200, r.text
    body = r.json()["order"]
    assert body["subtotal"] == 800.0   # 400 * 2
    assert body["discount_total"] == 100.0
    assert body["total_amount"] == 700.0


# ---- POST /product-orders/validate-coupon ----
def test_validate_coupon_happy(od):
    od.seed_profile("u1")
    p = od.seed_product(price=1000.0)
    od.seed_coupon(code="SAVE20", discount_type="percentage", discount_value=20)
    od.login_as("u1")

    r = od.client.post(
        f"{ORDERS}/validate-coupon",
        json={"code": "save20", "items": [{"product_id": p["id"], "quantity": 1}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert body["coupon_code"] == "SAVE20"
    assert body["breakdown"]["subtotal"] == 1000.0
    assert body["breakdown"]["discount_amount"] == 200.0
    assert body["breakdown"]["total_amount"] == 800.0


def test_validate_coupon_invalid_code(od):
    od.seed_profile("u1")
    p = od.seed_product(price=1000.0)
    od.login_as("u1")

    r = od.client.post(
        f"{ORDERS}/validate-coupon",
        json={"code": "NOPE", "items": [{"product_id": p["id"], "quantity": 1}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is False
    assert body["breakdown"] is None


def test_validate_coupon_requires_auth(od):
    r = od.client.post(
        f"{ORDERS}/validate-coupon",
        json={"code": "SAVE20", "items": [{"product_id": str(uuid.uuid4()), "quantity": 1}]},
    )
    assert r.status_code in (401, 403), r.text


# ---- GET /product-orders/available-coupons ----
def test_available_coupons_lists_active_platform_product_coupons(od):
    od.seed_profile("u1")
    od.seed_coupon(code="SAVE20")
    od.seed_coupon(code="SERVICEONLY", applies_to="service")  # must not appear
    od.login_as("u1")

    r = od.client.get(f"{ORDERS}/available-coupons")
    assert r.status_code == 200, r.text
    codes = [c["code"] for c in r.json()]
    assert codes == ["SAVE20"]


def test_available_coupons_requires_auth(od):
    r = od.client.get(f"{ORDERS}/available-coupons")
    assert r.status_code in (401, 403), r.text


# ---- Redemption at payment-captured time (verify / dev-verify / webhook) ----
def test_verify_payment_redeems_coupon_exactly_once(od):
    coupon = od.seed_coupon(code="SAVE20")
    order = od.seed_order(
        "u1", razorpay_order_id="order_x",
        coupon_id=coupon["id"], coupon_code=coupon["code"], discount_total=200.0,
    )
    od.login_as("u1")
    FakeRazorpay.valid = True

    r = od.client.post(f"{ORDERS}/verify", json=_verify_payload("order_x"))
    assert r.status_code == 200, r.text
    assert len(od.db.table("coupon_redemptions").rows) == 1
    redemption = od.db.table("coupon_redemptions").rows[0]
    assert redemption["product_order_id"] == order["id"]
    assert redemption["discount_amount"] == 200.0
    assert od.db.table("coupons").rows[0]["used_count"] == 1

    # A second confirmation of the same already-paid order must not redeem twice.
    r2 = od.client.post(f"{ORDERS}/verify", json=_verify_payload("order_x"))
    assert r2.status_code == 200, r2.text
    assert len(od.db.table("coupon_redemptions").rows) == 1
    assert od.db.table("coupons").rows[0]["used_count"] == 1


def test_verify_payment_without_coupon_does_not_touch_redemptions(od):
    od.seed_order("u1", razorpay_order_id="order_x")
    od.login_as("u1")
    FakeRazorpay.valid = True

    r = od.client.post(f"{ORDERS}/verify", json=_verify_payload("order_x"))
    assert r.status_code == 200, r.text
    assert od.db.table("coupon_redemptions").rows == []


def test_dev_verify_redeems_coupon(od):
    coupon = od.seed_coupon(code="SAVE20")
    order = od.seed_order("u1", coupon_id=coupon["id"], discount_total=200.0)
    od.login_as("u1")

    r = od.client.post(f"{ORDERS}/dev-verify/{order['id']}")
    assert r.status_code == 200, r.text
    assert len(od.db.table("coupon_redemptions").rows) == 1
    assert od.db.table("coupons").rows[0]["used_count"] == 1
