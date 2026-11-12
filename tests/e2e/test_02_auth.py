"""Auth per role: login, /auth/me, bad password, refresh, logout.

regular_buyer login is exercised in the buyer flow (test_06), because that
account only exists once a buyer request has been approved in the same run.
"""
import pytest

from .support.client import detail, expect

FLOW = "auth"
FLOW_TITLE = "Auth per role"
pytestmark = pytest.mark.e2e


def role_of(data: dict) -> str | None:
    for container in (data, data.get("user") or {}, data.get("data") or {}, data.get("profile") or {}):
        if isinstance(container, dict) and container.get("user_role"):
            return container["user_role"]
    return None


@pytest.mark.parametrize("role,expected", [
    ("admin", "admin"),
    ("rm", "relationship_manager"),
    ("vendor", "vendor"),
    ("customer", "customer"),
])
def test_login_and_me(api, world, role, expected):
    """Login + GET /auth/me returns the right role"""
    sess = world.session(role)
    assert sess.get("access_token") and sess.get("refresh_token"), "login did not return both tokens"
    assert role_of(sess) == expected, f"login payload role {role_of(sess)!r} != {expected!r}"
    me = expect(api.get("/auth/me", token=sess["access_token"]), 200)
    assert role_of(me) == expected, f"/auth/me role {role_of(me)!r} != {expected!r}: {me}"


def test_bad_password_401(api, world):
    """Wrong password is rejected with 401 (not 500, no account enumeration)"""
    world.require_seeded()
    resp = api.post("/auth/login", json={"email": world.accounts["customer"]["email"], "password": "Wrong-Pass-123"})
    assert resp.status_code == 401, f"expected 401, got {resp.status_code}: {resp.text[:300]}"
    unknown = detail(resp).lower()
    assert "not found" not in unknown and "no user" not in unknown, f"message leaks account existence: {unknown}"


def test_no_token_401(api):
    """GET /auth/me without a token is 401"""
    resp = api.get("/auth/me")
    assert resp.status_code in (401, 403), f"got {resp.status_code}"


def test_garbage_token_401(api):
    """GET /auth/me with a forged token is 401"""
    resp = api.get("/auth/me", token="eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.bad")
    assert resp.status_code == 401, f"got {resp.status_code}: {resp.text[:200]}"


def test_refresh_token(api, world, flow):
    """POST /auth/refresh returns a working new access token"""
    sess = world.session("customer")
    data = expect(api.post("/auth/refresh", json={"refresh_token": sess["refresh_token"]}), 200)
    new_access = data.get("access_token") or (data.get("data") or {}).get("access_token")
    assert new_access, f"no access_token in refresh response: {list(data)}"
    expect(api.get("/auth/me", token=new_access), 200, what="new access token")
    flow["refreshed_token"] = new_access


def test_refresh_rejects_access_token(api, world):
    """POST /auth/refresh with an ACCESS token (wrong type) is rejected"""
    resp = api.post("/auth/refresh", json={"refresh_token": world.token("customer")})
    # Fixed: tokens carry a `type` claim (app/core/auth.py _reject_wrong_token_type).
    # Only tokens minted AFTER that deploy are typed — world tokens are fresh per run.
    assert resp.status_code in (400, 401, 403), f"got {resp.status_code}: {resp.text[:200]}"


def test_refresh_token_not_usable_as_access_token(api, world):
    """A REFRESH token is not accepted as a Bearer access token"""
    resp = api.get("/auth/me", token=world.session("customer")["refresh_token"])
    assert resp.status_code == 401, f"got {resp.status_code}"


def test_logout_revokes_token(api, world, flow):
    """POST /auth/logout blacklists that token only (original session keeps working)"""
    token = flow.need("refreshed_token")
    expect(api.post("/auth/logout", token=token), 200)
    resp = api.get("/auth/me", token=token)
    assert resp.status_code == 401, f"logged-out token still accepted: {resp.status_code}"
    expect(api.get("/auth/me", token=world.token("customer")), 200, what="original session after logout of another token")
