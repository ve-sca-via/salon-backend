"""
Mocked route tests for the career_service module (app/api/careers.py +
app/services/career_service.py).

These run WITHOUT a real Supabase stack or a Cloudinary account. The Supabase DB
client is replaced with a small in-memory fake (the same supabase-py builder
stand-in used by the booking tests, extended with `.ilike()` for the admin
search), CloudinaryService's network methods are monkeypatched, and the email
singleton + ActivityLogger are stubbed so nothing leaves the process. They
exercise the full HTTP path:

    HTTP -> FastAPI (auth dep overridden, rate limiter disabled) -> route ->
    CareerService -> FakeSupabase / CloudinaryService (faked).

Scope: every endpoint the module still exposes after the P1/P2 cleanup
(happy path + key error cases), the public apply flow the marketing site uses,
the admin list/detail/update/download flows, and regressions for the endpoint
removed in this cleanup.

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.services.career_service as career_module
from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import require_admin, TokenData
from app.services.career_service import CareerService
from app.services.cloudinary_service import CloudinaryService

API = settings.API_PREFIX
CAREERS = f"{API}/careers"


# =====================================================================
# In-memory fake Supabase client (covers the ops career_service uses)
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

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def ilike(self, col, pattern):
        self._filters.append(("ilike", col, pattern))
        return self

    def order(self, col, desc=False):
        self._order.append((col, desc))
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def _match(self, row):
        for op, c, v in self._filters:
            rv = row.get(c)
            if op == "eq" and rv != v:
                return False
            if op == "in" and rv not in v:
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


# =====================================================================
# Test handle + fixture
# =====================================================================
class Handle:
    def __init__(self, db, app):
        self.db = db
        self.app = app
        self.client = TestClient(app)
        self.cloudinary_should_fail = False
        self.last_upload = None
        self.last_signed_input = None

    def seed_application(self, **fields):
        app_id = fields.pop("id", str(uuid.uuid4()))
        row = {
            "id": app_id,
            "application_number": f"CA-20260112-{app_id[:8].upper()}",
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "9876543210",
            "position": "Relationship Manager",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }
        row.update(fields)
        self.db.table("career_applications").rows.append(row)
        return row

    def login_admin(self, user_id="admin-1"):
        td = TokenData(
            user_id=user_id, email="admin@example.com", user_role="admin",
            jti="jti-test", exp=datetime.utcnow() + timedelta(hours=1),
        )
        self.app.dependency_overrides[require_admin] = lambda: td
        return td

    def logout(self):
        self.app.dependency_overrides.pop(require_admin, None)

    def service(self):
        return CareerService(db_client=self.db)


@pytest.fixture()
def cr(app, monkeypatch):
    db = FakeSupabase()
    handle = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db

    # --- Cloudinary: replace network methods with in-process fakes ---
    async def _upload(self, file, folder, custom_filename=None):
        if handle.cloudinary_should_fail:
            raise Exception("cloudinary boom")
        await file.read()  # mirror real read of the UploadFile
        handle.last_upload = {"folder": folder, "filename": custom_filename}
        return f"https://res.cloudinary.com/demo/image/private/{folder}/{custom_filename}"

    def _signed(self, db_url, expires_in=None):
        handle.last_signed_input = db_url
        return f"https://res.cloudinary.com/demo/signed/{db_url.rsplit('/', 1)[-1]}?sig=xyz"

    monkeypatch.setattr(CloudinaryService, "upload_file", _upload)
    monkeypatch.setattr(CloudinaryService, "generate_download_url", _signed)

    # --- Email + activity log: stub so nothing touches the network ---
    async def _noop(*args, **kwargs):
        return True

    monkeypatch.setattr(career_module.email_service,
                        "send_career_application_confirmation", _noop, raising=False)
    monkeypatch.setattr(career_module.email_service,
                        "send_new_career_application_notification", _noop, raising=False)
    monkeypatch.setattr(career_module.ActivityLogger, "log", staticmethod(_noop))

    yield handle

    handle.logout()
    app.dependency_overrides.pop(get_db_client, None)


def _docs(resume="resume.pdf", aadhaar="aadhaar.jpg", photo="photo.jpg"):
    files = {}
    if resume is not None:
        files["resume"] = (resume, b"%PDF-1.4 fake", "application/pdf")
    if aadhaar is not None:
        files["aadhaar_card"] = (aadhaar, b"imgbytes", "image/jpeg")
    if photo is not None:
        files["photo"] = (photo, b"imgbytes", "image/jpeg")
    return files


def _form(**over):
    data = {
        "full_name": "John Applicant",
        "email": "john@example.com",
        "phone": "9876543210",
        "age": "28",
        "permanent_address": "1 Test Street",
        "current_address": "2 Test Avenue",
        "position": "Relationship Manager",
        "experience_years": "3",
        "highest_qualification": "Bachelor's Degree",
        "cover_letter": "I would love to join.",
    }
    data.update(over)
    return data


# =====================================================================
# POST /careers/apply  (public — the marketing site flow)
# =====================================================================
def test_apply_happy(cr):
    r = cr.client.post(f"{CAREERS}/apply", data=_form(), files=_docs())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["application_number"].startswith("CA-")
    assert body["email_sent"] is True
    assert "warning" not in body or body["warning"] is None
    # Row persisted with only the columns that still exist in the DB.
    rows = cr.db.table("career_applications").rows
    assert len(rows) == 1
    saved = rows[0]
    assert saved["status"] == "pending"
    assert saved["resume_url"].startswith("https://res.cloudinary.com")
    assert saved["aadhaar_url"]
    assert saved["photo_url"]


def test_apply_is_public_no_auth_required(cr):
    # No require_admin override and no bearer token -> still succeeds.
    r = cr.client.post(f"{CAREERS}/apply", data=_form(), files=_docs())
    assert r.status_code == 200, r.text


def test_apply_missing_required_file_is_422(cr):
    # 'photo' is a required File(...) -> FastAPI rejects before the service runs.
    r = cr.client.post(f"{CAREERS}/apply", data=_form(), files=_docs(photo=None))
    assert r.status_code == 422, r.text


def test_apply_invalid_email_is_422(cr):
    # EmailStr at the route boundary rejects malformed addresses.
    r = cr.client.post(f"{CAREERS}/apply", data=_form(email="not-an-email"), files=_docs())
    assert r.status_code == 422, r.text


def test_apply_file_without_extension_is_400(cr):
    # Service-layer _get_file_extension rejects a filename with no extension.
    r = cr.client.post(f"{CAREERS}/apply", data=_form(), files=_docs(resume="resume"))
    assert r.status_code == 400, r.text


def test_apply_experience_out_of_range_is_422(cr):
    # Form(ge=0, le=50) bound on experience_years.
    r = cr.client.post(f"{CAREERS}/apply", data=_form(experience_years="99"), files=_docs())
    assert r.status_code == 422, r.text


def test_apply_email_failure_still_succeeds_with_warning(cr, monkeypatch):
    async def _boom(*args, **kwargs):
        raise Exception("smtp down")
    monkeypatch.setattr(career_module.email_service,
                        "send_career_application_confirmation", _boom, raising=False)

    r = cr.client.post(f"{CAREERS}/apply", data=_form(), files=_docs())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email_sent"] is False
    assert body["warning"]


# =====================================================================
# GET /careers/applications  (admin list)
# =====================================================================
def test_list_happy(cr):
    cr.seed_application(full_name="Alice")
    cr.seed_application(full_name="Bob")
    cr.login_admin()

    r = cr.client.get(f"{CAREERS}/applications")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["count"] == 2
    assert len(body["applications"]) == 2


def test_list_status_filter(cr):
    cr.seed_application(status="pending")
    cr.seed_application(status="shortlisted")
    cr.login_admin()

    r = cr.client.get(f"{CAREERS}/applications", params={"status": "shortlisted"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert all(a["status"] == "shortlisted" for a in body["applications"])


def test_list_search_by_name(cr):
    cr.seed_application(full_name="Priya Sharma", email="priya@x.com")
    cr.seed_application(full_name="Rahul Verma", email="rahul@x.com")
    cr.login_admin()

    r = cr.client.get(f"{CAREERS}/applications", params={"search": "priya"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["applications"][0]["full_name"] == "Priya Sharma"


def test_list_search_no_match_returns_empty(cr):
    cr.seed_application(full_name="Alice")
    cr.login_admin()

    r = cr.client.get(f"{CAREERS}/applications", params={"search": "zzzznomatch"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 0
    assert body["applications"] == []


def test_list_pagination(cr):
    for i in range(25):
        cr.seed_application(full_name=f"Cand {i:02d}",
                            created_at=f"2026-06-01T00:{i:02d}:00")
    cr.login_admin()

    r = cr.client.get(f"{CAREERS}/applications", params={"skip": 10, "limit": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 25       # exact total, not page length
    assert body["count"] == 10       # this page
    assert len(body["applications"]) == 10


def test_list_requires_admin(cr):
    # No override -> real require_admin runs -> no bearer -> 401/403.
    r = cr.client.get(f"{CAREERS}/applications")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# GET /careers/applications/{id}  (admin detail)
# =====================================================================
def test_get_one_happy(cr):
    app_row = cr.seed_application(full_name="Detail Person")
    cr.login_admin()

    r = cr.client.get(f"{CAREERS}/applications/{app_row['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Detail Person"


def test_get_one_not_found(cr):
    cr.login_admin()
    r = cr.client.get(f"{CAREERS}/applications/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


def test_get_one_requires_admin(cr):
    app_row = cr.seed_application()
    r = cr.client.get(f"{CAREERS}/applications/{app_row['id']}")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# PATCH /careers/applications/{id}  (admin status update)
# =====================================================================
def test_update_status_happy(cr):
    app_row = cr.seed_application(status="pending")
    cr.login_admin()

    r = cr.client.patch(
        f"{CAREERS}/applications/{app_row['id']}",
        json={"status": "shortlisted", "admin_notes": "strong candidate"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["message"] == "Application updated successfully"
    assert body["application"]["status"] == "shortlisted"
    assert body["application"]["admin_notes"] == "strong candidate"
    # Persisted.
    assert cr.db.table("career_applications").rows[0]["status"] == "shortlisted"


def test_update_status_invalid_value_is_422(cr):
    app_row = cr.seed_application()
    cr.login_admin()
    r = cr.client.patch(
        f"{CAREERS}/applications/{app_row['id']}",
        json={"status": "not_a_real_status"},
    )
    assert r.status_code == 422, r.text  # Literal validation at the route


def test_update_status_not_found(cr):
    cr.login_admin()
    r = cr.client.patch(
        f"{CAREERS}/applications/{uuid.uuid4()}",
        json={"status": "hired"},
    )
    assert r.status_code == 404, r.text


def test_update_status_requires_admin(cr):
    app_row = cr.seed_application()
    r = cr.client.patch(
        f"{CAREERS}/applications/{app_row['id']}",
        json={"status": "hired"},
    )
    assert r.status_code in (401, 403), r.text


def test_update_service_rejects_bad_status_directly(cr):
    # The service guard (VALID_STATUSES, derived from the schema Literal) raises
    # 400 if ever handed a bad status outside the route's Literal validation.
    import asyncio
    from fastapi import HTTPException
    app_row = cr.seed_application()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(cr.service().update_application_status(
            application_id=app_row["id"], new_status="bogus",
        ))
    assert exc.value.status_code == 400


# =====================================================================
# GET /careers/applications/{id}/download/{document_type}  (admin)
# =====================================================================
def test_download_happy_signs_cloudinary_url(cr):
    cloud_url = "https://res.cloudinary.com/demo/image/private/applications/x/resume.pdf"
    app_row = cr.seed_application(resume_url=cloud_url)
    cr.login_admin()

    r = cr.client.get(f"{CAREERS}/applications/{app_row['id']}/download/resume")
    assert r.status_code == 200, r.text
    assert "res.cloudinary.com/demo/signed" in r.json()["download_url"]
    assert cr.last_signed_input == cloud_url


def test_download_aadhaar_uses_mapped_column(cr):
    # 'aadhaar_card' must resolve to the aadhaar_url column, not aadhaar_card_url.
    cloud_url = "https://res.cloudinary.com/demo/image/private/applications/x/aadhaar.jpg"
    app_row = cr.seed_application(aadhaar_url=cloud_url)
    cr.login_admin()

    r = cr.client.get(f"{CAREERS}/applications/{app_row['id']}/download/aadhaar_card")
    assert r.status_code == 200, r.text
    assert cr.last_signed_input == cloud_url


def test_download_legacy_non_cloudinary_url_passthrough(cr):
    legacy = "https://old.storage.example/applications/x/resume.pdf"
    app_row = cr.seed_application(resume_url=legacy)
    cr.login_admin()

    r = cr.client.get(f"{CAREERS}/applications/{app_row['id']}/download/resume")
    assert r.status_code == 200, r.text
    assert r.json()["download_url"] == legacy   # returned as-is, not signed
    assert cr.last_signed_input is None


def test_download_missing_document_is_404(cr):
    app_row = cr.seed_application()  # no photo_url
    cr.login_admin()
    r = cr.client.get(f"{CAREERS}/applications/{app_row['id']}/download/photo")
    assert r.status_code == 404, r.text


def test_download_requires_admin(cr):
    app_row = cr.seed_application(resume_url="https://res.cloudinary.com/x/resume.pdf")
    r = cr.client.get(f"{CAREERS}/applications/{app_row['id']}/download/resume")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# Regression: the by-number endpoint removed in P1 cleanup must be gone
# =====================================================================
def test_removed_by_number_endpoint_is_gone(cr):
    cr.login_admin()
    r = cr.client.get(f"{CAREERS}/applications/by-number/CA-20260112-A1B2C3D4")
    assert r.status_code == 404, r.text
