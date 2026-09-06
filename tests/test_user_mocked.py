"""
Mocked route tests for the user_service module (app/api/admin/users.py +
app/services/user_service.py).

These run WITHOUT a real Supabase stack. The DB client is an in-memory fake that
also exposes the GoTrue admin auth API (auth.admin.create_user / delete_user)
the refactored UserService now uses. ActivityLogger is stubbed. They exercise the
full HTTP path:

    HTTP -> FastAPI (require_admin overridden, rate limiter disabled) -> route ->
    UserService -> FakeSupabase (tables + auth.admin).

Scope: every admin user endpoint (happy path + key error cases), including the
cleanup applied this module — the role field is no longer accepted on update, and
the routes now translate the service's ValueErrors into 404/400 instead of 500.

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import uuid
from types import SimpleNamespace
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import require_admin, TokenData
from app.services.activity_log_service import ActivityLogger

API = settings.API_PREFIX
USERS = f"{API}/admin/users"


# =====================================================================
# In-memory fake Supabase client (tables + auth.admin)
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
        self._count = None
        self._order = []
        self._range = None
        self._negate_is = False

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

    @property
    def not_(self):
        self._negate_is = True
        return self

    def is_(self, col, val):
        op = "isnotnull" if self._negate_is else "isnull"
        self._negate_is = False
        self._filters.append((op, col, None))
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
            if op == "isnull" and rv is not None:
                return False
            if op == "isnotnull" and rv is None:
                return False
        return True

    def execute(self):
        op, payload = self._op
        rows = self._table.rows

        if op == "select":
            matched = [dict(r) for r in rows if self._match(r)]
            total = len(matched)
            for col, desc in reversed(self._order):
                matched.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
            if self._range is not None:
                s, e = self._range
                matched = matched[s:e]
            count = total if self._count == "exact" else None
            return _Resp(matched, count=count)

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


class _FakeAuthAdmin:
    def __init__(self, db):
        self._db = db
        self.created = []
        self.deleted = []
        self.next_id = None
        self.raise_on_create = False

    def create_user(self, payload):
        if self.raise_on_create:
            raise Exception("gotrue boom")
        uid = self.next_id or str(uuid.uuid4())
        self.next_id = None
        self.created.append({"id": uid, **payload})
        return SimpleNamespace(user=SimpleNamespace(id=uid))

    def delete_user(self, uid):
        self.deleted.append(uid)
        # Simulate the profiles.id -> auth.users.id CASCADE delete.
        prof = self._db.table("profiles")
        prof.rows[:] = [r for r in prof.rows if r.get("id") != uid]


class FakeSupabase:
    def __init__(self):
        self._tables = {}
        self.auth = SimpleNamespace(admin=_FakeAuthAdmin(self))

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

    def seed_profile(self, user_id=None, role="customer", email=None, **fields):
        uid = user_id or str(uuid.uuid4())
        row = {
            "id": uid,
            "email": email or f"user+{uid[:8]}@example.com",
            "full_name": "Test User",
            "phone": "9876543210",
            "user_role": role,
            "is_active": True,
            # NOT NULL DEFAULT false in the schema, so every real row has it.
            # The admin users list filters staff out with .eq("is_internal", False).
            "is_internal": False,
            "created_at": datetime.utcnow().isoformat(),
        }
        row.update(fields)
        self.db.table("profiles").rows.append(row)
        return row

    def seed_rm_profile(self, user_id, **fields):
        row = {"id": user_id, "employee_id": "RM0001", "is_active": True}
        row.update(fields)
        self.db.table("rm_profiles").rows.append(row)
        return row

    def login_admin(self):
        td = TokenData(user_id="admin-1", email="admin@example.com", user_role="admin",
                       jti="jti", exp=datetime.utcnow() + timedelta(hours=1))
        self.app.dependency_overrides[require_admin] = lambda: td
        return td

    def logout(self):
        self.app.dependency_overrides.pop(require_admin, None)


@pytest.fixture()
def us(app, monkeypatch):
    db = FakeSupabase()
    handle = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db

    async def _noop(*args, **kwargs):
        return True
    monkeypatch.setattr(ActivityLogger, "user_created", staticmethod(_noop), raising=False)

    yield handle

    handle.logout()
    app.dependency_overrides.pop(get_db_client, None)


def _create_body(**over):
    body = {
        "email": f"new+{uuid.uuid4().hex[:8]}@example.com",
        "full_name": "New User",
        "password": "StrongPass123",
        "role": "customer",
        "phone": "9876543210",
        "age": 30,
        "gender": "male",
    }
    body.update(over)
    return body


# =====================================================================
# POST /admin/users/  (create)
# =====================================================================
def test_create_customer_happy(us):
    us.login_admin()
    body = _create_body(role="customer")

    r = us.client.post(f"{USERS}/", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["success"] is True
    assert data["data"]["role"] == "customer"
    # Auth user + profile created
    assert len(us.db.auth.admin.created) == 1
    profiles = us.db.table("profiles").rows
    assert len(profiles) == 1 and profiles[0]["email"] == body["email"]


def test_create_rm_generates_employee_id(us):
    us.login_admin()
    r = us.client.post(f"{USERS}/", json=_create_body(role="relationship_manager"))
    assert r.status_code == 200, r.text
    rms = us.db.table("rm_profiles").rows
    assert len(rms) == 1
    assert rms[0]["employee_id"] == "RM0001"


def test_create_duplicate_email_is_400(us):
    us.login_admin()
    us.seed_profile(email="dupe@example.com")
    r = us.client.post(f"{USERS}/", json=_create_body(email="dupe@example.com"))
    assert r.status_code == 400, r.text
    assert "already exists" in r.text.lower()


def test_create_invalid_role_is_400(us):
    us.login_admin()
    r = us.client.post(f"{USERS}/", json=_create_body(role="vendor"))
    assert r.status_code == 400, r.text


def test_create_underage_is_422(us):
    us.login_admin()
    r = us.client.post(f"{USERS}/", json=_create_body(age=15))
    assert r.status_code == 422, r.text   # schema ge=18


def test_create_requires_admin(us):
    r = us.client.post(f"{USERS}/", json=_create_body())
    assert r.status_code in (401, 403), r.text


# =====================================================================
# PUT /admin/users/{id}  (update)
# =====================================================================
def test_update_happy(us):
    user = us.seed_profile(role="customer", full_name="Old")
    us.login_admin()

    r = us.client.put(f"{USERS}/{user['id']}", json={"full_name": "New Name"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["full_name"] == "New Name"
    assert us.db.table("profiles").rows[0]["full_name"] == "New Name"


def test_update_role_field_is_ignored(us):
    # `role` was dropped from UserUpdate; sending it is a 422 (extra fields are
    # allowed by default, but pydantic ignores -> let's assert role is unchanged).
    user = us.seed_profile(role="customer")
    us.login_admin()

    r = us.client.put(f"{USERS}/{user['id']}", json={"full_name": "X", "role": "admin"})
    assert r.status_code == 200, r.text
    assert us.db.table("profiles").rows[0]["user_role"] == "customer"   # not promoted


def test_update_deactivating_rm_also_deactivates_rm_profile(us):
    user = us.seed_profile(role="relationship_manager")
    us.seed_rm_profile(user["id"], is_active=True)
    us.login_admin()

    r = us.client.put(f"{USERS}/{user['id']}", json={"is_active": False})
    assert r.status_code == 200, r.text
    assert us.db.table("rm_profiles").rows[0]["is_active"] is False


def test_update_not_found_is_404(us):
    us.login_admin()
    r = us.client.put(f"{USERS}/{uuid.uuid4()}", json={"full_name": "X"})
    assert r.status_code == 404, r.text   # was 500 before the route fix


def test_update_admin_target_is_400(us):
    admin_user = us.seed_profile(role="admin")
    us.login_admin()
    r = us.client.put(f"{USERS}/{admin_user['id']}", json={"full_name": "X"})
    assert r.status_code == 400, r.text
    assert "admin" in r.text.lower()


def test_update_no_valid_fields_is_400(us):
    user = us.seed_profile(role="customer")
    us.login_admin()
    r = us.client.put(f"{USERS}/{user['id']}", json={})
    assert r.status_code == 400, r.text


def test_update_requires_admin(us):
    r = us.client.put(f"{USERS}/{uuid.uuid4()}", json={"full_name": "X"})
    assert r.status_code in (401, 403), r.text


# =====================================================================
# DELETE /admin/users/{id}
# =====================================================================
def test_delete_customer_happy(us):
    user = us.seed_profile(role="customer")
    us.login_admin()

    r = us.client.delete(f"{USERS}/{user['id']}")
    assert r.status_code == 200, r.text
    assert user["id"] in us.db.auth.admin.deleted
    assert us.db.table("profiles").rows == []   # CASCADE-removed via fake auth


def test_delete_rm_removes_rm_profile(us):
    user = us.seed_profile(role="relationship_manager")
    us.seed_rm_profile(user["id"])
    us.login_admin()

    r = us.client.delete(f"{USERS}/{user['id']}")
    assert r.status_code == 200, r.text
    assert us.db.table("rm_profiles").rows == []
    assert user["id"] in us.db.auth.admin.deleted


def test_delete_blocked_by_active_bookings_is_400(us):
    user = us.seed_profile(role="customer")
    us.db.table("bookings").rows.append(
        {"id": str(uuid.uuid4()), "customer_id": user["id"], "deleted_at": None}
    )
    us.login_admin()

    r = us.client.delete(f"{USERS}/{user['id']}")
    assert r.status_code == 400, r.text   # was 500 before the route fix
    assert "booking" in r.text.lower()
    assert us.db.table("profiles").rows != []   # not deleted


def test_delete_blocked_by_payment_history_is_400(us):
    # Regression: the guard used to query the retired `booking_payments` table and
    # never fired for anyone who transacted after the payments-table migration.
    user = us.seed_profile(role="customer")
    us.db.table("payments").rows.append(
        {"id": str(uuid.uuid4()), "customer_id": user["id"], "deleted_at": None}
    )
    us.login_admin()

    r = us.client.delete(f"{USERS}/{user['id']}")
    assert r.status_code == 400, r.text
    assert "payment" in r.text.lower()
    assert us.db.table("profiles").rows != []   # not deleted


def test_delete_admin_is_400(us):
    admin_user = us.seed_profile(role="admin")
    us.login_admin()
    r = us.client.delete(f"{USERS}/{admin_user['id']}")
    assert r.status_code == 400, r.text
    assert "admin" in r.text.lower()


def test_delete_not_found_is_404(us):
    us.login_admin()
    r = us.client.delete(f"{USERS}/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


def test_delete_requires_admin(us):
    r = us.client.delete(f"{USERS}/{uuid.uuid4()}")
    assert r.status_code in (401, 403), r.text


# =====================================================================
# GET /admin/users/  (list)
# =====================================================================
def test_list_happy(us):
    us.seed_profile(role="customer")
    us.seed_profile(role="vendor")
    us.login_admin()

    r = us.client.get(f"{USERS}/")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["total"] == 2
    assert body["page"] == 1


def test_list_role_filter(us):
    us.seed_profile(role="customer")
    us.seed_profile(role="relationship_manager")
    us.login_admin()

    r = us.client.get(f"{USERS}/", params={"role": "relationship_manager"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert all(u["user_role"] == "relationship_manager" for u in body["data"])


def test_list_is_active_filter(us):
    us.seed_profile(role="customer", is_active=True)
    us.seed_profile(role="customer", is_active=False)
    us.login_admin()

    r = us.client.get(f"{USERS}/", params={"is_active": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert all(u["is_active"] is False for u in body["data"])


def test_list_hides_internal_staff_from_client_admins(us):
    """
    Internal staff accounts are ordinary admins apart from is_internal, so
    without this filter they show up in the client's user list and invite
    questions about who published content the client did not publish.
    """
    us.seed_profile(role="customer", email="client-user@example.com")
    us.seed_profile(role="admin", email="dev@agency.example", is_internal=True)
    us.login_admin()

    r = us.client.get(f"{USERS}/")
    assert r.status_code == 200, r.text
    emails = [u["email"] for u in r.json()["data"]]

    assert "client-user@example.com" in emails
    assert "dev@agency.example" not in emails


def test_search_cannot_surface_an_internal_account(us):
    """
    The search branch runs its own id lookup that bypasses the main query, so
    it needs the filter independently or search becomes a way around the hide.
    """
    us.seed_profile(role="admin", email="dev@agency.example", is_internal=True)
    us.login_admin()

    r = us.client.get(f"{USERS}/", params={"search": "dev@agency"})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0


def test_internal_staff_can_see_internal_accounts(us):
    """Staff still need a working user list, including their own accounts."""
    us.seed_profile(role="admin", email="dev@agency.example", is_internal=True)
    td = us.login_admin()
    td.is_internal = True

    r = us.client.get(f"{USERS}/")
    assert r.status_code == 200, r.text
    assert "dev@agency.example" in [u["email"] for u in r.json()["data"]]


def test_list_search_by_email(us):
    us.seed_profile(role="customer", email="alice@example.com")
    us.seed_profile(role="customer", email="bob@example.com")
    us.login_admin()

    r = us.client.get(f"{USERS}/", params={"search": "alice"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["data"][0]["email"] == "alice@example.com"


def test_list_search_no_match_empty(us):
    us.seed_profile(role="customer", email="alice@example.com")
    us.login_admin()

    r = us.client.get(f"{USERS}/", params={"search": "zzzznope"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 0
    assert body["data"] == []


def test_list_pagination(us):
    for i in range(25):
        us.seed_profile(role="customer", created_at=f"2026-06-01T00:{i:02d}:00")
    us.login_admin()

    r = us.client.get(f"{USERS}/", params={"page": 2, "limit": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 25
    assert len(body["data"]) == 10
    assert body["page"] == 2


def test_list_requires_admin(us):
    r = us.client.get(f"{USERS}/")
    assert r.status_code in (401, 403), r.text
