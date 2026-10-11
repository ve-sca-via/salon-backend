"""
Razorpay webhook endpoint — authentication, dispatch and routing.

This endpoint is unauthenticated by necessity (Razorpay holds no token of ours),
so its HMAC check is the only thing between the public internet and code that
records payments. These tests cover that boundary and the routing decision that
follows it; the cart booking it produces is covered end to end in
test_customer_mocked.py, against the fake that already knows how to build a
booking.

Status codes are assertions too, not decoration: they are instructions to
Razorpay's retry machinery, and getting one wrong either drops a notification
about money or invites an endless redelivery loop.
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db_client

WEBHOOK = "/api/webhooks/razorpay"
SECRET = "whsec_test_secret"


# =====================================================================
# Minimal fake Supabase — only the tables the dispatcher touches
# =====================================================================
class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table):
        self._t = table
        self._filters = []
        self._op = ("select", "*")
        self._maybe = False

    def select(self, cols="*", count=None):
        self._op = ("select", cols)
        return self

    def insert(self, payload):
        self._op = ("insert", payload)
        return self

    def update(self, payload):
        self._op = ("update", payload)
        return self

    def eq(self, c, v):
        self._filters.append((c, v))
        return self

    def maybe_single(self):
        self._maybe = True
        return self

    def _match(self, row):
        return all(row.get(c) == v for c, v in self._filters)

    def execute(self):
        op, payload = self._op
        rows = self._t.rows
        self._t.db.queries.append((self._t.name, op))

        if op == "select":
            matched = [dict(r) for r in rows if self._match(r)]
            if self._maybe:
                return _Resp(matched[0] if matched else None)
            return _Resp(matched)
        if op == "insert":
            new = payload if isinstance(payload, list) else [payload]
            added = []
            for nr in new:
                r = dict(nr)
                r.setdefault("id", str(uuid.uuid4()))
                r.setdefault("created_at", datetime.utcnow().isoformat())
                rows.append(r)
                added.append(dict(r))
            return _Resp(added)
        if op == "update":
            updated = []
            for r in rows:
                if self._match(r):
                    r.update(payload)
                    updated.append(dict(r))
            return _Resp(updated)
        return _Resp(None)


class _Table:
    def __init__(self, db, name):
        self.db = db
        self.name = name
        self.rows = []

    def select(self, cols="*", count=None):
        return _Query(self).select(cols)

    def insert(self, p):
        return _Query(self).insert(p)

    def update(self, p):
        return _Query(self).update(p)


class FakeSupabase:
    def __init__(self):
        self._t = {}
        self.queries = []

    def table(self, name):
        if name not in self._t:
            self._t[name] = _Table(self, name)
        return self._t[name]

    def add(self, table, **row):
        row.setdefault("id", str(uuid.uuid4()))
        self.table(table).rows.append(row)
        return row


# =====================================================================
# Fixtures + helpers
# =====================================================================
@pytest.fixture()
def wh(app):
    db = FakeSupabase()
    app.dependency_overrides[get_db_client] = lambda: db
    db.add("system_config", config_key="razorpay_webhook_secret",
           config_value=SECRET, is_active=True)
    yield db
    app.dependency_overrides.pop(get_db_client, None)


def _sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post(client: TestClient, event: dict, secret: str = SECRET, signature=None):
    """Send an event signed over the exact bytes transmitted."""
    body = json.dumps(event).encode()
    headers = {"Content-Type": "application/json"}
    if signature is not False:
        headers["X-Razorpay-Signature"] = signature or _sign(body, secret)
    return client.post(WEBHOOK, content=body, headers=headers)


def _captured(order_id="order_X", payment_id="pay_X", amount=6000):
    return {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {
            "id": payment_id,
            "order_id": order_id,
            "amount": amount,
            "status": "captured",
        }}},
    }


def _failed(order_id="order_X", payment_id="pay_X", reason="card declined"):
    return {
        "event": "payment.failed",
        "payload": {"payment": {"entity": {
            "id": payment_id,
            "order_id": order_id,
            "amount": 6000,
            "error_description": reason,
        }}},
    }


def _seed_intent(db, **over):
    row = dict(
        razorpay_order_id="order_X",
        intent_type="cart_checkout",
        customer_id="cust-1",
        salon_id="salon-1",
        amount=60.0,
        pricing={"convenience_fee_due": 60.0},
        cart_snapshot=[{"service_id": "svc-1", "quantity": 1, "unit_price": 1000.0}],
        coupon_code=None,
        booking_date="2099-01-01",
        time_slots=["10:00 AM"],
        status="created",
        razorpay_payment_id=None,
        booking_id=None,
    )
    row.update(over)
    return db.add("payment_intents", **row)


@pytest.fixture()
def booked(monkeypatch):
    """
    Stub the cart completion so these tests are about routing, not booking.

    Records each call and returns a booking, as the real method does on success.
    """
    calls = []

    async def _complete(self, intent, payment_id, background_tasks=None):
        calls.append({"intent": intent, "payment_id": payment_id})
        return {"id": "booking-1", "booking_number": "BK-1"}

    from app.services.customer_service import CustomerService
    monkeypatch.setattr(CustomerService, "create_booking_from_intent", _complete)
    return calls


# =====================================================================
# AUTHENTICATION
# =====================================================================
def test_valid_signature_is_accepted(wh, client, booked):
    _seed_intent(wh)
    r = _post(client, _captured())
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"


def test_wrong_signature_is_rejected(wh, client, booked):
    _seed_intent(wh)
    r = _post(client, _captured(), signature="deadbeef")
    assert r.status_code == 400, r.text
    assert r.json()["status"] == "invalid_signature"
    # Nothing was acted on.
    assert booked == []


def test_signature_from_a_different_secret_is_rejected(wh, client, booked):
    _seed_intent(wh)
    r = _post(client, _captured(), secret="whsec_attacker")
    assert r.status_code == 400, r.text
    assert booked == []


def test_missing_signature_header_is_rejected(wh, client, booked):
    _seed_intent(wh)
    r = _post(client, _captured(), signature=False)
    assert r.status_code == 400, r.text
    assert booked == []


def test_body_tampered_after_signing_is_rejected(wh, client, booked):
    """
    The signature is over the raw bytes, so changing the payment id invalidates
    it — this is what stops anyone claiming an arbitrary payment was captured.
    """
    _seed_intent(wh)
    body = json.dumps(_captured()).encode()
    signature = _sign(body)
    tampered = body.replace(b"pay_X", b"pay_Y")

    r = client.post(WEBHOOK, content=tampered, headers={
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature,
    })
    assert r.status_code == 400, r.text
    assert booked == []


def test_no_configured_secret_is_503_so_razorpay_retries(wh, client, booked):
    """
    Our own misconfiguration, not a bad request: 503 keeps Razorpay redelivering
    until someone sets the secret, instead of the notification being lost.
    """
    wh.table("system_config").rows.clear()
    _seed_intent(wh)

    r = _post(client, _captured())
    assert r.status_code == 503, r.text
    assert r.json()["status"] == "not_configured"
    assert booked == []


def test_verified_but_unparseable_body_is_400(wh, client):
    body = b"{not json"
    r = client.post(WEBHOOK, content=body, headers={
        "Content-Type": "application/json",
        "X-Razorpay-Signature": _sign(body),
    })
    assert r.status_code == 400, r.text
    assert r.json()["status"] == "invalid_body"


# =====================================================================
# DISPATCH
# =====================================================================
def test_unhandled_event_is_acknowledged_not_errored(wh, client, booked):
    """
    A 2xx means "received". Returning an error for an event we simply do not act
    on would make Razorpay redeliver it forever.
    """
    r = _post(client, {"event": "subscription.charged", "payload": {}})
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "ignored"
    assert booked == []


def test_event_without_a_payment_entity_is_ignored(wh, client, booked):
    r = _post(client, {"event": "payment.captured", "payload": {}})
    assert r.status_code == 200, r.text
    assert r.json()["reason"] == "no_payment_entity"


def test_capture_without_an_order_id_is_ignored(wh, client, booked):
    event = _captured()
    del event["payload"]["payment"]["entity"]["order_id"]
    r = _post(client, event)
    assert r.status_code == 200, r.text
    assert r.json()["reason"] == "no_order_id"


def test_handler_failure_is_500_so_razorpay_retries(wh, client, monkeypatch):
    _seed_intent(wh)

    async def _boom(self, intent, payment_id, background_tasks=None):
        raise RuntimeError("database on fire")

    from app.services.customer_service import CustomerService
    monkeypatch.setattr(CustomerService, "create_booking_from_intent", _boom)

    r = _post(client, _captured())
    assert r.status_code == 500, r.text
    assert r.json()["status"] == "error"


# =====================================================================
# FLOW A — cart checkout
# =====================================================================
def test_capture_with_an_intent_completes_the_booking(wh, client, booked):
    _seed_intent(wh)

    r = _post(client, _captured())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action"] == "booking_completed"
    assert body["flow"] == "cart_checkout"
    assert body["booking_id"] == "booking-1"
    assert booked[0]["payment_id"] == "pay_X"

    intent = wh.table("payment_intents").rows[0]
    assert intent["status"] == "completed"
    assert intent["booking_id"] == "booking-1"
    assert intent["razorpay_payment_id"] == "pay_X"


def test_capture_records_the_money_even_when_no_booking_can_be_made(wh, client, monkeypatch):
    """
    The capture is pinned to the intent *before* the booking is attempted, so a
    payment that cannot be turned into a booking is still findable rather than
    invisible — which is the whole complaint behind C-3.
    """
    _seed_intent(wh)

    async def _cannot(self, intent, payment_id, background_tasks=None):
        return None

    from app.services.customer_service import CustomerService
    monkeypatch.setattr(CustomerService, "create_booking_from_intent", _cannot)

    r = _post(client, _captured())
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "unresolved"

    intent = wh.table("payment_intents").rows[0]
    assert intent["razorpay_payment_id"] == "pay_X"
    assert intent["captured_at"] is not None
    assert intent["status"] == "created"      # never claimed as completed


def test_capture_for_less_than_pinned_is_refused(wh, client, booked):
    """
    Recording a booking as paid for more than was collected is worse than leaving
    it for a person, so a short capture stops here.
    """
    _seed_intent(wh, amount=60.0)
    r = _post(client, _captured(amount=100))      # ₹1 against a pinned ₹60

    assert r.status_code == 200, r.text
    assert r.json()["reason"] == "amount_mismatch"
    assert booked == []
    # Still recorded as captured — the money did move.
    assert wh.table("payment_intents").rows[0]["razorpay_payment_id"] == "pay_X"


def test_capture_for_more_than_pinned_still_books(wh, client, booked):
    _seed_intent(wh, amount=60.0)
    r = _post(client, _captured(amount=7000))

    assert r.status_code == 200, r.text
    assert r.json()["action"] == "booking_completed"


def test_redelivery_of_the_same_capture_is_safe(wh, client, booked):
    """
    Webhooks are delivered at least once. A second delivery must not produce a
    second booking — the completion method is the idempotency point, so it is
    simply called again and returns the booking that exists.
    """
    _seed_intent(wh)
    first = _post(client, _captured())
    second = _post(client, _captured())

    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["action"] == "booking_completed"
    assert len(wh.table("payment_intents").rows) == 1


# =====================================================================
# FLOW B — product order
# =====================================================================
def test_capture_marks_a_pending_product_order_paid(wh, client, booked):
    wh.add("product_orders", razorpay_order_id="order_X", order_number="ORD-1",
           user_id="cust-1", status="pending", payment_status="pending")

    r = _post(client, _captured())
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "order_paid"
    assert r.json()["flow"] == "product_order"

    order = wh.table("product_orders").rows[0]
    assert order["status"] == "paid"
    assert order["payment_status"] == "completed"
    assert order["razorpay_payment_id"] == "pay_X"
    assert booked == []


def test_capture_leaves_an_already_paid_product_order_alone(wh, client):
    wh.add("product_orders", razorpay_order_id="order_X", order_number="ORD-1",
           user_id="cust-1", status="paid", payment_status="completed",
           razorpay_payment_id="pay_EARLIER")

    r = _post(client, _captured())
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "already_settled"
    # The earlier payment id is not overwritten.
    assert wh.table("product_orders").rows[0]["razorpay_payment_id"] == "pay_EARLIER"


def test_capture_cannot_revive_a_cancelled_product_order(wh, client):
    """
    The browser path updates on the order id alone and would happily re-mark a
    cancelled order as paid. The webhook is guarded on `payment_status='pending'`,
    so it cannot.
    """
    wh.add("product_orders", razorpay_order_id="order_X", order_number="ORD-1",
           user_id="cust-1", status="cancelled", payment_status="cancelled")

    r = _post(client, _captured())
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "already_settled"
    assert wh.table("product_orders").rows[0]["status"] == "cancelled"


# =====================================================================
# FLOW C — vendor registration
# =====================================================================
def test_capture_records_a_registration_fee(wh, client, monkeypatch):
    wh.add("vendor_registration_payments", razorpay_order_id="order_X",
           vendor_id="vendor-1", status="pending", amount=1000.0)

    seen = {}

    async def _complete(self, razorpay_order_id, razorpay_payment_id, background_tasks=None):
        seen.update(order_id=razorpay_order_id, payment_id=razorpay_payment_id)
        return {"success": True, "activated": True, "salon_id": "salon-1"}

    from app.services.payment_service import PaymentService
    monkeypatch.setattr(
        PaymentService, "complete_vendor_registration_from_webhook", _complete
    )

    r = _post(client, _captured())
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "registration_recorded"
    assert r.json()["activated"] is True
    assert seen == {"order_id": "order_X", "payment_id": "pay_X"}


# =====================================================================
# ORPHANS AND FAILURES
# =====================================================================
def test_capture_matching_nothing_is_acknowledged_and_flagged(wh, client, booked, caplog):
    """
    Money taken against an order we have no record of. Acknowledged (redelivery
    would not help) but logged at ERROR, because it needs a person.
    """
    with caplog.at_level("ERROR"):
        r = _post(client, _captured(order_id="order_UNKNOWN"))

    assert r.status_code == 200, r.text
    assert r.json()["action"] == "orphan"
    assert any("matches no payment intent" in rec.message for rec in caplog.records)


def test_payment_failed_marks_the_intent_failed(wh, client):
    _seed_intent(wh)
    r = _post(client, _failed())

    assert r.status_code == 200, r.text
    assert r.json()["action"] == "failure_recorded"
    intent = wh.table("payment_intents").rows[0]
    assert intent["status"] == "failed"
    assert intent["failure_reason"] == "card declined"


def test_a_late_failure_cannot_undo_a_completed_intent(wh, client):
    """
    A customer who fails once and then pays must not have the booking's intent
    flipped to `failed` by the earlier attempt's delivery arriving late.
    """
    _seed_intent(wh, status="completed", booking_id="booking-1")
    r = _post(client, _failed())

    assert r.status_code == 200, r.text
    assert wh.table("payment_intents").rows[0]["status"] == "completed"
