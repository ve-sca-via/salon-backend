"""
Mocked route tests for the admin_service module (app/api/admin/dashboard.py +
app/api/admin/vendor_requests.py [AdminService-backed routes] +
app/services/admin_service.py).

These run WITHOUT a real Supabase stack. The DB client is an in-memory fake that
supports count="exact", gte/lte, in_, and embedded profiles(...) projection.
They exercise the full HTTP path:

    HTTP -> FastAPI (require_admin overridden, limiter off) -> route ->
    AdminService -> FakeSupabase.

Scope: GET /admin/stats (dashboard aggregation incl. revenue) and
GET /admin/vendor-requests (now with batched RM enrichment), plus a regression
that the removed GET /admin/vendor-requests/{id} is gone. (approve/reject ->
vendor_approval_service and recent-activity -> activity_log_service are other
modules.)

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import re
import uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import require_admin, TokenData

API = settings.API_PREFIX
STATS = f"{API}/admin/stats"
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
        self._cols = "*"
        self._filters = []   # (op, col, val)
        self._op = ("select", "*")
        self._count = None
        self._order = []
        self._range = None

    def select(self, cols="*", count=None):
        self._op = ("select", cols)
        self._cols = cols
        self._count = count
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def gte(self, col, val):
        self._filters.append(("gte", col, val))
        return self

    def lte(self, col, val):
        self._filters.append(("lte", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
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
            if op == "gte" and not (rv is not None and rv >= v):
                return False
            if op == "lte" and not (rv is not None and rv <= v):
                return False
            if op == "in" and rv not in v:
                return False
        return True

    def _embed(self, row):
        m = re.search(r"profiles\(([^)]*)\)", self._cols)
        if not m:
            return dict(row)
        cols = [c.strip() for c in m.group(1).split(",") if c.strip()]
        prof = next((p for p in self._db.table("profiles").rows if p.get("id") == row.get("id")), None)
        out = dict(row)
        out["profiles"] = ({c: prof.get(c) for c in cols} if prof and cols != ["*"]
                           else (dict(prof) if prof else None))
        return out

    def execute(self):
        op, _ = self._op
        rows = self._table.rows
        if op == "select":
            matched = [r for r in rows if self._match(r)]
            total = len(matched)
            for col, desc in reversed(self._order):
                matched.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
            if self._range is not None:
                s, e = self._range
                matched = matched[s:e]
            data = [self._embed(r) if "profiles(" in self._cols else dict(r) for r in matched]
            count = total if self._count == "exact" else None
            return _Resp(data, count=count)
        return _Resp(None)


class _Table:
    def __init__(self, db):
        self.db = db
        self.rows = []

    def select(self, cols="*", count=None):
        return _Query(self).select(cols, count=count)


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

    def add(self, table, **row):
        row.setdefault("id", str(uuid.uuid4()))
        self.db.table(table).rows.append(row)
        return row

    def seed_rm(self, rm_id, full_name="RM One"):
        self.db.table("profiles").rows.append({
            "id": rm_id, "full_name": full_name, "email": f"{rm_id[:6]}@x.com",
            "phone": "999", "is_active": True, "avatar_url": None,
            "user_role": "relationship_manager",
        })
        self.db.table("rm_profiles").rows.append({"id": rm_id, "performance_score": 0})

    def login_admin(self):
        td = TokenData(user_id="admin-1", email="admin@example.com", user_role="admin",
                       jti="jti", exp=datetime.utcnow() + timedelta(hours=1))
        self.app.dependency_overrides[require_admin] = lambda: td
        return td

    def logout(self):
        self.app.dependency_overrides.pop(require_admin, None)


@pytest.fixture()
def ad(app):
    db = FakeSupabase()
    handle = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db
    yield handle
    handle.logout()
    app.dependency_overrides.pop(get_db_client, None)


# =====================================================================
# GET /admin/stats
# =====================================================================
def test_dashboard_stats(ad):
    now = datetime.now().isoformat()
    today = date.today().isoformat()

    # vendor requests: 2 pending, 1 approved
    ad.add("vendor_join_requests", status="pending")
    ad.add("vendor_join_requests", status="pending")
    ad.add("vendor_join_requests", status="approved")
    # salons: 3 total, 2 active, 1 unpaid
    ad.add("salons", is_active=True, registration_fee_paid=True)
    ad.add("salons", is_active=True, registration_fee_paid=True)
    ad.add("salons", is_active=False, registration_fee_paid=False)
    # RMs: 2 active relationship managers
    ad.add("profiles", user_role="relationship_manager", is_active=True)
    ad.add("profiles", user_role="relationship_manager", is_active=True)
    ad.add("profiles", user_role="customer", is_active=True)  # not an RM
    # bookings: 3 total, 1 today
    ad.add("bookings", booking_date=today)
    ad.add("bookings", booking_date="2000-01-01")
    ad.add("bookings", booking_date="2000-01-02")
    # revenue: 100 (booking payment) + 500 (registration) this month
    ad.add("payments", status="success", amount=100, created_at=now)
    ad.add("vendor_registration_payments", status="success", amount=500, payment_completed_at=now)

    ad.login_admin()
    r = ad.client.get(STATS)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["pending_requests"] == 2
    assert s["total_salons"] == 3
    assert s["active_salons"] == 2
    assert s["pending_payment_salons"] == 1
    assert s["total_rms"] == 2
    assert s["total_bookings"] == 3
    assert s["today_bookings"] == 1
    assert s["total_revenue"] == 600.0
    assert s["this_month_revenue"] == 600.0


def test_dashboard_stats_empty(ad):
    ad.login_admin()
    r = ad.client.get(STATS)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["total_salons"] == 0
    assert s["total_revenue"] == 0.0


def test_dashboard_stats_requires_admin(ad):
    r = ad.client.get(STATS)
    assert r.status_code in (401, 403), r.text


# =====================================================================
# GET /admin/vendor-requests
# =====================================================================
def _vreq_row(ad, rm_id, status="pending", **over):
    row = {
        "id": str(uuid.uuid4()),
        "rm_id": rm_id,
        "status": status,
        "business_name": "Biz",
        "business_type": "salon",
        "owner_name": "Owner",
        "owner_email": "owner@x.com",
        "owner_phone": "999",
        "business_address": "123 Test Street",
        "city": "Testville",
        "state": "State",
        "pincode": "560001",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    row.update(over)
    ad.db.table("vendor_join_requests").rows.append(row)
    return row


def test_vendor_requests_enriched_with_rm_profile(ad):
    rm_id = str(uuid.uuid4())
    ad.seed_rm(rm_id, full_name="Alice RM")
    _vreq_row(ad, rm_id, status="pending")
    ad.login_admin()

    r = ad.client.get(VREQS)  # default status_filter=pending
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 1
    assert data[0]["rm_profile"]["profiles"]["full_name"] == "Alice RM"


def test_vendor_requests_status_filter(ad):
    rm_id = str(uuid.uuid4())
    ad.seed_rm(rm_id)
    _vreq_row(ad, rm_id, status="pending")
    _vreq_row(ad, rm_id, status="approved")
    ad.login_admin()

    r = ad.client.get(VREQS, params={"status_filter": "approved"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 1
    assert data[0]["status"] == "approved"


def test_vendor_requests_missing_rm_profile_is_null(ad):
    # request whose rm has no rm_profiles/profiles row -> rm_profile is null
    _vreq_row(ad, str(uuid.uuid4()), status="pending")
    ad.login_admin()

    r = ad.client.get(VREQS)
    assert r.status_code == 200, r.text
    assert r.json()[0]["rm_profile"] is None


def test_vendor_requests_requires_admin(ad):
    r = ad.client.get(VREQS)
    assert r.status_code in (401, 403), r.text


# =====================================================================
# Regression: removed GET /admin/vendor-requests/{id}
# =====================================================================
def test_removed_single_vendor_request_is_404(ad):
    ad.login_admin()
    r = ad.client.get(f"{VREQS}/{uuid.uuid4()}")
    assert r.status_code == 404, r.text
