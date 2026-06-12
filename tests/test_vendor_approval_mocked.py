"""
Mocked route tests for the vendor_approval_service module:

    app/api/admin/vendor_requests.py   (POST .../{id}/approve, POST .../{id}/reject)
    app/services/vendor_approval_service.py

These run WITHOUT a real Supabase stack. The DB client is an in-memory fake
(the builder stand-in used by the other *_mocked suites, extended with
maybe_single() and embedded `profiles(...)` projection). They exercise the full
HTTP path:

    HTTP -> FastAPI (require_admin overridden, limiter off) -> route ->
    VendorApprovalService -> FakeSupabase

The service's external collaborators are NOT real here — they are monkeypatched
to deterministic stand-ins so the tests assert the approval/rejection
*orchestration*, not third-party behavior:
  * geocoding_service.geocode_address
  * email_service.send_vendor_approval_email / send_rm_salon_approved_email /
    send_vendor_rejection_email
  * create_registration_token
  * RMService.update_rm_score        (score award on approve / penalty on reject)
  * ActivityLogger.salon_approved / salon_rejected (route-level audit log)

The TestClient is built with raise_server_exceptions=False so unhandled service
errors surface as the 500 a real HTTP client would receive (the app registers a
general Exception handler) instead of bubbling into the test.

Scope note: GET /admin/vendor-requests (the pending list) belongs to the
admin_service module and is covered in tests/test_admin_mocked.py — it is
intentionally not duplicated here.

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import re
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import require_admin, TokenData

import app.services.vendor_approval_service as approval_mod
import app.api.admin.vendor_requests as route_mod
from app.services.rm_service import RMService

API = settings.API_PREFIX
VREQS = f"{API}/admin/vendor-requests"


# =====================================================================
# In-memory fake Supabase client
# =====================================================================
class _Resp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, table):
        self._table = table
        self._db = table.db
        self._filters = []
        self._op = ("select", "*")
        self._single = False
        self._maybe_single = False

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

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._maybe_single = True
        return self

    def _match(self, row):
        for op, c, v in self._filters:
            rv = row.get(c)
            if op == "eq" and rv != v:
                return False
            if op == "in" and rv not in v:
                return False
        return True

    def _embed(self, row, cols):
        """Attach a `profiles` object joined on id, mimicking PostgREST embeds."""
        out = dict(row)
        m = re.search(r"profiles\(([^)]*)\)", cols)
        if not m:
            return out
        wanted = [c.strip() for c in m.group(1).split(",") if c.strip()]
        prof = next((p for p in self._db.table("profiles").rows
                     if p.get("id") == row.get("id")), None)
        if prof is None:
            out["profiles"] = None
        else:
            out["profiles"] = ({c: prof.get(c) for c in wanted}
                               if wanted else dict(prof))
        return out

    def execute(self):
        op, payload = self._op
        rows = self._table.rows

        if op == "select":
            cols = payload
            matched = [r for r in rows if self._match(r)]
            if "profiles(" in cols:
                matched = [self._embed(r, cols) for r in matched]
            else:
                matched = [dict(r) for r in matched]
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
# Spy for the patched external collaborators
# =====================================================================
class _ScoreResult:
    def __init__(self, success=True, new_total_score=42, error=None):
        self.success = success
        self.new_total_score = new_total_score
        self.error = error


class Spy:
    def __init__(self):
        self.emails = []        # list of (kind, kwargs)
        self.score_calls = []   # list of kwargs dicts
        self.tokens = []        # list of kwargs dicts
        self.geocode_return = None    # tuple (lat, lng) or None
        self.score_success = True     # toggle RMService.update_rm_score outcome


# =====================================================================
# Test handle + fixture
# =====================================================================
ADMIN_ID = "admin-1"


class Handle:
    def __init__(self, db, app, spy):
        self.db = db
        self.app = app
        self.spy = spy
        # raise_server_exceptions=False -> see the real 500 response, not a raise
        self.client = TestClient(app, raise_server_exceptions=False)

    # --- seeding ---
    def seed_config(self, *, rm_score="10", penalty="5", fee="500"):
        rows = self.db.table("system_config").rows
        if rm_score is not None:
            rows.append({"id": str(uuid.uuid4()), "config_key": "rm_score_per_approval",
                         "config_value": rm_score, "is_active": True})
        if penalty is not None:
            rows.append({"id": str(uuid.uuid4()), "config_key": "rm_rejection_penalty",
                         "config_value": penalty, "is_active": True})
        if fee is not None:
            rows.append({"id": str(uuid.uuid4()), "config_key": "registration_fee_amount",
                         "config_value": fee, "is_active": True})

    def seed_rm(self, rm_id, *, full_name="Alice RM", email="rm@example.com"):
        self.db.table("profiles").rows.append({
            "id": rm_id, "full_name": full_name, "email": email, "is_active": True,
        })
        self.db.table("rm_profiles").rows.append({"id": rm_id, "performance_score": 0})

    def seed_request(self, rm_id, *, status="pending", **over):
        now = datetime.utcnow().isoformat()
        row = {
            "id": str(uuid.uuid4()),
            "rm_id": rm_id,
            "status": status,
            "request_type": "salon",
            "business_name": "Glamour Studio",
            "business_type": "salon",
            "owner_name": "Owner One",
            "owner_email": "owner@example.com",
            "owner_phone": "+919999999999",
            "business_address": "1 Test Street",
            "city": "Testville",
            "state": "Test State",
            "pincode": "560001",
            "documents": {"description": "A nice salon"},
            "created_at": now,
            "updated_at": now,
        }
        row.update(over)
        self.db.table("vendor_join_requests").rows.append(row)
        return row

    def login_admin(self):
        td = TokenData(user_id=ADMIN_ID, email="admin@example.com", user_role="admin",
                       jti="jti", exp=datetime.utcnow() + timedelta(hours=1))
        self.app.dependency_overrides[require_admin] = lambda: td
        return td

    def logout(self):
        self.app.dependency_overrides.pop(require_admin, None)


@pytest.fixture()
def va(app, monkeypatch):
    db = FakeSupabase()
    spy = Spy()
    handle = Handle(db=db, app=app, spy=spy)
    app.dependency_overrides[get_db_client] = lambda: db
    handle.login_admin()

    # --- patch external collaborators -------------------------------------
    async def fake_geocode(address):
        return spy.geocode_return
    monkeypatch.setattr(approval_mod.geocoding_service, "geocode_address", fake_geocode)

    def fake_token(**kwargs):
        spy.tokens.append(kwargs)
        return "registration-token-xyz"
    monkeypatch.setattr(approval_mod, "create_registration_token", fake_token)

    async def fake_vendor_email(**kwargs):
        spy.emails.append(("vendor_approval", kwargs))
        return True
    async def fake_rm_approved_email(**kwargs):
        spy.emails.append(("rm_approved", kwargs))
        return True
    async def fake_rejection_email(**kwargs):
        spy.emails.append(("rejection", kwargs))
        return True
    monkeypatch.setattr(approval_mod.email_service, "send_vendor_approval_email", fake_vendor_email)
    monkeypatch.setattr(approval_mod.email_service, "send_rm_salon_approved_email", fake_rm_approved_email)
    monkeypatch.setattr(approval_mod.email_service, "send_vendor_rejection_email", fake_rejection_email)

    async def fake_update_rm_score(self, **kwargs):
        spy.score_calls.append(kwargs)
        return _ScoreResult(success=spy.score_success)
    monkeypatch.setattr(RMService, "update_rm_score", fake_update_rm_score)

    async def fake_salon_approved(**kwargs):
        return None
    async def fake_salon_rejected(**kwargs):
        return None
    monkeypatch.setattr(route_mod.ActivityLogger, "salon_approved", fake_salon_approved)
    monkeypatch.setattr(route_mod.ActivityLogger, "salon_rejected", fake_salon_rejected)

    yield handle

    handle.logout()
    app.dependency_overrides.pop(get_db_client, None)


# =====================================================================
# POST /admin/vendor-requests/{id}/approve
# =====================================================================
def test_approve_happy(va):
    rm_id = str(uuid.uuid4())
    va.seed_config()
    va.seed_rm(rm_id)
    req = va.seed_request(rm_id, latitude=12.97, longitude=77.59)

    r = va.client.post(f"{VREQS}/{req['id']}/approve", json={"admin_notes": "Looks good"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["data"]["rm_score_awarded"] == 10
    salon_id = body["data"]["salon_id"]
    assert salon_id

    # request flipped to approved + audited fields written
    vjr = va.db.table("vendor_join_requests").rows[0]
    assert vjr["status"] == "approved"
    assert vjr["reviewed_by"] == ADMIN_ID
    assert vjr["admin_notes"] == "Looks good"

    # salon created and linked back to the request / RM
    salon = next(s for s in va.db.table("salons").rows if s["id"] == salon_id)
    assert salon["business_name"] == "Glamour Studio"
    assert salon["assigned_rm"] == rm_id
    assert salon["join_request_id"] == req["id"]
    assert salon["latitude"] == 12.97 and salon["longitude"] == 77.59
    assert salon["is_active"] is False and salon["registration_fee_paid"] is False

    # RM awarded a POSITIVE score; both emails dispatched; token generated
    assert any(c["score_change"] == 10 for c in va.spy.score_calls)
    kinds = {k for k, _ in va.spy.emails}
    assert {"vendor_approval", "rm_approved"} <= kinds
    assert len(va.spy.tokens) == 1


def test_approve_skips_vendor_email_when_owner_is_rm(va):
    # When the vendor's owner_email equals the RM email, the vendor approval
    # email is skipped (testing scenario), but the RM notification still goes out.
    rm_id = str(uuid.uuid4())
    va.seed_config()
    va.seed_rm(rm_id, email="same@example.com")
    req = va.seed_request(rm_id, owner_email="same@example.com",
                          latitude=12.97, longitude=77.59)

    r = va.client.post(f"{VREQS}/{req['id']}/approve", json={"admin_notes": "ok"})
    assert r.status_code == 200, r.text
    kinds = [k for k, _ in va.spy.emails]
    assert "vendor_approval" not in kinds
    assert "rm_approved" in kinds


def test_approve_geocodes_when_no_coordinates(va):
    rm_id = str(uuid.uuid4())
    va.seed_config()
    va.seed_rm(rm_id)
    req = va.seed_request(rm_id)          # no lat/long provided
    va.spy.geocode_return = (10.0, 20.0)  # geocoder resolves the address

    r = va.client.post(f"{VREQS}/{req['id']}/approve", json={})
    assert r.status_code == 200, r.text
    salon = va.db.table("salons").rows[0]
    assert salon["latitude"] == 10.0 and salon["longitude"] == 20.0


def test_approve_geocode_failure_sets_zero_and_warns(va):
    rm_id = str(uuid.uuid4())
    va.seed_config()
    va.seed_rm(rm_id)
    req = va.seed_request(rm_id)          # no coords
    va.spy.geocode_return = None          # geocoder fails -> fallback 0.0

    r = va.client.post(f"{VREQS}/{req['id']}/approve", json={})
    assert r.status_code == 200, r.text
    warnings = r.json()["data"]["warnings"] or []
    assert any("geocod" in w.lower() for w in warnings)
    salon = va.db.table("salons").rows[0]
    assert salon["latitude"] == 0.0 and salon["longitude"] == 0.0


def test_approve_rm_score_failure_is_nonfatal_warning(va):
    # If the score update fails, the salon is still created and the request
    # still approves — the failure is surfaced as a warning, not a 500.
    rm_id = str(uuid.uuid4())
    va.seed_config()
    va.seed_rm(rm_id)
    req = va.seed_request(rm_id, latitude=1.0, longitude=2.0)
    va.spy.score_success = False

    r = va.client.post(f"{VREQS}/{req['id']}/approve", json={})
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    assert va.db.table("salons").rows  # salon created
    warnings = r.json()["data"]["warnings"] or []
    assert any("rm score" in w.lower() for w in warnings)


def test_approve_already_processed_500(va):
    rm_id = str(uuid.uuid4())
    va.seed_config()
    va.seed_rm(rm_id)
    req = va.seed_request(rm_id, status="approved")

    r = va.client.post(f"{VREQS}/{req['id']}/approve", json={})
    assert r.status_code == 500, r.text
    assert "already" in r.json()["message"].lower()
    # no salon should have been created
    assert va.db.table("salons").rows == []


def test_approve_missing_request_500(va):
    va.seed_config()
    r = va.client.post(f"{VREQS}/{uuid.uuid4()}/approve", json={})
    assert r.status_code == 500, r.text


def test_approve_missing_fee_config_500(va):
    # rm_score / penalty fall back to defaults, but registration_fee_amount has
    # no fallback — its absence aborts the approval.
    rm_id = str(uuid.uuid4())
    va.seed_config(fee=None)
    va.seed_rm(rm_id)
    req = va.seed_request(rm_id, latitude=1.0, longitude=2.0)

    r = va.client.post(f"{VREQS}/{req['id']}/approve", json={})
    assert r.status_code == 500, r.text
    assert va.db.table("salons").rows == []


def test_approve_requires_admin(va):
    va.logout()
    r = va.client.post(f"{VREQS}/{uuid.uuid4()}/approve", json={})
    assert r.status_code in (401, 403), r.text


# =====================================================================
# POST /admin/vendor-requests/{id}/reject
# =====================================================================
def test_reject_happy(va):
    rm_id = str(uuid.uuid4())
    va.seed_config()
    va.seed_rm(rm_id)
    req = va.seed_request(rm_id)

    r = va.client.post(f"{VREQS}/{req['id']}/reject",
                       json={"admin_notes": "Incomplete documents"})
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True

    vjr = va.db.table("vendor_join_requests").rows[0]
    assert vjr["status"] == "rejected"
    assert vjr["reviewed_by"] == ADMIN_ID
    assert vjr["admin_notes"] == "Incomplete documents"

    # RM penalized with a NEGATIVE score change; rejection email sent
    assert any(c["score_change"] == -5 for c in va.spy.score_calls)
    assert any(k == "rejection" for k, _ in va.spy.emails)


def test_reject_missing_rm_profile_still_succeeds(va):
    # Regression for the dedup change (P3b): a missing RM profile must NOT break
    # rejection — the request is still rejected, the notification email is just
    # skipped silently.
    rm_id = str(uuid.uuid4())
    va.seed_config()
    # NOTE: no seed_rm(rm_id) -> rm_profiles/profiles row is absent
    req = va.seed_request(rm_id)

    r = va.client.post(f"{VREQS}/{req['id']}/reject", json={"admin_notes": "No"})
    assert r.status_code == 200, r.text
    assert va.db.table("vendor_join_requests").rows[0]["status"] == "rejected"
    assert all(k != "rejection" for k, _ in va.spy.emails)  # email skipped


def test_reject_requires_reason_422(va):
    # VendorRejectionRequest.admin_notes is required (min_length=1).
    rm_id = str(uuid.uuid4())
    va.seed_rm(rm_id)
    req = va.seed_request(rm_id)

    r_empty = va.client.post(f"{VREQS}/{req['id']}/reject", json={"admin_notes": ""})
    assert r_empty.status_code == 422, r_empty.text

    r_missing = va.client.post(f"{VREQS}/{req['id']}/reject", json={})
    assert r_missing.status_code == 422, r_missing.text


def test_reject_already_processed_500(va):
    rm_id = str(uuid.uuid4())
    va.seed_config()
    va.seed_rm(rm_id)
    req = va.seed_request(rm_id, status="rejected")

    r = va.client.post(f"{VREQS}/{req['id']}/reject", json={"admin_notes": "again"})
    assert r.status_code == 500, r.text


def test_reject_missing_request_500(va):
    va.seed_config()
    r = va.client.post(f"{VREQS}/{uuid.uuid4()}/reject", json={"admin_notes": "x"})
    assert r.status_code == 500, r.text


def test_reject_requires_admin(va):
    va.logout()
    r = va.client.post(f"{VREQS}/{uuid.uuid4()}/reject", json={"admin_notes": "x"})
    assert r.status_code in (401, 403), r.text
