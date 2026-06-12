"""
Mocked unit/route tests for the booking_service module.

These run WITHOUT a real Supabase stack. The Supabase DB client is replaced with
a small in-memory fake (a faithful-enough stand-in for the supabase-py builder:
select/insert/update/delete + eq/gte/lte/in_/order/range/single + count="exact"),
the email_service singleton and ActivityLogService are monkeypatched so nothing
touches the network.

Coverage (the surface that ships in prod for this module):
  * GET  /admin/bookings/                      -> get_admin_bookings  (route + pagination)
  * PUT  /customers/bookings/{id}/cancel       -> cancel_booking      (route + guards)
  * BookingService.create_booking              -> pricing / fee / idempotency / errors
    (the create HTTP endpoint was removed; cart checkout calls this method in-process,
     so the method is exercised directly here.)

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import asyncio
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import get_current_user, TokenData
from app.core.exceptions import AppException, ValidationError
from app.services.booking_service import BookingService
from app.services import booking_service as booking_service_module
from app.services.activity_log_service import ActivityLogService
from app.schemas import BookingCreate
from app.schemas.request.booking import ServiceItem
from datetime import datetime, timedelta as _td

API = settings.API_PREFIX


# =====================================================================
# In-memory fake Supabase client (covers the ops booking_service uses)
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

    def gte(self, col, val):
        self._filters.append(("gte", col, val))
        return self

    def lte(self, col, val):
        self._filters.append(("lte", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
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
            if op == "gte" and not (rv is not None and rv >= v):
                return False
            if op == "lte" and not (rv is not None and rv <= v):
                return False
            if op == "in" and rv not in v:
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
                if len(matched) != 1:
                    raise Exception("PGRST116: results contain 0 or multiple rows")
                return _Resp(matched[0])
            if self._maybe:
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

    # booking_service reads the admin list from a view via .from_()
    def from_(self, name):
        return self.table(name)


# =====================================================================
# Test handle + fixture
# =====================================================================
class Handle:
    def __init__(self, db, app):
        self.db = db
        self.app = app
        self.client = TestClient(app)

    # --- seeding helpers ---
    def seed_profile(self, **fields):
        prof = {
            "id": str(uuid.uuid4()),
            "email": f"user+{uuid.uuid4().hex[:8]}@example.com",
            "full_name": "Test User",
            "phone": "+919876543210",
            "user_role": "customer",
        }
        prof.update(fields)
        self.db.table("profiles").rows.append(prof)
        return prof

    def seed_salon(self, vendor_id=None, **fields):
        salon = {
            "id": str(uuid.uuid4()),
            "business_name": "Test Salon",
            "vendor_id": vendor_id,
            "city": "Testville",
            "address": "1 Test St",
        }
        salon.update(fields)
        self.db.table("salons").rows.append(salon)
        return salon

    def seed_service(self, salon_id, price=500.0, duration_minutes=30,
                     discounted_price=None, **fields):
        svc = {
            "id": str(uuid.uuid4()),
            "name": "Test Service",
            "salon_id": salon_id,
            "price": price,
            "duration_minutes": duration_minutes,
            "discounted_price": discounted_price,
        }
        svc.update(fields)
        self.db.table("services").rows.append(svc)
        return svc

    def seed_fee_config(self, pct="6"):
        self.db.table("system_config").rows.append({
            "id": str(uuid.uuid4()),
            "config_key": "convenience_fee_percentage",
            "config_value": pct,
            "is_active": True,
        })

    def seed_booking(self, **fields):
        booking = {
            "id": str(uuid.uuid4()),
            "booking_number": f"BK{uuid.uuid4().hex[:8]}",
            "customer_id": str(uuid.uuid4()),
            "salon_id": str(uuid.uuid4()),
            "status": "pending",
            "booking_date": (date.today() + timedelta(days=5)).isoformat(),
            "time_slots": ["10:00"],
            "services": [{"name": "Cut", "unit_price": 100, "quantity": 1}],
            "total_amount": 100.0,
        }
        booking.update(fields)
        self.db.table("bookings").rows.append(booking)
        return booking

    def login_as(self, user_id, email="user@example.com", role="customer"):
        td = TokenData(
            user_id=user_id, email=email, user_role=role,
            jti="jti-test", exp=datetime.utcnow() + _td(hours=1),
        )
        self.app.dependency_overrides[get_current_user] = lambda: td
        return td

    def service(self):
        return BookingService(db_client=self.db)


@pytest.fixture()
def bk(app, monkeypatch):
    db = FakeSupabase()
    handle = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db

    # Stub every email + activity-log call the booking paths make (no network).
    async def _noop(*args, **kwargs):
        return True

    for name in (
        "send_booking_confirmation_to_customer",
        "send_new_booking_notification_to_vendor",
        "send_booking_cancellation_email",
        "send_booking_cancellation_notification_to_vendor",
    ):
        monkeypatch.setattr(booking_service_module.email_service, name, _noop, raising=False)
    monkeypatch.setattr(ActivityLogService, "log", staticmethod(_noop))

    yield handle

    app.dependency_overrides.pop(get_db_client, None)
    app.dependency_overrides.pop(get_current_user, None)


def _make_booking_create(salon_id, service_id, quantity=1, **over):
    payload = dict(
        salon_id=salon_id,
        booking_date=(date.today() + timedelta(days=5)).isoformat(),
        booking_time="10:00",
        time_slots=["10:00"],
        services=[ServiceItem(service_id=service_id, quantity=quantity)],
    )
    payload.update(over)
    return BookingCreate(**payload)


# =====================================================================
# BookingService.create_booking  (the live create path, called in-process)
# =====================================================================
def test_create_booking_happy_pricing(bk):
    customer = bk.seed_profile(role="customer")
    vendor = bk.seed_profile(user_role="vendor")
    salon = bk.seed_salon(vendor_id=vendor["id"])
    service = bk.seed_service(salon["id"], price=500.0, duration_minutes=45)
    bk.seed_fee_config("6")

    booking = asyncio.run(bk.service().create_booking(
        _make_booking_create(salon["id"], service["id"], quantity=2),
        current_user_id=customer["id"],
    ))

    assert booking["booking_number"].startswith("BK")
    assert booking["customer_id"] == customer["id"]
    assert booking["salon_id"] == salon["id"]
    assert booking["status"] == "pending"          # no payment -> pending
    assert booking["service_price"] == 1000.0       # 500 * 2
    assert booking["duration_minutes"] == 90        # 45 * 2
    assert booking["convenience_fee"] == 60.0       # 6% of 1000
    assert booking["total_amount"] == 1060.0
    assert len(booking["services"]) == 1
    # service_payment record created (pending)
    pays = bk.db.table("payments").rows
    assert any(p["payment_type"] == "service_payment" for p in pays)


def test_create_booking_uses_discounted_price_for_service_total(bk):
    customer = bk.seed_profile()
    salon = bk.seed_salon()
    service = bk.seed_service(salon["id"], price=1000.0, discounted_price=800.0)
    bk.seed_fee_config("6")

    booking = asyncio.run(bk.service().create_booking(
        _make_booking_create(salon["id"], service["id"], quantity=1),
        current_user_id=customer["id"],
    ))
    # Amount due at salon uses discounted price; fee is charged on original total.
    assert booking["service_price"] == 800.0
    assert booking["convenience_fee"] == 60.0        # 6% of original 1000
    assert booking["total_amount"] == 860.0


def test_create_booking_paid_is_confirmed(bk):
    customer = bk.seed_profile()
    salon = bk.seed_salon()
    service = bk.seed_service(salon["id"], price=200.0)
    bk.seed_fee_config("6")

    booking = asyncio.run(bk.service().create_booking(
        _make_booking_create(salon["id"], service["id"], payment_status="paid"),
        current_user_id=customer["id"],
    ))
    assert booking["status"] == "confirmed"


def test_create_booking_empty_services_rejected(bk):
    customer = bk.seed_profile()
    salon = bk.seed_salon()
    bk.seed_fee_config("6")
    payload = _make_booking_create(salon["id"], str(uuid.uuid4()))
    payload.services = []  # bypass: schema allows empty list, service must reject

    with pytest.raises(ValidationError):
        asyncio.run(bk.service().create_booking(payload, current_user_id=customer["id"]))


def test_create_booking_unknown_service_rejected(bk):
    customer = bk.seed_profile()
    salon = bk.seed_salon()
    bk.seed_fee_config("6")

    with pytest.raises(AppException):
        asyncio.run(bk.service().create_booking(
            _make_booking_create(salon["id"], str(uuid.uuid4())),
            current_user_id=customer["id"],
        ))


def test_create_booking_missing_fee_config_is_clean_error(bk):
    """No convenience_fee_percentage config -> explicit 500, not a raw crash."""
    customer = bk.seed_profile()
    salon = bk.seed_salon()
    service = bk.seed_service(salon["id"])
    # deliberately NOT seeding fee config

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(bk.service().create_booking(
            _make_booking_create(salon["id"], service["id"]),
            current_user_id=customer["id"],
        ))
    assert exc.value.status_code == 500
    assert "configuration" in exc.value.detail.lower()


def test_create_booking_idempotent_on_payment_id(bk):
    """Reusing a razorpay_payment_id returns the existing booking, no duplicate."""
    customer = bk.seed_profile()
    salon = bk.seed_salon()
    service = bk.seed_service(salon["id"])
    bk.seed_fee_config("6")
    existing = bk.seed_booking(customer_id=customer["id"], salon_id=salon["id"],
                               razorpay_payment_id="pay_DUP123")

    result = asyncio.run(bk.service().create_booking(
        _make_booking_create(salon["id"], service["id"], razorpay_payment_id="pay_DUP123"),
        current_user_id=customer["id"],
    ))
    assert result["id"] == existing["id"]
    # No new booking row was inserted (still just the seeded one).
    assert len(bk.db.table("bookings").rows) == 1


# =====================================================================
# PUT /customers/bookings/{id}/cancel  (route + guards)
# =====================================================================
def test_cancel_booking_http_happy(bk):
    customer = bk.seed_profile()
    salon = bk.seed_salon()
    booking = bk.seed_booking(customer_id=customer["id"], salon_id=salon["id"],
                              status="confirmed")
    bk.login_as(customer["id"], email=customer["email"], role="customer")

    r = bk.client.put(f"{API}/customers/bookings/{booking['id']}/cancel")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["booking"]["status"] == "cancelled"


def test_cancel_booking_not_found(bk):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(bk.service().cancel_booking(
            booking_id=str(uuid.uuid4()), reason=None,
            current_user_id=str(uuid.uuid4()), current_user_role="customer",
        ))
    assert exc.value.status_code == 404


def test_cancel_booking_already_cancelled_rejected(bk):
    customer = bk.seed_profile()
    salon = bk.seed_salon()
    booking = bk.seed_booking(customer_id=customer["id"], salon_id=salon["id"],
                              status="cancelled")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(bk.service().cancel_booking(
            booking_id=booking["id"], reason=None,
            current_user_id=customer["id"], current_user_role="customer",
        ))
    assert exc.value.status_code == 400


def test_cancel_booking_past_date_rejected(bk):
    customer = bk.seed_profile()
    salon = bk.seed_salon()
    booking = bk.seed_booking(customer_id=customer["id"], salon_id=salon["id"],
                              status="confirmed", booking_date="2000-01-01")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(bk.service().cancel_booking(
            booking_id=booking["id"], reason=None,
            current_user_id=customer["id"], current_user_role="customer",
        ))
    assert exc.value.status_code == 400


def test_cancel_booking_other_user_forbidden(bk):
    owner = bk.seed_profile()
    salon = bk.seed_salon()
    booking = bk.seed_booking(customer_id=owner["id"], salon_id=salon["id"],
                              status="confirmed")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(bk.service().cancel_booking(
            booking_id=booking["id"], reason=None,
            current_user_id=str(uuid.uuid4()), current_user_role="customer",
        ))
    assert exc.value.status_code == 403


def test_cancel_booking_admin_can_cancel_others(bk):
    owner = bk.seed_profile()
    salon = bk.seed_salon()
    booking = bk.seed_booking(customer_id=owner["id"], salon_id=salon["id"],
                              status="confirmed")
    result = asyncio.run(bk.service().cancel_booking(
        booking_id=booking["id"], reason="admin override",
        current_user_id=str(uuid.uuid4()), current_user_role="admin",
    ))
    assert result["success"] is True
    assert result["booking"]["status"] == "cancelled"


def test_cancel_requires_auth(bk):
    # No login_as override -> real get_current_user runs -> no bearer -> 401/403
    r = bk.client.put(f"{API}/customers/bookings/{uuid.uuid4()}/cancel")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# GET /admin/bookings/  (route + pagination — the K fix)
# =====================================================================
def _seed_admin_rows(bk, n):
    view = bk.db.from_("bookings_with_payments")
    for i in range(n):
        view.rows.append({
            "id": str(uuid.uuid4()),
            "booking_number": f"BK{i:04d}",
            "customer_id": str(uuid.uuid4()),
            "salon_id": str(uuid.uuid4()),
            "status": "pending",
            "booking_date": f"2026-06-{(i % 28) + 1:02d}",
            "created_at": f"2026-06-01T00:{i:02d}:00",
            "customer_name": f"Cust {i}",
            "customer_email": f"c{i}@example.com",
            "customer_phone": "+919999999999",
        })


def test_admin_bookings_pagination_first_page(bk):
    _seed_admin_rows(bk, 25)
    bk.login_as(str(uuid.uuid4()), role="admin")

    r = bk.client.get(f"{API}/admin/bookings/", params={"page": 1, "limit": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["data"]) == 10
    pg = body["pagination"]
    assert pg["total"] == 25          # exact total, not page length
    assert pg["total_pages"] == 3     # ceil(25/10)
    assert pg["has_next"] is True
    assert pg["has_prev"] is False
    # enrichment: profiles object built from customer_* view fields
    assert body["data"][0]["profiles"]["full_name"]


def test_admin_bookings_pagination_last_page(bk):
    _seed_admin_rows(bk, 25)
    bk.login_as(str(uuid.uuid4()), role="admin")

    r = bk.client.get(f"{API}/admin/bookings/", params={"page": 3, "limit": 10})
    assert r.status_code == 200, r.text
    pg = r.json()["pagination"]
    assert len(r.json()["data"]) == 5
    assert pg["total"] == 25
    assert pg["total_pages"] == 3
    assert pg["has_next"] is False
    assert pg["has_prev"] is True


def test_admin_bookings_empty(bk):
    bk.login_as(str(uuid.uuid4()), role="admin")
    r = bk.client.get(f"{API}/admin/bookings/", params={"page": 1, "limit": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data"] == []
    assert body["pagination"]["total"] == 0
    assert body["pagination"]["total_pages"] == 0
    assert body["pagination"]["has_next"] is False


def test_admin_bookings_status_filter(bk):
    view = bk.db.from_("bookings_with_payments")
    view.rows.append({"id": str(uuid.uuid4()), "status": "completed",
                      "booking_date": "2026-06-01", "created_at": "2026-06-01T00:00:00"})
    view.rows.append({"id": str(uuid.uuid4()), "status": "pending",
                      "booking_date": "2026-06-02", "created_at": "2026-06-02T00:00:00"})
    bk.login_as(str(uuid.uuid4()), role="admin")

    r = bk.client.get(f"{API}/admin/bookings/", params={"status": "completed"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pagination"]["total"] == 1
    assert all(b["status"] == "completed" for b in body["data"])


def test_admin_bookings_requires_admin(bk):
    bk.login_as(str(uuid.uuid4()), role="customer")
    r = bk.client.get(f"{API}/admin/bookings/")
    assert r.status_code == 403, r.text
