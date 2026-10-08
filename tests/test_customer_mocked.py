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
        # Round-trip log. Phase 1 of the payment audit is about how many reads
        # /cart/checkout makes after the customer has been charged, so the fake
        # records each one (see the checkout tests at the end of this file).
        self._db.queries.append((self._t.name, op))
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
                # created_at/updated_at both DEFAULT now() in the real schema.
                r.setdefault("created_at", datetime.utcnow().isoformat())
                r.setdefault("updated_at", datetime.utcnow().isoformat())
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
    def __init__(self, db, name=""):
        self.db = db
        self.name = name
        self.rows = []

    def select(self, cols="*", count=None): return _Query(self).select(cols, count=count)
    def insert(self, p): return _Query(self).insert(p)
    def update(self, p): return _Query(self).update(p)
    def delete(self): return _Query(self).delete()


class FakeSupabase:
    def __init__(self):
        self._t = {}
        # (table_name, op) for every .execute() the app made, in order.
        self.queries = []

    def table(self, name):
        if name not in self._t:
            self._t[name] = _Table(self, name)
        return self._t[name]

    def count_queries(self, table, op="select"):
        """How many `op` round trips the app made against `table`."""
        return sum(1 for t, o in self.queries if t == table and o == op)


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
# POST /customers/cart/checkout — the post-charge request
#
# This is the request the customer waits on *after* Razorpay has taken their
# money, and it had no happy-path test. Phase 1 of the payment audit
# restructured it (one PaymentService, salon/fee/idempotency handed to
# create_booking, profiles read behind the response), so these cover both the
# outcome and the round-trip count.
# =====================================================================
PINNED_PRICING = {
    "subtotal_service_price": 1000.0,
    "discount_amount": 0.0,
    "service_total_due": 1000.0,
    "convenience_fee_base": 1000.0,
    "convenience_fee_discount": 0.0,
    "convenience_fee_due": 60.0,
    "total_amount": 1060.0,
    "coupon_id": None,
    "coupon_code": None,
    "coupon_gross_discount": 0.0,
}


class _FakeRazorpayOrders:
    """Stands in for razorpay.Client().order — returns our pinned notes."""

    def __init__(self, notes, fail=False):
        self._notes = notes
        self._fail = fail
        self.fetched = []

    def fetch(self, order_id):
        self.fetched.append(order_id)
        if self._fail:
            raise Exception("razorpay unreachable")
        return {"id": order_id, "status": "paid", "notes": self._notes}


class _FakeRazorpayClient:
    def __init__(self, orders):
        self.order = orders


class _FakeRazorpay:
    def __init__(self, orders, signature_valid=True):
        self.client = _FakeRazorpayClient(orders)
        self._signature_valid = signature_valid

    def verify_payment_signature(self, order_id, payment_id, signature):
        if not self._signature_valid:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Invalid payment signature")
        return True


BOOKING_DATE = (date.today() + timedelta(days=3)).isoformat()


def _seed_payment_intent(cs, salon, service, **over):
    """
    The `payment_intents` row written when the Razorpay order was created.

    Since Phase 2 this, not the Razorpay order's notes, is where checkout reads
    the pinned breakdown and the cart snapshot from (payment audit H-2).
    """
    row = dict(
        razorpay_order_id="order_CART1",
        intent_type="cart_checkout",
        customer_id="cust-1",
        salon_id=salon["id"],
        amount=60.0,
        currency="INR",
        pricing=dict(PINNED_PRICING),
        cart_snapshot=[{"service_id": service["id"], "quantity": 1, "unit_price": 1000.0}],
        coupon_code=None,
        booking_date=BOOKING_DATE,
        time_slots=["10:00 AM"],
        status="created",
        razorpay_payment_id=None,
        booking_id=None,
        captured_at=None,
        completed_at=None,
    )
    row.update(over)
    return cs.add("payment_intents", **row)


def _seed_checkout_state(cs, fee="6", price=1000.0, accepting_bookings=True,
                         with_intent=True):
    """
    Everything /cart/checkout reads: salon, service, cart, profiles, fee config,
    and the payment intent holding the pinned snapshot.

    `with_intent=False` leaves the intent out, which is the pre-Phase-2 shape:
    checkout then falls back to the Razorpay order notes.
    """
    salon = cs.seed_salon(accepting_bookings=accepting_bookings, vendor_id="vendor-1",
                          opening_time="09:00", closing_time="21:00",
                          working_days=None, business_hours=None)
    service = cs.seed_service(salon["id"], price=price)
    cs.seed_cart_item("cust-1", service["id"], salon["id"], quantity=1)
    cs.add("profiles", id="cust-1", email="c@x.com", full_name="Cust One",
           phone="+919876543210", user_role="customer")
    cs.add("profiles", id="vendor-1", email="v@x.com", full_name="Vendor One",
           user_role="vendor")
    cs.add("system_config", config_key="convenience_fee_percentage",
           config_value=fee, is_active=True)
    if with_intent:
        _seed_payment_intent(cs, salon, service)
    return salon, service


def _install_fake_razorpay(cs, monkeypatch, service, signature_valid=True, fetch_fails=False):
    """Stub PaymentService's Razorpay so no credential read and no network happens."""
    import json
    from app.services.payment_service import PaymentService

    orders = _FakeRazorpayOrders(
        notes={
            "pricing": json.dumps(PINNED_PRICING),
            "cart_snapshot": json.dumps(
                [{"service_id": service["id"], "quantity": 1, "unit_price": 1000.0}]
            ),
            "cart_item_count": 1,
        },
        fail=fetch_fails,
    )

    async def _fake_init(self):
        self.razorpay = _FakeRazorpay(orders, signature_valid=signature_valid)
        self._razorpay_key_id = "test_key_id"
        self._razorpay_initialized = True

    monkeypatch.setattr(PaymentService, "_initialize_razorpay", _fake_init)
    return orders


def _stub_booking_emails(monkeypatch):
    sent = []

    async def _capture(**kwargs):
        sent.append(kwargs)
        return True

    for name in ("send_booking_confirmation_to_customer",
                 "send_new_booking_notification_to_vendor"):
        monkeypatch.setattr(booking_service_module.email_service, name, _capture,
                            raising=False)
    return sent


def _checkout_payload(**over):
    payload = {
        "booking_date": BOOKING_DATE,
        "time_slots": ["10:00 AM"],
        "razorpay_order_id": "order_CART1",
        "razorpay_payment_id": "pay_CART1",
        "razorpay_signature": "sig_CART1",
    }
    payload.update(over)
    return payload


def test_checkout_happy_records_the_pinned_amounts(cs, monkeypatch):
    salon, service = _seed_checkout_state(cs)
    _install_fake_razorpay(cs, monkeypatch, service)
    _stub_booking_emails(monkeypatch)
    cs.login()

    r = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert r.status_code == 200, r.text

    booking = cs.db.table("bookings").rows[0]
    assert booking["status"] == "confirmed"
    assert booking["razorpay_payment_id"] == "pay_CART1"
    # Recorded == charged: straight from the order's pinned breakdown.
    assert booking["service_price"] == 1000.0
    assert booking["convenience_fee"] == 60.0
    assert booking["total_amount"] == 1060.0
    # Cart cleared, ledger written.
    assert cs.db.table("cart_items").rows == []
    assert {p["payment_type"] for p in cs.db.table("payments").rows} == {
        "convenience_fee", "service_payment"
    }


def test_checkout_reads_each_row_once(cs, monkeypatch):
    """
    The salon, the fee config and the payment-id idempotency lookup were each
    read twice per checkout — once here, once inside create_booking
    (payment audit M-2/M-3/M-4).
    """
    salon, service = _seed_checkout_state(cs)
    _install_fake_razorpay(cs, monkeypatch, service)
    _stub_booking_emails(monkeypatch)
    cs.login()

    cs.db.queries.clear()
    r = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert r.status_code == 200, r.text

    assert cs.db.count_queries("salons") == 1
    assert cs.db.count_queries("system_config") == 1
    assert cs.db.count_queries("bookings", "select") == 1
    # One multi-row insert, not one per ledger row (M-10).
    assert cs.db.count_queries("payments", "insert") == 1
    # clear_cart counts the rows the delete returns instead of counting them first.
    assert cs.db.count_queries("cart_items", "select") == 1   # get_cart only
    assert cs.db.count_queries("cart_items", "delete") == 1


def test_checkout_makes_nine_round_trips_before_responding(cs, monkeypatch):
    """
    A budget, deliberately exact so that adding a read to the post-charge path
    has to be a decision rather than an accident.

    The nine, in order: bookings (idempotency), cart_items, salons,
    system_config, payment_intents, services, INSERT bookings, INSERT payments,
    DELETE cart_items.

    This is one *more* local query than Phase 1's eight and one *fewer* external
    call: the pinned snapshot now comes from our own `payment_intents` row rather
    than a Razorpay `orders.fetch` over the network (H-2). Trading an HTTPS round
    trip to Mumbai for a query alongside the other eight is the entire point.

    Not counted here: the two auth round trips (its own test covers those) and
    the two Razorpay credential reads (cached, and stubbed out here).
    """
    salon, service = _seed_checkout_state(cs)
    orders = _install_fake_razorpay(cs, monkeypatch, service)
    _stub_booking_emails(monkeypatch)
    cs.login()

    cs.db.queries.clear()
    r = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert r.status_code == 200, r.text

    # TestClient drains background tasks before returning, so split on the last
    # thing the response itself depends on.
    deferred_from = cs.db.queries.index(("cart_items", "delete")) + 1
    in_request = cs.db.queries[:deferred_from]
    deferred = cs.db.queries[deferred_from:]

    assert in_request == [
        ("bookings", "select"),
        ("cart_items", "select"),
        ("salons", "select"),
        ("system_config", "select"),
        ("payment_intents", "select"),
        ("services", "select"),
        ("bookings", "insert"),
        ("payments", "insert"),
        ("cart_items", "delete"),
    ], in_request

    # No external call at all in the post-charge path any more.
    assert orders.fetched == []

    # Closing the intent out is bookkeeping for reconciliation, so it waits with
    # the two profile reads the confirmation emails need. (Order follows the
    # queue: create_booking adds the emails, checkout_cart adds the intent
    # update after it returns.)
    assert deferred == [
        ("profiles", "select"),
        ("profiles", "select"),
        ("payment_intents", "update"),
    ], deferred


def test_checkout_does_not_read_profiles_before_responding(cs, monkeypatch):
    """
    Both profile reads exist only to address the confirmation emails, which run
    after the response. TestClient runs background tasks on the way out, so the
    count is taken from the queries logged before the booking insert.
    """
    salon, service = _seed_checkout_state(cs)
    _install_fake_razorpay(cs, monkeypatch, service)
    sent = _stub_booking_emails(monkeypatch)
    cs.login()

    cs.db.queries.clear()
    r = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert r.status_code == 200, r.text

    before_insert = cs.db.queries[:cs.db.queries.index(("bookings", "insert"))]
    assert [q for q in before_insert if q[0] == "profiles"] == []
    # The emails did go out afterwards, addressed from those rows.
    assert len(sent) == 2
    assert sent[0]["customer_email"] == "c@x.com"
    assert sent[1]["vendor_email"] == "v@x.com"


def test_checkout_never_calls_razorpay_when_an_intent_exists(cs, monkeypatch):
    """
    H-2: the pinned snapshot lives in our own table, so the post-charge request
    makes no external call to read it back.
    """
    salon, service = _seed_checkout_state(cs)
    orders = _install_fake_razorpay(cs, monkeypatch, service)
    _stub_booking_emails(monkeypatch)
    cs.login()

    r = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert r.status_code == 200, r.text
    assert orders.fetched == []
    # Still the pinned amounts, not a recompute.
    assert cs.db.table("bookings").rows[0]["total_amount"] == 1060.0


def test_checkout_records_the_booking_against_the_intent(cs, monkeypatch):
    """
    The intent is closed out with the booking it produced. That is what makes
    "captured but never completed" a findable state for reconciliation, and what
    stops the webhook treating an already-booked payment as outstanding.
    """
    salon, service = _seed_checkout_state(cs)
    _install_fake_razorpay(cs, monkeypatch, service)
    _stub_booking_emails(monkeypatch)
    cs.login()

    r = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert r.status_code == 200, r.text

    intent = cs.db.table("payment_intents").rows[0]
    assert intent["status"] == "completed"
    assert intent["booking_id"] == cs.db.table("bookings").rows[0]["id"]
    assert intent["razorpay_payment_id"] == "pay_CART1"


def test_checkout_falls_back_to_the_order_notes_without_an_intent(cs, monkeypatch):
    """
    An order created before `payment_intents` existed still has its snapshot in
    the Razorpay order's notes. Reading it keeps payments that were in flight
    across the deploy recording pinned amounts rather than recomputing.
    """
    salon, service = _seed_checkout_state(cs, with_intent=False)
    orders = _install_fake_razorpay(cs, monkeypatch, service)
    _stub_booking_emails(monkeypatch)
    cs.login()

    r = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert r.status_code == 200, r.text
    assert orders.fetched == ["order_CART1"]
    assert cs.db.table("bookings").rows[0]["total_amount"] == 1060.0


def test_checkout_rejects_a_changed_cart_from_the_intent_snapshot(cs, monkeypatch):
    """
    The guard against a cart edited mid-payment now reads the snapshot from the
    intent, so it must still fail closed with Razorpay never contacted.
    """
    salon, service = _seed_checkout_state(cs)
    orders = _install_fake_razorpay(cs, monkeypatch, service)
    _stub_booking_emails(monkeypatch)
    other = cs.seed_service(salon["id"], price=250.0)
    cs.seed_cart_item("cust-1", other["id"], salon["id"], quantity=1)
    cs.login()

    r = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert r.status_code == 400, r.text
    assert "cart" in r.text.lower()
    assert cs.db.table("bookings").rows == []
    assert orders.fetched == []


def test_checkout_is_idempotent_on_the_payment_id(cs, monkeypatch):
    """A replayed checkout returns the existing booking instead of a second one."""
    salon, service = _seed_checkout_state(cs)
    _install_fake_razorpay(cs, monkeypatch, service)
    _stub_booking_emails(monkeypatch)
    cs.login()

    first = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert first.status_code == 200, first.text
    booking_id = cs.db.table("bookings").rows[0]["id"]

    # Re-seed the cart: the replay must not need it, and must not re-book it.
    cs.seed_cart_item("cust-1", service["id"], salon["id"], quantity=1)
    second = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())

    assert second.status_code == 200, second.text
    assert second.json()["id"] == booking_id
    assert len(cs.db.table("bookings").rows) == 1


def test_checkout_rejects_a_cart_changed_since_payment(cs, monkeypatch):
    """
    The same guard on the legacy path, where the snapshot comes from the order
    notes — a cart edited mid-payment must fail closed there too.
    """
    salon, service = _seed_checkout_state(cs, with_intent=False)
    _install_fake_razorpay(cs, monkeypatch, service)
    _stub_booking_emails(monkeypatch)
    # A second item the pinned snapshot does not know about.
    other = cs.seed_service(salon["id"], price=250.0)
    cs.seed_cart_item("cust-1", other["id"], salon["id"], quantity=1)
    cs.login()

    r = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert r.status_code == 400, r.text
    assert "cart" in r.text.lower()
    assert cs.db.table("bookings").rows == []


def test_checkout_still_books_when_the_order_snapshot_is_unreadable(cs, monkeypatch):
    """
    Fail-open on the snapshot read: the customer has already paid, so no intent
    row *and* an unreachable Razorpay falls back to a server-side recompute
    rather than stranding them (audit M-8 documents the trade-off).
    """
    salon, service = _seed_checkout_state(cs, with_intent=False)
    _install_fake_razorpay(cs, monkeypatch, service, fetch_fails=True)
    _stub_booking_emails(monkeypatch)
    cs.login()

    r = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert r.status_code == 200, r.text

    booking = cs.db.table("bookings").rows[0]
    assert booking["status"] == "confirmed"
    assert booking["convenience_fee"] == 60.0     # recomputed: 6% of 1000
    assert booking["total_amount"] == 1060.0


def test_checkout_rejects_a_bad_signature(cs, monkeypatch):
    salon, service = _seed_checkout_state(cs)
    _install_fake_razorpay(cs, monkeypatch, service, signature_valid=False)
    _stub_booking_emails(monkeypatch)
    cs.login()

    r = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert r.status_code == 400, r.text
    assert cs.db.table("bookings").rows == []


def test_checkout_rejects_a_salon_not_accepting_bookings(cs, monkeypatch):
    salon, service = _seed_checkout_state(cs, accepting_bookings=False)
    _install_fake_razorpay(cs, monkeypatch, service)
    _stub_booking_emails(monkeypatch)
    cs.login()

    r = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert r.status_code == 400, r.text
    assert "accepting" in r.text.lower()


def test_checkout_missing_fee_config_is_a_clean_500(cs, monkeypatch):
    salon, service = _seed_checkout_state(cs)
    cs.db.table("system_config").rows.clear()
    _install_fake_razorpay(cs, monkeypatch, service)
    _stub_booking_emails(monkeypatch)
    cs.login()

    r = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert r.status_code == 500, r.text
    assert "configuration" in r.text.lower()
    assert cs.db.table("bookings").rows == []


def test_checkout_is_idempotent_even_with_an_empty_cart(cs, monkeypatch):
    """
    The payment-id check runs before the cart is read, because the webhook can
    get here first and clears the paid items on its way through. Without this
    ordering a late-arriving browser callback is told "Cart is empty" for a
    booking that exists, and the customer sees a failure for a payment that
    worked (audit C-3's webhook against C-2's retry button).
    """
    salon, service = _seed_checkout_state(cs)
    _install_fake_razorpay(cs, monkeypatch, service)
    _stub_booking_emails(monkeypatch)
    cs.add("bookings", customer_id="cust-1", salon_id=salon["id"],
           booking_number="BK-ALREADY", razorpay_payment_id="pay_CART1",
           status="confirmed", booking_date=BOOKING_DATE,
           time_slots=["10:00 AM"], total_amount=1060.0,
           service_price=1000.0, convenience_fee=60.0)
    cs.db.table("cart_items").rows.clear()
    cs.login()

    r = cs.client.post(f"{CUST}/cart/checkout", json=_checkout_payload())
    assert r.status_code == 200, r.text
    assert r.json()["booking_number"] == "BK-ALREADY"
    assert len(cs.db.table("bookings").rows) == 1


# =====================================================================
# WEBHOOK RECOVERY — a booking completed with no browser involved
#
# The path taken when the customer's success callback never arrives: tab closed,
# network dropped, crash between the charge and our request. Before this existed
# that was captured money, no booking, and no record of it anywhere but
# Razorpay's dashboard (payment audit C-3).
#
# The dispatch and signature side lives in test_webhook_mocked.py; these drive
# the real completion against the same fake the checkout tests use.
# =====================================================================
def _complete_from_intent(cs, intent, payment_id="pay_WEBHOOK"):
    return customer_module.CustomerService(cs.db).create_booking_from_intent(
        intent, payment_id
    )


@pytest.mark.asyncio
async def test_webhook_creates_the_booking_the_browser_never_reported(cs, monkeypatch):
    salon, service = _seed_checkout_state(cs)
    intent = cs.db.table("payment_intents").rows[0]
    sent = _stub_booking_emails(monkeypatch)

    booking = await _complete_from_intent(cs, intent)

    assert booking is not None
    row = cs.db.table("bookings").rows[0]
    assert row["razorpay_payment_id"] == "pay_WEBHOOK"
    assert row["status"] == "confirmed"
    # The pinned breakdown, not a recompute — recorded == charged.
    assert row["service_price"] == 1000.0
    assert row["convenience_fee"] == 60.0
    assert row["total_amount"] == 1060.0
    # The ledger is written exactly as on the browser path.
    assert {p["payment_type"] for p in cs.db.table("payments").rows} == {
        "convenience_fee", "service_payment"
    }
    # And the customer is told, which is the only notice they will get.
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_webhook_booking_carries_no_signature(cs, monkeypatch):
    """
    There is no order|payment signature on this path — the proof was an HMAC over
    the webhook body. The `payments` row has to be recordable without one, which
    is what the Phase 2 migration relaxed.
    """
    salon, service = _seed_checkout_state(cs)
    _stub_booking_emails(monkeypatch)

    await _complete_from_intent(cs, cs.db.table("payment_intents").rows[0])

    fee_row = next(p for p in cs.db.table("payments").rows
                   if p["payment_type"] == "convenience_fee")
    assert fee_row["razorpay_payment_id"] == "pay_WEBHOOK"
    assert fee_row.get("razorpay_signature") in (None, "")
    assert fee_row["status"] == "success"


@pytest.mark.asyncio
async def test_webhook_is_idempotent_against_the_browser(cs, monkeypatch):
    """Both paths can run; the second finds the booking the first made."""
    salon, service = _seed_checkout_state(cs)
    _stub_booking_emails(monkeypatch)
    cs.add("bookings", customer_id="cust-1", salon_id=salon["id"],
           booking_number="BK-FROM-BROWSER", razorpay_payment_id="pay_WEBHOOK",
           status="confirmed", booking_date=BOOKING_DATE,
           time_slots=["10:00 AM"], total_amount=1060.0)

    booking = await _complete_from_intent(cs, cs.db.table("payment_intents").rows[0])

    assert booking["booking_number"] == "BK-FROM-BROWSER"
    assert len(cs.db.table("bookings").rows) == 1


@pytest.mark.asyncio
async def test_webhook_clears_only_the_items_that_were_paid_for(cs, monkeypatch):
    """
    `clear_cart` empties the whole cart, which is right in the browser flow. Here
    the customer may have added something else while the webhook was in flight,
    and that is not ours to delete.
    """
    salon, service = _seed_checkout_state(cs)
    _stub_booking_emails(monkeypatch)
    added_later = cs.seed_service(salon["id"], price=250.0)
    cs.seed_cart_item("cust-1", added_later["id"], salon["id"], quantity=1)

    await _complete_from_intent(cs, cs.db.table("payment_intents").rows[0])

    remaining = [i["service_id"] for i in cs.db.table("cart_items").rows]
    assert remaining == [added_later["id"]]


@pytest.mark.asyncio
async def test_webhook_cannot_book_without_an_appointment_on_the_intent(cs, monkeypatch, caplog):
    """
    A client that did not send the date and slots at order time leaves nothing to
    book. That is money needing a person, so it logs at ERROR with the payment id
    rather than failing quietly.
    """
    salon, service = _seed_checkout_state(cs, with_intent=False)
    _seed_payment_intent(cs, salon, service, booking_date=None, time_slots=None)
    _stub_booking_emails(monkeypatch)

    with caplog.at_level("ERROR"):
        booking = await _complete_from_intent(cs, cs.db.table("payment_intents").rows[0])

    assert booking is None
    assert cs.db.table("bookings").rows == []
    assert any("no appointment pinned" in rec.message for rec in caplog.records)
    assert any("pay_WEBHOOK" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_webhook_will_not_book_an_appointment_that_has_passed(cs, monkeypatch, caplog):
    """`bookings` refuses a past date (valid_booking_datetime), so stop before it."""
    salon, service = _seed_checkout_state(cs, with_intent=False)
    _seed_payment_intent(cs, salon, service,
                         booking_date=(date.today() - timedelta(days=1)).isoformat())
    _stub_booking_emails(monkeypatch)

    with caplog.at_level("ERROR"):
        booking = await _complete_from_intent(cs, cs.db.table("payment_intents").rows[0])

    assert booking is None
    assert cs.db.table("bookings").rows == []
    assert any("has passed" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_webhook_books_at_a_salon_that_has_since_stopped_accepting(cs, monkeypatch, caplog):
    """
    Deliberately more permissive than checkout_cart. The browser path refuses
    before any money moves; here it is already taken, so recording what it bought
    beats dropping it — with a warning, because it may need cancelling.
    """
    salon, service = _seed_checkout_state(cs, accepting_bookings=False)
    _stub_booking_emails(monkeypatch)

    with caplog.at_level("WARNING"):
        booking = await _complete_from_intent(cs, cs.db.table("payment_intents").rows[0])

    assert booking is not None
    assert len(cs.db.table("bookings").rows) == 1
    assert any("no longer active/accepting" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_webhook_gives_up_when_the_salon_is_gone(cs, monkeypatch, caplog):
    salon, service = _seed_checkout_state(cs)
    _stub_booking_emails(monkeypatch)
    cs.db.table("salons").rows.clear()

    with caplog.at_level("ERROR"):
        booking = await _complete_from_intent(cs, cs.db.table("payment_intents").rows[0])

    assert booking is None
    assert cs.db.table("bookings").rows == []
    assert any("no longer exists" in rec.message for rec in caplog.records)


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


def test_favorites_hide_private_salon_fields(cs):
    # Favorites return whole salon rows; the customer must not receive the
    # owner's contact details, tax ids or the registration/agreement trail.
    salon = cs.seed_salon(vendor_id="vendor-1", gst_number="27AAPFU0939F1ZV",
                          pan_number="AAPFU0939F", registration_payment_id="pay-1",
                          agreement_document_url="https://files.example.com/a.pdf",
                          email="owner@example.com")
    cs.add("favorites", user_id="cust-1", salon_id=salon["id"])
    cs.login()

    r = cs.client.get(f"{CUST}/favorites")
    assert r.status_code == 200, r.text
    fav = r.json()["favorites"][0]
    for field in ("vendor_id", "gst_number", "pan_number", "registration_payment_id",
                  "agreement_document_url", "registration_fee_paid", "phone", "email"):
        assert field not in fav, f"favorites leaked {field}"
    assert fav["business_name"] == "Salon X"


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
