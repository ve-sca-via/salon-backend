"""
Mocked route tests for the product_service module (app/api/products.py +
app/services/product_service.py).

These run WITHOUT a real Supabase stack. The Supabase DB client is replaced with
a small in-memory fake (the same supabase-py builder stand-in used by the booking
tests: select/insert/update/delete + eq/ilike/order/range/single + count="exact").
They exercise the full HTTP path:

    HTTP -> FastAPI (auth deps overridden, rate limiter disabled) -> route ->
    ProductService -> FakeSupabase.

Scope: every endpoint the module exposes (happy path + key error cases), the
public catalog flow the storefront uses, the B2B price-swap applied for
vendor/regular_buyer roles, and the admin create/update/delete flows — including
the P1 change that hides inactive products by id from non-admin callers.

NOTE on "not found": get_product_by_id / get_product_by_slug use PostgREST's
`.maybe_single()`, which returns None (no raise) on 0 rows, so a missing id/slug
returns a clean 404. The fake mirrors both `.single()` and `.maybe_single()`.

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import require_admin, get_optional_user, TokenData

API = settings.API_PREFIX
PRODUCTS = f"{API}/products"


# =====================================================================
# In-memory fake Supabase client (covers the ops product_service uses)
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
        self._maybe = False
        self._order = []            # list of (col, desc)
        self._range = None          # (start, end) inclusive
        self._count = None

    # --- builder ops ---
    def select(self, cols="*", count=None):
        self._op = ("select", cols)
        self._count = count
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

    def ilike(self, col, pattern):
        self._filters.append(("ilike", col, pattern))
        return self

    def order(self, col, desc=False):
        self._order.append((col, desc))
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._maybe = True
        return self

    def _match(self, row):
        for op, c, v in self._filters:
            rv = row.get(c)
            if op == "eq" and rv != v:
                return False
            if op == "ilike":
                needle = v.strip("%").lower()
                if rv is None or needle not in str(rv).lower():
                    return False
        return True

    def execute(self):
        op, payload = self._op
        rows = self._table.rows

        if op == "select":
            matched = [dict(r) for r in rows if self._match(r)]
            total = len(matched)
            for col, desc in reversed(self._order):
                matched.sort(
                    key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc
                )
            if self._range is not None:
                s, e = self._range
                matched = matched[s:e + 1]
            if self._single:
                # PostgREST .single() raises unless exactly one row matched.
                if len(matched) != 1:
                    raise Exception("PGRST116: results contain 0 or multiple rows")
                return _Resp(matched[0])
            if self._maybe:
                # .maybe_single() returns the row or None (no raise on 0 rows).
                return _Resp(matched[0] if matched else None)
            count = total if self._count == "exact" else None
            return _Resp(matched, count=count)

        if op == "insert":
            new_rows = payload if isinstance(payload, list) else [payload]
            added = []
            for nr in new_rows:
                row = dict(nr)
                row.setdefault("id", str(uuid.uuid4()))
                row.setdefault("created_at", datetime.utcnow().isoformat())
                row.setdefault("updated_at", datetime.utcnow().isoformat())
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
# Test handle + fixture
# =====================================================================
class Handle:
    def __init__(self, db, app):
        self.db = db
        self.app = app
        self.client = TestClient(app)

    def seed_product(self, **fields):
        pid = fields.pop("id", str(uuid.uuid4()))
        name = fields.pop("name", "Hair Serum")
        row = {
            "id": pid,
            "name": name,
            "slug": fields.pop("slug", f"{name.lower().replace(' ', '-')}-{pid[:8]}"),
            "description": "A nice product",
            "price": 1000.0,
            "discount_price": None,
            "discount_percentage": None,
            "b2b_discount_price": None,
            "b2b_discount_percentage": None,
            "category": "haircare",
            "image_urls": [],
            "stock_quantity": 10,
            "is_active": True,
            "is_featured": False,
            "tags": [],
            "created_at": datetime.utcnow().isoformat(),
        }
        row.update(fields)
        self.db.table("products").rows.append(row)
        return row

    def login_admin(self, user_id="admin-1"):
        td = TokenData(
            user_id=user_id, email="admin@example.com", user_role="admin",
            jti="jti-test", exp=datetime.utcnow() + timedelta(hours=1),
        )
        self.app.dependency_overrides[require_admin] = lambda: td
        return td

    def as_optional_user(self, role):
        """Override get_optional_user to simulate a logged-in storefront user."""
        td = TokenData(
            user_id=f"{role}-1", email=f"{role}@example.com", user_role=role,
            jti="jti-test", exp=datetime.utcnow() + timedelta(hours=1),
        )
        self.app.dependency_overrides[get_optional_user] = lambda: td
        return td

    def clear_overrides(self):
        self.app.dependency_overrides.pop(require_admin, None)
        self.app.dependency_overrides.pop(get_optional_user, None)


@pytest.fixture()
def pr(app):
    db = FakeSupabase()
    handle = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db

    yield handle

    handle.clear_overrides()
    app.dependency_overrides.pop(get_db_client, None)


# =====================================================================
# GET /products  (public list)
# =====================================================================
def test_list_happy(pr):
    pr.seed_product(name="A", category="haircare")
    pr.seed_product(name="B", category="skincare")

    r = pr.client.get(PRODUCTS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["total"] == 2
    assert body["count"] == 2
    assert len(body["products"]) == 2


def test_list_excludes_inactive(pr):
    pr.seed_product(name="Active", is_active=True)
    pr.seed_product(name="Hidden", is_active=False)

    r = pr.client.get(PRODUCTS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["products"][0]["name"] == "Active"


def test_list_category_filter(pr):
    pr.seed_product(name="Shampoo", category="haircare")
    pr.seed_product(name="Cream", category="skincare")

    r = pr.client.get(PRODUCTS, params={"category": "skincare"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert all(p["category"] == "skincare" for p in body["products"])


def test_list_featured_filter(pr):
    pr.seed_product(name="Star", is_featured=True)
    pr.seed_product(name="Plain", is_featured=False)

    r = pr.client.get(PRODUCTS, params={"is_featured": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["products"][0]["name"] == "Star"


def test_list_search_by_name(pr):
    pr.seed_product(name="Argan Hair Oil")
    pr.seed_product(name="Face Wash")

    r = pr.client.get(PRODUCTS, params={"search": "argan"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["products"][0]["name"] == "Argan Hair Oil"


def test_list_pagination(pr):
    for i in range(25):
        pr.seed_product(name=f"P{i:02d}", created_at=f"2026-06-01T00:{i:02d}:00")

    r = pr.client.get(PRODUCTS, params={"limit": 10, "offset": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 25      # exact total, not page length
    assert body["count"] == 10      # this page
    assert len(body["products"]) == 10


def test_list_b2b_pricing_applied_for_vendor(pr):
    pr.seed_product(name="Wholesale Item", price=1000.0,
                    discount_price=900.0, discount_percentage=10.0,
                    b2b_discount_price=700.0, b2b_discount_percentage=30.0)
    pr.as_optional_user("vendor")

    r = pr.client.get(PRODUCTS)
    assert r.status_code == 200, r.text
    p = r.json()["products"][0]
    assert p["is_b2b_price"] is True
    assert p["discount_price"] == 700.0           # swapped to B2B price
    assert p["discount_percentage"] == 30.0
    assert p["original_discount_price"] == 900.0   # standard price preserved


def test_list_b2b_pricing_not_applied_for_anonymous(pr):
    pr.seed_product(name="Wholesale Item", price=1000.0,
                    discount_price=900.0, b2b_discount_price=700.0)

    r = pr.client.get(PRODUCTS)
    assert r.status_code == 200, r.text
    p = r.json()["products"][0]
    assert p["is_b2b_price"] is False
    assert p["discount_price"] == 900.0            # standard price unchanged


# =====================================================================
# GET /products/categories
# =====================================================================
def test_categories_distinct_and_sorted(pr):
    pr.seed_product(name="A", category="skincare")
    pr.seed_product(name="B", category="haircare")
    pr.seed_product(name="C", category="haircare")
    pr.seed_product(name="D", category="bodycare", is_active=False)  # inactive ignored

    r = pr.client.get(f"{PRODUCTS}/categories")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["categories"] == ["haircare", "skincare"]


# =====================================================================
# GET /products/slug/{slug}
# =====================================================================
def test_get_by_slug_happy(pr):
    pr.seed_product(name="Detail", slug="detail-product")

    r = pr.client.get(f"{PRODUCTS}/slug/detail-product")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["product"]["slug"] == "detail-product"


def test_get_by_slug_b2b_for_vendor(pr):
    pr.seed_product(name="Detail", slug="b2b-detail", price=1000.0,
                    discount_price=900.0, b2b_discount_price=600.0,
                    b2b_discount_percentage=40.0)
    pr.as_optional_user("regular_buyer")

    r = pr.client.get(f"{PRODUCTS}/slug/b2b-detail")
    assert r.status_code == 200, r.text
    p = r.json()["product"]
    assert p["is_b2b_price"] is True
    assert p["discount_price"] == 600.0


def test_get_by_slug_inactive_or_missing_is_404(pr):
    # Inactive product is filtered out by the slug query (is_active=True), so
    # .maybe_single() matches 0 rows and the service returns a clean 404.
    pr.seed_product(name="Hidden", slug="hidden-product", is_active=False)

    r = pr.client.get(f"{PRODUCTS}/slug/hidden-product")
    assert r.status_code == 404, r.text

    # A completely unknown slug is also a 404.
    r2 = pr.client.get(f"{PRODUCTS}/slug/does-not-exist")
    assert r2.status_code == 404, r2.text


# =====================================================================
# GET /products/{product_id}
# =====================================================================
def test_get_by_id_happy_anonymous(pr):
    prod = pr.seed_product(name="ById")

    r = pr.client.get(f"{PRODUCTS}/{prod['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["product"]["id"] == prod["id"]


def test_get_by_id_inactive_hidden_from_anonymous(pr):
    # P1 change: non-admin callers must not see soft-deleted products by id.
    prod = pr.seed_product(name="Soft Deleted", is_active=False)

    r = pr.client.get(f"{PRODUCTS}/{prod['id']}")
    assert r.status_code == 404, r.text


def test_get_by_id_inactive_visible_to_admin(pr):
    prod = pr.seed_product(name="Soft Deleted", is_active=False)
    pr.login_admin()
    # Admin uses get_optional_user on this route; simulate the admin token there.
    pr.as_optional_user("admin")

    r = pr.client.get(f"{PRODUCTS}/{prod['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["product"]["id"] == prod["id"]


def test_get_by_id_b2b_for_vendor(pr):
    prod = pr.seed_product(name="ById B2B", price=1000.0,
                           discount_price=900.0, b2b_discount_price=500.0,
                           b2b_discount_percentage=50.0)
    pr.as_optional_user("vendor")

    r = pr.client.get(f"{PRODUCTS}/{prod['id']}")
    assert r.status_code == 200, r.text
    p = r.json()["product"]
    assert p["is_b2b_price"] is True
    assert p["discount_price"] == 500.0


def test_get_by_id_missing_is_404(pr):
    # .maybe_single() on 0 rows returns None -> service returns a clean 404.
    r = pr.client.get(f"{PRODUCTS}/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


# =====================================================================
# GET /products/admin/all  (admin list — includes inactive)
# =====================================================================
def test_admin_list_includes_inactive(pr):
    pr.seed_product(name="Active", is_active=True)
    pr.seed_product(name="Hidden", is_active=False)
    pr.login_admin()

    r = pr.client.get(f"{PRODUCTS}/admin/all")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2


def test_admin_list_requires_admin(pr):
    r = pr.client.get(f"{PRODUCTS}/admin/all")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# POST /products  (admin create)
# =====================================================================
def test_create_happy_autoslug(pr):
    pr.login_admin()
    r = pr.client.post(PRODUCTS, json={"name": "Hair Serum 250ml", "price": 499.0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    prod = body["product"]
    assert prod["slug"] == "hair-serum-250ml"   # auto-generated from name
    assert prod["id"]
    assert len(pr.db.table("products").rows) == 1


def test_create_auto_discount_percentage(pr):
    pr.login_admin()
    r = pr.client.post(PRODUCTS, json={"name": "On Sale", "price": 1000.0,
                                       "discount_price": 750.0})
    assert r.status_code == 200, r.text
    assert r.json()["product"]["discount_percentage"] == 25.0


def test_create_auto_b2b_discount_percentage(pr):
    pr.login_admin()
    r = pr.client.post(PRODUCTS, json={"name": "Wholesale", "price": 1000.0,
                                       "b2b_discount_price": 600.0})
    assert r.status_code == 200, r.text
    assert r.json()["product"]["b2b_discount_percentage"] == 40.0


def test_create_duplicate_name_gets_suffixed_slug(pr):
    pr.login_admin()
    pr.client.post(PRODUCTS, json={"name": "Repeat Item", "price": 100.0})
    r2 = pr.client.post(PRODUCTS, json={"name": "Repeat Item", "price": 100.0})
    assert r2.status_code == 200, r2.text
    assert r2.json()["product"]["slug"] == "repeat-item-2"   # uniqueness suffix


def test_create_price_must_be_positive(pr):
    pr.login_admin()
    r = pr.client.post(PRODUCTS, json={"name": "Free", "price": 0})
    assert r.status_code == 422, r.text   # schema gt=0


def test_create_discount_price_above_price_rejected(pr):
    pr.login_admin()
    r = pr.client.post(PRODUCTS, json={"name": "Bad Discount", "price": 100.0,
                                       "discount_price": 150.0})
    assert r.status_code == 422, r.text   # schema validator


def test_create_requires_admin(pr):
    r = pr.client.post(PRODUCTS, json={"name": "NoAuth", "price": 100.0})
    assert r.status_code in (401, 403), r.text


# =====================================================================
# PUT /products/{product_id}  (admin update)
# =====================================================================
def test_update_happy(pr):
    prod = pr.seed_product(name="Old Name", price=500.0)
    pr.login_admin()

    r = pr.client.put(f"{PRODUCTS}/{prod['id']}", json={"name": "New Name"})
    assert r.status_code == 200, r.text
    assert r.json()["product"]["name"] == "New Name"
    assert pr.db.table("products").rows[0]["name"] == "New Name"


def test_update_recalculates_discount_percentage(pr):
    prod = pr.seed_product(name="Item", price=1000.0)
    pr.login_admin()

    r = pr.client.put(f"{PRODUCTS}/{prod['id']}", json={"discount_price": 800.0})
    assert r.status_code == 200, r.text
    assert r.json()["product"]["discount_percentage"] == 20.0


def test_update_slug_collision_rejected(pr):
    pr.seed_product(name="First", slug="taken-slug")
    target = pr.seed_product(name="Second", slug="second-slug")
    pr.login_admin()

    r = pr.client.put(f"{PRODUCTS}/{target['id']}", json={"slug": "taken-slug"})
    assert r.status_code == 400, r.text


def test_update_no_fields_rejected(pr):
    prod = pr.seed_product(name="Item")
    pr.login_admin()
    # All values None -> nothing to update after exclude_none on the route AND
    # the service guard; an empty body yields a 400.
    r = pr.client.put(f"{PRODUCTS}/{prod['id']}", json={})
    assert r.status_code == 400, r.text


def test_update_requires_admin(pr):
    prod = pr.seed_product(name="Item")
    r = pr.client.put(f"{PRODUCTS}/{prod['id']}", json={"name": "X"})
    assert r.status_code in (401, 403), r.text


# =====================================================================
# DELETE /products/{product_id}  (admin)
# =====================================================================
def test_soft_delete_happy(pr):
    prod = pr.seed_product(name="To Deactivate", is_active=True)
    pr.login_admin()

    r = pr.client.delete(f"{PRODUCTS}/{prod['id']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["message"] == "Product deactivated"
    assert pr.db.table("products").rows[0]["is_active"] is False


def test_soft_delete_missing_is_404(pr):
    pr.login_admin()
    r = pr.client.delete(f"{PRODUCTS}/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


def test_hard_delete_removes_row(pr):
    prod = pr.seed_product(name="Gone Forever")
    pr.login_admin()

    r = pr.client.delete(f"{PRODUCTS}/{prod['id']}", params={"hard": True})
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "Product permanently deleted"
    assert pr.db.table("products").rows == []


def test_delete_requires_admin(pr):
    prod = pr.seed_product(name="Item")
    r = pr.client.delete(f"{PRODUCTS}/{prod['id']}")
    assert r.status_code in (401, 403), r.text
