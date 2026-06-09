"""
Integration tests — run the real FastAPI app against a LOCAL Supabase stack
(`supabase start`) with all migrations applied. These exercise the full path:
HTTP -> FastAPI -> Supabase Auth (GoTrue) + Postgres (PostgREST).

They are the backward-compatibility check for schema changes: if a migration
breaks a column or contract these flows rely on, the test goes red BEFORE merge.

Skipped automatically when the local stack isn't running.
"""
import uuid

import pytest

from app.core.config import settings
from tests.conftest import auth_header

pytestmark = pytest.mark.integration

# Routers are mounted under settings.API_PREFIX (see main.py). Build paths from
# it so the tests follow the configured prefix instead of hardcoding "/api".
API = settings.API_PREFIX


def _signup_payload(**overrides):
    email = overrides.pop("email", f"signup+{uuid.uuid4().hex[:10]}@example.com")
    payload = {
        "email": email,
        "password": "TestPassw0rd!23",
        "full_name": "Smoke Customer",
        "age": 28,
        "gender": "female",
    }
    payload.update(overrides)
    return payload


def test_signup_issues_token_and_me_resolves(integration_client):
    """
    Public signup self-issues a JWT (works even with email confirmation on),
    and that token authenticates against /auth/me — proves app<->GoTrue<->DB.
    """
    payload = _signup_payload()
    resp = integration_client.post(f"{API}/auth/signup", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["email"] == payload["email"]

    me = integration_client.get(f"{API}/auth/me", headers=auth_header(body["access_token"]))
    assert me.status_code == 200, me.text
    assert me.json()["user"]["email"] == payload["email"]


def test_login_with_confirmed_user(integration_client, make_user):
    """A pre-confirmed seeded user can log in via email/password."""
    user = make_user(role="customer")
    resp = integration_client.post(
        f"{API}/auth/login", json={"email": user["email"], "password": user["password"]}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["email"] == user["email"]


def test_login_rejects_bad_password(integration_client, make_user):
    user = make_user(role="customer")
    resp = integration_client.post(
        f"{API}/auth/login", json={"email": user["email"], "password": "wrong-password"}
    )
    assert resp.status_code == 401, resp.text


def test_me_requires_authentication(integration_client):
    resp = integration_client.get(f"{API}/auth/me")
    assert resp.status_code in (401, 403), resp.text


def test_vendor_role_round_trips(integration_client, make_user):
    """
    Seeding non-customer roles works and the role survives login -> /auth/me.
    This is the pattern role-gated flow tests (salon/booking/RM) build on.
    """
    vendor = make_user(role="vendor")
    login = integration_client.post(
        f"{API}/auth/login", json={"email": vendor["email"], "password": vendor["password"]}
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = integration_client.get(f"{API}/auth/me", headers=auth_header(token))
    assert me.status_code == 200, me.text
    assert me.json()["user"]["user_role"] == "vendor"
