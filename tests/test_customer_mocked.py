"""
Mocked route tests for the customer_service module (app/api/customers.py +
the public review/feedback routes in app/api/salons.py + app/services/customer_service.py).

These run WITHOUT a real Supabase stack. The DB client is an in-memory fake that
supports embedded selects (services(...), salons(...), profiles(...)), is_/in_,
single/maybe_single, count, limit, order. email + activity-log singletons and the
feedback-token verifier are stubbed. They exercise the full HTTP path:

    HTTP -> FastAPI (auth dep overridden, limiter off) -> route ->
    CustomerService (or BookingService for cancel) -> FakeSupabase.

Scope: cart (incl. the add_to_cart 404 fix), bookings list, the BookingService-
backed cancel route (feature lock), favorites, reviews, and the public
salon-reviews/feedback flow.

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import re
import uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import get_current_user, TokenData
from app.services import booking_service as booking_service_module
from app.services.activity_log_service import ActivityLogService
import app.services.customer_service as customer_module

API = settings.API_PREFIX
CUST = f"{API}/customers"
SALONS = f"{API}/salons"


# =====================================================================
# In-memory fake Supabase client
# =====================================================================
_EMBED_RE = re.compile(r"(\w+)(?:![\w]+)?\(([^()]*)\)")
_FK = {"services": "service_id", "salons": "salon_id", "profiles": "customer_id"}


class _Resp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, table):
        self._t = table
        self._db = table.db
        self._cols = "*"
        self._filters = []        # (op, col, val)
        self._op = ("select", "*")
        self._count = None
        self._single = False
        self._maybe = False
        self._order = []
        self._range = None
        self._limit = None

    def select(self, cols="*", count=None):
        self._op = ("select", cols); self._cols = cols; self._count = count; return self

    def insert(self, payload):
        self._op = ("insert", payload); return self

    def update(self, payload):
        self._op = ("update", payload); return self

    def delete(self):
        self._op = ("delete", None); return self

    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def neq(self, c, v): self._filters.append(("neq", c, v)); return self
    def gte(self, c, v): self._filters.append(("gte", c, v)); return self
    def lte(self, c, v): self._filters.append(("lte", c, v)); return self
    def in_(self, c, vals): self._filters.append(("in", c, list(vals))); return self
    def is_(self, c, v): self._filters.append(("isnull", c, None)); return self
    def order(self, c, desc=False): self._order.append((c, desc)); return self
    def range(self, s, e): self._range = (s, e); return self
    def limit(self, n): self._limit = n; return self
    def single(self): self._single = True; return self
    def maybe_single(self): self._maybe = True; return self

    def _match(self, row):
        for op, c, v in self._filters:
            rv = row.get(c)
            if op == "eq" and rv != v: return False
            if op == "neq" and rv == v: return False
            if op == "gte" and not (rv is not None and rv >= v): return False
            if op == "lte" and not (rv is not None and rv <= v): return False
            if op == "in" and rv not in v: return False
            if op == "isnull" and rv is not None: return False
        return True

    def _embed(self, row):
        out = dict(row)
        for m in _EMBED_RE.finditer(self._cols):
            tname, cols = m.group(1), m.group(2)
            cols = [c.strip() for c in cols.split(",") if c.strip()]
            ref = row.get(_FK.get(tname, "id"))
            rel = next((r for r in self._db.table(tname).rows if r.get("id") == ref), None)
            if rel is None:
                out[tname] = None
            elif cols and cols != ["*"]:
                out[tname] = {c: rel.get(c) for c in cols}
            else:
                out[tname] = dict(rel)
        return out

    def execute(self):
        op, payload = self._op
        rows = self._t.rows
        if op == "select":
            matched = [r for r in rows if self._match(r)]
            total = len(matched)
            for c, desc in reversed(self._order):
                matched.sort(key=lambda r: (r.get(c) is None, r.get(c)), reverse=desc)
            if self._range is not None:
                s, e = self._range; matched = matched[s:e]
            if self._limit is not None:
                matched = matched[:self._limit]
            data = [self._embed(r) if "(" in self._cols else dict(r) for r in matched]
            if self._single:
                if len(data) != 1:
                    raise Exception("PGRST116: 0 or multiple rows")
                return _Resp(data[0])
            if self._maybe:
                return _Resp(data[0] if data else None)
            return _Resp(data, count=total if self._count == "exact" else None)
        if op == "insert":
            new = payload if isinstance(payload, list) else [payload]
            added = []
            for nr in new:
                r = dict(nr); r.setdefault("id", str(uuid.uuid4()))
                r.setdefault("created_at", datetime.utcnow().isoformat())
                rows.append(r); added.append(dict(r))
            return _Resp(added)
        if op == "update":
            upd = []
            for r in rows:
                if self._match(r):
                    r.update(payload); upd.append(dict(r))
            return _Resp(upd)
        if op == "delete":
            removed = [dict(r) for r in rows if self._match(r)]
            rows[:] = [r for r in rows if not self._match(r)]
            return _Resp(removed)
        return _Resp(None)


class _Table:
    def __init__(self, db): self.db = db; self.rows = []
    def select(self, cols="*", count=None): return _Query(self).select(cols, count=count)
    def insert(self, p): return _Query(self).insert(p)
    def update(self, p): return _Query(self).update(p)
    def delete(self): return _Query(self).delete()


class FakeSupabase:
    def __init__(self): self._t = {}
    def table(self, name): return self._t.setdefault(name, _Table(self))


# =====================================================================
# Handle + fixture
# =====================================================================
class Handle:
    def __init__(self, db, app):
        self.db = db; self.app = app; self.client = TestClient(app)

    def add(self, table, **row):
        row.setdefault("id", str(uuid.uuid4()))
        row.setdefault("created_at", datetime.utcnow().isoformat())
        row.setdefault("updated_at", datetime.utcnow().isoformat())
        self.db.table(table).rows.append(row)
        return row

    def seed_service(self, salon_id, price=500.0, discounted_price=None, is_active=True, **o):
        return self.add("services", salon_id=salon_id, name="Cut", price=price,
                        discounted_price=discounted_price, duration_minutes=30,
                        is_active=is_active, image_url=None, **o)

    def seed_salon(self, is_active=True, accepting_bookings=True, **o):
        return self.add("salons", business_name="Salon X", city="Townsville",
                        state="ST", address="1 St", phone="999", logo_url=None,
                        is_active=is_active, is_verified=True, registration_fee_paid=True,
                        accepting_bookings=accepting_bookings, **o)

    def seed_cart_item(self, user_id, service_id, salon_id, quantity=1):
        return self.add("cart_items", user_id=user_id, service_id=service_id,
                        salon_id=salon_id, quantity=quantity, metadata={})

    def login(self, user_id="cust-1", role="customer"):
        td = TokenData(user_id=user_id, email="c@x.com", user_role=role,
                       jti="j", exp=datetime.utcnow() + timedelta(hours=1))
        self.app.dependency_overrides[get_current_user] = lambda: td
        return td

    def logout(self):
        self.app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def cs(app, monkeypatch):
    db = FakeSupabase()
    h = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db

    async def _noop(*a, **k): return True
    for name in ("send_booking_cancellation_email", "send_booking_cancellation_notification_to_vendor"):
        monkeypatch.setattr(booking_service_module.email_service, name, _noop, raising=False)
    monkeypatch.setattr(ActivityLogService, "log", staticmethod(_noop))

    yield h
    h.logout()
    app.dependency_overrides.pop(get_db_client, None)


# =====================================================================
# CART
# =====================================================================
def test_get_cart_empty(cs):
    cs.login()
    r = cs.client.get(f"{CUST}/cart")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["items"] == [] and b["total_amount"] == 0 and b["item_count"] == 0


def test_get_cart_uses_discounted_price(cs):
    salon = cs.seed_salon()
    svc = cs.seed_service(salon["id"], price=500.0, discounted_price=400.0)
    cs.seed_cart_item("cust-1", svc["id"], salon["id"], quantity=2)
    cs.login()

    r = cs.client.get(f"{CUST}/cart")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["item_count"] == 2
    assert b["total_amount"] == 800.0  # discounted 400 * 2
    assert b["items"][0]["unit_price"] == 400.0


def test_add_to_cart_new(cs):
    salon = cs.seed_salon()
    svc = cs.seed_service(salon["id"])
    cs.login()

    r = cs.client.post(f"{CUST}/cart", json={"service_id": svc["id"], "quantity": 1})
    assert r.status_code == 200, r.text
    assert len(cs.db.table("cart_items").rows) == 1


def test_add_to_cart_increments_existing(cs):
    salon = cs.seed_salon()
    svc = cs.seed_service(salon["id"])
    cs.seed_cart_item("cust-1", svc["id"], salon["id"], quantity=1)
    cs.login()

    r = cs.client.post(f"{CUST}/cart", json={"service_id": svc["id"], "quantity": 2})
    assert r.status_code == 200, r.text
    rows = cs.db.table("cart_items").rows
    assert len(rows) == 1 and rows[0]["quantity"] == 3


def test_add_to_cart_missing_service_404(cs):
    # was a 500 before the .single()->.maybe_single() fix
    cs.login()
    r = cs.client.post(f"{CUST}/cart", json={"service_id": str(uuid.uuid4()), "quantity": 1})
    assert r.status_code == 404, r.text


def test_add_to_cart_inactive_service_400(cs):
    salon = cs.seed_salon()
    svc = cs.seed_service(salon["id"], is_active=False)
    cs.login()
    r = cs.client.post(f"{CUST}/cart", json={"service_id": svc["id"]})
    assert r.status_code == 400, r.text


def test_add_to_cart_salon_not_accepting_400(cs):
    salon = cs.seed_salon(accepting_bookings=False)
    svc = cs.seed_service(salon["id"])
    cs.login()
    r = cs.client.post(f"{CUST}/cart", json={"service_id": svc["id"]})
    assert r.status_code == 400, r.text


def test_add_to_cart_different_salon_400(cs):
    salon_a = cs.seed_salon()
    salon_b = cs.seed_salon()
    svc_a = cs.seed_service(salon_a["id"])
    svc_b = cs.seed_service(salon_b["id"])
    cs.seed_cart_item("cust-1", svc_a["id"], salon_a["id"])
    cs.login()

    r = cs.client.post(f"{CUST}/cart", json={"service_id": svc_b["id"]})
    assert r.status_code == 400, r.text
    assert "different salon" in r.text.lower()


def test_update_cart_item_happy(cs):
    salon = cs.seed_salon()
    svc = cs.seed_service(salon["id"])
    item = cs.seed_cart_item("cust-1", svc["id"], salon["id"], quantity=1)
    cs.login()

    r = cs.client.put(f"{CUST}/cart/{item['id']}", json={"quantity": 4})
    assert r.status_code == 200, r.text
    assert cs.db.table("cart_items").rows[0]["quantity"] == 4


def test_update_cart_item_zero_400(cs):
    salon = cs.seed_salon()
    svc = cs.seed_service(salon["id"])
    item = cs.seed_cart_item("cust-1", svc["id"], salon["id"])
    cs.login()
    r = cs.client.put(f"{CUST}/cart/{item['id']}", json={"quantity": 0})
    assert r.status_code == 422, r.text   # schema gt=0 rejects before the service


def test_update_cart_item_not_found_404(cs):
    cs.login()
    r = cs.client.put(f"{CUST}/cart/{uuid.uuid4()}", json={"quantity": 2})
    assert r.status_code == 404, r.text


def test_remove_from_cart_happy(cs):
    salon = cs.seed_salon()
    svc = cs.seed_service(salon["id"])
    item = cs.seed_cart_item("cust-1", svc["id"], salon["id"])
    cs.login()
    r = cs.client.delete(f"{CUST}/cart/{item['id']}")
    assert r.status_code == 200, r.text
    assert cs.db.table("cart_items").rows == []


def test_remove_from_cart_not_found_404(cs):
    cs.login()
    r = cs.client.delete(f"{CUST}/cart/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


def test_clear_cart(cs):
    salon = cs.seed_salon()
    svc = cs.seed_service(salon["id"])
    cs.seed_cart_item("cust-1", svc["id"], salon["id"])
    cs.seed_cart_item("cust-1", svc["id"], salon["id"])
    cs.login()
    r = cs.client.delete(f"{CUST}/cart/clear/all")
    assert r.status_code == 200, r.text
    assert cs.db.table("cart_items").rows == []


def test_checkout_empty_cart_400(cs):
    cs.login()
    r = cs.client.post(f"{CUST}/cart/checkout",
                       json={"booking_date": "2026-07-01", "time_slots": ["10:00"]})
    assert r.status_code == 400, r.text
    assert "empty" in r.text.lower()


def test_cart_requires_auth(cs):
    r = cs.client.get(f"{CUST}/cart")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# BOOKINGS (list + BookingService-backed cancel)
# =====================================================================
def test_get_my_bookings(cs):
    salon = cs.seed_salon()
    cs.add("bookings", customer_id="cust-1", salon_id=salon["id"], status="confirmed",
           booking_date=(date.today() + timedelta(days=3)).isoformat(),
           booking_time="10:00", services=[{"name": "Cut", "unit_price": 100, "quantity": 1}],
           total_amount=100.0)
    cs.login()

    r = cs.client.get(f"{CUST}/bookings/my-bookings")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["count"] == 1
    assert b["data"][0]["salon_name"] == "Salon X"   # flattened from embed
    assert b["data"][0]["services"][0]["name"] == "Cut"


def test_cancel_booking_feature_works(cs):
    # Locks the feature: route delegates to BookingService.cancel_booking.
    customer = cs.add("profiles", id="cust-1", full_name="Cust", email="c@x.com", phone="999")
    salon = cs.seed_salon()
    booking = cs.add("bookings", customer_id="cust-1", salon_id=salon["id"], status="confirmed",
                     booking_number="BK1", booking_date=(date.today() + timedelta(days=5)).isoformat(),
                     time_slots=["10:00"], services=[{"name": "Cut", "unit_price": 100, "quantity": 1}],
                     total_amount=100.0)
    cs.login("cust-1")

    r = cs.client.put(f"{CUST}/bookings/{booking['id']}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["booking"]["status"] == "cancelled"
    assert cs.db.table("bookings").rows[0]["status"] == "cancelled"


# =====================================================================
# FAVORITES
# =====================================================================
def test_favorites_empty(cs):
    cs.login()
    r = cs.client.get(f"{CUST}/favorites")
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 0


def test_favorites_with_items(cs):
    salon = cs.seed_salon()
    cs.add("favorites", user_id="cust-1", salon_id=salon["id"])
    cs.login()
    r = cs.client.get(f"{CUST}/favorites")
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 1


def test_add_favorite_new_then_idempotent(cs):
    salon = cs.seed_salon()
    cs.login()
    r1 = cs.client.post(f"{CUST}/favorites", json={"salon_id": salon["id"]})
    assert r1.status_code == 200, r1.text
    r2 = cs.client.post(f"{CUST}/favorites", json={"salon_id": salon["id"]})
    assert r2.status_code == 200, r2.text
    assert len(cs.db.table("favorites").rows) == 1  # no duplicate


def test_remove_favorite(cs):
    salon = cs.seed_salon()
    cs.add("favorites", user_id="cust-1", salon_id=salon["id"])
    cs.login()
    r = cs.client.delete(f"{CUST}/favorites/{salon['id']}")
    assert r.status_code == 200, r.text
    assert cs.db.table("favorites").rows == []


# =====================================================================
# PRODUCT FAVORITES
# =====================================================================
def _seed_product(cs, is_active=True, **o):
    return cs.add("products", name="Hair Serum", price=500.0, is_active=is_active, **o)


def test_product_favorites_empty(cs):
    cs.login()
    r = cs.client.get(f"{CUST}/favorites/products")
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 0


def test_product_favorites_with_items(cs):
    product = _seed_product(cs)
    cs.add("product_favorites", user_id="cust-1", product_id=product["id"])
    cs.login()
    r = cs.client.get(f"{CUST}/favorites/products")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1
    assert body["favorites"][0]["id"] == product["id"]


def test_product_favorites_excludes_inactive(cs):
    product = _seed_product(cs, is_active=False)
    cs.add("product_favorites", user_id="cust-1", product_id=product["id"])
    cs.login()
    r = cs.client.get(f"{CUST}/favorites/products")
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 0  # inactive products are filtered out


def test_add_favorite_product_new_then_idempotent(cs):
    product = _seed_product(cs)
    cs.login()
    r1 = cs.client.post(f"{CUST}/favorites/products", json={"product_id": product["id"]})
    assert r1.status_code == 200, r1.text
    r2 = cs.client.post(f"{CUST}/favorites/products", json={"product_id": product["id"]})
    assert r2.status_code == 200, r2.text
    assert len(cs.db.table("product_favorites").rows) == 1  # no duplicate


def test_add_favorite_product_unknown_404(cs):
    cs.login()
    r = cs.client.post(f"{CUST}/favorites/products", json={"product_id": str(uuid.uuid4())})
    assert r.status_code == 404, r.text
    assert cs.db.table("product_favorites").rows == []


def test_remove_favorite_product(cs):
    product = _seed_product(cs)
    cs.add("product_favorites", user_id="cust-1", product_id=product["id"])
    cs.login()
    r = cs.client.delete(f"{CUST}/favorites/products/{product['id']}")
    assert r.status_code == 200, r.text
    assert cs.db.table("product_favorites").rows == []


def test_product_favorites_requires_auth(cs):
    # No login -> get_current_user dependency rejects the request.
    r = cs.client.get(f"{CUST}/favorites/products")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# REVIEWS
# =====================================================================
def _completed_booking(cs, salon_id, service_id, customer_id="cust-1"):
    return cs.add("bookings", customer_id=customer_id, salon_id=salon_id, status="completed",
                  booking_number="BK1", booking_date="2026-01-01",
                  services=[{"service_id": service_id, "name": "Cut", "quantity": 1}])


def test_get_my_reviews(cs):
    salon = cs.seed_salon()
    cs.add("reviews", customer_id="cust-1", salon_id=salon["id"], rating=5,
           review_text="Great", is_verified=True)
    cs.login()
    r = cs.client.get(f"{CUST}/reviews/my-reviews")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["count"] == 1
    assert b["reviews"][0]["salon_name"] == "Salon X"


def test_create_review_happy(cs):
    salon = cs.seed_salon()
    svc = cs.seed_service(salon["id"])
    booking = _completed_booking(cs, salon["id"], svc["id"])
    cs.login()

    r = cs.client.post(f"{CUST}/reviews", json={
        "salon_id": salon["id"], "rating": 5, "comment": "Loved every minute of it",
        "booking_id": booking["id"]})
    assert r.status_code == 200, r.text
    assert len(cs.db.table("reviews").rows) == 1


def test_create_review_missing_booking_id_400(cs):
    salon = cs.seed_salon()
    cs.login()
    r = cs.client.post(f"{CUST}/reviews", json={
        "salon_id": salon["id"], "rating": 5, "comment": "A perfectly valid comment"})
    assert r.status_code == 400, r.text


def test_create_review_not_completed_400(cs):
    salon = cs.seed_salon()
    svc = cs.seed_service(salon["id"])
    booking = cs.add("bookings", customer_id="cust-1", salon_id=salon["id"], status="confirmed",
                     services=[{"service_id": svc["id"], "quantity": 1}])
    cs.login()
    r = cs.client.post(f"{CUST}/reviews", json={
        "salon_id": salon["id"], "rating": 5, "comment": "A perfectly valid comment",
        "booking_id": booking["id"]})
    assert r.status_code == 400, r.text


def test_create_review_duplicate_409(cs):
    salon = cs.seed_salon()
    svc = cs.seed_service(salon["id"])
    booking = _completed_booking(cs, salon["id"], svc["id"])
    cs.add("reviews", booking_id=booking["id"], customer_id="cust-1", salon_id=salon["id"],
           rating=4, review_text="old")
    cs.login()
    r = cs.client.post(f"{CUST}/reviews", json={
        "salon_id": salon["id"], "rating": 5, "comment": "Another valid comment here",
        "booking_id": booking["id"]})
    assert r.status_code == 409, r.text


def test_update_review_happy(cs):
    salon = cs.seed_salon()
    review = cs.add("reviews", customer_id="cust-1", salon_id=salon["id"], rating=3,
                    review_text="ok")
    cs.login()
    r = cs.client.put(f"{CUST}/reviews/{review['id']}",
                      json={"rating": 5, "comment": "Much better service now"})
    assert r.status_code == 200, r.text
    assert cs.db.table("reviews").rows[0]["rating"] == 5


def test_update_review_not_found_404(cs):
    cs.login()
    r = cs.client.put(f"{CUST}/reviews/{uuid.uuid4()}", json={"rating": 5})
    assert r.status_code == 404, r.text


# =====================================================================
# PUBLIC SALON REVIEWS + FEEDBACK (salons.py, public)
# =====================================================================
def test_public_salon_reviews(cs):
    salon = cs.seed_salon()
    svc = cs.seed_service(salon["id"])
    cs.add("profiles", id="cust-1", full_name="Jane")
    cs.add("reviews", customer_id="cust-1", salon_id=salon["id"], service_id=svc["id"],
           rating=5, review_text="Nice", is_hidden=False, is_verified=True)

    r = cs.client.get(f"{SALONS}/{salon['id']}/reviews")  # public, no auth
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["count"] == 1
    assert b["reviews"][0]["customer_name"] == "Jane"


def test_feedback_context_and_submit(cs, monkeypatch):
    salon = cs.seed_salon()
    svc = cs.seed_service(salon["id"])
    cs.add("profiles", id="cust-1", full_name="Jane", email="j@x.com")
    booking = _completed_booking(cs, salon["id"], svc["id"])

    def _verify(token):
        return {"salon_id": salon["id"], "booking_id": booking["id"], "customer_id": "cust-1"}
    monkeypatch.setattr(customer_module, "verify_review_feedback_token", _verify)

    token = "feedback-token-abcdef-123456"  # >= 20 chars (schema requirement)

    # context
    rc = cs.client.get(f"{SALONS}/{salon['id']}/feedback", params={"token": token})
    assert rc.status_code == 200, rc.text
    assert rc.json()["booking"]["id"] == booking["id"]

    # submit
    rs = cs.client.post(f"{SALONS}/{salon['id']}/feedback",
                        json={"token": token, "rating": 5, "comment": "Great service overall"})
    assert rs.status_code == 200, rs.text
    assert len(cs.db.table("reviews").rows) == 1
