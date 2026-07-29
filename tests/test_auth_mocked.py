"""
Mocked unit/route tests for the auth_service module.

These run WITHOUT a real Supabase stack or MessageCentral account. The Supabase
DB + GoTrue auth clients are replaced with small in-memory fakes via FastAPI
dependency overrides, and OTPService / ActivityLogService are monkeypatched so
nothing touches the network. They exercise the full HTTP path:

    HTTP -> FastAPI (Pydantic validation, rate limiter disabled) -> route ->
    AuthService -> fake DB / fake auth / mocked OTP.

Scope: every endpoint in app/api/auth.py (happy path + key error cases), plus
the request/response contracts the web frontend and admin panel depend on.

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client, get_auth_client
from app.core.auth import get_current_user, TokenData, create_refresh_token
from app.services.otp_service import OTPService
from app.services.activity_log_service import ActivityLogService

API = settings.API_PREFIX


# =====================================================================
# In-memory fake Supabase (DB) client
# =====================================================================
class _Resp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    """A chainable query that mimics the supabase-py builder for the ops the
    auth module actually uses: select/insert/update/delete, the eq/gte/in_/is_
    filters, count="exact", and single/maybe_single."""

    def __init__(self, table):
        self._table = table
        self._filters = []
        self._op = ("select", "*")
        self._single = False
        self._maybe_single = False
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
        self._filters.append(lambda r: r.get(col) == val)
        return self

    def gte(self, col, val):
        self._filters.append(lambda r: r.get(col) is not None and r.get(col) >= val)
        return self

    def in_(self, col, vals):
        self._filters.append(lambda r: r.get(col) in vals)
        return self

    def is_(self, col, val):
        # supabase spells IS NULL as .is_(col, "null")
        if val == "null":
            self._filters.append(lambda r: r.get(col) is None)
        else:
            self._filters.append(lambda r: r.get(col) is val)
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._maybe_single = True
        return self

    def _match(self, row):
        return all(f(row) for f in self._filters)

    def execute(self):
        op, payload = self._op
        rows = self._table.rows

        if op == "select":
            matched = [dict(r) for r in rows if self._match(r)]
            if self._count == "exact":
                return _Resp(matched, count=len(matched))
            if self._single:
                if len(matched) != 1:
                    # supabase .single() raises (PGRST116) when not exactly one row
                    raise Exception("PGRST116: results contain 0 or multiple rows")
                return _Resp(matched[0])
            if self._maybe_single:
                return _Resp(matched[0] if matched else None)
            return _Resp(matched)

        if op == "insert":
            new_rows = payload if isinstance(payload, list) else [payload]
            for nr in new_rows:
                email = nr.get("email")
                if email and any(r.get("email") == email for r in rows):
                    raise Exception(
                        'duplicate key value violates unique constraint "profiles_email_key"'
                    )
                rows.append(dict(nr))
            return _Resp([dict(r) for r in new_rows])

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


class _FakeGoTrueAdmin:
    """Stand-in for `supabase.auth.admin` on the service-role client.

    delete_user CASCADEs to profiles in real Postgres, so the fake mirrors that
    by dropping the matching profile row.
    """

    def __init__(self, db):
        self._db = db
        self.deleted = []
        self.updated = {}
        self.delete_error = None

    def delete_user(self, user_id):
        if self.delete_error:
            raise Exception(self.delete_error)
        self.deleted.append(user_id)
        profiles = self._db.table("profiles").rows
        profiles[:] = [r for r in profiles if r.get("id") != user_id]
        return True

    def update_user_by_id(self, user_id, attrs):
        self.updated[user_id] = attrs
        return True


class _FakeDbAuth:
    def __init__(self, db):
        self.admin = _FakeGoTrueAdmin(db)


class FakeSupabase:
    def __init__(self):
        self._tables = {}
        self.auth = _FakeDbAuth(self)

    def table(self, name):
        return self._tables.setdefault(name, _Table())


# =====================================================================
# In-memory fake GoTrue (auth) client
# =====================================================================
class _User:
    def __init__(self, id, email, email_confirmed_at=None):
        self.id = id
        self.email = email
        # Supabase sets this when the address is confirmed; auth responses expose
        # it to clients as `email_verified`.
        self.email_confirmed_at = email_confirmed_at


class _AuthResult:
    def __init__(self, user):
        self.user = user


class FakeGoTrue:
    """Configurable stand-in for supabase `.auth`.

    Note: deliberately exposes `reset_password_for_email` but NOT
    `reset_password_email`, matching the feature-detection branch the service
    takes against supabase==2.0.3.
    """

    _UNSET = object()

    def __init__(self):
        self.sign_in_user = self._UNSET   # set to None to simulate bad credentials
        self.sign_in_error = None         # set to a str to raise from sign_in
        self.session_user = None          # set for password-reset/confirm happy path
        self.update_user_result = None
        self.reset_called = False

    def sign_in_with_password(self, creds):
        if self.sign_in_error:
            raise Exception(self.sign_in_error)
        if self.sign_in_user is self._UNSET:
            return _AuthResult(_User(str(uuid.uuid4()), creds.get("email")))
        return _AuthResult(self.sign_in_user)

    def sign_up(self, payload):
        return _AuthResult(_User(str(uuid.uuid4()), payload.get("email")))

    def set_session(self, access, refresh):
        if self.session_user is None:
            raise Exception("invalid or expired token")
        return _AuthResult(self.session_user)

    def update_user(self, payload):
        return _AuthResult(self.update_user_result or _User(str(uuid.uuid4()), "x@example.com"))

    def reset_password_for_email(self, email, options=None):
        self.reset_called = True
        return True


class FakeAuthClient:
    def __init__(self):
        self.auth = FakeGoTrue()


# =====================================================================
# Test handle + fixture
# =====================================================================
class MockHandle:
    def __init__(self, db, auth, app):
        self.db = db
        self.auth = auth
        self.app = app
        self.client = None
        self.otp_valid = True  # flip to False to simulate a wrong OTP

    @property
    def gotrue(self) -> FakeGoTrue:
        return self.auth.auth

    def seed_profile(self, **fields):
        prof = {
            "id": str(uuid.uuid4()),
            "email": f"user+{uuid.uuid4().hex[:8]}@example.com",
            "full_name": "Test User",
            "user_role": "customer",
            "is_active": True,
            "phone": None,
            "phone_verified": False,
            "age": 30,
            "gender": "other",
        }
        prof.update(fields)
        self.db.table("profiles").rows.append(prof)
        return prof

    def login_as(self, user_id, email="user@example.com", role="customer", jti="jti-test"):
        td = TokenData(
            user_id=user_id,
            email=email,
            user_role=role,
            jti=jti,
            exp=datetime.utcnow() + timedelta(hours=1),
        )
        self.app.dependency_overrides[get_current_user] = lambda: td
        return td


@pytest.fixture()
def mock_auth(app, monkeypatch):
    db = FakeSupabase()
    auth = FakeAuthClient()
    handle = MockHandle(db=db, auth=auth, app=app)

    app.dependency_overrides[get_db_client] = lambda: db
    app.dependency_overrides[get_auth_client] = lambda: auth

    # Mock OTP + activity logging so nothing hits the network.
    async def _send_otp(phone, country_code="91"):
        return {
            "verification_id": "vid-test-123",
            "expires_in": 300,
            "phone": f"+{country_code}****{str(phone)[-4:]}",
        }

    async def _verify_otp(verification_id, otp_code):
        return handle.otp_valid

    async def _log(*args, **kwargs):
        return True

    monkeypatch.setattr(OTPService, "send_otp", staticmethod(_send_otp))
    monkeypatch.setattr(OTPService, "verify_otp", staticmethod(_verify_otp))
    monkeypatch.setattr(ActivityLogService, "log", staticmethod(_log))

    handle.client = TestClient(app)
    yield handle

    app.dependency_overrides.pop(get_db_client, None)
    app.dependency_overrides.pop(get_auth_client, None)
    app.dependency_overrides.pop(get_current_user, None)


# =====================================================================
# /auth/login
# =====================================================================
def test_login_happy(mock_auth):
    prof = mock_auth.seed_profile(user_role="customer")
    mock_auth.gotrue.sign_in_user = _User(prof["id"], prof["email"])

    r = mock_auth.client.post(f"{API}/auth/login", json={"email": prof["email"], "password": "pw"})
    assert r.status_code == 200, r.text
    body = r.json()
    # Contract relied on by web/admin/mobile login flows:
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["email"] == prof["email"]
    assert body["user"]["role"] == "customer"  # admin validateSession reads user.role


def test_login_reports_email_verified(mock_auth):
    """Clients render the 'confirm your email' banner off this flag."""
    prof = mock_auth.seed_profile(user_role="customer")
    mock_auth.gotrue.sign_in_user = _User(
        prof["id"], prof["email"], email_confirmed_at="2026-01-01T00:00:00Z"
    )

    r = mock_auth.client.post(f"{API}/auth/login", json={"email": prof["email"], "password": "pw"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email_verified"] is True


def test_login_reports_email_unverified(mock_auth):
    prof = mock_auth.seed_profile(user_role="customer")
    mock_auth.gotrue.sign_in_user = _User(prof["id"], prof["email"])  # never confirmed

    r = mock_auth.client.post(f"{API}/auth/login", json={"email": prof["email"], "password": "pw"})
    assert r.status_code == 200, r.text
    # Explicitly False, not None: None means "unknown" and keeps clients silent.
    assert r.json()["user"]["email_verified"] is False


def test_login_unconfirmed_email_returns_403(mock_auth):
    """Supabase refuses unconfirmed logins; that must not surface as a 500."""
    mock_auth.gotrue.sign_in_error = "Email not confirmed"
    r = mock_auth.client.post(
        f"{API}/auth/login", json={"email": "x@example.com", "password": "pw"}
    )
    assert r.status_code == 403, r.text
    assert "confirm" in r.json()["message"].lower()


def test_login_bad_credentials(mock_auth):
    mock_auth.gotrue.sign_in_error = "Invalid login credentials"
    r = mock_auth.client.post(f"{API}/auth/login", json={"email": "x@example.com", "password": "bad"})
    assert r.status_code == 401, r.text


def test_login_inactive_account(mock_auth):
    prof = mock_auth.seed_profile(is_active=False)
    mock_auth.gotrue.sign_in_user = _User(prof["id"], prof["email"])
    r = mock_auth.client.post(f"{API}/auth/login", json={"email": prof["email"], "password": "pw"})
    assert r.status_code == 403, r.text


def test_login_profile_missing(mock_auth):
    # Auth succeeds but no profile row exists -> 404. authenticate_user uses
    # maybe_single(), so a missing profile returns empty data and hits the explicit
    # 404 branch (rather than raising PGRST116 and being masked as a 500).
    mock_auth.gotrue.sign_in_user = _User(str(uuid.uuid4()), "ghost@example.com")
    r = mock_auth.client.post(f"{API}/auth/login", json={"email": "ghost@example.com", "password": "pw"})
    assert r.status_code == 404, r.text


# =====================================================================
# /auth/signup
# =====================================================================
def _signup_body(**over):
    body = {
        "email": f"new+{uuid.uuid4().hex[:8]}@example.com",
        "password": "TestPassw0rd!23",
        "full_name": "New Customer",
        "age": 25,
        "gender": "female",
    }
    body.update(over)
    return body


def test_signup_happy(mock_auth):
    body = _signup_body()
    r = mock_auth.client.post(f"{API}/auth/signup", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["success"] is True
    assert data["access_token"] and data["refresh_token"]
    assert data["user"]["email"] == body["email"]


def test_signup_duplicate_email(mock_auth):
    existing = mock_auth.seed_profile()
    r = mock_auth.client.post(f"{API}/auth/signup", json=_signup_body(email=existing["email"]))
    assert r.status_code == 400, r.text


def test_signup_invalid_gender(mock_auth):
    r = mock_auth.client.post(f"{API}/auth/signup", json=_signup_body(gender="unknown"))
    assert r.status_code == 400, r.text


def test_signup_age_below_minimum_rejected_by_schema(mock_auth):
    # Pydantic ge=13 -> 422 before the handler runs
    r = mock_auth.client.post(f"{API}/auth/signup", json=_signup_body(age=10))
    assert r.status_code == 422, r.text


# =====================================================================
# /auth/refresh
# =====================================================================
def test_refresh_happy(mock_auth):
    prof = mock_auth.seed_profile()
    token = create_refresh_token({"sub": prof["id"], "email": prof["email"], "user_role": "customer"})
    r = mock_auth.client.post(f"{API}/auth/refresh", json={"refresh_token": token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"] and body["refresh_token"]


def test_refresh_invalid_token(mock_auth):
    r = mock_auth.client.post(f"{API}/auth/refresh", json={"refresh_token": "not-a-jwt"})
    assert r.status_code == 401, r.text


# =====================================================================
# /auth/me  (GET + PUT)
# =====================================================================
def test_me_get_happy(mock_auth):
    prof = mock_auth.seed_profile()
    mock_auth.login_as(prof["id"], email=prof["email"], role="customer")
    r = mock_auth.client.get(f"{API}/auth/me")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == prof["email"]
    assert body["user"]["role"] == "customer"  # frontend backward-compat field


def test_me_includes_email_verified(mock_auth, monkeypatch):
    """
    /auth/me is the only endpoint a long-lived session re-checks, so it is where
    the confirm-your-email banner gets its truth. `profiles` has no such column —
    it comes from Supabase auth.users via _is_auth_user_email_confirmed.
    """
    from app.services.auth_service import AuthService

    async def _unconfirmed(self, uid):
        return False

    monkeypatch.setattr(AuthService, "_is_auth_user_email_confirmed", _unconfirmed)

    prof = mock_auth.seed_profile()
    mock_auth.login_as(prof["id"], email=prof["email"], role="customer")
    r = mock_auth.client.get(f"{API}/auth/me")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email_verified"] is False


def test_me_email_verified_unknown_stays_none(mock_auth, monkeypatch):
    """A failed auth-user lookup must report None, never a bogus False."""
    from app.services.auth_service import AuthService

    async def _unknown(self, uid):
        return None

    monkeypatch.setattr(AuthService, "_is_auth_user_email_confirmed", _unknown)

    prof = mock_auth.seed_profile()
    mock_auth.login_as(prof["id"], email=prof["email"], role="customer")
    r = mock_auth.client.get(f"{API}/auth/me")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email_verified"] is None


def test_me_get_profile_missing_returns_404(mock_auth):
    # Authenticated, but the profile row is gone -> maybe_single() yields no data
    # and get_user_profile returns 404 (not a masked 500).
    mock_auth.login_as(str(uuid.uuid4()), email="gone@example.com", role="customer")
    r = mock_auth.client.get(f"{API}/auth/me")
    assert r.status_code == 404, r.text


def test_me_requires_auth(mock_auth):
    # No login_as override -> real get_current_user runs -> no bearer -> 401
    r = mock_auth.client.get(f"{API}/auth/me")
    assert r.status_code in (401, 403), r.text


def test_me_put_happy(mock_auth):
    prof = mock_auth.seed_profile(full_name="Old Name")
    mock_auth.login_as(prof["id"], email=prof["email"], role="customer")
    r = mock_auth.client.put(f"{API}/auth/me", json={"full_name": "New Name", "age": 41})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["full_name"] == "New Name"
    assert body["user"]["age"] == 41


def test_me_put_rejected_for_non_customer(mock_auth):
    prof = mock_auth.seed_profile(user_role="vendor")
    mock_auth.login_as(prof["id"], email=prof["email"], role="vendor")
    # Valid-length name so Pydantic passes and we reach the handler's role gate.
    r = mock_auth.client.put(f"{API}/auth/me", json={"full_name": "Valid Name"})
    assert r.status_code == 403, r.text


def test_me_put_invalid_phone(mock_auth):
    prof = mock_auth.seed_profile()
    mock_auth.login_as(prof["id"], email=prof["email"], role="customer")
    r = mock_auth.client.put(f"{API}/auth/me", json={"phone": "123"})
    assert r.status_code == 400, r.text


# =====================================================================
# /auth/logout  +  /auth/logout-all
# =====================================================================
def test_logout_happy(mock_auth):
    prof = mock_auth.seed_profile()
    mock_auth.login_as(prof["id"], email=prof["email"], role="customer")
    r = mock_auth.client.post(f"{API}/auth/logout")
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    # token was blacklisted
    assert len(mock_auth.db.table("token_blacklist").rows) == 1


def test_logout_all_happy(mock_auth):
    """Regression for the P0 bug: a correct password must return 200 (not 500)
    and stamp token_valid_after."""
    prof = mock_auth.seed_profile()
    mock_auth.login_as(prof["id"], email=prof["email"], role="customer")
    mock_auth.gotrue.sign_in_user = _User(prof["id"], prof["email"])

    r = mock_auth.client.post(f"{API}/auth/logout-all", json={"password": "correct"})
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    row = mock_auth.db.table("profiles").rows[0]
    assert row.get("token_valid_after")  # timestamp was written


def test_logout_all_wrong_password(mock_auth):
    prof = mock_auth.seed_profile()
    mock_auth.login_as(prof["id"], email=prof["email"], role="customer")
    mock_auth.gotrue.sign_in_user = None  # falsy user -> invalid password
    r = mock_auth.client.post(f"{API}/auth/logout-all", json={"password": "wrong"})
    assert r.status_code == 401, r.text


# =====================================================================
# DELETE /auth/me  (Google Play account-deletion requirement)
# =====================================================================
def _seed_deletable_customer(mock_auth, **fields):
    """A signed-in customer whose password check will succeed."""
    prof = mock_auth.seed_profile(user_role="customer", **fields)
    mock_auth.login_as(prof["id"], email=prof["email"], role="customer")
    mock_auth.gotrue.sign_in_user = _User(prof["id"], prof["email"])
    return prof


def _delete_me(mock_auth, confirmation="DELETE", **proof):
    """Defaults to password proof; pass verification_id/otp for the OTP path."""
    body = {"confirmation": confirmation}
    body.update(proof or {"password": "correct"})
    return mock_auth.client.request("DELETE", f"{API}/auth/me", json=body)


def test_delete_account_hard_deletes_when_no_history(mock_auth):
    """A customer who never booked leaves nothing worth retaining, so the rows go."""
    prof = _seed_deletable_customer(mock_auth)

    r = _delete_me(mock_auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["retained_records"] == {"bookings": 0, "payments": 0}
    # Auth user removed -> profile CASCADEd away
    assert prof["id"] in mock_auth.db.auth.admin.deleted
    assert mock_auth.db.table("profiles").rows == []


def test_delete_account_anonymises_when_records_must_be_retained(mock_auth):
    """Booking/payment rows are ON DELETE RESTRICT, so the profile is scrubbed instead."""
    prof = _seed_deletable_customer(mock_auth, phone="+919876543210", phone_verified=True)
    original_email = prof["email"]  # the fake DB stores the same dict, so copy it first
    mock_auth.db.table("bookings").rows.append({
        "id": str(uuid.uuid4()),
        "customer_id": prof["id"],
        "status": "completed",
        "booking_date": "2020-01-01",
        "deleted_at": None,
    })
    mock_auth.db.table("cart_items").rows.append({"id": "c1", "user_id": prof["id"]})
    mock_auth.db.table("favorites").rows.append({"id": "f1", "user_id": prof["id"]})

    r = _delete_me(mock_auth)
    assert r.status_code == 200, r.text
    assert r.json()["retained_records"]["bookings"] == 1

    # Profile survives (the booking FK needs it) but carries nothing identifying.
    row = mock_auth.db.table("profiles").rows[0]
    assert row["full_name"] == "Deleted User"
    assert row["email"].endswith("@deleted.lubist.com")
    assert row["email"] != original_email
    assert row["phone"] is None
    assert row["phone_verified"] is False
    assert row["is_active"] is False
    assert row["deleted_at"]
    assert row["token_valid_after"]  # every existing token is now rejected

    # Personal-only data is gone, and the credentials were rewritten.
    assert mock_auth.db.table("cart_items").rows == []
    assert mock_auth.db.table("favorites").rows == []
    assert mock_auth.db.auth.admin.updated[prof["id"]]["email"] == row["email"]


def test_delete_account_soft_deletes_reviews(mock_auth):
    """A named public review must not outlive the account."""
    prof = _seed_deletable_customer(mock_auth)
    mock_auth.db.table("bookings").rows.append({
        "id": str(uuid.uuid4()), "customer_id": prof["id"],
        "status": "completed", "booking_date": "2020-01-01", "deleted_at": None,
    })
    mock_auth.db.table("reviews").rows.append({
        "id": "r1", "customer_id": prof["id"], "deleted_at": None,
    })

    assert _delete_me(mock_auth).status_code == 200
    assert mock_auth.db.table("reviews").rows[0]["deleted_at"]


def test_delete_account_blocked_by_upcoming_booking(mock_auth):
    """Money is in flight - the user is told to resolve it first."""
    prof = _seed_deletable_customer(mock_auth)
    future = (datetime.utcnow() + timedelta(days=3)).date().isoformat()
    mock_auth.db.table("bookings").rows.append({
        "id": str(uuid.uuid4()), "customer_id": prof["id"],
        "status": "confirmed", "booking_date": future, "deleted_at": None,
    })

    r = _delete_me(mock_auth)
    assert r.status_code == 409, r.text
    assert "upcoming booking" in r.json()["message"]
    # Nothing was touched.
    assert mock_auth.db.table("profiles").rows[0]["full_name"] == "Test User"


def test_delete_account_ignores_past_and_cancelled_bookings(mock_auth):
    """Only open, future bookings block deletion."""
    prof = _seed_deletable_customer(mock_auth)
    future = (datetime.utcnow() + timedelta(days=3)).date().isoformat()
    mock_auth.db.table("bookings").rows.extend([
        {"id": "b1", "customer_id": prof["id"], "status": "cancelled",
         "booking_date": future, "deleted_at": None},
        {"id": "b2", "customer_id": prof["id"], "status": "completed",
         "booking_date": "2020-01-01", "deleted_at": None},
    ])

    assert _delete_me(mock_auth).status_code == 200


def test_delete_account_with_otp_instead_of_password(mock_auth):
    """Phone-first signups never learn their password, so an OTP must be enough."""
    _seed_deletable_customer(mock_auth, phone="+919876543210", phone_verified=True)
    mock_auth.gotrue.sign_in_user = None  # password path would fail - unused here

    r = _delete_me(mock_auth, verification_id="vid-test-123", otp="123456")
    assert r.status_code == 200, r.text


def test_delete_account_wrong_otp(mock_auth):
    _seed_deletable_customer(mock_auth, phone="+919876543210", phone_verified=True)
    mock_auth.otp_valid = False

    r = _delete_me(mock_auth, verification_id="vid-test-123", otp="000000")
    assert r.status_code == 401, r.text
    assert mock_auth.db.table("profiles").rows[0]["full_name"] == "Test User"


def test_delete_account_otp_rejected_without_verified_phone(mock_auth):
    """An OTP cannot stand in for identity on an account with no phone on file."""
    _seed_deletable_customer(mock_auth, phone=None, phone_verified=False)

    r = _delete_me(mock_auth, verification_id="vid-test-123", otp="123456")
    assert r.status_code == 400, r.text


def test_delete_account_requires_some_proof(mock_auth):
    _seed_deletable_customer(mock_auth)

    r = mock_auth.client.request("DELETE", f"{API}/auth/me", json={"confirmation": "DELETE"})
    assert r.status_code == 400, r.text
    assert "password" in r.json()["message"].lower()


def test_delete_otp_sends_to_phone_on_file(mock_auth):
    """The number comes from the profile - the caller cannot nominate one."""
    _seed_deletable_customer(mock_auth, phone="+919876543210", phone_verified=True)

    r = mock_auth.client.post(f"{API}/auth/me/delete/send-otp")
    assert r.status_code == 200, r.text
    assert r.json()["verification_id"] == "vid-test-123"


def test_delete_otp_send_requires_verified_phone(mock_auth):
    _seed_deletable_customer(mock_auth, phone=None, phone_verified=False)

    r = mock_auth.client.post(f"{API}/auth/me/delete/send-otp")
    assert r.status_code == 400, r.text
    assert "password" in r.json()["message"].lower()


def test_delete_account_wrong_password(mock_auth):
    prof = _seed_deletable_customer(mock_auth)
    mock_auth.gotrue.sign_in_user = None  # falsy user -> invalid password

    r = _delete_me(mock_auth, password="wrong")
    assert r.status_code == 401, r.text
    assert mock_auth.db.table("profiles").rows[0]["full_name"] == "Test User"


def test_delete_account_requires_typed_confirmation(mock_auth):
    _seed_deletable_customer(mock_auth)

    r = _delete_me(mock_auth, confirmation="yes")
    assert r.status_code == 400, r.text
    assert mock_auth.db.table("profiles").rows[0]["full_name"] == "Test User"


def test_delete_account_confirmation_is_case_insensitive(mock_auth):
    _seed_deletable_customer(mock_auth)
    assert _delete_me(mock_auth, confirmation=" delete ").status_code == 200


def test_delete_account_blocked_for_business_roles(mock_auth):
    """Vendors hold salon and payout records - routed to support instead."""
    prof = mock_auth.seed_profile(user_role="vendor")
    mock_auth.login_as(prof["id"], email=prof["email"], role="vendor")
    mock_auth.gotrue.sign_in_user = _User(prof["id"], prof["email"])

    r = _delete_me(mock_auth)
    assert r.status_code == 403, r.text
    assert "support@lubist.com" in r.json()["message"]


def test_delete_account_already_deleted(mock_auth):
    _seed_deletable_customer(mock_auth, deleted_at="2026-01-01T00:00:00")

    r = _delete_me(mock_auth)
    assert r.status_code == 410, r.text


def test_delete_account_requires_auth(mock_auth):
    mock_auth.app.dependency_overrides.pop(get_current_user, None)
    r = _delete_me(mock_auth)
    assert r.status_code in (401, 403)


# =====================================================================
# /auth/password-reset  +  /confirm
# =====================================================================
def test_password_reset_existing_email(mock_auth):
    prof = mock_auth.seed_profile()
    r = mock_auth.client.post(f"{API}/auth/password-reset", json={"email": prof["email"]})
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    assert mock_auth.gotrue.reset_called is True


def test_password_reset_unknown_email_still_success(mock_auth):
    # Account-enumeration protection: unknown email also returns success
    r = mock_auth.client.post(f"{API}/auth/password-reset", json={"email": "nobody@example.com"})
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True


def test_password_reset_confirm_happy(mock_auth):
    prof = mock_auth.seed_profile()
    mock_auth.gotrue.session_user = _User(prof["id"], prof["email"])
    r = mock_auth.client.post(
        f"{API}/auth/password-reset/confirm",
        json={"token": "valid-access-token", "new_password": "BrandNewPw1!"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["access_token"]


def test_password_reset_confirm_profile_missing_returns_404(mock_auth):
    # Valid reset session, but no profile row -> maybe_single() yields no data -> 404.
    mock_auth.gotrue.session_user = _User(str(uuid.uuid4()), "gone@example.com")
    r = mock_auth.client.post(
        f"{API}/auth/password-reset/confirm",
        json={"token": "valid-access-token", "new_password": "BrandNewPw1!"},
    )
    assert r.status_code == 404, r.text


def test_password_reset_confirm_invalid_token(mock_auth):
    # session_user left None -> set_session raises -> 400
    r = mock_auth.client.post(
        f"{API}/auth/password-reset/confirm",
        json={"token": "bad", "new_password": "BrandNewPw1!"},
    )
    assert r.status_code == 400, r.text


# =====================================================================
# /auth/resend-verification
# =====================================================================
def test_resend_verification_already_verified(mock_auth, monkeypatch):
    from app.services.auth_service import AuthService

    async def _confirmed(self, uid):
        return True

    monkeypatch.setattr(AuthService, "_is_auth_user_email_confirmed", _confirmed)

    prof = mock_auth.seed_profile()
    mock_auth.login_as(prof["id"], email=prof["email"], role="customer")
    r = mock_auth.client.post(f"{API}/auth/resend-verification")
    assert r.status_code == 200, r.text
    assert r.json().get("already_verified") is True


def test_resend_verification_sends(mock_auth, monkeypatch):
    from app.services.auth_service import AuthService

    async def _unconfirmed(self, uid):
        return False

    monkeypatch.setattr(AuthService, "_is_auth_user_email_confirmed", _unconfirmed)

    async def _resend(self, email):
        return None

    monkeypatch.setattr(AuthService, "_supabase_resend_signup_confirmation", _resend)

    prof = mock_auth.seed_profile()
    mock_auth.login_as(prof["id"], email=prof["email"], role="customer")
    r = mock_auth.client.post(f"{API}/auth/resend-verification")
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True


# =====================================================================
# /auth/signup/phone/send-otp  +  verify-otp
# =====================================================================
def test_signup_phone_send_otp_happy(mock_auth):
    r = mock_auth.client.post(
        f"{API}/auth/signup/phone/send-otp", json={"phone": "9876543210", "country_code": "91"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["verification_id"] == "vid-test-123"


def test_signup_phone_send_otp_already_registered(mock_auth):
    mock_auth.seed_profile(phone="+919876543210", phone_verified=True)
    r = mock_auth.client.post(
        f"{API}/auth/signup/phone/send-otp", json={"phone": "9876543210", "country_code": "91"}
    )
    assert r.status_code == 400, r.text


def test_signup_phone_verify_otp_happy(mock_auth):
    mock_auth.otp_valid = True
    r = mock_auth.client.post(
        f"{API}/auth/signup/phone/verify-otp",
        json={"phone": "9876543210", "otp": "123456", "verification_id": "vid-test-123"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["verification_token"]  # consumed by /auth/signup


def test_signup_phone_verify_otp_invalid(mock_auth):
    mock_auth.otp_valid = False
    r = mock_auth.client.post(
        f"{API}/auth/signup/phone/verify-otp",
        json={"phone": "9876543210", "otp": "000000", "verification_id": "vid-test-123"},
    )
    assert r.status_code == 401, r.text


# =====================================================================
# /auth/login/phone/send-otp  +  verify-otp  (CUSTOMERS ONLY)
# =====================================================================
def test_login_phone_send_otp_happy(mock_auth):
    mock_auth.seed_profile(
        phone="+919876543210", phone_verified=True, user_role="customer", full_name="Phone User"
    )
    r = mock_auth.client.post(
        f"{API}/auth/login/phone/send-otp", json={"phone": "9876543210", "country_code": "91"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verification_id"] == "vid-test-123"
    assert body["customer_name"] == "Phone User"


def test_login_phone_send_otp_not_registered(mock_auth):
    r = mock_auth.client.post(
        f"{API}/auth/login/phone/send-otp", json={"phone": "9876543210", "country_code": "91"}
    )
    assert r.status_code == 404, r.text


def test_login_phone_send_otp_not_verified(mock_auth):
    mock_auth.seed_profile(phone="+919876543210", phone_verified=False, user_role="customer")
    r = mock_auth.client.post(
        f"{API}/auth/login/phone/send-otp", json={"phone": "9876543210", "country_code": "91"}
    )
    assert r.status_code == 403, r.text


def test_login_phone_send_otp_non_customer_blocked(mock_auth):
    mock_auth.seed_profile(phone="+919876543210", phone_verified=True, user_role="vendor")
    r = mock_auth.client.post(
        f"{API}/auth/login/phone/send-otp", json={"phone": "9876543210", "country_code": "91"}
    )
    assert r.status_code == 403, r.text


def test_login_phone_verify_otp_happy(mock_auth):
    prof = mock_auth.seed_profile(
        phone="+919876543210", phone_verified=True, user_role="customer"
    )
    mock_auth.otp_valid = True
    r = mock_auth.client.post(
        f"{API}/auth/login/phone/verify-otp",
        json={"phone": "9876543210", "otp": "123456", "verification_id": "vid-test-123"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["email"] == prof["email"]


def test_login_phone_verify_otp_invalid(mock_auth):
    mock_auth.seed_profile(phone="+919876543210", phone_verified=True, user_role="customer")
    mock_auth.otp_valid = False
    r = mock_auth.client.post(
        f"{API}/auth/login/phone/verify-otp",
        json={"phone": "9876543210", "otp": "000000", "verification_id": "vid-test-123"},
    )
    assert r.status_code == 401, r.text


def test_login_phone_verify_otp_non_customer_blocked(mock_auth):
    mock_auth.seed_profile(phone="+919876543210", phone_verified=True, user_role="admin")
    mock_auth.otp_valid = True
    r = mock_auth.client.post(
        f"{API}/auth/login/phone/verify-otp",
        json={"phone": "9876543210", "otp": "123456", "verification_id": "vid-test-123"},
    )
    assert r.status_code == 403, r.text


# =====================================================================
# /auth/verify-phone/send-otp  +  confirm-otp  (authenticated)
# =====================================================================
def test_verify_phone_send_otp_happy(mock_auth):
    prof = mock_auth.seed_profile()
    mock_auth.login_as(prof["id"], email=prof["email"], role="customer")
    r = mock_auth.client.post(
        f"{API}/auth/verify-phone/send-otp", json={"phone": "9876543210", "country_code": "91"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["verification_id"] == "vid-test-123"


def test_verify_phone_confirm_otp_happy(mock_auth):
    prof = mock_auth.seed_profile()
    mock_auth.login_as(prof["id"], email=prof["email"], role="customer")
    mock_auth.otp_valid = True
    r = mock_auth.client.post(
        f"{API}/auth/verify-phone/confirm-otp",
        json={"phone": "9876543210", "otp": "123456", "verification_id": "vid-test-123"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["phone_verified"] is True
    assert body["phone"] == "+919876543210"


def test_verify_phone_confirm_otp_invalid(mock_auth):
    prof = mock_auth.seed_profile()
    mock_auth.login_as(prof["id"], email=prof["email"], role="customer")
    mock_auth.otp_valid = False
    r = mock_auth.client.post(
        f"{API}/auth/verify-phone/confirm-otp",
        json={"phone": "9876543210", "otp": "000000", "verification_id": "vid-test-123"},
    )
    assert r.status_code == 401, r.text
