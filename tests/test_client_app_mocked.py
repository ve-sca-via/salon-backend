"""
Mocked tests for client identification, the minimum-app-version policy and the
vendor/partner-app role rules (app/core/client_app.py,
docs/CLIENT_APPS_AND_VERSIONING.md).

No Supabase stack: the policy read is monkeypatched, and the auth paths reuse
the in-memory fakes from test_auth_mocked. No marker -> runs in the fast job.
"""
import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core import client_app as ca
from app.core import database
from app.core.auth import TokenData, create_access_token, create_refresh_token, get_current_user
from app.core.config import settings
from app.core.database import get_db_client
from app.core.handlers import register_exception_handlers
from app.services.config_service import AVAILABLE_SYSTEM_CONFIGS, clear_config_cache

# Re-exported fixture + fakes (pytest discovers fixtures in module scope).
from tests.test_auth_mocked import FakeSupabase, _User, mock_auth  # noqa: F401

API = settings.API_PREFIX

CUSTOMER_ANDROID_1_4 = {
    "X-Client-App": "customer-app",
    "X-App-Platform": "android",
    "X-App-Version": "1.4.2",
}


# =====================================================================
# Helpers
# =====================================================================
@pytest.fixture()
def policy_rows(monkeypatch):
    """
    Serve the client policy from a list the test fills in.

    Patches the one DB round trip (and get_db, so no real client is built) - the
    cache, parsing and flag logic all run for real.
    """
    rows = []

    async def _fake_fetch(db):
        return list(rows)

    monkeypatch.setattr(ca, "_fetch_policy_rows", _fake_fetch)
    monkeypatch.setattr(database, "get_db", lambda: object())
    ca.clear_client_policy_cache()

    def set_rows(**values):
        rows.clear()
        rows.extend({"config_key": k, "config_value": v, "is_active": True} for k, v in values.items())
        ca.clear_client_policy_cache()

    yield set_rows
    ca.clear_client_policy_cache()


@pytest.fixture()
def flags(monkeypatch):
    """Set the env-level switches for one test."""
    def _set(**values):
        for name, value in values.items():
            monkeypatch.setattr(settings, name, value)
        ca.clear_client_policy_cache()
    return _set


# =====================================================================
# Version comparison
# =====================================================================
@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("1.4.2", "1.4.2", 0),
        ("1.4.2", "1.4.10", -1),   # numeric, not lexical
        ("1.10.0", "1.9.9", 1),
        ("2", "1.99.99", 1),
        ("1.4", "1.4.0", 0),       # missing parts count as 0
        ("v1.4.2", "1.4.2", 0),    # leading v tolerated
        ("1.4.2-beta.1", "1.4.2", -1),  # prerelease sorts before release
        ("1.4.2-beta.2", "1.4.2-beta.10", -1),
        ("1.4.2-alpha", "1.4.2-beta", -1),
        ("1.4.2-1", "1.4.2-alpha", -1),  # numeric ids before alphanumeric
        ("1.4.2+build.7", "1.4.2", 0),   # build metadata ignored
        (" 1.4.2 ", "1.4.2", 0),
    ],
)
def test_compare_versions(a, b, expected):
    assert ca.compare_versions(a, b) == expected


@pytest.mark.parametrize("bad", ["", "abc", "1.x", "1..2", "1.2.3.4", "latest", None])
def test_unparseable_versions(bad):
    assert ca.parse_version(bad) is None
    assert ca.compare_versions(bad, "1.0.0") is None


def test_is_version_below_never_blocks_on_garbage():
    assert ca.is_version_below("1.0.0", "1.2.0") is True
    assert ca.is_version_below("1.2.0", "1.2.0") is False
    assert ca.is_version_below("garbage", "1.2.0") is False
    assert ca.is_version_below("1.0.0", "garbage") is False
    assert ca.is_version_below(None, "1.2.0") is False
    assert ca.is_version_below("1.0.0", None) is False


def test_header_normalisation():
    assert ca.normalise_client_app(" Customer-App ") == "customer-app"
    assert ca.normalise_client_app("something-else") is None
    assert ca.normalise_platform("ANDROID") == "android"
    assert ca.normalise_platform("windows") is None


# =====================================================================
# Policy + flags
# =====================================================================
def test_policy_flags_default_to_env(flags):
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=True)
    policy = ca.ClientPolicy()
    assert policy.enforce_partner_app_for_vendors is True
    assert policy.enforce_partner_app_roles is False
    assert policy.require_client_app_header_for_vendors is False


def test_policy_system_config_overrides_env_both_ways(flags):
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=True, ENFORCE_PARTNER_APP_ROLES=False)
    policy = ca.ClientPolicy(values={
        "enforce_partner_app_for_vendors": "false",
        "enforce_partner_app_roles": "TRUE",
        "require_client_app_header_for_vendors": "maybe",  # unreadable -> env
    })
    assert policy.enforce_partner_app_for_vendors is False
    assert policy.enforce_partner_app_roles is True
    assert policy.require_client_app_header_for_vendors is False


def test_empty_config_value_means_unset():
    policy = ca.ClientPolicy(values={"customer_app_android_min_version": "  "})
    assert policy.min_version("customer-app", "android") is None


def test_inactive_rows_are_ignored(monkeypatch):
    async def _fake_fetch(db):
        return [{"config_key": "customer_app_android_min_version", "config_value": "9.0.0", "is_active": False}]

    monkeypatch.setattr(ca, "_fetch_policy_rows", _fake_fetch)
    import asyncio
    policy = asyncio.run(ca.get_client_policy(db=object()))
    assert policy.min_version("customer-app", "android") is None


def test_policy_read_failure_fails_open_and_is_not_cached(monkeypatch):
    calls = {"n": 0}

    async def _boom(db):
        calls["n"] += 1
        raise RuntimeError("db down")

    monkeypatch.setattr(ca, "_fetch_policy_rows", _boom)
    import asyncio
    assert asyncio.run(ca.get_client_policy(db=object())).values == {}
    asyncio.run(ca.get_client_policy(db=object()))
    assert calls["n"] == 2  # retried, not cached


def test_policy_is_cached_and_config_write_invalidates(policy_rows, monkeypatch):
    import asyncio
    calls = {"n": 0}
    original = ca._fetch_policy_rows

    async def _counting(db):
        calls["n"] += 1
        return await original(db)

    monkeypatch.setattr(ca, "_fetch_policy_rows", _counting)
    asyncio.run(ca.get_client_policy())
    asyncio.run(ca.get_client_policy())
    assert calls["n"] == 1
    clear_config_cache("customer_app_android_min_version")  # what ConfigService calls on write
    asyncio.run(ca.get_client_policy())
    assert calls["n"] == 2
    clear_config_cache("convenience_fee_percentage")  # unrelated key: keep the snapshot
    asyncio.run(ca.get_client_policy())
    assert calls["n"] == 2


def test_new_keys_are_registered_for_the_admin_panel():
    keys = {entry["config_key"] for entry in AVAILABLE_SYSTEM_CONFIGS}
    assert ca.CLIENT_POLICY_KEYS <= keys
    for entry in AVAILABLE_SYSTEM_CONFIGS:
        if entry["config_key"] in ca.FLAG_KEYS:
            assert entry["config_type"] == "boolean"
    assert "partner_app_ios_min_version" in keys
    assert "customer_app_update_message" in keys


# =====================================================================
# GET /app-config
# =====================================================================
def test_app_config_without_policy_is_all_nulls(client, policy_rows):
    r = client.get(f"{API}/app-config", params={"client_app": "customer-app", "platform": "android", "version": "1.4.2"})
    assert r.status_code == 200, r.text
    assert r.json() == {
        "success": True,
        "client_app": "customer-app",
        "platform": "android",
        "current_version": "1.4.2",
        "min_supported_version": None,
        "latest_version": None,
        "update_required": False,
        "update_available": False,
        "store_url": None,
        "message": None,
    }
    assert "max-age" in r.headers["cache-control"]


def test_app_config_update_required(client, policy_rows):
    policy_rows(
        customer_app_android_min_version="1.5.0",
        customer_app_android_latest_version="1.6.0",
        customer_app_android_store_url="https://play.google.com/store/apps/details?id=com.lubist",
        customer_app_update_message="Please update.",
        # Other app/platform must not leak in.
        customer_app_ios_min_version="9.9.9",
    )
    r = client.get(f"{API}/app-config", params={"client_app": "customer-app", "platform": "android", "version": "1.4.2"})
    body = r.json()
    assert body["min_supported_version"] == "1.5.0"
    assert body["latest_version"] == "1.6.0"
    assert body["update_required"] is True
    assert body["update_available"] is True
    assert body["store_url"] == "https://play.google.com/store/apps/details?id=com.lubist"
    assert body["message"] == "Please update."


def test_app_config_update_available_only(client, policy_rows):
    policy_rows(partner_app_ios_min_version="1.0.0", partner_app_ios_latest_version="1.3.0")
    r = client.get(f"{API}/app-config", params={"client_app": "partner-app", "platform": "ios", "version": "1.2.9"})
    body = r.json()
    assert (body["update_required"], body["update_available"]) == (False, True)


def test_app_config_up_to_date(client, policy_rows):
    policy_rows(partner_app_ios_min_version="1.0.0", partner_app_ios_latest_version="1.3.0")
    r = client.get(f"{API}/app-config", params={"client_app": "partner-app", "platform": "ios", "version": "1.3.0"})
    body = r.json()
    assert (body["update_required"], body["update_available"]) == (False, False)


def test_app_config_falls_back_to_headers_and_query_wins(client, policy_rows):
    policy_rows(customer_app_android_min_version="1.5.0", partner_app_android_min_version="2.0.0")
    r = client.get(f"{API}/app-config", headers=CUSTOMER_ANDROID_1_4)
    assert r.status_code == 200, r.text
    assert r.json()["client_app"] == "customer-app"
    assert r.json()["current_version"] == "1.4.2"
    assert r.json()["update_required"] is True

    r = client.get(f"{API}/app-config", params={"client_app": "partner-app", "version": "2.0.0"}, headers=CUSTOMER_ANDROID_1_4)
    body = r.json()
    assert body["client_app"] == "partner-app"
    assert body["platform"] == "android"  # from header
    assert body["update_required"] is False


def test_app_config_without_version_reports_no_update(client, policy_rows):
    policy_rows(customer_app_android_min_version="1.5.0")
    r = client.get(f"{API}/app-config", params={"client_app": "customer-app", "platform": "android"})
    body = r.json()
    assert body["current_version"] is None
    assert body["min_supported_version"] == "1.5.0"
    assert body["update_required"] is False


def test_app_config_unparseable_version_is_not_required(client, policy_rows):
    policy_rows(customer_app_android_min_version="1.5.0")
    r = client.get(f"{API}/app-config", params={"client_app": "customer-app", "platform": "android", "version": "dev-build"})
    assert r.status_code == 200
    assert r.json()["update_required"] is False


@pytest.mark.parametrize(
    "params,code",
    [
        ({"client_app": "web", "platform": "android"}, "INVALID_CLIENT_APP"),
        ({"client_app": "admin-panel", "platform": "android"}, "INVALID_CLIENT_APP"),
        ({"client_app": "nope", "platform": "android"}, "INVALID_CLIENT_APP"),
        ({"platform": "android"}, "INVALID_CLIENT_APP"),
        ({"client_app": "customer-app", "platform": "web"}, "INVALID_PLATFORM"),
        ({"client_app": "customer-app", "platform": "windows"}, "INVALID_PLATFORM"),
        ({"client_app": "customer-app"}, "INVALID_PLATFORM"),
    ],
)
def test_app_config_rejects_unknown_app_or_platform(client, policy_rows, params, code):
    r = client.get(f"{API}/app-config", params=params)
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error_code"] == code
    assert "must be one of" in body["message"]


# =====================================================================
# Global 426 enforcement
# =====================================================================
MISSING = f"{API}/definitely-not-a-route"  # DB-free: a 404 means "let through"


def test_outdated_native_app_gets_426(client, policy_rows):
    policy_rows(
        customer_app_android_min_version="1.5.0",
        customer_app_android_store_url="https://play.google.com/x",
    )
    r = client.get(MISSING, headers=CUSTOMER_ANDROID_1_4)
    assert r.status_code == 426, r.text
    body = r.json()
    assert body["error_code"] == "APP_UPDATE_REQUIRED"
    assert body["message"]
    assert body["min_supported_version"] == "1.5.0"
    assert body["store_url"] == "https://play.google.com/x"
    assert r.headers.get("x-request-id")  # still inside the logging middleware


def test_426_uses_admin_message(client, policy_rows):
    policy_rows(customer_app_android_min_version="1.5.0", customer_app_update_message="Update now!")
    assert client.get(MISSING, headers=CUSTOMER_ANDROID_1_4).json()["message"] == "Update now!"


def test_426_on_post_too(client, policy_rows):
    policy_rows(customer_app_android_min_version="1.5.0")
    r = client.post(f"{API}/auth/login", json={"email": "a@b.co", "password": "x"}, headers=CUSTOMER_ANDROID_1_4)
    assert r.status_code == 426


def test_current_version_passes(client, policy_rows):
    policy_rows(customer_app_android_min_version="1.4.2")
    assert client.get(MISSING, headers=CUSTOMER_ANDROID_1_4).status_code == 404


def test_other_platform_policy_does_not_apply(client, policy_rows):
    policy_rows(customer_app_ios_min_version="9.0.0", partner_app_android_min_version="9.0.0")
    assert client.get(MISSING, headers=CUSTOMER_ANDROID_1_4).status_code == 404


@pytest.mark.parametrize("path", ["/health", "/", "APP_CONFIG"])
def test_exempt_paths(client, policy_rows, path):
    policy_rows(customer_app_android_min_version="1.5.0")
    if path == "APP_CONFIG":
        path = f"{API}/app-config"
    r = client.get(path, headers=CUSTOMER_ANDROID_1_4)
    assert r.status_code == 200, r.text
    if path.endswith("app-config"):
        assert r.json()["update_required"] is True


@pytest.mark.parametrize(
    "headers",
    [
        {},  # old builds / curl
        {"X-Client-App": "web", "X-App-Platform": "web", "X-App-Version": "0.0.1"},
        {"X-Client-App": "admin-panel", "X-App-Version": "0.0.1"},
        {"X-Client-App": "unknown-app", "X-App-Platform": "android", "X-App-Version": "0.0.1"},
        {"X-Client-App": "customer-app", "X-App-Platform": "android"},  # no version
        {"X-Client-App": "customer-app", "X-App-Version": "0.0.1"},     # no platform
        {"X-Client-App": "customer-app", "X-App-Platform": "android", "X-App-Version": "garbage"},
    ],
)
def test_requests_that_cannot_be_judged_are_not_blocked(client, policy_rows, headers):
    policy_rows(
        customer_app_android_min_version="1.5.0",
        customer_app_ios_min_version="1.5.0",
    )
    assert client.get(MISSING, headers=headers).status_code == 404


def test_policy_read_failure_does_not_block(client, monkeypatch):
    async def _boom(db):
        raise RuntimeError("db down")

    monkeypatch.setattr(ca, "_fetch_policy_rows", _boom)
    monkeypatch.setattr(database, "get_db", lambda: object())
    assert client.get(MISSING, headers=CUSTOMER_ANDROID_1_4).status_code == 404


def test_no_headers_never_reads_the_policy(client, monkeypatch):
    async def _fail(db):
        raise AssertionError("policy must not be read for header-less requests")

    monkeypatch.setattr(ca, "_fetch_policy_rows", _fail)
    assert client.get(MISSING).status_code == 404


def test_cors_preflight_allows_client_headers(client):
    origin = settings.allowed_origins_list[0] if settings.allowed_origins_list else None
    if not origin:
        pytest.skip("test.env has no ALLOWED_ORIGINS")
    r = client.options(
        f"{API}/app-config",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-client-app, x-app-version, x-app-platform",
        },
    )
    assert r.status_code == 200, r.text
    allowed = r.headers.get("access-control-allow-headers", "").lower()
    for h in ("x-client-app", "x-app-version", "x-app-platform"):
        assert h in allowed


# =====================================================================
# Role rule: pure decision table
# =====================================================================
def _policy(**flag_values):
    return ca.ClientPolicy(values={k: ("true" if v else "false") for k, v in flag_values.items()})


ALL_OFF = _policy()
VENDOR_BLOCK = _policy(enforce_partner_app_for_vendors=True)
PARTNER_ROLES = _policy(enforce_partner_app_roles=True)
STRICT = _policy(require_client_app_header_for_vendors=True)


@pytest.mark.parametrize("client_app", [None, "customer-app", "partner-app", "web", "admin-panel"])
@pytest.mark.parametrize("role", ["customer", "vendor", "regular_buyer", "admin", "relationship_manager"])
def test_all_flags_off_blocks_nobody(client_app, role, flags):
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=False, ENFORCE_PARTNER_APP_ROLES=False, REQUIRE_CLIENT_APP_HEADER_FOR_VENDORS=False)
    assert ca.client_role_violation(client_app, role, ALL_OFF) is None


def test_vendor_block_decisions():
    v = ca.client_role_violation("customer-app", "vendor", VENDOR_BLOCK)
    assert (v.status_code, v.error_code, v.detail) == (403, "USE_PARTNER_APP", "Salon partner accounts use the Lubist Partner app.")
    rb = ca.client_role_violation("customer-app", "regular_buyer", VENDOR_BLOCK)
    assert (rb.status_code, rb.error_code) == (403, "USE_WEB_PORTAL")
    assert "website" in rb.detail
    for app_name in (None, "web", "partner-app", "admin-panel"):
        assert ca.client_role_violation(app_name, "vendor", VENDOR_BLOCK) is None
    for role in ("customer", "admin", "relationship_manager"):
        assert ca.client_role_violation("customer-app", role, VENDOR_BLOCK) is None


def test_partner_app_role_decisions():
    assert ca.client_role_violation("partner-app", "vendor", PARTNER_ROLES) is None
    for role in ("customer", "admin", "relationship_manager"):
        v = ca.client_role_violation("partner-app", role, PARTNER_ROLES)
        assert (v.status_code, v.error_code) == (403, "USE_CUSTOMER_APP")
    rb = ca.client_role_violation("partner-app", "regular_buyer", PARTNER_ROLES)
    assert (rb.status_code, rb.error_code) == (403, "USE_WEB_PORTAL")
    # Rule is scoped to the partner app.
    assert ca.client_role_violation("customer-app", "customer", PARTNER_ROLES) is None
    assert ca.client_role_violation("web", "admin", PARTNER_ROLES) is None


def test_strict_mode_decisions():
    v = ca.client_role_violation(None, "vendor", STRICT)
    assert (v.status_code, v.error_code) == (403, "USE_PARTNER_APP")
    assert ca.client_role_violation(None, "regular_buyer", STRICT).error_code == "USE_WEB_PORTAL"
    for app_name in ("web", "partner-app", "admin-panel"):
        assert ca.client_role_violation(app_name, "vendor", STRICT) is None
    # Strict mode alone does not block an identified customer-app vendor.
    assert ca.client_role_violation("customer-app", "vendor", STRICT) is None
    for role in ("customer", "admin"):
        assert ca.client_role_violation(None, role, STRICT) is None


def test_role_from_auth_result_shapes():
    token = create_access_token({"sub": "u1", "email": "a@b.co", "user_role": "vendor"})
    assert ca.role_from_auth_result({"user": {"user_role": "vendor"}}) == "vendor"
    assert ca.role_from_auth_result({"data": {"user": {"role": "regular_buyer"}}}) == "regular_buyer"
    assert ca.role_from_auth_result({"access_token": token, "refresh_token": "x"}) == "vendor"
    assert ca.role_from_auth_result({"success": True}) is None
    assert ca.role_from_auth_result(None) is None


# =====================================================================
# Role rule at login / refresh / OTP login (real routes, fake DB)
# =====================================================================
@pytest.fixture()
def auth_env(mock_auth, monkeypatch):
    """
    mock_auth, with the version middleware reading the same fake DB.

    The middleware loads the policy through get_db() (it sits outside FastAPI's
    dependency injection); pointing that at the fake keeps it off the network
    and lets one cached policy serve both the middleware and the route.
    """
    monkeypatch.setattr(database, "get_db", lambda: mock_auth.db)
    return mock_auth


def _vendor_login(mock_auth, role="vendor", headers=None):
    prof = mock_auth.seed_profile(user_role=role)
    mock_auth.gotrue.sign_in_user = _User(prof["id"], prof["email"])
    return mock_auth.client.post(
        f"{API}/auth/login", json={"email": prof["email"], "password": "pw"}, headers=headers or {}
    )


CUSTOMER_APP_HDR = {"X-Client-App": "customer-app", "X-App-Platform": "android", "X-App-Version": "1.4.2"}
PARTNER_APP_HDR = {"X-Client-App": "partner-app", "X-App-Platform": "android", "X-App-Version": "1.0.0"}


def test_login_vendor_on_customer_app_allowed_when_flag_off(auth_env, flags):
    mock_auth = auth_env
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=False)
    r = _vendor_login(mock_auth, headers=CUSTOMER_APP_HDR)
    assert r.status_code == 200, r.text


def test_login_vendor_on_customer_app_blocked_when_flag_on(auth_env, flags):
    mock_auth = auth_env
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=True)
    r = _vendor_login(mock_auth, headers=CUSTOMER_APP_HDR)
    assert r.status_code == 403, r.text
    assert r.json()["error_code"] == "USE_PARTNER_APP"
    assert r.json()["message"] == "Salon partner accounts use the Lubist Partner app."
    assert "access_token" not in r.json()


def test_login_regular_buyer_on_customer_app_blocked(auth_env, flags):
    mock_auth = auth_env
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=True)
    r = _vendor_login(mock_auth, role="regular_buyer", headers=CUSTOMER_APP_HDR)
    assert r.status_code == 403
    assert r.json()["error_code"] == "USE_WEB_PORTAL"


@pytest.mark.parametrize("headers", [{}, {"X-Client-App": "web"}, PARTNER_APP_HDR, {"X-Client-App": "admin-panel"}])
def test_login_vendor_elsewhere_unaffected_by_flag(auth_env, flags, headers):
    mock_auth = auth_env
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=True, ENFORCE_PARTNER_APP_ROLES=True)
    assert _vendor_login(mock_auth, headers=headers).status_code == 200


def test_login_customer_on_customer_app_unaffected(auth_env, flags):
    mock_auth = auth_env
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=True, REQUIRE_CLIENT_APP_HEADER_FOR_VENDORS=True)
    assert _vendor_login(mock_auth, role="customer", headers=CUSTOMER_APP_HDR).status_code == 200


def test_login_flag_from_system_config_without_env(auth_env, flags):
    mock_auth = auth_env
    """The no-redeploy lever: a system_config row turns the block on."""
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=False)
    mock_auth.db.table("system_config").rows.append(
        {"config_key": "enforce_partner_app_for_vendors", "config_value": "true", "is_active": True}
    )
    r = _vendor_login(mock_auth, headers=CUSTOMER_APP_HDR)
    assert r.status_code == 403
    assert r.json()["error_code"] == "USE_PARTNER_APP"


def test_login_system_config_can_turn_env_flag_off(auth_env, flags):
    mock_auth = auth_env
    """...and the same row is the rollback, even with the env var on."""
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=True)
    mock_auth.db.table("system_config").rows.append(
        {"config_key": "enforce_partner_app_for_vendors", "config_value": "false", "is_active": True}
    )
    assert _vendor_login(mock_auth, headers=CUSTOMER_APP_HDR).status_code == 200


def test_partner_app_rule_at_login(auth_env, flags):
    mock_auth = auth_env
    flags(ENFORCE_PARTNER_APP_ROLES=True)
    r = _vendor_login(mock_auth, role="customer", headers=PARTNER_APP_HDR)
    assert r.status_code == 403
    assert r.json()["error_code"] == "USE_CUSTOMER_APP"
    assert _vendor_login(mock_auth, role="vendor", headers=PARTNER_APP_HDR).status_code == 200


def test_partner_app_rule_off_by_default(auth_env, flags):
    mock_auth = auth_env
    flags(ENFORCE_PARTNER_APP_ROLES=False)
    assert _vendor_login(mock_auth, role="customer", headers=PARTNER_APP_HDR).status_code == 200


def test_strict_mode_at_login(auth_env, flags):
    mock_auth = auth_env
    flags(REQUIRE_CLIENT_APP_HEADER_FOR_VENDORS=True)
    r = _vendor_login(mock_auth, headers={})
    assert r.status_code == 403
    assert r.json()["error_code"] == "USE_PARTNER_APP"
    # Unknown values do not identify a client either.
    assert _vendor_login(mock_auth, headers={"X-Client-App": "curl"}).status_code == 403
    assert _vendor_login(mock_auth, headers={"X-Client-App": "web"}).status_code == 200
    assert _vendor_login(mock_auth, headers=PARTNER_APP_HDR).status_code == 200


def test_refresh_blocked_for_vendor_on_customer_app(auth_env, flags):
    mock_auth = auth_env
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=True)
    prof = mock_auth.seed_profile(user_role="vendor")
    refresh = create_refresh_token({"sub": prof["id"], "email": prof["email"], "user_role": "vendor"})
    r = mock_auth.client.post(f"{API}/auth/refresh", json={"refresh_token": refresh}, headers=CUSTOMER_APP_HDR)
    assert r.status_code == 403, r.text
    assert r.json()["error_code"] == "USE_PARTNER_APP"
    r = mock_auth.client.post(f"{API}/auth/refresh", json={"refresh_token": refresh}, headers=PARTNER_APP_HDR)
    assert r.status_code == 200, r.text


def test_phone_otp_login_blocked_for_regular_buyer_on_customer_app(auth_env, flags):
    mock_auth = auth_env
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=True)
    prof = mock_auth.seed_profile(user_role="regular_buyer", phone="+919876543210", phone_verified=True)
    body = {"phone": "9876543210", "otp": "123456", "verification_id": "vid-test-123", "country_code": "91"}
    r = mock_auth.client.post(f"{API}/auth/login/phone/verify-otp", json=body, headers=CUSTOMER_APP_HDR)
    assert r.status_code == 403, r.text
    assert r.json()["error_code"] == "USE_WEB_PORTAL"
    r = mock_auth.client.post(f"{API}/auth/login/phone/verify-otp", json=body, headers={"X-Client-App": "web"})
    assert r.status_code == 200, r.text
    assert prof["id"]


# =====================================================================
# Role rule in get_current_user (restored sessions)
# =====================================================================
@pytest.fixture()
def guarded_app():
    """A minimal app with one route behind the real get_current_user."""
    db = FakeSupabase()
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/api/whoami")
    async def whoami(user: TokenData = Depends(get_current_user)):
        return {"role": user.user_role}

    @app.post(f"{API}/auth/logout")
    async def logout(user: TokenData = Depends(get_current_user)):
        return {"ok": True}

    app.dependency_overrides[get_db_client] = lambda: db

    def token_for(role):
        uid = str(uuid.uuid4())
        db.table("profiles").rows.append(
            {"id": uid, "email": f"{uid[:8]}@example.com", "user_role": role, "is_active": True, "is_internal": False}
        )
        return create_access_token({"sub": uid, "email": f"{uid[:8]}@example.com", "user_role": role})

    client = TestClient(app)
    client.token_for = token_for
    client.db = db
    return client


def _auth(token, extra=None):
    return {"Authorization": f"Bearer {token}", **(extra or {})}


def test_restored_vendor_session_blocked_in_customer_app(guarded_app, flags):
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=True)
    token = guarded_app.token_for("vendor")
    r = guarded_app.get("/api/whoami", headers=_auth(token, CUSTOMER_APP_HDR))
    assert r.status_code == 403, r.text
    assert r.json()["error_code"] == "USE_PARTNER_APP"
    assert guarded_app.get("/api/whoami", headers=_auth(token, PARTNER_APP_HDR)).status_code == 200
    assert guarded_app.get("/api/whoami", headers=_auth(token)).status_code == 200


def test_restored_vendor_session_allowed_when_flag_off(guarded_app, flags):
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=False)
    token = guarded_app.token_for("vendor")
    assert guarded_app.get("/api/whoami", headers=_auth(token, CUSTOMER_APP_HDR)).status_code == 200


def test_blocked_vendor_can_still_log_out(guarded_app, flags):
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=True)
    token = guarded_app.token_for("vendor")
    r = guarded_app.post(f"{API}/auth/logout", headers=_auth(token, CUSTOMER_APP_HDR))
    assert r.status_code == 200, r.text


def test_partner_app_rule_in_get_current_user(guarded_app, flags):
    flags(ENFORCE_PARTNER_APP_ROLES=True)
    for role in ("customer", "admin"):
        r = guarded_app.get("/api/whoami", headers=_auth(guarded_app.token_for(role), PARTNER_APP_HDR))
        assert r.status_code == 403
        assert r.json()["error_code"] == "USE_CUSTOMER_APP"
    assert guarded_app.get("/api/whoami", headers=_auth(guarded_app.token_for("vendor"), PARTNER_APP_HDR)).status_code == 200


def test_strict_mode_in_get_current_user(guarded_app, flags):
    flags(REQUIRE_CLIENT_APP_HEADER_FOR_VENDORS=True)
    vendor = guarded_app.token_for("vendor")
    assert guarded_app.get("/api/whoami", headers=_auth(vendor)).json()["error_code"] == "USE_PARTNER_APP"
    assert guarded_app.get("/api/whoami", headers=_auth(vendor, {"X-Client-App": "web", "X-App-Platform": "web"})).status_code == 200
    # Customers and admins without headers (legacy web, scripts) are untouched.
    assert guarded_app.get("/api/whoami", headers=_auth(guarded_app.token_for("customer"))).status_code == 200
    assert guarded_app.get("/api/whoami", headers=_auth(guarded_app.token_for("admin"))).status_code == 200


def test_web_and_admin_panel_never_blocked(guarded_app, flags):
    flags(ENFORCE_PARTNER_APP_FOR_VENDORS=True, ENFORCE_PARTNER_APP_ROLES=True, REQUIRE_CLIENT_APP_HEADER_FOR_VENDORS=True)
    for role in ("customer", "vendor", "regular_buyer", "admin", "relationship_manager"):
        token = guarded_app.token_for(role)
        for hdr in ({"X-Client-App": "web", "X-App-Platform": "web"}, {"X-Client-App": "admin-panel"}):
            assert guarded_app.get("/api/whoami", headers=_auth(token, hdr)).status_code == 200, (role, hdr)


def test_customer_session_never_reads_policy(guarded_app, monkeypatch):
    """The common path (customer, no partner-app header) costs no policy lookup."""
    async def _fail(db):
        raise AssertionError("policy read for a request no rule can apply to")

    monkeypatch.setattr(ca, "_fetch_policy_rows", _fail)
    token = guarded_app.token_for("customer")
    assert guarded_app.get("/api/whoami", headers=_auth(token, CUSTOMER_APP_HDR)).status_code == 200
