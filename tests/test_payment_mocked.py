"""
Mocked route tests for the payment module (app/api/payments.py +
app/services/payment_service.py + app/services/payment.py gateway).

These run WITHOUT a real Supabase stack or Razorpay account. The DB client is a
small in-memory fake; PaymentService._initialize_razorpay is stubbed so it uses
a FakeRazorpay (no network, controllable signature check) and a test key_id.
They exercise the full HTTP path:

    HTTP -> FastAPI (auth deps overridden, rate limiter disabled) -> route ->
    PaymentService -> FakeSupabase / FakeRazorpay.

Scope: the surviving payment surface after the module cleanup —
    POST /payments/cart/create-order
    POST /payments/registration/create-order
    POST /payments/registration/verify
(The booking/verify, booking/create-order, history, vendor/earnings and
webhook endpoints were removed during the audit and are intentionally absent.)

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import get_current_user, get_current_user_id, TokenData
from app.services.payment_service import PaymentService
from app.services.email import email_service

API = settings.API_PREFIX
PAYMENTS = f"{API}/payments"


# =====================================================================
# In-memory fake Supabase client (same shape as other *_mocked tests)
# =====================================================================
class _Resp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, table):
        self._table = table
        self._filters = []
        self._op = ("select", "*")
        self._single = False
        self._maybe_single = False
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
        # Like the real client: one row or None, never a PGRST116 raise on 0 rows.
        self._maybe_single = True
        return self

    def _match(self, row):
        for op, c, v in self._filters:
            if op == "eq" and row.get(c) != v:
                return False
        return True

    def execute(self):
        op, payload = self._op
        rows = self._table.rows
        # Round-trip log — Phase 1 of the payment audit is about how many reads
        # the payment paths make, so the fake records every one.
        self._table.log(op)

        if op == "select":
            matched = [dict(r) for r in rows if self._match(r)]
            for col, desc in reversed(self._order):
                matched.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
            if self._single:
                if len(matched) != 1:
                    raise Exception("PGRST116: results contain 0 or multiple rows")
                return _Resp(matched[0])
            if self._maybe_single:
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
    def __init__(self, name="", queries=None):
        self.rows = []
        self._name = name
        self._queries = queries if queries is not None else []

    def log(self, op):
        self._queries.append((self._name, op))

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
        # (table_name, op) for every .execute() the app made, in order.
        self.queries = []

    def table(self, name):
        if name not in self._tables:
            self._tables[name] = _Table(name, self.queries)
        return self._tables[name]

    def count_queries(self, table, op="select"):
        """How many `op` round trips the app made against `table`."""
        return sum(1 for t, o in self.queries if t == table and o == op)


# =====================================================================
# Fake Razorpay (signature check controllable per test)
# =====================================================================
class FakeRazorpay:
    valid = True  # class-level switch flipped by individual tests
    # Every create_order call, so tests can assert what we send Razorpay — since
    # Phase 2 the notes carry scalars only, not the snapshot blobs.
    orders_created = []

    # Async to match the real RazorpayService, whose blocking `requests` call to
    # Razorpay now goes through the threadpool (payment audit C-4).
    async def create_order(self, amount, currency="INR", receipt=None, notes=None):
        FakeRazorpay.orders_created.append({"amount": amount, "notes": dict(notes or {})})
        return {
            "order_id": f"order_{uuid.uuid4().hex[:12]}",
            "amount": amount,
            "amount_paise": int(amount * 100),
            "currency": currency,
            "status": "created",
            "created_at": 0,
        }

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
        self.sent_emails = []

    # ---- seeding helpers ----
    def seed_config(self, key, value, config_type="number", is_active=True):
        # is_active mirrors the real table's default (true); the fee accessor
        # filters on it, so the fake has to carry it.
        self.db.table("system_config").rows.append(
            {"id": str(uuid.uuid4()), "config_key": key,
             "config_value": value, "config_type": config_type,
             "is_active": is_active}
        )

    def seed_cart_item(self, user_id="u1", price=1000.0, discounted_price=None,
                       quantity=1, salon_id="salon-1", service_id=None):
        service_id = service_id or str(uuid.uuid4())
        self.db.table("cart_items").rows.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "service_id": service_id,
            "quantity": quantity,
            "services": {
                "id": service_id, "name": "Haircut",
                "price": price, "discounted_price": discounted_price,
                "salon_id": salon_id,
            },
        })

    def seed_vendor_request(self, req_id="vr1", status="approved", **extra):
        row = {"id": req_id, "status": status, "rm_id": "rm-1",
               "owner_name": "Owner", "owner_email": "owner@example.com"}
        row.update(extra)
        self.db.table("vendor_join_requests").rows.append(row)
        return row

    def seed_reg_payment(self, **fields):
        row = {
            "id": str(uuid.uuid4()),
            "vendor_id": "u1",
            "vendor_request_id": "vr1",
            "razorpay_order_id": "order_reg",
            "razorpay_payment_id": None,
            "salon_id": None,
            "amount": 1000.0,
            "status": "pending",
        }
        row.update(fields)
        self.db.table("vendor_registration_payments").rows.append(row)
        return row

    def seed_salon(self, salon_id="s1", join_request_id="vr1", **extra):
        row = {"id": salon_id, "business_name": "Test Salon",
               "vendor_id": "u1", "join_request_id": join_request_id}
        row.update(extra)
        self.db.table("salons").rows.append(row)
        return row

    # ---- auth ----
    def login_as(self, user_id="u1", role="customer"):
        td = TokenData(user_id=user_id, email=f"{role}@example.com", user_role=role,
                       jti="jti", exp=datetime.utcnow() + timedelta(hours=1))
        self.app.dependency_overrides[get_current_user] = lambda: td
        self.app.dependency_overrides[get_current_user_id] = lambda: user_id
        return td

    def logout(self):
        self.app.dependency_overrides.pop(get_current_user, None)
        self.app.dependency_overrides.pop(get_current_user_id, None)


@pytest.fixture()
def pm(app, monkeypatch):
    db = FakeSupabase()
    handle = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db

    # Stub Razorpay init: no network, no credential/config/encryption path.
    FakeRazorpay.valid = True
    FakeRazorpay.orders_created = []

    async def _fake_init(self):
        self.razorpay = FakeRazorpay()
        self._razorpay_key_id = "test_key_id"
        self._razorpay_initialized = True

    monkeypatch.setattr(PaymentService, "_initialize_razorpay", _fake_init)

    # Stub the registration receipt email: no real Resend/network call from tests.
    async def _fake_send_receipt(**kwargs):
        handle.sent_emails.append(kwargs)
        return True
    monkeypatch.setattr(email_service, "send_vendor_registration_receipt_email", _fake_send_receipt)

    yield handle

    handle.logout()
    app.dependency_overrides.pop(get_db_client, None)


# =====================================================================
# POST /payments/cart/create-order
# =====================================================================
def test_cart_create_order_happy(pm):
    pm.seed_cart_item(user_id="u1", price=1000.0, quantity=1, salon_id="salon-1")
    pm.seed_config("convenience_fee_percentage", "10")
    pm.login_as("u1")

    r = pm.client.post(f"{PAYMENTS}/cart/create-order")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["order_id"].startswith("order_")
    assert body["key_id"] == "test_key_id"
    assert body["currency"] == "INR"
    # 10% of 1000 = 100
    assert body["amount"] == 100.0
    assert body["breakdown"]["booking_fee"] == 100.0
    assert body["breakdown"]["pay_at_salon"] == 1000.0


def test_cart_create_order_uses_discounted_price_for_pay_at_salon(pm):
    pm.seed_cart_item(user_id="u1", price=1000.0, discounted_price=800.0, quantity=2)
    pm.seed_config("convenience_fee_percentage", "5")
    pm.login_as("u1")

    r = pm.client.post(f"{PAYMENTS}/cart/create-order")
    assert r.status_code == 200, r.text
    body = r.json()
    # booking fee is computed on the ORIGINAL total: 5% of (1000*2) = 100
    assert body["breakdown"]["booking_fee"] == 100.0
    # pay-at-salon uses the discounted total: 800*2 = 1600
    assert body["breakdown"]["pay_at_salon"] == 1600.0


def test_cart_create_order_empty_cart_is_400(pm):
    pm.seed_config("convenience_fee_percentage", "10")
    pm.login_as("u1")
    r = pm.client.post(f"{PAYMENTS}/cart/create-order")
    assert r.status_code == 400, r.text


def test_cart_create_order_missing_fee_config_is_500(pm):
    # Cart present but the platform fee config is absent -> not configured.
    pm.seed_cart_item(user_id="u1")
    pm.login_as("u1")
    r = pm.client.post(f"{PAYMENTS}/cart/create-order")
    assert r.status_code == 500, r.text


def test_cart_create_order_requires_auth(pm):
    r = pm.client.post(f"{PAYMENTS}/cart/create-order")
    assert r.status_code in (401, 403), r.text


def test_cart_create_order_reads_the_cart_and_the_fee_once_each(pm):
    """
    Order creation is what the customer stares at a disabled Pay button through,
    so it gets the same round-trip budget treatment as checkout. (Razorpay
    initialisation is stubbed by the fixture; its credential reads have their
    own test below.)
    """
    pm.seed_cart_item(user_id="u1", price=1000.0, quantity=1)
    pm.seed_config("convenience_fee_percentage", "10")
    pm.login_as("u1")

    pm.db.queries.clear()
    r = pm.client.post(f"{PAYMENTS}/cart/create-order")
    assert r.status_code == 200, r.text

    assert pm.db.count_queries("cart_items") == 1
    assert pm.db.count_queries("system_config") == 1


# =====================================================================
# The payment intent written alongside the Razorpay order (audit H-2 / C-3)
# =====================================================================
def test_cart_create_order_pins_the_snapshot_in_our_own_table(pm):
    """
    The pinned breakdown and cart snapshot are what make recorded == charged.
    They now live in `payment_intents`, so checkout reads them locally instead of
    paying for a Razorpay `orders.fetch` after the customer has been charged.
    """
    pm.seed_cart_item(user_id="u1", price=1000.0, quantity=2,
                      salon_id="salon-1", service_id="svc-1")
    pm.seed_config("convenience_fee_percentage", "10")
    pm.login_as("u1")

    r = pm.client.post(f"{PAYMENTS}/cart/create-order")
    assert r.status_code == 200, r.text

    intents = pm.db.table("payment_intents").rows
    assert len(intents) == 1
    intent = intents[0]
    assert intent["razorpay_order_id"] == r.json()["order_id"]
    assert intent["customer_id"] == "u1"
    assert intent["salon_id"] == "salon-1"
    assert intent["status"] == "created"
    # 10% of 2000
    assert intent["amount"] == 200.0
    assert intent["pricing"]["convenience_fee_due"] == 200.0
    assert intent["pricing"]["total_amount"] == 2200.0
    assert intent["cart_snapshot"] == [
        {"service_id": "svc-1", "quantity": 2, "unit_price": 1000.0}
    ]


def test_cart_create_order_pins_the_appointment_for_webhook_recovery(pm):
    """
    The date and slots are not priced or validated here — they exist so the
    `payment.captured` webhook can finish the booking if the browser never comes
    back (audit C-3).
    """
    pm.seed_cart_item(user_id="u1", price=1000.0)
    pm.seed_config("convenience_fee_percentage", "10")
    pm.login_as("u1")

    r = pm.client.post(f"{PAYMENTS}/cart/create-order", json={
        "booking_date": "2099-03-04",
        "time_slots": ["10:00 AM", "10:15 AM"],
    })
    assert r.status_code == 200, r.text

    intent = pm.db.table("payment_intents").rows[0]
    assert intent["booking_date"] == "2099-03-04"
    assert intent["time_slots"] == ["10:00 AM", "10:15 AM"]


def test_cart_create_order_without_an_appointment_still_works(pm):
    """Both fields are optional: a client that omits them gets a normal order."""
    pm.seed_cart_item(user_id="u1", price=1000.0)
    pm.seed_config("convenience_fee_percentage", "10")
    pm.login_as("u1")

    r = pm.client.post(f"{PAYMENTS}/cart/create-order", json={"coupon_code": None})
    assert r.status_code == 200, r.text

    intent = pm.db.table("payment_intents").rows[0]
    assert intent["booking_date"] is None
    assert intent["time_slots"] is None


def test_cart_create_order_rejects_a_malformed_date(pm):
    pm.seed_cart_item(user_id="u1", price=1000.0)
    pm.seed_config("convenience_fee_percentage", "10")
    pm.login_as("u1")

    r = pm.client.post(f"{PAYMENTS}/cart/create-order",
                       json={"booking_date": "04-03-2099"})
    assert r.status_code == 422, r.text
    assert pm.db.table("payment_intents").rows == []


def test_cart_create_order_no_longer_puts_the_snapshot_in_razorpay_notes(pm):
    """
    Razorpay caps a note value at 256 characters, so a cart of a few services
    could truncate the snapshot it used to hold. The scalars stay — they are what
    makes the Razorpay dashboard readable — but the blobs are ours now.
    """
    pm.seed_cart_item(user_id="u1", price=1000.0, salon_id="salon-1")
    pm.seed_config("convenience_fee_percentage", "10")
    pm.login_as("u1")

    r = pm.client.post(f"{PAYMENTS}/cart/create-order")
    assert r.status_code == 200, r.text

    notes = FakeRazorpay.orders_created[-1]["notes"]
    assert "pricing" not in notes
    assert "cart_snapshot" not in notes
    assert notes["customer_id"] == "u1"
    assert notes["salon_id"] == "salon-1"
    assert notes["type"] == "cart_checkout"
    assert notes["cart_item_count"] == 1


def test_an_error_escaping_the_intent_service_still_fails_the_order(pm, monkeypatch):
    """
    Where the tolerance ends. `create_cart_intent` swallows *database* failures
    itself (next test), but anything escaping it reaches create_cart_payment_order's
    handler and the customer gets a 500 rather than an order we know nothing about.

    Documented, not desired: the Razorpay order already exists at that point, so a
    retry leaves an orphan order behind — the same data-hygiene issue as audit M-9.
    """
    pm.seed_cart_item(user_id="u1", price=1000.0)
    pm.seed_config("convenience_fee_percentage", "10")
    pm.login_as("u1")

    from app.services.payment_intent_service import PaymentIntentService
    original = PaymentIntentService.create_cart_intent

    async def _boom(self, **kwargs):
        raise RuntimeError("payment_intents unavailable")

    monkeypatch.setattr(PaymentIntentService, "create_cart_intent", _boom)
    try:
        r = pm.client.post(f"{PAYMENTS}/cart/create-order")
    finally:
        monkeypatch.setattr(PaymentIntentService, "create_cart_intent", original)

    assert r.status_code == 500, r.text


def test_cart_create_order_tolerates_an_unwritable_intent_table(pm, monkeypatch, caplog):
    """
    The same tolerance one level down, where it actually lives: a DB error on the
    insert is swallowed by the intent service and logged at ERROR, and the order
    is still returned.
    """
    pm.seed_cart_item(user_id="u1", price=1000.0)
    pm.seed_config("convenience_fee_percentage", "10")
    pm.login_as("u1")

    real_table = pm.db.table

    def _explode(name):
        if name == "payment_intents":
            raise RuntimeError("payment_intents unavailable")
        return real_table(name)

    monkeypatch.setattr(pm.db, "table", _explode)

    with caplog.at_level("ERROR"):
        r = pm.client.post(f"{PAYMENTS}/cart/create-order")

    assert r.status_code == 200, r.text
    assert r.json()["order_id"].startswith("order_")
    assert any("Failed to record payment intent" in rec.message for rec in caplog.records)


def test_razorpay_credentials_come_from_one_pair_of_reads(pm):
    """
    The two credentials are Fernet-decrypted reads that ran FOUR times in a
    single cart checkout: twice per PaymentService, and checkout constructed two
    of them (payment audit H-3 + 10.3). Cached, a second resolve — even from a
    different ConfigService — costs nothing.
    """
    import asyncio
    from app.services.config_service import ConfigService
    from app.services.payment import resolve_razorpay_credentials

    pm.seed_config("razorpay_key_id", "rzp_test_abc", config_type="string")
    pm.seed_config("razorpay_key_secret", "secret_abc", config_type="string")

    pm.db.queries.clear()
    first = asyncio.run(resolve_razorpay_credentials(ConfigService(pm.db)))
    reads_after_first = pm.db.count_queries("system_config")
    second = asyncio.run(resolve_razorpay_credentials(ConfigService(pm.db)))

    assert first == second == ("rzp_test_abc", "secret_abc")
    assert reads_after_first == 2, "one read per credential, the first time"
    assert pm.db.count_queries("system_config") == 2, "the second resolve should be free"


# =====================================================================
# POST /payments/registration/create-order
# =====================================================================
def test_registration_create_order_happy(pm):
    pm.seed_vendor_request("vr1", status="approved")
    pm.seed_config("registration_fee_amount", "1500")
    pm.login_as("u1", role="vendor")

    r = pm.client.post(f"{PAYMENTS}/registration/create-order?vendor_request_id=vr1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["order_id"].startswith("order_")
    assert body["amount"] == 1500.0
    assert body["key_id"] == "test_key_id"
    # a pending payment row was persisted
    rows = pm.db.table("vendor_registration_payments").rows
    assert len(rows) == 1 and rows[0]["status"] == "pending"


def test_registration_create_order_not_approved_is_400(pm):
    pm.seed_vendor_request("vr1", status="pending")
    pm.seed_config("registration_fee_amount", "1500")
    pm.login_as("u1", role="vendor")

    r = pm.client.post(f"{PAYMENTS}/registration/create-order?vendor_request_id=vr1")
    assert r.status_code == 400, r.text


def test_registration_create_order_already_paid_is_400(pm):
    pm.seed_vendor_request("vr1", status="approved")
    pm.seed_config("registration_fee_amount", "1500")
    pm.seed_reg_payment(vendor_request_id="vr1", status="success")
    pm.login_as("u1", role="vendor")

    r = pm.client.post(f"{PAYMENTS}/registration/create-order?vendor_request_id=vr1")
    assert r.status_code == 400, r.text


def test_registration_create_order_requires_auth(pm):
    r = pm.client.post(f"{PAYMENTS}/registration/create-order?vendor_request_id=vr1")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# POST /payments/registration/verify
# =====================================================================
def _verify_payload(order_id="order_reg"):
    return {"razorpay_order_id": order_id,
            "razorpay_payment_id": "pay_reg_1",
            "razorpay_signature": "sig_1"}


def test_registration_verify_happy_activates_salon(pm):
    pm.seed_reg_payment(razorpay_order_id="order_reg", status="pending", vendor_request_id="vr1")
    pm.seed_vendor_request("vr1", status="approved")
    pm.seed_salon("s1", join_request_id="vr1")
    pm.login_as("u1", role="vendor")
    FakeRazorpay.valid = True

    r = pm.client.post(f"{PAYMENTS}/registration/verify", json=_verify_payload("order_reg"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["salon_id"] == "s1"
    assert body["salon_name"] == "Test Salon"
    # payment marked success + salon activated
    pay = pm.db.table("vendor_registration_payments").rows[0]
    assert pay["status"] == "success"
    assert pay["razorpay_payment_id"] == "pay_reg_1"
    salon = pm.db.table("salons").rows[0]
    assert salon["is_active"] is True
    assert salon["registration_fee_paid"] is True
    # payment receipt + welcome email fired to the vendor join request's owner
    assert len(pm.sent_emails) == 1
    sent = pm.sent_emails[0]
    assert sent["to_email"] == "owner@example.com"
    assert sent["owner_name"] == "Owner"
    assert sent["salon_name"] == "Test Salon"
    assert sent["amount"] == 1000.0
    assert sent["razorpay_payment_id"] == "pay_reg_1"
    assert sent["salon_id"] == "s1"


def test_registration_verify_missing_owner_email_skips_receipt_email(pm):
    pm.seed_reg_payment(razorpay_order_id="order_reg", status="pending", vendor_request_id="vr1")
    pm.seed_vendor_request("vr1", status="approved", owner_email=None)
    pm.seed_salon("s1", join_request_id="vr1")
    pm.login_as("u1", role="vendor")
    FakeRazorpay.valid = True

    r = pm.client.post(f"{PAYMENTS}/registration/verify", json=_verify_payload("order_reg"))
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    assert pm.sent_emails == []


def test_registration_verify_already_success_does_not_resend_email(pm):
    pm.seed_reg_payment(razorpay_order_id="order_reg", status="success",
                        razorpay_payment_id="pay_old", salon_id="s1")
    pm.login_as("u1", role="vendor")
    FakeRazorpay.valid = True

    r = pm.client.post(f"{PAYMENTS}/registration/verify", json=_verify_payload("order_reg"))
    assert r.status_code == 200, r.text
    assert pm.sent_emails == []


def test_registration_verify_invalid_signature_is_400(pm):
    pm.seed_reg_payment(razorpay_order_id="order_reg", status="pending")
    pm.login_as("u1", role="vendor")
    FakeRazorpay.valid = False

    r = pm.client.post(f"{PAYMENTS}/registration/verify", json=_verify_payload("order_reg"))
    assert r.status_code == 400, r.text


def test_registration_verify_idempotent_when_already_success(pm):
    pm.seed_reg_payment(razorpay_order_id="order_reg", status="success",
                        razorpay_payment_id="pay_old", salon_id="s1")
    pm.login_as("u1", role="vendor")
    FakeRazorpay.valid = True

    r = pm.client.post(f"{PAYMENTS}/registration/verify", json=_verify_payload("order_reg"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert "already verified" in body["message"].lower()
    assert body["payment_id"] == "pay_old"


def test_registration_verify_retries_activation_when_salon_was_missing(pm):
    # Audit H-6: a payment recorded as `success` before its salon row existed used
    # to be unrecoverable — verify returned early on the idempotency check and
    # create-order refused a second attempt, so the vendor stayed paid-but-inactive
    # forever. A repeat verify must now complete the activation.
    pm.seed_reg_payment(razorpay_order_id="order_reg", status="success",
                        razorpay_payment_id="pay_old", salon_id=None,
                        vendor_request_id="vr1")
    pm.seed_vendor_request("vr1", status="approved")
    pm.seed_salon("s1", join_request_id="vr1", is_active=False,
                  registration_fee_paid=False)
    pm.login_as("u1", role="vendor")
    FakeRazorpay.valid = True

    r = pm.client.post(f"{PAYMENTS}/registration/verify", json=_verify_payload("order_reg"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["activated"] is True
    assert body["salon_id"] == "s1"

    salon = next(s for s in pm.db.table("salons").rows if s["id"] == "s1")
    assert salon["is_active"] is True
    assert salon["registration_fee_paid"] is True
    # And the payment row is now linked, so the next verify short-circuits.
    payment = pm.db.table("vendor_registration_payments").rows[0]
    assert payment["salon_id"] == "s1"


def test_registration_verify_reports_not_activated_when_no_salon_exists(pm):
    # Paid, but nothing to activate yet: `success` must not imply a live account,
    # or the client promises the vendor a dashboard that bounces them straight back.
    pm.seed_reg_payment(razorpay_order_id="order_reg", status="pending",
                        vendor_request_id="vr1")
    pm.seed_vendor_request("vr1", status="approved")
    pm.login_as("u1", role="vendor")
    FakeRazorpay.valid = True

    r = pm.client.post(f"{PAYMENTS}/registration/verify", json=_verify_payload("order_reg"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["activated"] is False
    assert body["salon_id"] is None


def test_registration_verify_requires_auth(pm):
    r = pm.client.post(f"{PAYMENTS}/registration/verify", json=_verify_payload())
    assert r.status_code in (401, 403), r.text


# =====================================================================
# Removed endpoints stay removed (regression guard for the cleanup)
# =====================================================================
@pytest.mark.parametrize("method,path", [
    ("post", f"{PAYMENTS}/booking/create-order"),
    ("post", f"{PAYMENTS}/booking/verify"),
    ("get", f"{PAYMENTS}/history"),
    ("get", f"{PAYMENTS}/vendor/earnings"),
    ("post", f"{PAYMENTS}/webhook/razorpay"),
])
def test_removed_endpoints_return_404(pm, method, path):
    pm.login_as("u1")
    r = getattr(pm.client, method)(path)
    assert r.status_code == 404, f"{path} -> {r.status_code} (expected 404; endpoint should be gone)"
