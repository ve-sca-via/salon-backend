"""
Mocked route tests for the partner ("Partner with us") module
(app/api/partner.py + app/services/partner_service.py).

These run WITHOUT a real Supabase stack. The Supabase DB client is replaced
with a small in-memory fake (the same builder stand-in used by the career
tests, including `.ilike()` for the admin search) and ActivityLogger is
stubbed so nothing leaves the process. They exercise the full HTTP path:

    HTTP -> FastAPI (auth dep overridden) -> route -> PartnerService ->
    FakeSupabase

Scope: the public apply flow the marketing site uses, plus the admin
list/detail/update flows (happy path + key error cases).

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.services.partner_service as partner_module
from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import require_admin, TokenData
from app.services.partner_service import PartnerService

API = settings.API_PREFIX
PARTNERS = f"{API}/partners"


# =====================================================================
# In-memory fake Supabase client (covers the ops partner_service uses)
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
        self._order = []
        self._range = None
        self._count = None

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

    def seed_request(self, **fields):
        req_id = fields.pop("id", str(uuid.uuid4()))
        row = {
            "id": req_id,
            "owner_name": "Jane Owner",
            "shop_name": "Glow Salon",
            "shop_type": "Salon",
            "email": "jane@example.com",
            "phone": "9876543210",
            "location": "Bengaluru",
            "status": "new",
            "created_at": datetime.utcnow().isoformat(),
        }
        row.update(fields)
        self.db.table("partner_requests").rows.append(row)
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
        return PartnerService(db_client=self.db)


@pytest.fixture()
def pr(app, monkeypatch):
    db = FakeSupabase()
    handle = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db

    async def _noop(*args, **kwargs):
        return True

    monkeypatch.setattr(partner_module.ActivityLogger, "log", staticmethod(_noop))

    yield handle

    handle.logout()
    app.dependency_overrides.pop(get_db_client, None)


def _payload(**over):
    data = {
        "owner_name": "John Owner",
        "shop_name": "Sharp Cuts",
        "shop_type": "Salon",
        "email": "john@example.com",
        "phone": "9876543210",
        "location": "Mumbai, Andheri West",
    }
    data.update(over)
    return data


# =====================================================================
# POST /partners/apply  (public — the marketing site flow)
# =====================================================================
def test_apply_happy(pr):
    r = pr.client.post(f"{PARTNERS}/apply", json=_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"]
    assert "contact you" in body["message"].lower()
    rows = pr.db.table("partner_requests").rows
    assert len(rows) == 1
    saved = rows[0]
    assert saved["status"] == "new"
    assert saved["owner_name"] == "John Owner"
    assert saved["shop_type"] == "Salon"


def test_apply_is_public_no_auth_required(pr):
    # No require_admin override, no bearer token -> still succeeds.
    r = pr.client.post(f"{PARTNERS}/apply", json=_payload())
    assert r.status_code == 200, r.text


def test_apply_invalid_email_is_422(pr):
    r = pr.client.post(f"{PARTNERS}/apply", json=_payload(email="not-an-email"))
    assert r.status_code == 422, r.text


def test_apply_invalid_shop_type_is_422(pr):
    # shop_type is a Literal -> must be one of the allowed values.
    r = pr.client.post(f"{PARTNERS}/apply", json=_payload(shop_type="Barbershop"))
    assert r.status_code == 422, r.text


def test_apply_missing_required_field_is_422(pr):
    body = _payload()
    del body["owner_name"]
    r = pr.client.post(f"{PARTNERS}/apply", json=body)
    assert r.status_code == 422, r.text


def test_apply_blank_owner_name_is_422(pr):
    # field_validator strips and rejects whitespace-only values.
    r = pr.client.post(f"{PARTNERS}/apply", json=_payload(owner_name="   "))
    assert r.status_code == 422, r.text


def test_apply_trims_whitespace(pr):
    r = pr.client.post(f"{PARTNERS}/apply", json=_payload(shop_name="  Trimmed Shop  "))
    assert r.status_code == 200, r.text
    assert pr.db.table("partner_requests").rows[0]["shop_name"] == "Trimmed Shop"


# =====================================================================
# GET /partners/requests  (admin list)
# =====================================================================
def test_list_happy(pr):
    pr.seed_request(owner_name="Alice")
    pr.seed_request(owner_name="Bob")
    pr.login_admin()

    r = pr.client.get(f"{PARTNERS}/requests")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["count"] == 2
    assert len(body["requests"]) == 2


def test_list_status_filter(pr):
    pr.seed_request(status="new")
    pr.seed_request(status="approved")
    pr.login_admin()

    r = pr.client.get(f"{PARTNERS}/requests", params={"status": "approved"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert all(x["status"] == "approved" for x in body["requests"])


def test_list_shop_type_filter(pr):
    pr.seed_request(shop_type="Salon")
    pr.seed_request(shop_type="Spa")
    pr.login_admin()

    r = pr.client.get(f"{PARTNERS}/requests", params={"shop_type": "Spa"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["requests"][0]["shop_type"] == "Spa"


def test_list_search_by_shop_name(pr):
    pr.seed_request(shop_name="Priya Beauty", owner_name="Priya")
    pr.seed_request(shop_name="Rahul Spa", owner_name="Rahul")
    pr.login_admin()

    r = pr.client.get(f"{PARTNERS}/requests", params={"search": "priya"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["requests"][0]["shop_name"] == "Priya Beauty"


def test_list_search_no_match_returns_empty(pr):
    pr.seed_request(owner_name="Alice")
    pr.login_admin()

    r = pr.client.get(f"{PARTNERS}/requests", params={"search": "zzzznomatch"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 0
    assert body["requests"] == []


def test_list_pagination(pr):
    for i in range(25):
        pr.seed_request(owner_name=f"Owner {i:02d}",
                        created_at=f"2026-06-01T00:{i:02d}:00")
    pr.login_admin()

    r = pr.client.get(f"{PARTNERS}/requests", params={"skip": 10, "limit": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 25
    assert body["count"] == 10
    assert len(body["requests"]) == 10


def test_list_requires_admin(pr):
    r = pr.client.get(f"{PARTNERS}/requests")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# GET /partners/requests/{id}  (admin detail)
# =====================================================================
def test_get_one_happy(pr):
    row = pr.seed_request(shop_name="Detail Shop")
    pr.login_admin()

    r = pr.client.get(f"{PARTNERS}/requests/{row['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["shop_name"] == "Detail Shop"


def test_get_one_not_found(pr):
    pr.login_admin()
    r = pr.client.get(f"{PARTNERS}/requests/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


def test_get_one_requires_admin(pr):
    row = pr.seed_request()
    r = pr.client.get(f"{PARTNERS}/requests/{row['id']}")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# PATCH /partners/requests/{id}  (admin status update)
# =====================================================================
def test_update_status_happy(pr):
    row = pr.seed_request(status="new")
    pr.login_admin()

    r = pr.client.patch(
        f"{PARTNERS}/requests/{row['id']}",
        json={"status": "contacted", "admin_notes": "called the owner"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["message"] == "Partner request updated successfully"
    assert body["request"]["status"] == "contacted"
    assert body["request"]["admin_notes"] == "called the owner"
    assert pr.db.table("partner_requests").rows[0]["status"] == "contacted"


def test_update_status_invalid_value_is_422(pr):
    row = pr.seed_request()
    pr.login_admin()
    r = pr.client.patch(
        f"{PARTNERS}/requests/{row['id']}",
        json={"status": "not_a_real_status"},
    )
    assert r.status_code == 422, r.text


def test_update_status_not_found(pr):
    pr.login_admin()
    r = pr.client.patch(
        f"{PARTNERS}/requests/{uuid.uuid4()}",
        json={"status": "approved"},
    )
    assert r.status_code == 404, r.text


def test_update_status_requires_admin(pr):
    row = pr.seed_request()
    r = pr.client.patch(
        f"{PARTNERS}/requests/{row['id']}",
        json={"status": "approved"},
    )
    assert r.status_code in (401, 403), r.text


def test_update_service_rejects_bad_status_directly(pr):
    # Service guard (VALID_STATUSES, derived from the schema Literal) raises 400
    # if ever handed a bad status outside the route's Literal validation.
    import asyncio
    from fastapi import HTTPException
    row = pr.seed_request()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(pr.service().update_request_status(
            request_id=row["id"], new_status="bogus",
        ))
    assert exc.value.status_code == 400
