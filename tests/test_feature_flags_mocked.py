"""
Mocked route tests for the feature entitlement system
(app/core/features.py + app/core/auth.py::RequireFeature + app/api/features.py).

This is the gate that keeps a built-but-unpaid-for feature invisible in
production, so the tests are weighted toward the ways it could silently fail
open: a client admin reaching a gated route, an unsold feature leaking into the
/features payload, the kill switch not applying to staff, and a stale cache
serving the old answer after a flip.

Auth is injected by overriding get_current_user, which is what RequireFeature
actually depends on. The Supabase client is a small in-memory fake.

No marker -> runs in the fast (no-stack) job alongside the smoke suite.
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import get_current_user, TokenData
from app.core.features import invalidate_feature_cache

API = settings.API_PREFIX
FEATURES = f"{API}/features"
BLOG = f"{API}/blog"


# =====================================================================
# In-memory fake Supabase client (feature_flags only)
# =====================================================================
class _Resp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self._filters = []
        self._op = "select"
        self._payload = None
        self._single = False

    # -- builders --
    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def order(self, *_a, **_kw):
        return self

    def maybe_single(self):
        self._single = True
        return self

    # -- execution --
    def _matching(self):
        out = self.rows
        for col, val in self._filters:
            out = [r for r in out if r.get(col) == val]
        return out

    def execute(self):
        matched = self._matching()

        if self._op == "update":
            for row in matched:
                previous = row.get("status")
                row.update(self._payload)
                # Mirror the migration's trigger so the audit column is tested.
                if row.get("status") == "enabled" and previous != "enabled":
                    row["enabled_at"] = datetime.utcnow().isoformat()
                elif row.get("status") != "enabled":
                    row["enabled_at"] = None
                    row["enabled_by"] = None
            return _Resp(list(matched))

        if self._single:
            return _Resp(matched[0] if matched else None)
        return _Resp(list(matched))


class FakeSupabase:
    def __init__(self, flags):
        self.rows = [
            {
                "key": key,
                "name": key.title(),
                "description": None,
                "status": flag_status,
                "enabled_at": None,
                "enabled_by": None,
            }
            for key, flag_status in flags.items()
        ]

    def table(self, name):
        assert name == "feature_flags", f"unexpected table {name}"
        return _Query(self.rows)


# =====================================================================
# Fixtures
# =====================================================================
@pytest.fixture(autouse=True)
def _clear_flag_cache():
    """The flag cache is module-global; leaking it across tests hides bugs."""
    invalidate_feature_cache()
    yield
    invalidate_feature_cache()


@pytest.fixture()
def app():
    from main import app as fastapi_app
    return fastapi_app


def _user(role="admin", is_internal=False, user_id="u-1"):
    return TokenData(
        user_id=user_id,
        email=f"{user_id}@example.com",
        user_role=role,
        is_internal=is_internal,
        jti="jti-test",
        exp=datetime.utcnow() + timedelta(hours=1),
    )


@pytest.fixture()
def make_client(app):
    """Build a TestClient for a given flag state and calling user."""

    def _make(flags, user):
        db = FakeSupabase(flags)
        app.dependency_overrides[get_db_client] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app), db

    yield _make

    app.dependency_overrides.pop(get_db_client, None)
    app.dependency_overrides.pop(get_current_user, None)


# =====================================================================
# The core gate: who can reach a feature-gated route
# =====================================================================
def test_client_admin_gets_404_while_feature_is_internal(make_client):
    """The whole point: an unsold feature is invisible to the client."""
    client, _ = make_client({"blog": "internal"}, _user(is_internal=False))

    resp = client.get(f"{BLOG}/admin/all")

    assert resp.status_code == 404
    # 403 would confirm the feature exists; the body must stay generic.
    assert "blog" not in resp.text.lower()


def test_internal_staff_reach_the_feature_while_it_is_internal(make_client):
    """Staff must be able to use the feature in production before it is sold."""
    client, _ = make_client({"blog": "internal"}, _user(is_internal=True))

    resp = client.get(f"{BLOG}/admin/all")

    assert resp.status_code != 404


def test_client_admin_reaches_the_feature_once_enabled(make_client):
    """Flipping to 'enabled' is the 'client paid' switch."""
    client, _ = make_client({"blog": "enabled"}, _user(is_internal=False))

    resp = client.get(f"{BLOG}/admin/all")

    assert resp.status_code != 404


def test_disabled_is_a_kill_switch_that_also_stops_internal_staff(make_client):
    """A kill switch that staff bypass cannot take a broken feature down."""
    client, _ = make_client({"blog": "disabled"}, _user(is_internal=True))

    assert client.get(f"{BLOG}/admin/all").status_code == 404


def test_unregistered_feature_fails_closed(make_client):
    """A typo'd or unseeded key must close the door, not open it."""
    client, _ = make_client({}, _user(is_internal=True))

    assert client.get(f"{BLOG}/admin/all").status_code == 404


def test_role_failure_reports_403_not_404(make_client):
    """
    Role and entitlement are separate failures. A non-admin should get the
    normal 403; collapsing it into 404 would make genuine permission bugs
    indistinguishable from a hidden feature.
    """
    client, _ = make_client({"blog": "enabled"}, _user(role="customer"))

    assert client.get(f"{BLOG}/admin/all").status_code == 403


def test_write_routes_are_gated_too(make_client):
    """Hiding only the read route would leave the feature fully usable."""
    client, _ = make_client({"blog": "internal"}, _user(is_internal=False))

    payload = {"title": "Sneaky", "content": "<p>hi</p>"}
    assert client.post(BLOG, json=payload).status_code == 404
    assert client.put(f"{BLOG}/some-id", json=payload).status_code == 404
    assert client.delete(f"{BLOG}/some-id").status_code == 404


def test_public_blog_routes_stay_open_while_gated(make_client):
    """
    Posts published by staff must still render for readers and crawlers. Only
    the admin surface is hidden, never the public output.
    """
    client, _ = make_client({"blog": "internal"}, _user(is_internal=False))

    # Reaches the route (the fake db has no blog_posts table, so it errors
    # past the gate) - the point is that it is NOT a 404 from the gate.
    assert client.get(f"{BLOG}/tags").status_code != 404


# =====================================================================
# GET /features - the map the admin panel renders from
# =====================================================================
def test_feature_map_omits_internal_features_for_client_admin(make_client):
    """
    Absent, not present-and-false: the payload must not disclose that a
    hidden feature exists, since the client can read it in devtools.
    """
    client, _ = make_client(
        {"blog": "internal", "banners": "enabled"}, _user(is_internal=False)
    )

    body = client.get(FEATURES).json()

    assert body["features"] == {"banners": "enabled"}
    assert "blog" not in body["features"]
    assert body["is_internal"] is False


def test_feature_map_includes_internal_features_for_staff(make_client):
    client, _ = make_client(
        {"blog": "internal", "banners": "enabled"}, _user(is_internal=True)
    )

    body = client.get(FEATURES).json()

    assert body["features"] == {"blog": "internal", "banners": "enabled"}
    assert body["is_internal"] is True


def test_feature_map_omits_disabled_features_from_everyone(make_client):
    client, _ = make_client({"blog": "disabled"}, _user(is_internal=False))

    assert client.get(FEATURES).json()["features"] == {}


# =====================================================================
# The management endpoints must be internal-only
# =====================================================================
def test_client_admin_cannot_list_the_registry(make_client):
    """A flags screen listing every unsold feature would defeat the gate."""
    client, _ = make_client({"blog": "internal"}, _user(is_internal=False))

    assert client.get(f"{FEATURES}/admin/all").status_code == 404


def test_client_admin_cannot_enable_a_feature_for_themselves(make_client):
    client, _ = make_client({"blog": "internal"}, _user(is_internal=False))

    resp = client.patch(f"{FEATURES}/admin/blog", json={"status": "enabled"})

    assert resp.status_code == 404


def test_internal_staff_can_list_and_flip(make_client):
    client, db = make_client({"blog": "internal"}, _user(is_internal=True))

    listing = client.get(f"{FEATURES}/admin/all")
    assert listing.status_code == 200
    assert [f["key"] for f in listing.json()["features"]] == ["blog"]

    flip = client.patch(f"{FEATURES}/admin/blog", json={"status": "enabled"})
    assert flip.status_code == 200
    assert db.rows[0]["status"] == "enabled"
    assert db.rows[0]["enabled_at"] is not None


def test_flip_takes_effect_immediately_without_waiting_for_the_cache(make_client):
    """
    Reads are cached for 60s. If a write did not invalidate, enabling a feature
    would appear to do nothing for a minute and get 'fixed' by a redeploy.
    """
    client, _ = make_client({"blog": "internal"}, _user(is_internal=True))

    # Warm the cache.
    assert client.get(FEATURES).json()["features"] == {"blog": "internal"}

    client.patch(f"{FEATURES}/admin/blog", json={"status": "enabled"})

    assert client.get(FEATURES).json()["features"] == {"blog": "enabled"}


def test_invalid_status_is_rejected(make_client):
    client, db = make_client({"blog": "internal"}, _user(is_internal=True))

    resp = client.patch(f"{FEATURES}/admin/blog", json={"status": "on"})

    assert resp.status_code == 400
    assert db.rows[0]["status"] == "internal"


def test_flipping_an_unregistered_feature_404s(make_client):
    client, _ = make_client({"blog": "internal"}, _user(is_internal=True))

    resp = client.patch(f"{FEATURES}/admin/nope", json={"status": "enabled"})

    assert resp.status_code == 404
