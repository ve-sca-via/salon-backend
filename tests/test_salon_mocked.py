"""
Mocked route tests for the salon_service module:

    app/api/salons.py        (public salon endpoints)
    app/api/location.py      (the SalonService-backed /location/salons/nearby)
    app/api/admin/salons.py  (admin salon management)
    app/services/salon_service.py

These run WITHOUT a real Supabase stack. The Supabase DB client is replaced with
a small in-memory fake (the same builder stand-in used by the product/booking
tests, extended with the ops salon_service needs: neq / in_ / limit / rpc and
nested-join passthrough). They exercise the full HTTP path:

    HTTP -> FastAPI (auth deps overridden, rate limiter disabled) -> route ->
    SalonService -> FakeSupabase.

Scope: every endpoint the module exposes (happy path + key error cases) plus the
P1-P4 cleanup invariants for this module:
  * public listing/detail honours the three visibility gates
    (active + verified + paid) via the new SalonService.is_publicly_visible
    predicate, and excludes regular_buyer (product-only) salons;
  * search + public list share the _public_salons_query / _finalize_public_salons
    helpers (business_type flattening, city normalization, discount flags);
  * available-slots depends only on the salon's hours — existing bookings never
    remove a slot, because a salon takes multiple bookings for the same time.

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import require_admin, TokenData

API = settings.API_PREFIX
SALONS = f"{API}/salons"
LOCATION = f"{API}/location"
ADMIN_SALONS = f"{API}/admin/salons"


# =====================================================================
# In-memory fake Supabase client (covers the ops salon_service uses)
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

    def ilike(self, col, pattern):
        self._filters.append(("ilike", col, pattern))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    @property
    def not_(self):
        # Mirrors supabase-py's `.not_.in_(col, vals)` negated filter builder.
        query = self

        class _Not:
            def in_(self, col, vals):
                query._filters.append(("not_in", col, list(vals)))
                return query

        return _Not()

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
            if op == "in" and rv not in v:
                return False
            if op == "not_in" and rv in v:
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
    def __init__(self, data):
        self._data = data

    def execute(self):
        return _Resp(self._data)


class FakeSupabase:
    def __init__(self):
        self._tables = {}
        self.rpc_results = {}   # name -> list[dict]

    def table(self, name):
        return self._tables.setdefault(name, _Table())

    def rpc(self, name, params=None):
        return _Rpc(self.rpc_results.get(name, []))


# =====================================================================
# Test handle + fixture
# =====================================================================
class Handle:
    def __init__(self, db, app):
        self.db = db
        self.app = app
        self.client = TestClient(app)

    def seed_salon(self, *, public=True, **fields):
        """Seed a salon row. `public=True` sets the three visibility gates."""
        sid = fields.pop("id", str(uuid.uuid4()))
        row = {
            "id": sid,
            "business_name": fields.pop("business_name", "Glamour Studio"),
            "email": "salon@example.com",
            "phone": "+919999999999",
            "address": "1 Test Street",
            "city": "Testville",
            "state": "Test State",
            "pincode": "560001",
            "salon_type": "salon",
            "is_active": public,
            "is_verified": public,
            "registration_fee_paid": public,
            "opening_time": "09:00:00",
            "closing_time": "18:00:00",
            "average_rating": 0.0,
            "total_reviews": 0,
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
            "price": 500.0,
            "duration_minutes": 60,
            "is_active": True,
            "category_id": fields.pop("category_id", "cat-1"),
        }
        row.update(fields)
        self.db.table("services").rows.append(row)
        return row

    def seed_coupon(self, *, scope, salon_id=None, code="SAVE10", **fields):
        """Seed a coupon row (defaults to an active, no-window percentage coupon)."""
        row = {
            "id": fields.pop("id", str(uuid.uuid4())),
            "code": code,
            "title": fields.pop("title", "Save now"),
            "scope": scope,
            "salon_id": salon_id,
            "applies_to": "service_price",
            "discount_type": "percentage",
            "discount_value": 10.0,
            "max_discount_cap": None,
            "min_order_amount": None,
            "first_time_scope": None,
            "valid_from": None,
            "valid_until": None,
            "usage_limit_total": None,
            "used_count": 0,
            "is_active": True,
        }
        row.update(fields)
        self.db.table("coupons").rows.append(row)
        return row

    def seed_booking(self, salon_id, date, time_slot, duration_minutes=60, status="confirmed"):
        self.db.table("bookings").rows.append({
            "id": str(uuid.uuid4()),
            "salon_id": salon_id,
            "booking_date": date,
            "time_slots": [time_slot],
            "duration_minutes": duration_minutes,
            "status": status,
        })

    def login_admin(self, user_id="admin-1"):
        td = TokenData(
            user_id=user_id, email="admin@example.com", user_role="admin",
            jti="jti-test", exp=datetime.utcnow() + timedelta(hours=1),
        )
        self.app.dependency_overrides[require_admin] = lambda: td
        return td

    def clear_overrides(self):
        self.app.dependency_overrides.pop(require_admin, None)


@pytest.fixture()
def sa(app):
    db = FakeSupabase()
    handle = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db

    yield handle

    handle.clear_overrides()
    app.dependency_overrides.pop(get_db_client, None)


# =====================================================================
# GET /salons/public
# =====================================================================
def test_public_list_happy(sa):
    sa.seed_salon(business_name="A")
    sa.seed_salon(business_name="B")

    r = sa.client.get(f"{SALONS}/public")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2
    assert len(body["salons"]) == 2
    # discount flag attached by _finalize_public_salons even with no services
    assert all("has_discounted_services" in s for s in body["salons"])


def test_public_list_hides_non_public(sa):
    sa.seed_salon(business_name="Live")
    sa.seed_salon(business_name="Inactive", public=False)
    sa.seed_salon(business_name="Unverified", is_verified=False)
    sa.seed_salon(business_name="Unpaid", registration_fee_paid=False)

    r = sa.client.get(f"{SALONS}/public")
    assert r.status_code == 200, r.text
    names = [s["business_name"] for s in r.json()["salons"]]
    assert names == ["Live"]


def test_public_list_excludes_regular_buyer(sa):
    sa.seed_salon(business_name="Real Salon")
    sa.seed_salon(business_name="Product Buyer", salon_type="regular_buyer")

    r = sa.client.get(f"{SALONS}/public")
    assert r.status_code == 200, r.text
    names = [s["business_name"] for s in r.json()["salons"]]
    assert names == ["Real Salon"]


def test_public_list_city_filter(sa):
    sa.seed_salon(business_name="Mumbai One", city="Mumbai")
    sa.seed_salon(business_name="Delhi One", city="Delhi")

    # lower-case input is normalized + matched case-insensitively
    r = sa.client.get(f"{SALONS}/public", params={"city": "mumbai"})
    assert r.status_code == 200, r.text
    names = [s["business_name"] for s in r.json()["salons"]]
    assert names == ["Mumbai One"]


def test_public_list_business_type_flattened(sa):
    sa.seed_salon(business_name="Spa", vendor_join_requests={"business_type": "spa"})

    r = sa.client.get(f"{SALONS}/public")
    assert r.status_code == 200, r.text
    salon = r.json()["salons"][0]
    assert salon["business_type"] == "spa"
    # the raw join key must be popped, not leaked
    assert "vendor_join_requests" not in salon


def test_public_list_discount_flag_true_when_service_discounted(sa):
    s = sa.seed_salon(business_name="On Sale")
    sa.seed_service(s["id"], discounted_price=300.0)

    r = sa.client.get(f"{SALONS}/public")
    assert r.status_code == 200, r.text
    assert r.json()["salons"][0]["has_discounted_services"] is True


def test_public_list_max_discount_percentage(sa):
    s = sa.seed_salon(business_name="Big Sale")
    sa.seed_service(s["id"], name="Small", discount_percentage=10.0)
    sa.seed_service(s["id"], name="Big", discount_percentage=25.0)

    r = sa.client.get(f"{SALONS}/public")
    assert r.status_code == 200, r.text
    assert r.json()["salons"][0]["max_discount_percentage"] == 25


def test_public_list_max_discount_from_discounted_price(sa):
    # No explicit %, only an absolute discounted_price -> % is derived.
    s = sa.seed_salon(business_name="Derived")
    sa.seed_service(s["id"], price=400.0, discounted_price=300.0)  # 25% off

    r = sa.client.get(f"{SALONS}/public")
    assert r.status_code == 200, r.text
    assert r.json()["salons"][0]["max_discount_percentage"] == 25


def test_public_list_attaches_vendor_coupons(sa):
    s = sa.seed_salon(business_name="Couponed")
    sa.seed_coupon(scope="vendor", salon_id=s["id"], code="SALON20", discount_value=20.0)
    # A platform coupon must NOT appear on the card (vendor-only there).
    sa.seed_coupon(scope="platform", code="PLAT5", discount_value=5.0)

    r = sa.client.get(f"{SALONS}/public")
    assert r.status_code == 200, r.text
    coupons = r.json()["salons"][0]["coupons"]
    codes = [c["code"] for c in coupons]
    assert codes == ["SALON20"]
    assert coupons[0]["summary"] == "20% OFF"


def test_public_list_hides_expired_and_inactive_coupons(sa):
    s = sa.seed_salon(business_name="Stale")
    sa.seed_coupon(scope="vendor", salon_id=s["id"], code="LIVE")
    sa.seed_coupon(scope="vendor", salon_id=s["id"], code="OFF", is_active=False)
    sa.seed_coupon(
        scope="vendor", salon_id=s["id"], code="EXPIRED",
        valid_until="2000-01-01T00:00:00+00:00",
    )
    sa.seed_coupon(
        scope="vendor", salon_id=s["id"], code="MAXED",
        usage_limit_total=5, used_count=5,
    )

    r = sa.client.get(f"{SALONS}/public")
    assert r.status_code == 200, r.text
    codes = [c["code"] for c in r.json()["salons"][0]["coupons"]]
    assert codes == ["LIVE"]


def test_salon_detail_attaches_vendor_and_platform_coupons(sa):
    s = sa.seed_salon(business_name="Detail Offers")
    sa.seed_coupon(scope="vendor", salon_id=s["id"], code="MYSALON")
    sa.seed_coupon(scope="vendor", salon_id="other-salon", code="NOTMINE")
    sa.seed_coupon(scope="platform", code="PLATFORM10", discount_value=10.0)

    r = sa.client.get(f"{SALONS}/{s['id']}")
    assert r.status_code == 200, r.text
    salon = r.json()["salon"]
    assert [c["code"] for c in salon["coupons"]] == ["MYSALON"]
    assert [c["code"] for c in salon["platform_coupons"]] == ["PLATFORM10"]


# =====================================================================
# GET /salons/popular-cities
# =====================================================================
def test_popular_cities(sa):
    sa.db.rpc_results["get_popular_cities"] = [
        {"city": "Mumbai", "salon_count": 5},
        {"city": "Delhi", "salon_count": 3},
    ]
    r = sa.client.get(f"{SALONS}/popular-cities")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["cities"][0]["city"] == "Mumbai"


# =====================================================================
# GET /salons/{salon_id}
# =====================================================================
def test_get_salon_happy(sa):
    s = sa.seed_salon(business_name="Detail Salon")

    r = sa.client.get(f"{SALONS}/{s['id']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["salon"]["id"] == s["id"]
    assert body["services"] is None


def test_get_salon_business_type_flattened(sa):
    # business_type lives on the join request; the detail endpoint must join +
    # flatten it (same as the public list) so it matches the listing cards.
    s = sa.seed_salon(business_name="Barber", vendor_join_requests={"business_type": "barber_shop"})

    r = sa.client.get(f"{SALONS}/{s['id']}")
    assert r.status_code == 200, r.text
    salon = r.json()["salon"]
    assert salon["business_type"] == "barber_shop"
    # the raw join key must be popped, not leaked
    assert "vendor_join_requests" not in salon


def test_get_salon_include_services(sa):
    s = sa.seed_salon(business_name="With Services")
    # get_salon embeds services(*) via the join column; seed the nested key.
    s["services"] = [{"id": "svc-1", "name": "Cut"}]

    r = sa.client.get(f"{SALONS}/{s['id']}", params={"include_services": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["services"] == [{"id": "svc-1", "name": "Cut"}]
    # services must be stripped out of the salon object itself
    assert "services" not in body["salon"]


def test_get_salon_missing_404(sa):
    r = sa.client.get(f"{SALONS}/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


def test_get_salon_not_public_404(sa):
    s = sa.seed_salon(business_name="Hidden", public=False)
    r = sa.client.get(f"{SALONS}/{s['id']}")
    assert r.status_code == 404, r.text


def test_get_salon_regular_buyer_404(sa):
    s = sa.seed_salon(business_name="Buyer", salon_type="regular_buyer")
    r = sa.client.get(f"{SALONS}/{s['id']}")
    assert r.status_code == 404, r.text


# =====================================================================
# GET /salons/{salon_id}/services
# =====================================================================
def test_salon_services_happy_with_taxonomy(sa):
    s = sa.seed_salon(business_name="Service Salon")
    sa.seed_service(
        s["id"], name="Haircut",
        service_categories={"id": "cat-1", "name": "Hair", "icon_url": None},
        service_subcategories={"id": "sub-1", "name": "Mens Cut",
                               "icon_url": None, "parent_category_id": "cat-1",
                               "parent_subcategory_id": None},
    )

    r = sa.client.get(f"{SALONS}/{s['id']}/services")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1
    svc = body["services"][0]
    assert svc["taxonomy"]["category"]["name"] == "Hair"
    assert svc["taxonomy"]["subcategory"]["name"] == "Mens Cut"
    assert svc["taxonomy"]["sub_subcategory"] is None


def test_salon_services_only_active(sa):
    s = sa.seed_salon(business_name="Service Salon")
    sa.seed_service(s["id"], name="Active", is_active=True)
    sa.seed_service(s["id"], name="Retired", is_active=False)

    r = sa.client.get(f"{SALONS}/{s['id']}/services")
    assert r.status_code == 200, r.text
    names = [s["name"] for s in r.json()["services"]]
    assert names == ["Active"]


def test_salon_services_missing_salon_404(sa):
    r = sa.client.get(f"{SALONS}/{uuid.uuid4()}/services")
    assert r.status_code == 404, r.text


# =====================================================================
# GET /salons/{salon_id}/available-slots
# =====================================================================
# A pure future date (never today) so slot generation isn't affected by the
# current time — only the past-time filter cares about "today".
FUTURE_DATE = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")


def test_available_slots_happy(sa):
    s = sa.seed_salon(business_name="Slots", opening_time="09:00:00",
                      closing_time="12:00:00")

    r = sa.client.get(f"{SALONS}/{s['id']}/available-slots",
                      params={"date": FUTURE_DATE})
    assert r.status_code == 200, r.text
    body = r.json()
    # 09-12 with default 60-min service on a 30-min grid: a slot is offered when
    # start+60min <= 12:00 -> 09:00, 09:30, 10:00, 10:30, 11:00.
    assert body["available_slots"] == [
        "09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM", "11:00 AM"
    ]


def test_available_slots_keeps_booked_hour(sa):
    """A salon serves several customers at once: a booked hour stays offered."""
    s = sa.seed_salon(business_name="Slots", opening_time="09:00:00",
                      closing_time="12:00:00")
    sa.seed_booking(s["id"], FUTURE_DATE, "10:00:00", duration_minutes=60)

    r = sa.client.get(f"{SALONS}/{s['id']}/available-slots",
                      params={"date": FUTURE_DATE})
    assert r.status_code == 200, r.text
    slots = r.json()["available_slots"]
    assert "10:00 AM" in slots
    assert "09:00 AM" in slots and "11:00 AM" in slots


def test_available_slots_unaffected_by_repeat_bookings(sa):
    """Several bookings on the same hour still leave that hour bookable."""
    s = sa.seed_salon(business_name="Slots", opening_time="09:00:00",
                      closing_time="12:00:00")
    for _ in range(3):
        sa.seed_booking(s["id"], FUTURE_DATE, "10:00:00", duration_minutes=60)

    r = sa.client.get(f"{SALONS}/{s['id']}/available-slots",
                      params={"date": FUTURE_DATE})
    assert r.status_code == 200, r.text
    assert r.json()["available_slots"] == [
        "09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM", "11:00 AM"
    ]


def test_available_slots_past_date_empty(sa):
    """Past dates must never yield bookable slots."""
    s = sa.seed_salon(business_name="Slots", opening_time="09:00:00",
                      closing_time="18:00:00")
    past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    r = sa.client.get(f"{SALONS}/{s['id']}/available-slots",
                      params={"date": past})
    assert r.status_code == 200, r.text
    assert r.json()["available_slots"] == []


def test_available_slots_closed_day_empty(sa):
    """A day not in working_days yields no slots."""
    # Salon open only on the weekday *after* our future date, so FUTURE_DATE is closed.
    open_day = (datetime.now() + timedelta(days=4)).strftime("%A")
    s = sa.seed_salon(business_name="Slots", opening_time="09:00:00",
                      closing_time="18:00:00", working_days=[open_day])
    r = sa.client.get(f"{SALONS}/{s['id']}/available-slots",
                      params={"date": FUTURE_DATE})
    assert r.status_code == 200, r.text
    assert r.json()["available_slots"] == []


def test_available_slots_not_public_404(sa):
    s = sa.seed_salon(business_name="Hidden", public=False)
    r = sa.client.get(f"{SALONS}/{s['id']}/available-slots",
                      params={"date": FUTURE_DATE})
    assert r.status_code == 404, r.text


# =====================================================================
# GET /salons/search/query
# =====================================================================
def test_search_by_name(sa):
    sa.seed_salon(business_name="Glamour Studio")
    sa.seed_salon(business_name="Barber Bros")

    r = sa.client.get(f"{SALONS}/search/query", params={"q": "glamour"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1
    assert body["salons"][0]["business_name"] == "Glamour Studio"
    assert body["query"] == "glamour"


def test_search_excludes_non_public_and_regular_buyer(sa):
    sa.seed_salon(business_name="Glam Live")
    sa.seed_salon(business_name="Glam Hidden", public=False)
    sa.seed_salon(business_name="Glam Buyer", salon_type="regular_buyer")

    r = sa.client.get(f"{SALONS}/search/query", params={"q": "glam"})
    assert r.status_code == 200, r.text
    names = [s["business_name"] for s in r.json()["salons"]]
    assert names == ["Glam Live"]


def test_search_city_filter(sa):
    sa.seed_salon(business_name="Spa One", city="Pune")
    sa.seed_salon(business_name="Spa Two", city="Jaipur")

    r = sa.client.get(f"{SALONS}/search/query", params={"city": "pune"})
    assert r.status_code == 200, r.text
    names = [s["business_name"] for s in r.json()["salons"]]
    assert names == ["Spa One"]


# =====================================================================
# GET /location/salons/nearby
# =====================================================================
def test_nearby_happy(sa):
    s1 = sa.seed_salon(business_name="Near A")
    s2 = sa.seed_salon(business_name="Near B")
    sa.db.rpc_results["get_nearby_salons"] = [
        {"id": s1["id"], "business_name": "Near A", "distance_km": 1.2,
         "is_active": True, "is_verified": True},
        {"id": s2["id"], "business_name": "Near B", "distance_km": 3.4,
         "is_active": True, "is_verified": True},
    ]

    r = sa.client.get(f"{LOCATION}/salons/nearby",
                      params={"lat": 19.0, "lon": 72.8})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2
    assert body["query"]["latitude"] == 19.0


def test_nearby_excludes_regular_buyer(sa):
    s1 = sa.seed_salon(business_name="Near Salon")
    s2 = sa.seed_salon(business_name="Near Buyer", salon_type="regular_buyer")
    sa.db.rpc_results["get_nearby_salons"] = [
        {"id": s1["id"], "business_name": "Near Salon", "distance_km": 1.0,
         "is_active": True, "is_verified": True},
        {"id": s2["id"], "business_name": "Near Buyer", "distance_km": 2.0,
         "is_active": True, "is_verified": True},
    ]

    r = sa.client.get(f"{LOCATION}/salons/nearby",
                      params={"lat": 19.0, "lon": 72.8})
    assert r.status_code == 200, r.text
    names = [s["business_name"] for s in r.json()["salons"]]
    assert names == ["Near Salon"]


# =====================================================================
# GET /admin/salons/  (admin list)
# =====================================================================
def test_admin_list_requires_admin(sa):
    r = sa.client.get(f"{ADMIN_SALONS}/")
    assert r.status_code in (401, 403), r.text


def test_admin_list_happy_includes_non_public(sa):
    sa.seed_salon(business_name="Active")
    sa.seed_salon(business_name="Inactive", public=False)
    sa.login_admin()

    r = sa.client.get(f"{ADMIN_SALONS}/")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["count"] == 2     # admin sees inactive too


def test_admin_list_enriches_vendor_profile(sa):
    sa.seed_salon(business_name="Owned", vendor_id="vendor-1")
    sa.db.table("profiles").rows.append({"id": "vendor-1", "full_name": "Owner Jane"})
    sa.login_admin()

    r = sa.client.get(f"{ADMIN_SALONS}/")
    assert r.status_code == 200, r.text
    salon = r.json()["data"][0]
    assert salon["profiles"]["full_name"] == "Owner Jane"


def test_admin_list_filters(sa):
    sa.seed_salon(business_name="Verified", is_verified=True)
    sa.seed_salon(business_name="Pending", is_verified=False)
    sa.login_admin()

    r = sa.client.get(f"{ADMIN_SALONS}/", params={"is_verified": False})
    assert r.status_code == 200, r.text
    names = [s["business_name"] for s in r.json()["data"]]
    assert names == ["Pending"]


# =====================================================================
# PUT /admin/salons/{salon_id}  (admin update)
# =====================================================================
def test_admin_update_requires_admin(sa):
    s = sa.seed_salon()
    r = sa.client.put(f"{ADMIN_SALONS}/{s['id']}", json={"business_name": "X"})
    assert r.status_code in (401, 403), r.text


def test_admin_update_happy(sa):
    s = sa.seed_salon(business_name="Old Name")
    sa.login_admin()

    r = sa.client.put(f"{ADMIN_SALONS}/{s['id']}",
                      json={"business_name": "New Name"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["business_name"] == "New Name"
    assert sa.db.table("salons").rows[0]["business_name"] == "New Name"


def test_admin_update_normalizes_city(sa):
    s = sa.seed_salon(city="Testville")
    sa.login_admin()

    r = sa.client.put(f"{ADMIN_SALONS}/{s['id']}", json={"city": "mumbai"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["city"] == "Mumbai"   # normalized to Title Case


# =====================================================================
# PUT /admin/salons/{salon_id}/status  (toggle)
# =====================================================================
def test_admin_toggle_status(sa):
    s = sa.seed_salon(is_active=True)
    sa.login_admin()

    r = sa.client.put(f"{ADMIN_SALONS}/{s['id']}/status",
                      json={"is_active": False})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_active"] is False
    assert sa.db.table("salons").rows[0]["is_active"] is False


# =====================================================================
# DELETE /admin/salons/{salon_id}
# =====================================================================
def test_admin_soft_delete(sa):
    s = sa.seed_salon(is_active=True)
    sa.login_admin()

    r = sa.client.delete(f"{ADMIN_SALONS}/{s['id']}")
    assert r.status_code == 200, r.text
    # soft delete => deactivate + reason
    row = sa.db.table("salons").rows[0]
    assert row["is_active"] is False
    assert row["deactivation_reason"] == "Deleted by admin"


def test_admin_hard_delete_removes_row(sa):
    s = sa.seed_salon()
    sa.login_admin()

    r = sa.client.delete(f"{ADMIN_SALONS}/{s['id']}", params={"hard_delete": True})
    assert r.status_code == 200, r.text
    assert "permanently deleted" in r.json()["message"].lower()
    assert sa.db.table("salons").rows == []


def test_admin_delete_requires_admin(sa):
    s = sa.seed_salon()
    r = sa.client.delete(f"{ADMIN_SALONS}/{s['id']}")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# POST /admin/salons/{salon_id}/send-payment-reminder
# =====================================================================
def test_send_payment_reminder_happy(sa, monkeypatch):
    s = sa.seed_salon(business_name="Owes Money", email="owner@example.com",
                      registration_fee_paid=False)
    sa.db.table("system_config").rows.append(
        {"config_key": "registration_fee_amount", "config_value": "999"}
    )
    sa.login_admin()

    async def _fake_send(**kwargs):
        return True
    monkeypatch.setattr(
        "app.api.admin.salons.email_service.send_payment_reminder_email", _fake_send
    )

    r = sa.client.post(f"{ADMIN_SALONS}/{s['id']}/send-payment-reminder")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["owner_email"] == "owner@example.com"


def test_send_payment_reminder_already_paid_400(sa):
    s = sa.seed_salon(business_name="Paid Up", registration_fee_paid=True)
    sa.login_admin()

    r = sa.client.post(f"{ADMIN_SALONS}/{s['id']}/send-payment-reminder")
    assert r.status_code == 400, r.text


def test_send_payment_reminder_missing_salon_errors(sa):
    # The route fetches the salon with PostgREST `.single()`, which raises on
    # 0 rows; the generic handler turns that into a 500. (The `if not data`
    # 404 branch below it is effectively unreachable — documented here as the
    # current behavior, not an endorsement of it.)
    sa.login_admin()
    r = sa.client.post(f"{ADMIN_SALONS}/{uuid.uuid4()}/send-payment-reminder")
    assert r.status_code == 500, r.text


def test_send_payment_reminder_requires_admin(sa):
    s = sa.seed_salon(registration_fee_paid=False)
    r = sa.client.post(f"{ADMIN_SALONS}/{s['id']}/send-payment-reminder")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# GET /salons/{salon_id}/related  (Related Salons section)
# =====================================================================
def test_related_same_city_excludes_self(sa):
    base = sa.seed_salon(business_name="Base", city="Mumbai")
    sa.seed_salon(business_name="Neighbour A", city="Mumbai")
    sa.seed_salon(business_name="Neighbour B", city="Mumbai")
    sa.seed_salon(business_name="Faraway", city="Delhi")

    r = sa.client.get(f"{SALONS}/{base['id']}/related")
    assert r.status_code == 200, r.text
    names = [s["business_name"] for s in r.json()["salons"]]
    assert base["business_name"] not in names           # never recommend itself
    assert "Neighbour A" in names and "Neighbour B" in names


def test_related_ranked_by_rating(sa):
    base = sa.seed_salon(business_name="Base", city="Mumbai")
    sa.seed_salon(business_name="Low", city="Mumbai", average_rating=3.0)
    sa.seed_salon(business_name="High", city="Mumbai", average_rating=4.8)

    r = sa.client.get(f"{SALONS}/{base['id']}/related")
    assert r.status_code == 200, r.text
    names = [s["business_name"] for s in r.json()["salons"]]
    assert names[0] == "High"                            # highest-rated first


def test_related_hides_non_public_and_regular_buyer(sa):
    base = sa.seed_salon(business_name="Base", city="Mumbai")
    sa.seed_salon(business_name="Hidden", city="Mumbai", public=False)
    sa.seed_salon(business_name="Buyer", city="Mumbai", salon_type="regular_buyer")
    sa.seed_salon(business_name="Visible", city="Mumbai")

    r = sa.client.get(f"{SALONS}/{base['id']}/related")
    assert r.status_code == 200, r.text
    names = [s["business_name"] for s in r.json()["salons"]]
    assert "Hidden" not in names and "Buyer" not in names
    assert "Visible" in names


def test_related_backfills_other_cities(sa):
    # Only one same-city neighbour, but limit asks for more -> backfill by state,
    # then anywhere.
    base = sa.seed_salon(business_name="Base", city="Mumbai", state="MH")
    sa.seed_salon(business_name="Same City", city="Mumbai", state="MH")
    sa.seed_salon(business_name="Same State", city="Pune", state="MH")
    sa.seed_salon(business_name="Other State", city="Delhi", state="DL")

    r = sa.client.get(f"{SALONS}/{base['id']}/related", params={"limit": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 3                            # filled up to the limit
    names = [s["business_name"] for s in body["salons"]]
    assert names[0] == "Same City"                       # city match comes first
    assert base["business_name"] not in names


def test_related_respects_limit(sa):
    base = sa.seed_salon(business_name="Base", city="Mumbai")
    for i in range(8):
        sa.seed_salon(business_name=f"N{i}", city="Mumbai")

    r = sa.client.get(f"{SALONS}/{base['id']}/related", params={"limit": 5})
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 5


def test_related_missing_salon_is_404(sa):
    r = sa.client.get(f"{SALONS}/{uuid.uuid4()}/related")
    assert r.status_code == 404, r.text
