"""
Shared pytest fixtures and test-environment bootstrap.

IMPORTANT: This module loads tests/test.env into the process environment
*before* any application module (and therefore app.core.config.Settings) is
imported. pytest imports the top-level conftest.py before collecting test
modules, so doing the load here guarantees Settings() sees a complete, valid
configuration and never raises on missing env vars in CI.

Two tiers of tests:
  * Smoke tests (no marker) — boot the app, hit DB-free endpoints. No stack.
  * Integration tests (@pytest.mark.integration) — run against a LOCAL Supabase
    stack (`supabase start`). The `_local_supabase` fixture pulls the live keys
    via `supabase status -o env`, overrides settings, and resets the cached
    Supabase clients so the app talks to the local stack. If the stack is not
    running, integration tests are skipped (never failed) so the smoke suite
    still runs anywhere.
"""
import os
import re
import subprocess
import uuid
from pathlib import Path

from dotenv import load_dotenv

# --- Load the test environment BEFORE importing any app code -----------------
_TEST_ENV = Path(__file__).parent / "test.env"
# override=True so a developer's real .env / shell vars never leak into tests.
load_dotenv(_TEST_ENV, override=True)

import pytest  # noqa: E402  (import after env load is intentional)
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _disable_app_rate_limiter():
    """
    Turn off the slowapi limiter for the whole test session. The suite logs in /
    signs up many times from one client IP; the production limits (login 5/min,
    signup 3/min) would otherwise throttle the tests. Flow correctness — not the
    limiter — is what these tests verify. (Write a dedicated test that flips this
    back on if you ever want to assert the limiting itself.)
    """
    from app.core.rate_limit import limiter
    limiter.enabled = False
    yield


# =====================================================================
# SMOKE TIER (no running stack required)
# =====================================================================
@pytest.fixture(scope="session")
def app():
    """The FastAPI application, imported after the test env is in place."""
    from main import app as fastapi_app
    return fastapi_app


@pytest.fixture()
def client(app):
    """
    Lightweight TestClient that does NOT run the app lifespan, so smoke tests
    can hit DB-free endpoints (/health, /) without a running Supabase stack.
    """
    return TestClient(app)


# =====================================================================
# INTEGRATION TIER (requires `supabase start`)
# =====================================================================
def _read_supabase_env() -> dict | None:
    """
    Return the live local-stack credentials via `supabase status -o env`,
    or None if the stack isn't running / the CLI is unavailable.
    """
    try:
        proc = subprocess.run(
            ["supabase", "status", "-o", "env"],
            capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None

    env: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        m = re.match(r'^([A-Z_]+)="?(.*?)"?$', line.strip())
        if m:
            env[m.group(1)] = m.group(2)
    if not env.get("API_URL") or not env.get("SERVICE_ROLE_KEY"):
        return None
    return env


@pytest.fixture(scope="session")
def _local_supabase():
    """
    Point the app at the running local Supabase stack using its REAL keys.

    The keys in tests/test.env are deliberately fake (they make Settings()
    validate for the smoke suite) — they do NOT authenticate against the stack.
    Here we fetch the live keys and override settings + reset the cached
    Supabase singletons so every client the app builds targets local Supabase.
    """
    env = _read_supabase_env()
    if env is None:
        pytest.skip("Local Supabase stack not running (`supabase start`).")

    from app.core.config import settings
    settings.SUPABASE_URL = env["API_URL"]
    settings.SUPABASE_ANON_KEY = env["ANON_KEY"]
    settings.SUPABASE_SERVICE_ROLE_KEY = env["SERVICE_ROLE_KEY"]

    # Reset cached singletons so they rebuild with the live URL/keys.
    import app.core.database as database
    database._db_client = None
    database._auth_client = None
    database._storage_client = None

    yield settings


@pytest.fixture()
def service_client(_local_supabase):
    """Service-role Supabase client for seeding and cleanup (bypasses RLS)."""
    from app.core.database import get_db
    return get_db()


@pytest.fixture()
def integration_client(_local_supabase, app):
    """TestClient wired to the live local stack (auth endpoints need no lifespan)."""
    return TestClient(app)


@pytest.fixture()
def make_user(service_client):
    """
    Factory that creates a PRE-CONFIRMED auth user of any role plus its profile
    row, so `/auth/login` works (the stack has email confirmations enabled).

    Usage:
        user = make_user(role="vendor")
        # -> {"id", "email", "password", "role", "full_name"}

    Created users (and profiles) are deleted on teardown.
    """
    created_ids: list[str] = []
    default_password = "TestPassw0rd!23"

    def _make(role: str = "customer", password: str = default_password, **profile_extra):
        email = f"test+{role}+{uuid.uuid4().hex[:10]}@example.com"
        full_name = profile_extra.pop("full_name", f"Test {role.title()}")

        # 1) Create a confirmed auth user via the GoTrue admin API.
        res = service_client.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": full_name, "user_role": role},
        })
        user_id = res.user.id
        created_ids.append(user_id)

        # 2) Upsert the profile row the app reads on login.
        profile = {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "user_role": role,
            "is_active": True,
            "age": 30,
            "gender": "other",
            **profile_extra,
        }
        service_client.table("profiles").upsert(profile).execute()

        return {"id": user_id, "email": email, "password": password,
                "role": role, "full_name": full_name}

    yield _make

    # Teardown: remove profiles + auth users we created.
    for uid in created_ids:
        try:
            service_client.table("profiles").delete().eq("id", uid).execute()
        except Exception:
            pass
        try:
            service_client.auth.admin.delete_user(uid)
        except Exception:
            pass


@pytest.fixture()
def make_salon(service_client):
    """
    Factory that seeds a salon (plus a service category) directly via the
    service-role client, so booking/catalog flows have prerequisite state
    without depending on the admin/vendor creation endpoints.

    Cleanup removes, in FK-safe order, any bookings/services referencing the
    seeded salons, then the salons and the category.
    """
    salon_ids: list[str] = []
    category_ids: list[str] = []

    def _make(vendor_id: str | None = None, **extra):
        cat = service_client.table("service_categories").insert(
            {"name": f"Test Category {uuid.uuid4().hex[:6]}"}
        ).execute()
        category_id = cat.data[0]["id"]
        category_ids.append(category_id)

        salon = {
            "business_name": f"Test Salon {uuid.uuid4().hex[:6]}",
            "email": f"salon+{uuid.uuid4().hex[:8]}@example.com",
            "phone": "+919999999999",
            "address": "1 Test Street",
            "city": "Testville",
            "state": "Test State",
            "pincode": "560001",
            "vendor_id": vendor_id,
            **extra,
        }
        res = service_client.table("salons").insert(salon).execute()
        row = res.data[0]
        row["_category_id"] = category_id
        salon_ids.append(row["id"])
        return row

    yield _make

    for sid in salon_ids:
        for table in ("bookings", "services"):
            try:
                service_client.table(table).delete().eq("salon_id", sid).execute()
            except Exception:
                pass
        try:
            service_client.table("salons").delete().eq("id", sid).execute()
        except Exception:
            pass
    for cid in category_ids:
        try:
            service_client.table("service_categories").delete().eq("id", cid).execute()
        except Exception:
            pass


@pytest.fixture()
def make_service(service_client, make_salon):
    """
    Factory for a service row. Auto-seeds a salon if `salon_id` isn't given.
    Returns the inserted service row (includes its salon_id).
    """
    def _make(salon_id: str | None = None, category_id: str | None = None,
              price: float = 500.0, duration_minutes: int = 30, **extra):
        if salon_id is None:
            salon = make_salon()
            salon_id = salon["id"]
            category_id = category_id or salon["_category_id"]
        if category_id is None:
            cat = service_client.table("service_categories").insert(
                {"name": f"Test Category {uuid.uuid4().hex[:6]}"}
            ).execute()
            category_id = cat.data[0]["id"]

        service = {
            "name": f"Test Service {uuid.uuid4().hex[:6]}",
            "category_id": category_id,
            "salon_id": salon_id,
            "price": price,
            "duration_minutes": duration_minutes,
            **extra,
        }
        res = service_client.table("services").insert(service).execute()
        return res.data[0]

    return _make


def auth_header(token: str) -> dict:
    """Convenience for building a Bearer auth header in tests."""
    return {"Authorization": f"Bearer {token}"}
