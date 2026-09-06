"""
Mocked route tests for the rm_service module (app/api/rm.py + app/api/admin/rms.py
+ app/services/rm_service.py).

These run WITHOUT a real Supabase stack. The DB client is an in-memory fake that
honors PostgREST-style embedded selects (`profiles(...)`), projecting only the
requested columns — so the leaderboard's no-email guarantee is actually testable.
ActivityLogService is stubbed. They exercise the full HTTP path:

    HTTP -> FastAPI (require_rm/require_admin overridden, limiter off) -> route ->
    RMService -> FakeSupabase.

Scope: RM-facing endpoints (vendor-request CRUD, profile, score history, salons,
dashboard, public leaderboard) and admin endpoints (list + update), plus the
cleanup applied this module — leaderboard drops email, admin is_active filters at
the DB level, employee_id is no longer updatable, ValueErrors map to 404/400, and
the orphaned GET endpoints are gone.

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import re
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import require_rm, require_admin, TokenData
from app.services.activity_log_service import ActivityLogService
from app.services.cloudinary_service import CloudinaryService

API = settings.API_PREFIX
RM = f"{API}/rm"
ADMIN_RMS = f"{API}/admin/rms"


# =====================================================================
# In-memory fake Supabase client (with embedded-resource projection)
# =====================================================================
class _Resp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, table):
        self._table = table
        self._db = table.db
        self._cols = "*"
        self._filters = []
        self._op = ("select", "*")
        self._count = None
        self._single = False
        self._order = []
        self._range = None
        self._limit = None

    def select(self, cols="*", count=None):
        self._op = ("select", cols)
        self._cols = cols
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
        self._filters.append((col, val))
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
        return all(row.get(c) == v for c, v in self._filters)

    def _embed(self, row):
        """Attach embedded profiles(...) with only the requested columns."""
        m = re.search(r"profiles\(([^)]*)\)", self._cols)
        if not m:
            return dict(row)
        cols = [c.strip() for c in m.group(1).split(",") if c.strip()]
        prof = next((p for p in self._db.table("profiles").rows if p.get("id") == row.get("id")), None)
        out = dict(row)
        if prof is None:
            out["profiles"] = None
        elif cols and cols != ["*"]:
            out["profiles"] = {c: prof.get(c) for c in cols}
        else:
            out["profiles"] = dict(prof)
        return out

    def execute(self):
        op, payload = self._op
        rows = self._table.rows

        if op == "select":
            matched = [r for r in rows if self._match(r)]
            total = len(matched)
            for col, desc in reversed(self._order):
                matched.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
            if self._range is not None:
                s, e = self._range
                matched = matched[s:e]
            if self._limit is not None:
                matched = matched[:self._limit]
            if "profiles(" in self._cols:
                matched = [self._embed(r) for r in matched]
            else:
                matched = [dict(r) for r in matched]
            if self._single:
                if len(matched) != 1:
                    raise Exception("PGRST116: 0 or multiple rows")
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
# Test handle + fixture
# =====================================================================
class Handle:
    def __init__(self, db, app):
        self.db = db
        self.app = app
        self.client = TestClient(app)

    def seed_rm(self, rm_id=None, is_active=True, performance_score=0, **prof):
        rm_id = rm_id or str(uuid.uuid4())
        self.db.table("profiles").rows.append({
            "id": rm_id,
            "full_name": prof.get("full_name", "RM Person"),
            "email": prof.get("email", f"rm+{rm_id[:8]}@example.com"),
            "phone": prof.get("phone", "9876543210"),
            "is_active": is_active,
            "user_role": "relationship_manager",
            "avatar_url": None,
            "phone_verified": False,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        })
        self.db.table("rm_profiles").rows.append({
            "id": rm_id,
            "employee_id": prof.get("employee_id", "RM0001"),
            "performance_score": performance_score,
            "is_active": is_active,
            "assigned_territories": [],
            "manager_notes": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        })
        return rm_id

    def seed_vendor_request(self, rm_id, status="draft", **fields):
        row = {
            "id": fields.pop("id", str(uuid.uuid4())),
            "rm_id": rm_id,
            "status": status,
            "business_name": fields.pop("business_name", "Biz"),
            "created_at": datetime.utcnow().isoformat(),
        }
        row.update(fields)
        self.db.table("vendor_join_requests").rows.append(row)
        return row

    def seed_salon(self, rm_id, is_active=True):
        row = {"id": str(uuid.uuid4()), "assigned_rm": rm_id, "is_active": is_active,
               "created_at": datetime.utcnow().isoformat()}
        self.db.table("salons").rows.append(row)
        return row

    def seed_score(self, rm_id, points=10):
        self.db.table("rm_score_history").rows.append({
            "id": str(uuid.uuid4()), "rm_id": rm_id, "action": "x",
            "points": points, "description": "x", "created_at": datetime.utcnow().isoformat(),
        })

    def login_rm(self, rm_id):
        td = TokenData(user_id=rm_id, email="rm@example.com", user_role="relationship_manager",
                       jti="jti", exp=datetime.utcnow() + timedelta(hours=1))
        self.app.dependency_overrides[require_rm] = lambda: td
        return td

    def login_admin(self):
        td = TokenData(user_id="admin-1", email="admin@example.com", user_role="admin",
                       jti="jti", exp=datetime.utcnow() + timedelta(hours=1))
        self.app.dependency_overrides[require_admin] = lambda: td
        return td

    def logout(self):
        self.app.dependency_overrides.pop(require_rm, None)
        self.app.dependency_overrides.pop(require_admin, None)


@pytest.fixture()
def rm(app, monkeypatch):
    db = FakeSupabase()
    handle = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db

    async def _noop(*args, **kwargs):
        return True
    monkeypatch.setattr(ActivityLogService, "log", staticmethod(_noop))

    yield handle

    handle.logout()
    app.dependency_overrides.pop(get_db_client, None)


def _vr_payload(**over):
    body = {
        "business_name": "Test Salon",
        "business_type": "salon",
        "owner_name": "Owner Name",
        "owner_email": "owner@example.com",
        "owner_phone": "9876543210",
        "business_address": "123 Test Street, Test City",
        "city": "Testville",
        "state": "Test State",
        "pincode": "560001",
    }
    body.update(over)
    return body


# =====================================================================
# POST /rm/vendor-requests
# =====================================================================
def test_create_vendor_request_pending(rm):
    rm_id = rm.seed_rm(is_active=True)
    rm.login_rm(rm_id)

    r = rm.client.post(f"{RM}/vendor-requests", json=_vr_payload())
    assert r.status_code == 200, r.text
    rows = rm.db.table("vendor_join_requests").rows
    assert len(rows) == 1 and rows[0]["status"] == "pending"


def test_create_vendor_request_draft(rm):
    rm_id = rm.seed_rm(is_active=True)
    rm.login_rm(rm_id)

    r = rm.client.post(f"{RM}/vendor-requests?is_draft=true", json=_vr_payload())
    assert r.status_code == 200, r.text
    assert rm.db.table("vendor_join_requests").rows[0]["status"] == "draft"


def test_create_vendor_request_inactive_rm_403(rm):
    rm_id = rm.seed_rm(is_active=False)
    rm.login_rm(rm_id)

    r = rm.client.post(f"{RM}/vendor-requests", json=_vr_payload())
    assert r.status_code == 403, r.text


def test_create_vendor_request_no_rm_profile_404(rm):
    rm.login_rm(str(uuid.uuid4()))  # logged in but no rm_profiles row
    r = rm.client.post(f"{RM}/vendor-requests", json=_vr_payload())
    assert r.status_code == 404, r.text


def test_create_vendor_request_requires_auth(rm):
    r = rm.client.post(f"{RM}/vendor-requests", json=_vr_payload())
    assert r.status_code in (401, 403), r.text


# =====================================================================
# PUT /rm/vendor-requests/{id}
# =====================================================================
def test_update_draft_happy(rm):
    rm_id = rm.seed_rm()
    req = rm.seed_vendor_request(rm_id, status="draft")
    rm.login_rm(rm_id)

    r = rm.client.put(f"{RM}/vendor-requests/{req['id']}", json=_vr_payload(business_name="Updated"))
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "Draft updated successfully"


def test_update_submit_for_approval(rm):
    rm_id = rm.seed_rm()
    req = rm.seed_vendor_request(rm_id, status="draft")
    rm.login_rm(rm_id)

    r = rm.client.put(f"{RM}/vendor-requests/{req['id']}?submit_for_approval=true", json=_vr_payload())
    assert r.status_code == 200, r.text
    assert rm.db.table("vendor_join_requests").rows[0]["status"] == "pending"


def test_update_non_draft_rejected_400(rm):
    rm_id = rm.seed_rm()
    req = rm.seed_vendor_request(rm_id, status="approved")
    rm.login_rm(rm_id)

    r = rm.client.put(f"{RM}/vendor-requests/{req['id']}", json=_vr_payload())
    assert r.status_code == 400, r.text


def test_update_not_owned_404(rm):
    rm_id = rm.seed_rm()
    other = rm.seed_vendor_request(str(uuid.uuid4()), status="draft")
    rm.login_rm(rm_id)

    r = rm.client.put(f"{RM}/vendor-requests/{other['id']}", json=_vr_payload())
    assert r.status_code == 404, r.text


# =====================================================================
# DELETE /rm/vendor-requests/{id}
# =====================================================================
def test_delete_draft_happy(rm):
    rm_id = rm.seed_rm()
    req = rm.seed_vendor_request(rm_id, status="draft")
    rm.login_rm(rm_id)

    r = rm.client.delete(f"{RM}/vendor-requests/{req['id']}")
    assert r.status_code == 200, r.text
    assert rm.db.table("vendor_join_requests").rows == []


def test_delete_non_draft_400(rm):
    rm_id = rm.seed_rm()
    req = rm.seed_vendor_request(rm_id, status="pending")
    rm.login_rm(rm_id)

    r = rm.client.delete(f"{RM}/vendor-requests/{req['id']}")
    assert r.status_code == 400, r.text


def test_delete_not_found_404(rm):
    rm_id = rm.seed_rm()
    rm.login_rm(rm_id)
    r = rm.client.delete(f"{RM}/vendor-requests/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


def test_delete_draft_cleans_up_cloudinary_images(rm, monkeypatch):
    # Regression: cleanup used to call Supabase Storage on a Cloudinary URL
    # (silent no-op, false "Deleted N images" log) instead of Cloudinary itself.
    rm_id = rm.seed_rm()
    req = rm.seed_vendor_request(
        rm_id, status="draft",
        cover_image_url="https://res.cloudinary.com/demo/image/upload/salon-images/vendor/cover.jpg",
        gallery_images=["https://res.cloudinary.com/demo/image/upload/salon-images/vendor/g1.jpg"],
    )
    rm.login_rm(rm_id)

    deleted_urls = []
    monkeypatch.setattr(
        CloudinaryService, "delete_file",
        lambda self, url: deleted_urls.append(url) or True,
    )

    r = rm.client.delete(f"{RM}/vendor-requests/{req['id']}")
    assert r.status_code == 200, r.text
    assert set(deleted_urls) == {req["cover_image_url"], *req["gallery_images"]}


# =====================================================================
# GET /rm/vendor-requests (+ {id})
# =====================================================================
def test_list_own_requests_with_status_filter(rm):
    rm_id = rm.seed_rm()
    rm.seed_vendor_request(rm_id, status="draft")
    rm.seed_vendor_request(rm_id, status="pending")
    rm.login_rm(rm_id)

    r = rm.client.get(f"{RM}/vendor-requests", params={"status_filter": "pending"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1
    assert body["data"][0]["status"] == "pending"


def test_get_request_by_id_not_found_404(rm):
    rm_id = rm.seed_rm()
    rm.login_rm(rm_id)
    r = rm.client.get(f"{RM}/vendor-requests/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


# =====================================================================
# GET /rm/salons
# =====================================================================
def test_get_rm_salons(rm):
    rm_id = rm.seed_rm()
    rm.seed_salon(rm_id, is_active=True)
    rm.seed_salon(rm_id, is_active=False)  # excluded by default
    rm.login_rm(rm_id)

    r = rm.client.get(f"{RM}/salons")
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 1


# =====================================================================
# PUT /rm/profile
# =====================================================================
def test_update_own_profile_happy(rm):
    rm_id = rm.seed_rm(full_name="Old")
    rm.login_rm(rm_id)

    r = rm.client.put(f"{RM}/profile", json={"full_name": "New Name"})
    assert r.status_code == 200, r.text
    assert rm.db.table("profiles").rows[0]["full_name"] == "New Name"


def test_update_own_profile_no_valid_fields_400(rm):
    rm_id = rm.seed_rm()
    rm.login_rm(rm_id)
    # address is no longer an allowed self-update field -> filtered out -> 400
    r = rm.client.put(f"{RM}/profile", json={"address": "1 St"})
    assert r.status_code == 400, r.text


# =====================================================================
# GET /rm/score-history & /rm/dashboard
# =====================================================================
def test_score_history(rm):
    rm_id = rm.seed_rm()
    rm.seed_score(rm_id, points=10)
    rm.seed_score(rm_id, points=5)
    rm.login_rm(rm_id)

    r = rm.client.get(f"{RM}/score-history")
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2


def test_dashboard(rm):
    rm_id = rm.seed_rm(performance_score=42)
    rm.seed_vendor_request(rm_id, status="pending")
    rm.seed_vendor_request(rm_id, status="approved")
    rm.seed_vendor_request(rm_id, status="rejected")
    rm.seed_salon(rm_id, is_active=True)
    rm.seed_score(rm_id)
    rm.login_rm(rm_id)

    r = rm.client.get(f"{RM}/dashboard")
    assert r.status_code == 200, r.text
    stats = r.json()["statistics"]
    assert stats["total_score"] == 42
    assert stats["pending_requests"] == 1
    assert stats["approved_requests"] == 1
    assert stats["rejected_requests"] == 1
    assert stats["active_salons"] == 1
    assert stats["total_salons_added"] == 3   # total requests


# =====================================================================
# GET /rm/leaderboard  (public, NO email)
# =====================================================================
def test_leaderboard_public_no_email(rm):
    a = rm.seed_rm(performance_score=100, full_name="Top RM", email="top@example.com")
    rm.seed_rm(performance_score=50, full_name="Second RM")
    # no login -> public endpoint

    r = rm.client.get(f"{RM}/leaderboard")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    top = body["data"][0]
    assert top["rank"] == 1
    assert top["profiles"]["full_name"] == "Top RM"
    assert "email" not in top["profiles"]   # PII dropped


# =====================================================================
# Regression: orphan GET /rm/profile removed (PUT still exists -> 405)
# =====================================================================
def test_removed_rm_profile_get_is_405(rm):
    rm_id = rm.seed_rm()
    rm.login_rm(rm_id)
    r = rm.client.get(f"{RM}/profile")
    assert r.status_code == 405, r.text


# =====================================================================
# GET /admin/rms
# =====================================================================
def test_admin_list_rms(rm):
    rm.seed_rm()
    rm.seed_rm()
    rm.login_admin()

    r = rm.client.get(ADMIN_RMS)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2


def test_admin_list_rms_is_active_filter(rm):
    rm.seed_rm(is_active=True)
    rm.seed_rm(is_active=False)
    rm.login_admin()

    r = rm.client.get(ADMIN_RMS, params={"is_active": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 1   # filtered at DB level before pagination


def test_admin_list_requires_admin(rm):
    r = rm.client.get(ADMIN_RMS)
    assert r.status_code in (401, 403), r.text


# =====================================================================
# PUT /admin/rms/{id}
# =====================================================================
def test_admin_update_rm_happy(rm):
    rm_id = rm.seed_rm(full_name="Old")
    rm.login_admin()

    r = rm.client.put(f"{ADMIN_RMS}/{rm_id}", json={"full_name": "New", "manager_notes": "note"})
    assert r.status_code == 200, r.text
    assert rm.db.table("profiles").rows[0]["full_name"] == "New"
    assert rm.db.table("rm_profiles").rows[0]["manager_notes"] == "note"


def test_admin_update_rm_employee_id_ignored(rm):
    rm_id = rm.seed_rm(employee_id="RM0001")
    rm.login_admin()

    r = rm.client.put(f"{ADMIN_RMS}/{rm_id}", json={"full_name": "New Name", "employee_id": "RM9999"})
    assert r.status_code == 200, r.text
    assert rm.db.table("rm_profiles").rows[0]["employee_id"] == "RM0001"   # unchanged


def test_admin_update_rm_not_found_404(rm):
    rm.login_admin()
    r = rm.client.put(f"{ADMIN_RMS}/{uuid.uuid4()}", json={"full_name": "New Name"})
    assert r.status_code == 404, r.text


def test_admin_update_rm_no_valid_fields_400(rm):
    rm_id = rm.seed_rm()
    rm.login_admin()
    r = rm.client.put(f"{ADMIN_RMS}/{rm_id}", json={})
    assert r.status_code == 400, r.text


def test_admin_update_rm_requires_admin(rm):
    r = rm.client.put(f"{ADMIN_RMS}/{uuid.uuid4()}", json={"full_name": "X"})
    assert r.status_code in (401, 403), r.text


# =====================================================================
# Regression: orphan admin GETs removed
# =====================================================================
def test_removed_admin_get_by_id_is_405(rm):
    # PUT /admin/rms/{id} still exists -> GET on same path is 405
    rm.login_admin()
    r = rm.client.get(f"{ADMIN_RMS}/{uuid.uuid4()}")
    assert r.status_code == 405, r.text


def test_removed_admin_score_history_is_404(rm):
    rm.login_admin()
    r = rm.client.get(f"{ADMIN_RMS}/{uuid.uuid4()}/score-history")
    assert r.status_code == 404, r.text
