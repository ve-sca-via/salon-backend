"""
Mocked route tests for the banner module (app/api/banners.py +
app/services/banner_service.py).

Same approach as test_product_mocked.py: the Supabase client is replaced with a
small in-memory fake (select/insert/update/delete + eq/order/range/maybe_single),
and the auth dependency (require_admin) is overridden. The full HTTP path is
exercised:

    HTTP -> FastAPI (auth dep overridden, rate limiter disabled) -> route ->
    BannerService -> FakeSupabase.

Scope: the public carousel feed (active + ordered + schedule-window filtering),
and the admin list/create/update/reorder/delete flows.

No marker -> runs in the fast (no-stack) job alongside the smoke suite.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import require_admin, TokenData

API = settings.API_PREFIX
BANNERS = f"{API}/banners"


# =====================================================================
# In-memory fake Supabase client (covers the ops banner_service uses)
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
        self._maybe = False
        self._order = []
        self._range = None

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

    def maybe_single(self):
        self._maybe = True
        return self

    def _match(self, row):
        for op, c, v in self._filters:
            if op == "eq" and row.get(c) != v:
                return False
        return True

    def execute(self):
        op, payload = self._op
        rows = self._table.rows

        if op == "select":
            matched = [dict(r) for r in rows if self._match(r)]
            for col, desc in reversed(self._order):
                matched.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
            if self._range is not None:
                s, e = self._range
                matched = matched[s:e + 1]
            if self._maybe:
                return _Resp(matched[0] if matched else None)
            return _Resp(matched)

        if op == "insert":
            new_rows = payload if isinstance(payload, list) else [payload]
            added = []
            for nr in new_rows:
                row = dict(nr)
                row.setdefault("id", str(uuid.uuid4()))
                row.setdefault("created_at", datetime.utcnow().isoformat())
                row.setdefault("updated_at", datetime.utcnow().isoformat())
                row.setdefault("is_active", True)
                row.setdefault("sort_order", 0)
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

    def seed_banner(self, **fields):
        bid = fields.pop("id", str(uuid.uuid4()))
        row = {
            "id": bid,
            "title": fields.pop("title", "Promo"),
            "image_url": fields.pop("image_url", "https://res.cloudinary.com/x/banners/a.jpg"),
            "link_url": None,
            "sort_order": 0,
            "is_active": True,
            "starts_at": None,
            "ends_at": None,
            "created_at": datetime.utcnow().isoformat(),
        }
        row.update(fields)
        self.db.table("banners").rows.append(row)
        return row

    def login_admin(self, user_id="admin-1"):
        td = TokenData(
            user_id=user_id, email="admin@example.com", user_role="admin",
            jti="jti-test", exp=datetime.utcnow() + timedelta(hours=1),
        )
        self.app.dependency_overrides[require_admin] = lambda: td
        return td

    def clear_overrides(self):
        self.app.dependency_overrides.pop(require_admin, None)


@pytest.fixture()
def bn(app):
    db = FakeSupabase()
    handle = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db

    yield handle

    handle.clear_overrides()
    app.dependency_overrides.pop(get_db_client, None)


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat()


# =====================================================================
# GET /banners  (public feed)
# =====================================================================
def test_public_list_returns_active_only(bn):
    bn.seed_banner(title="Shown", is_active=True, sort_order=1)
    bn.seed_banner(title="Hidden", is_active=False, sort_order=2)

    r = bn.client.get(BANNERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert body["banners"][0]["title"] == "Shown"


def test_public_list_orders_by_sort_order(bn):
    bn.seed_banner(title="Third", sort_order=3)
    bn.seed_banner(title="First", sort_order=1)
    bn.seed_banner(title="Second", sort_order=2)

    r = bn.client.get(BANNERS)
    titles = [b["title"] for b in r.json()["banners"]]
    assert titles == ["First", "Second", "Third"]


def test_public_list_hides_out_of_window(bn):
    now = datetime.now(timezone.utc)
    bn.seed_banner(title="Future", starts_at=_iso(now + timedelta(days=1)))
    bn.seed_banner(title="Expired", ends_at=_iso(now - timedelta(days=1)))
    bn.seed_banner(title="Live", starts_at=_iso(now - timedelta(days=1)),
                   ends_at=_iso(now + timedelta(days=1)))

    r = bn.client.get(BANNERS)
    titles = [b["title"] for b in r.json()["banners"]]
    assert titles == ["Live"]


def test_public_list_is_unauthenticated(bn):
    # No admin override set; endpoint must still work without a token.
    bn.seed_banner(title="Anon-visible")
    r = bn.client.get(BANNERS)
    assert r.status_code == 200
    assert r.json()["count"] == 1


# =====================================================================
# GET /banners/admin/all
# =====================================================================
def test_admin_list_includes_inactive(bn):
    bn.login_admin()
    bn.seed_banner(title="Active", is_active=True)
    bn.seed_banner(title="Inactive", is_active=False)

    r = bn.client.get(f"{BANNERS}/admin/all")
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 2


def test_admin_list_includes_out_of_window(bn):
    bn.login_admin()
    now = datetime.now(timezone.utc)
    bn.seed_banner(title="Expired", ends_at=_iso(now - timedelta(days=1)))

    r = bn.client.get(f"{BANNERS}/admin/all")
    assert r.json()["count"] == 1  # admin view ignores the schedule window


# =====================================================================
# POST /banners  (create)
# =====================================================================
def test_create_banner(bn):
    bn.login_admin()
    r = bn.client.post(BANNERS, json={
        "image_url": "https://res.cloudinary.com/x/banners/new.jpg",
        "title": "New Year Sale",
        "sort_order": 5,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["banner"]["title"] == "New Year Sale"
    assert body["banner"]["sort_order"] == 5
    # Persisted to the fake table
    assert len(bn.db.table("banners").rows) == 1


def test_create_banner_requires_image_url(bn):
    bn.login_admin()
    r = bn.client.post(BANNERS, json={"title": "No image"})
    assert r.status_code == 422


def test_create_banner_rejects_bad_window(bn):
    bn.login_admin()
    now = datetime.now(timezone.utc)
    r = bn.client.post(BANNERS, json={
        "image_url": "https://x/a.jpg",
        "starts_at": _iso(now + timedelta(days=2)),
        "ends_at": _iso(now + timedelta(days=1)),
    })
    assert r.status_code == 422  # ends_at <= starts_at


# =====================================================================
# PUT /banners/{id}  (update)
# =====================================================================
def test_update_banner(bn):
    bn.login_admin()
    row = bn.seed_banner(title="Old")
    r = bn.client.put(f"{BANNERS}/{row['id']}", json={"title": "Renamed"})
    assert r.status_code == 200, r.text
    assert r.json()["banner"]["title"] == "Renamed"


def test_update_missing_banner_404(bn):
    bn.login_admin()
    r = bn.client.put(f"{BANNERS}/{uuid.uuid4()}", json={"title": "x"})
    assert r.status_code == 404


# =====================================================================
# PUT /banners/reorder
# =====================================================================
def test_reorder_banners(bn):
    bn.login_admin()
    a = bn.seed_banner(title="A", sort_order=1)
    b = bn.seed_banner(title="B", sort_order=2)

    r = bn.client.put(f"{BANNERS}/reorder", json={
        "orders": [
            {"id": a["id"], "sort_order": 2},
            {"id": b["id"], "sort_order": 1},
        ]
    })
    assert r.status_code == 200, r.text

    # Public feed now returns B before A.
    titles = [x["title"] for x in bn.client.get(BANNERS).json()["banners"]]
    assert titles == ["B", "A"]


def test_reorder_rejects_duplicate_ids(bn):
    bn.login_admin()
    a = bn.seed_banner(title="A")
    r = bn.client.put(f"{BANNERS}/reorder", json={
        "orders": [
            {"id": a["id"], "sort_order": 1},
            {"id": a["id"], "sort_order": 2},
        ]
    })
    assert r.status_code == 422


# =====================================================================
# DELETE /banners/{id}
# =====================================================================
def test_soft_delete_banner(bn):
    bn.login_admin()
    row = bn.seed_banner(title="ToHide")
    r = bn.client.delete(f"{BANNERS}/{row['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "Banner deactivated"
    # Row still exists but is inactive -> drops out of the public feed.
    assert bn.db.table("banners").rows[0]["is_active"] is False
    assert bn.client.get(BANNERS).json()["count"] == 0


def test_hard_delete_banner(bn):
    bn.login_admin()
    row = bn.seed_banner(title="ToPurge")
    r = bn.client.delete(f"{BANNERS}/{row['id']}", params={"hard": True})
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "Banner permanently deleted"
    assert bn.db.table("banners").rows == []
