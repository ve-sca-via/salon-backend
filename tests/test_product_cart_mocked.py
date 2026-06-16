"""
Mocked route tests for the product_cart_service module (the /customers/product-cart*
endpoints in app/api/customers.py + app/services/product_cart_service.py).

These run WITHOUT a real Supabase stack. The Supabase DB client is replaced with
a small in-memory fake (the supabase-py builder stand-in used by the other mocked
suites: select/insert/update/delete + eq/maybe_single + an embedded-resource join
`select("*, products(*)")` that get_cart relies on). They exercise the full HTTP
path:

    HTTP -> FastAPI (auth dep overridden, rate limiter disabled) -> route ->
    ProductCartService -> FakeSupabase.

Scope: every /product-cart endpoint (happy path + key error cases), B2B per-line
pricing, and the cleanup applied this module — the update_item/add_to_cart 404
fixes (were 500s) and the new stock-limit guard (400). Admin has no product cart,
so there is no admin tier here.

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import get_current_user, TokenData

API = settings.API_PREFIX
CART = f"{API}/customers/product-cart"


# =====================================================================
# In-memory fake Supabase client (covers the ops product_cart_service uses)
# =====================================================================
class _Resp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, table):
        self._table = table
        self._db = table.db
        self._cols = "*"
        self._filters = []          # list of (op, col, val)
        self._op = ("select", "*")
        self._single = False
        self._maybe = False

    # --- builder ops ---
    def select(self, cols="*", count=None):
        self._op = ("select", cols)
        self._cols = cols
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

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._maybe = True
        return self

    def _match(self, row):
        return all(row.get(c) == v for op, c, v in self._filters if op == "eq")

    def _embed_products(self, row):
        """Mimic PostgREST `products(*)` embed: attach the related product row."""
        product = next(
            (dict(p) for p in self._db.table("products").rows
             if p.get("id") == row.get("product_id")),
            {},
        )
        out = dict(row)
        out["products"] = product
        return out

    def execute(self):
        op, payload = self._op
        rows = self._table.rows

        if op == "select":
            matched = [dict(r) for r in rows if self._match(r)]
            if "products(" in self._cols:
                matched = [self._embed_products(r) for r in matched]
            if self._single:
                if len(matched) != 1:
                    raise Exception("PGRST116: results contain 0 or multiple rows")
                return _Resp(matched[0])
            if self._maybe:
                return _Resp(matched[0] if matched else None)
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
    def __init__(self, db):
        self.db = db
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
        return self._tables.setdefault(name, _Table(self))


# =====================================================================
# Test handle + fixture
# =====================================================================
class Handle:
    def __init__(self, db, app):
        self.db = db
        self.app = app
        self.client = TestClient(app)

    def seed_product(self, **fields):
        pid = fields.pop("id", str(uuid.uuid4()))
        row = {
            "id": pid,
            "name": "Hair Serum",
            "price": 1000.0,
            "discount_price": None,
            "b2b_discount_price": None,
            "image_urls": ["https://img/serum.jpg"],
            "stock_quantity": 10,
        }
        row.update(fields)
        self.db.table("products").rows.append(row)
        return row

    def seed_cart_item(self, user_id, product_id, quantity=1, **fields):
        row = {
            "id": fields.pop("id", str(uuid.uuid4())),
            "user_id": user_id,
            "product_id": product_id,
            "quantity": quantity,
        }
        row.update(fields)
        self.db.table("product_cart_items").rows.append(row)
        return row

    def login_as(self, user_id="user-1", role="customer"):
        td = TokenData(
            user_id=user_id, email=f"{role}@example.com", user_role=role,
            jti="jti-test", exp=datetime.utcnow() + timedelta(hours=1),
        )
        self.app.dependency_overrides[get_current_user] = lambda: td
        return td

    def logout(self):
        self.app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def cart(app):
    db = FakeSupabase()
    handle = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db

    yield handle

    handle.logout()
    app.dependency_overrides.pop(get_db_client, None)


# =====================================================================
# GET /customers/product-cart  (get_cart)
# =====================================================================
def test_get_cart_empty(cart):
    cart.login_as("u1")
    r = cart.client.get(CART)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["items"] == []
    assert body["total_amount"] == 0
    assert body["item_count"] == 0


def test_get_cart_computes_totals(cart):
    p = cart.seed_product(price=1000.0, stock_quantity=5)
    cart.seed_cart_item("u1", p["id"], quantity=2)
    cart.login_as("u1")

    r = cart.client.get(CART)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["item_count"] == 2
    assert body["total_amount"] == 2000.0
    item = body["items"][0]
    assert item["price"] == 1000.0
    assert item["total"] == 2000.0
    assert item["image_url"] == "https://img/serum.jpg"
    assert item["is_b2b_price"] is False


def test_get_cart_uses_discount_price(cart):
    p = cart.seed_product(price=1000.0, discount_price=800.0)
    cart.seed_cart_item("u1", p["id"], quantity=1)
    cart.login_as("u1")

    r = cart.client.get(CART)
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["price"] == 800.0


def test_get_cart_b2b_price_for_vendor(cart):
    p = cart.seed_product(price=1000.0, discount_price=800.0, b2b_discount_price=600.0)
    cart.seed_cart_item("v1", p["id"], quantity=1)
    cart.login_as("v1", role="vendor")

    r = cart.client.get(CART)
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert item["price"] == 600.0
    assert item["is_b2b_price"] is True


def test_get_cart_b2b_price_not_applied_for_customer(cart):
    p = cart.seed_product(price=1000.0, b2b_discount_price=600.0)
    cart.seed_cart_item("u1", p["id"], quantity=1)
    cart.login_as("u1", role="customer")

    r = cart.client.get(CART)
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert item["price"] == 1000.0
    assert item["is_b2b_price"] is False


def test_get_cart_requires_auth(cart):
    r = cart.client.get(CART)
    assert r.status_code in (401, 403), r.text


# =====================================================================
# POST /customers/product-cart  (add_to_cart)
# =====================================================================
def test_add_new_item(cart):
    p = cart.seed_product(stock_quantity=10)
    cart.login_as("u1")

    r = cart.client.post(CART, json={"product_id": p["id"], "quantity": 2})
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    rows = cart.db.table("product_cart_items").rows
    assert len(rows) == 1
    assert rows[0]["quantity"] == 2


def test_add_existing_item_increments(cart):
    p = cart.seed_product(stock_quantity=10)
    cart.seed_cart_item("u1", p["id"], quantity=2)
    cart.login_as("u1")

    r = cart.client.post(CART, json={"product_id": p["id"], "quantity": 3})
    assert r.status_code == 200, r.text
    rows = cart.db.table("product_cart_items").rows
    assert len(rows) == 1                 # not a second row
    assert rows[0]["quantity"] == 5       # 2 + 3


def test_add_missing_product_is_404(cart):
    # add_to_cart uses maybe_single now -> clean 404 (was a 500 before cleanup).
    cart.login_as("u1")
    r = cart.client.post(CART, json={"product_id": str(uuid.uuid4()), "quantity": 1})
    assert r.status_code == 404, r.text


def test_add_exceeding_stock_is_400(cart):
    p = cart.seed_product(stock_quantity=3)
    cart.login_as("u1")
    r = cart.client.post(CART, json={"product_id": p["id"], "quantity": 5})
    assert r.status_code == 400, r.text
    assert "stock" in r.text.lower()


def test_add_increment_exceeding_stock_is_400(cart):
    p = cart.seed_product(stock_quantity=4)
    cart.seed_cart_item("u1", p["id"], quantity=3)
    cart.login_as("u1")
    r = cart.client.post(CART, json={"product_id": p["id"], "quantity": 2})  # 3+2 > 4
    assert r.status_code == 400, r.text


def test_add_requires_auth(cart):
    r = cart.client.post(CART, json={"product_id": str(uuid.uuid4()), "quantity": 1})
    assert r.status_code in (401, 403), r.text


# =====================================================================
# PUT /customers/product-cart/{item_id}  (update_item)
# =====================================================================
def test_update_item_happy(cart):
    p = cart.seed_product(stock_quantity=10)
    item = cart.seed_cart_item("u1", p["id"], quantity=1)
    cart.login_as("u1")

    r = cart.client.put(f"{CART}/{item['id']}", json={"quantity": 4})
    assert r.status_code == 200, r.text
    assert cart.db.table("product_cart_items").rows[0]["quantity"] == 4


def test_update_item_zero_quantity_removes(cart):
    p = cart.seed_product(stock_quantity=10)
    item = cart.seed_cart_item("u1", p["id"], quantity=2)
    cart.login_as("u1")

    r = cart.client.put(f"{CART}/{item['id']}", json={"quantity": 0})
    assert r.status_code == 200, r.text
    assert cart.db.table("product_cart_items").rows == []   # delegated to remove


def test_update_item_not_found_is_404(cart):
    # Regression: this was swallowed into a 500 before the cleanup.
    cart.login_as("u1")
    r = cart.client.put(f"{CART}/{uuid.uuid4()}", json={"quantity": 2})
    assert r.status_code == 404, r.text


def test_update_item_exceeding_stock_is_400(cart):
    p = cart.seed_product(stock_quantity=3)
    item = cart.seed_cart_item("u1", p["id"], quantity=1)
    cart.login_as("u1")

    r = cart.client.put(f"{CART}/{item['id']}", json={"quantity": 5})
    assert r.status_code == 400, r.text


def test_update_item_requires_auth(cart):
    r = cart.client.put(f"{CART}/{uuid.uuid4()}", json={"quantity": 2})
    assert r.status_code in (401, 403), r.text


# =====================================================================
# DELETE /customers/product-cart/{item_id}  (remove_item)
# =====================================================================
def test_remove_item_happy(cart):
    p = cart.seed_product()
    item = cart.seed_cart_item("u1", p["id"], quantity=1)
    cart.login_as("u1")

    r = cart.client.delete(f"{CART}/{item['id']}")
    assert r.status_code == 200, r.text
    assert cart.db.table("product_cart_items").rows == []


def test_remove_item_requires_auth(cart):
    r = cart.client.delete(f"{CART}/{uuid.uuid4()}")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# DELETE /customers/product-cart/clear/all  (clear_cart)
# =====================================================================
def test_clear_cart_removes_only_current_user_items(cart):
    p = cart.seed_product()
    cart.seed_cart_item("u1", p["id"], quantity=1)
    cart.seed_cart_item("u1", str(uuid.uuid4()), quantity=2)
    other = cart.seed_cart_item("u2", p["id"], quantity=1)
    cart.login_as("u1")

    r = cart.client.delete(f"{CART}/clear/all")
    assert r.status_code == 200, r.text
    remaining = cart.db.table("product_cart_items").rows
    assert len(remaining) == 1
    assert remaining[0]["id"] == other["id"]   # u2's item untouched


def test_clear_cart_requires_auth(cart):
    r = cart.client.delete(f"{CART}/clear/all")
    assert r.status_code in (401, 403), r.text
