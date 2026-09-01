"""
Mocked route tests for the vendor_service module:

    app/api/vendors.py            (vendor self-service endpoints)
    app/services/vendor_service.py
    app/services/service_taxonomy.py (build_category_tree, shared after P3c)

These run WITHOUT a real Supabase stack. The Supabase DB client is replaced with
a small in-memory fake (the same builder stand-in used by the salon/booking tests,
extended with the ops vendor_service needs: from_ / is_ / gte / lte / limit /
count="exact"). They exercise the full HTTP path:

    HTTP -> FastAPI (require_vendor overridden, rate limiter disabled) -> route ->
    VendorService -> FakeSupabase.

Scope: every endpoint the module exposes (happy path + key error cases) plus the
cleanup invariants landed in this pass:
  * P3a — process-payment returns the fee from system_config, not a hardcoded 5000.
  * P3c — /service-categories still returns the nested 3-level tree after the
    assembly moved into ServiceTaxonomyResolver.build_category_tree.

The admin panel does NOT call any /vendors/* endpoint (admin vendor management is
the separate /admin/vendor-requests approval module), and the only "frontend"
caller is the vendor-facing app's vendorApi.js. So these route tests are the
integration surface for both the API contract and its single consumer.

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import require_vendor, TokenData
from app.services.booking_service import BookingService

API = settings.API_PREFIX
VENDORS = f"{API}/vendors"


# =====================================================================
# In-memory fake Supabase client (covers the ops vendor_service uses)
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
        self._order = []            # list of (col, desc)
        self._range = None          # (start, end) inclusive
        self._limit = None
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

    def neq(self, col, val):
        self._filters.append(("neq", col, val))
        return self

    def gte(self, col, val):
        self._filters.append(("gte", col, val))
        return self

    def lte(self, col, val):
        self._filters.append(("lte", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    def order(self, col, desc=False):
        self._order.append((col, desc))
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def single(self):
        self._single = True
        return self

    def _match(self, row):
        for op, c, v in self._filters:
            rv = row.get(c)
            if op == "eq" and rv != v:
                return False
            if op == "neq" and rv == v:
                return False
            if op == "gte" and not (rv is not None and rv >= v):
                return False
            if op == "lte" and not (rv is not None and rv <= v):
                return False
            if op == "in" and rv not in v:
                return False
            if op == "is":
                # only "null" is used by the service layer
                if v == "null" and rv is not None:
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
                matched = matched[s:e]
            if self._limit is not None:
                matched = matched[:self._limit]
            if self._single:
                if len(matched) != 1:
                    raise Exception("PGRST116: results contain 0 or multiple rows")
                return _Resp(matched[0])
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

    # get_salon_bookings reads from the bookings_with_payments view via .from_()
    def from_(self, name):
        return self.table(name)


# =====================================================================
# Test handle + fixture
# =====================================================================
VENDOR_ID = "vendor-1"


class Handle:
    def __init__(self, db, app):
        self.db = db
        self.app = app
        self.client = TestClient(app)

    # --- seeding helpers ---
    def seed_config(self, key="registration_fee_amount", value="2999"):
        self.db.table("system_config").rows.append(
            {"id": str(uuid.uuid4()), "config_key": key, "config_value": value}
        )

    def seed_salon(self, *, vendor_id=VENDOR_ID, **fields):
        sid = fields.pop("id", str(uuid.uuid4()))
        row = {
            "id": sid,
            "vendor_id": vendor_id,
            "business_name": fields.pop("business_name", "Glamour Studio"),
            "salon_type": "salon",
            "email": "salon@example.com",
            "phone": "+919999999999",
            "address": "1 Test Street",
            "city": "Testville",
            "state": "Test State",
            "pincode": "560001",
            "is_active": True,
            "is_verified": True,
            "registration_fee_paid": False,
            "average_rating": 4.5,
            "total_reviews": 2,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        row.update(fields)
        self.db.table("salons").rows.append(row)
        return row

    def seed_service(self, salon_id, **fields):
        row = {
            "id": fields.pop("id", str(uuid.uuid4())),
            "salon_id": salon_id,
            "name": fields.pop("name", "Haircut"),
            "description": None,
            "duration_minutes": 60,
            "price": 500.0,
            "discount_percentage": None,
            "discounted_price": None,
            "category_id": fields.pop("category_id", None),
            "subcategory_id": None,
            "gender_category": "both",
            "image_url": None,
            "is_active": True,
            "deleted_at": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        row.update(fields)
        self.db.table("services").rows.append(row)
        return row

    def seed_category(self, cid="cat-1", name="Hair", **fields):
        row = {
            "id": cid,
            "name": name,
            "description": None,
            "icon_url": None,
            "display_order": fields.pop("display_order", 1),
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        row.update(fields)
        self.db.table("service_categories").rows.append(row)
        return row

    def seed_subcategory(self, sid, name, parent_category_id="cat-1",
                         parent_subcategory_id=None, **fields):
        row = {
            "id": sid,
            "name": name,
            "parent_category_id": parent_category_id,
            "parent_subcategory_id": parent_subcategory_id,
            "icon_url": None,
            "display_order": fields.pop("display_order", 1),
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        row.update(fields)
        self.db.table("service_subcategories").rows.append(row)
        return row

    def seed_booking_view(self, salon_id, **fields):
        row = {
            "id": fields.pop("id", str(uuid.uuid4())),
            "booking_number": fields.pop("booking_number", "BK-001"),
            "customer_id": fields.pop("customer_id", "cust-1"),
            "salon_id": salon_id,
            "booking_date": fields.pop("booking_date", "2026-07-01"),
            "time_slots": ["09:00:00"],
            "services": fields.pop("services", [{"name": "Haircut"}]),
            "duration_minutes": 60,
            "status": fields.pop("status", "confirmed"),
            "service_price": 500.0,
            "convenience_fee": 0.0,
            "total_amount": 500.0,
            "deleted_at": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        row.update(fields)
        self.db.from_("bookings_with_payments").rows.append(row)
        return row

    def seed_booking(self, salon_id, **fields):
        """Seed a row in the real bookings table (for ownership + status update)."""
        row = {
            "id": fields.pop("id", str(uuid.uuid4())),
            "salon_id": salon_id,
            "status": fields.pop("status", "confirmed"),
            "total_amount": 500.0,
        }
        row.update(fields)
        self.db.table("bookings").rows.append(row)
        return row

    def login_vendor(self, user_id=VENDOR_ID, role="vendor"):
        td = TokenData(
            user_id=user_id, email="vendor@example.com", user_role=role,
            jti="jti-test", exp=datetime.utcnow() + timedelta(hours=1),
        )
        self.app.dependency_overrides[require_vendor] = lambda: td
        return td

    def clear_overrides(self):
        self.app.dependency_overrides.pop(require_vendor, None)


@pytest.fixture()
def vd(app):
    db = FakeSupabase()
    handle = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db
    handle.login_vendor()  # most endpoints require a vendor; tests can re-login

    yield handle

    handle.clear_overrides()
    app.dependency_overrides.pop(get_db_client, None)


# =====================================================================
# GET /vendors/salon
# =====================================================================
def test_get_salon_happy_attaches_fee(vd):
    vd.seed_config(value="2999")
    s = vd.seed_salon(business_name="My Salon")

    r = vd.client.get(f"{VENDORS}/salon")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == s["id"]
    assert body["registration_fee_amount"] == 2999.0


def test_get_salon_missing_404(vd):
    vd.seed_config()
    r = vd.client.get(f"{VENDORS}/salon")
    assert r.status_code == 404, r.text


def test_get_salon_missing_config_500(vd):
    # Salon exists but the registration_fee_amount config row is absent.
    vd.seed_salon()
    r = vd.client.get(f"{VENDORS}/salon")
    assert r.status_code == 500, r.text


def test_get_salon_requires_vendor(vd):
    vd.clear_overrides()
    r = vd.client.get(f"{VENDORS}/salon")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# PUT /vendors/salon
# =====================================================================
def test_update_salon_happy(vd):
    vd.seed_config()
    vd.seed_salon(business_name="Old Name")

    r = vd.client.put(f"{VENDORS}/salon", json={"business_name": "New Name"})
    assert r.status_code == 200, r.text
    assert r.json()["business_name"] == "New Name"
    assert vd.db.table("salons").rows[0]["business_name"] == "New Name"


def test_update_salon_missing_404(vd):
    vd.seed_config()
    r = vd.client.put(f"{VENDORS}/salon", json={"business_name": "New Name"})
    assert r.status_code == 404, r.text


# =====================================================================
# GET /vendors/service-categories  (P3c: shared tree builder)
# =====================================================================
def test_service_categories_tree(vd):
    vd.seed_category("cat-1", "Hair", display_order=1)
    vd.seed_category("cat-2", "Skin", display_order=2)
    vd.seed_subcategory("sub-1", "Mens Cut", parent_category_id="cat-1")
    vd.seed_subcategory("sub-1a", "Fade", parent_category_id="cat-1",
                        parent_subcategory_id="sub-1")  # level-3

    r = vd.client.get(f"{VENDORS}/service-categories")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    cats = {c["name"]: c for c in body["data"]}
    assert list(cats) == ["Hair", "Skin"]          # ordered by display_order
    hair_subs = cats["Hair"]["subcategories"]
    assert [s["name"] for s in hair_subs] == ["Mens Cut"]
    # level-3 nested under its parent subcategory
    assert [c["name"] for c in hair_subs[0]["subcategories"]] == ["Fade"]
    # level-2 nodes always carry a (possibly empty) subcategories list
    assert cats["Skin"]["subcategories"] == []


def test_service_categories_empty(vd):
    r = vd.client.get(f"{VENDORS}/service-categories")
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


# =====================================================================
# GET /vendors/services
# =====================================================================
def test_get_services_happy(vd):
    s = vd.seed_salon()
    vd.seed_service(s["id"], name="Cut")
    vd.seed_service(s["id"], name="Color")

    r = vd.client.get(f"{VENDORS}/services")
    assert r.status_code == 200, r.text
    names = {svc["name"] for svc in r.json()}
    assert names == {"Cut", "Color"}


def test_get_services_no_salon_404(vd):
    r = vd.client.get(f"{VENDORS}/services")
    assert r.status_code == 404, r.text


# =====================================================================
# POST /vendors/services
# =====================================================================
def test_create_service_happy(vd):
    s = vd.seed_salon()
    vd.seed_category("cat-1", "Hair")

    payload = {
        "name": "Premium Cut",
        "duration_minutes": 45,
        "price": 800,
        "category_id": "cat-1",
    }
    r = vd.client.post(f"{VENDORS}/services", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Premium Cut"
    assert body["salon_id"] == s["id"]          # auto-assigned
    assert body["category_id"] == "cat-1"


def test_create_service_computes_discount(vd):
    s = vd.seed_salon()
    vd.seed_category("cat-1", "Hair")

    payload = {
        "name": "Discounted Cut",
        "duration_minutes": 30,
        "price": 1000,
        "discount_percentage": 25,
        "category_id": "cat-1",
    }
    r = vd.client.post(f"{VENDORS}/services", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["discount_percentage"] == 25.0
    assert body["discounted_price"] == 750.0


def test_create_service_requires_category(vd):
    vd.seed_salon()
    payload = {"name": "No Category", "duration_minutes": 30, "price": 100}
    r = vd.client.post(f"{VENDORS}/services", json=payload)
    assert r.status_code == 400, r.text
    assert "category is required" in r.text.lower()


def test_create_service_no_salon_404(vd):
    vd.seed_category("cat-1", "Hair")
    payload = {"name": "Orphan Service", "duration_minutes": 30, "price": 100, "category_id": "cat-1"}
    r = vd.client.post(f"{VENDORS}/services", json=payload)
    assert r.status_code == 404, r.text


# =====================================================================
# PUT /vendors/services/{id}
# =====================================================================
def test_update_service_happy(vd):
    s = vd.seed_salon()
    svc = vd.seed_service(s["id"], name="Old", price=500.0)

    r = vd.client.put(f"{VENDORS}/services/{svc['id']}", json={"name": "Renamed"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"


def test_update_service_recomputes_discount_on_price_change(vd):
    s = vd.seed_salon()
    svc = vd.seed_service(s["id"], price=1000.0, discount_percentage=10.0)

    r = vd.client.put(f"{VENDORS}/services/{svc['id']}", json={"price": 200})
    assert r.status_code == 200, r.text
    body = r.json()
    # existing 10% discount re-applied to the new price
    assert body["discounted_price"] == 180.0


def test_update_service_not_owned_404(vd):
    vd.seed_salon()
    other = vd.seed_service("other-salon", name="Theirs")
    r = vd.client.put(f"{VENDORS}/services/{other['id']}", json={"name": "Hijack"})
    assert r.status_code == 404, r.text


# =====================================================================
# DELETE /vendors/services/{id}
# =====================================================================
def test_delete_service_happy(vd):
    s = vd.seed_salon()
    svc = vd.seed_service(s["id"])

    r = vd.client.delete(f"{VENDORS}/services/{svc['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    assert vd.db.table("services").rows == []


def test_delete_service_not_owned_404(vd):
    vd.seed_salon()
    other = vd.seed_service("other-salon")
    r = vd.client.delete(f"{VENDORS}/services/{other['id']}")
    assert r.status_code == 404, r.text


# =====================================================================
# GET /vendors/bookings
# =====================================================================
def test_get_bookings_enriched(vd):
    s = vd.seed_salon()
    vd.seed_booking_view(s["id"], services=[{"name": "Haircut"}, {"name": "Shave"}])

    r = vd.client.get(f"{VENDORS}/bookings")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    # BookingResponse drops the enriched service_names_str helper field, but
    # confirm the row came back intact.
    assert body[0]["salon_id"] == s["id"]


def test_get_bookings_status_filter(vd):
    s = vd.seed_salon()
    vd.seed_booking_view(s["id"], booking_number="BK-1", status="confirmed")
    vd.seed_booking_view(s["id"], booking_number="BK-2", status="completed")

    r = vd.client.get(f"{VENDORS}/bookings", params={"status_filter": "completed"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [b["booking_number"] for b in body] == ["BK-2"]


def test_get_bookings_no_salon_404(vd):
    r = vd.client.get(f"{VENDORS}/bookings")
    assert r.status_code == 404, r.text


# =====================================================================
# PUT /vendors/bookings/{id}/status
# =====================================================================
def test_update_booking_status_happy(vd):
    s = vd.seed_salon()
    bk = vd.seed_booking(s["id"], status="confirmed")

    r = vd.client.put(f"{VENDORS}/bookings/{bk['id']}/status",
                      json={"status": "no_show"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "no_show"
    assert vd.db.table("bookings").rows[0]["status"] == "no_show"


def test_update_booking_status_completed_sends_review_email(vd, monkeypatch):
    s = vd.seed_salon()
    bk = vd.seed_booking(s["id"], status="confirmed")

    calls = {}

    async def _fake_review(self, booking_id):
        calls["booking_id"] = booking_id
    monkeypatch.setattr(BookingService, "_send_review_request_email", _fake_review)

    r = vd.client.put(f"{VENDORS}/bookings/{bk['id']}/status",
                      json={"status": "completed"})
    assert r.status_code == 200, r.text
    assert calls.get("booking_id") == bk["id"]


def test_update_booking_status_invalid_400(vd):
    s = vd.seed_salon()
    bk = vd.seed_booking(s["id"])
    # 'cancelled' is intentionally NOT accepted (docstring fixed in P3b)
    r = vd.client.put(f"{VENDORS}/bookings/{bk['id']}/status",
                      json={"status": "cancelled"})
    assert r.status_code == 400, r.text


def test_update_booking_status_not_owned_404(vd):
    vd.seed_salon()
    other = vd.seed_booking("other-salon")
    r = vd.client.put(f"{VENDORS}/bookings/{other['id']}/status",
                      json={"status": "completed"})
    assert r.status_code == 404, r.text


# =====================================================================
# GET /vendors/analytics
# =====================================================================
def test_analytics_happy(vd):
    vd.seed_config()
    s = vd.seed_salon()
    vd.seed_service(s["id"], is_active=True)
    vd.seed_booking(s["id"], status="completed", total_amount=500.0)
    vd.seed_booking(s["id"], status="pending", total_amount=300.0)

    r = vd.client.get(f"{VENDORS}/analytics")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active_services"] == 1
    assert body["total_bookings"] == 2
    assert body["pending_bookings"] == 1
    assert body["total_revenue"] == 500.0
    assert body["average_rating"] == 4.5


# =====================================================================
# POST /vendors/process-payment  (P3a: fee sourced from system_config)
# =====================================================================
def test_process_payment_uses_config_fee(vd):
    vd.seed_config(value="2999")
    s = vd.seed_salon(business_name="Pays Up", registration_fee_paid=False)

    r = vd.client.post(f"{VENDORS}/process-payment")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["payment_amount"] == 2999.0          # not the old hardcoded 5000
    assert data["salon_name"] == "Pays Up"
    # salon activated + marked paid
    row = vd.db.table("salons").rows[0]
    assert row["registration_fee_paid"] is True
    assert row["is_active"] is True


# =====================================================================
# Promotions  (apply + active)
# =====================================================================
def test_apply_promotion_discounts_services(vd):
    s = vd.seed_salon()
    vd.seed_service(s["id"], price=1000.0)

    today = date.today().isoformat()
    payload = {
        "title": "Summer Sale",
        "discount_type": "percentage",
        "discount_value": 20,
        "start_date": today,
    }
    r = vd.client.post(f"{VENDORS}/promotions/apply", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Summer Sale"
    assert body["status"] == "active"
    assert body["services_updated"] == 1
    # the service now carries the promo discount
    svc = vd.db.table("services").rows[0]
    assert svc["discount_percentage"] == 20.0
    assert svc["discounted_price"] == 800.0


def test_get_active_promotion_none(vd):
    vd.seed_salon()
    r = vd.client.get(f"{VENDORS}/promotions/active")
    assert r.status_code == 200, r.text
    assert r.json() is None


def test_get_active_promotion_after_apply(vd):
    s = vd.seed_salon()
    vd.seed_service(s["id"], price=1000.0)
    today = date.today().isoformat()
    vd.client.post(f"{VENDORS}/promotions/apply", json={
        "title": "Sale", "discount_type": "flat_amount", "discount_value": 100,
        "start_date": today,
    })

    r = vd.client.get(f"{VENDORS}/promotions/active")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Sale"
    assert body["is_active"] is True


# =====================================================================
# POST /vendors/complete-registration  (error path without a real auth stack)
# =====================================================================
def test_complete_registration_invalid_token(vd):
    # No auth override needed (endpoint is token-based, not require_vendor).
    payload = {
        "token": "not-a-real-jwt",
        "full_name": "New Vendor",
        "password": "Secret123!",
        "confirm_password": "Secret123!",
        "age": 30,
        "gender": "male",
    }
    r = vd.client.post(f"{VENDORS}/complete-registration", json=payload)
    assert r.status_code in (400, 401, 422, 500), r.text
