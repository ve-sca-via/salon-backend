"""
E2E configuration: where to point the suite and which secrets it may use.

Sources, highest priority first:
  1. Real environment variables (CI injects these from repo secrets).
  2. tests/e2e/.env.staging (local; git-ignored by `.env.*`).

Every key is prefixed `E2E_` on purpose: tests/conftest.py force-loads the
dummy tests/test.env (SUPABASE_URL=localhost, ...) into os.environ for the
unit tiers, and an un-prefixed key would silently pick those up.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

E2E_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = E2E_DIR / ".env.staging"
REPORTS_DIR = E2E_DIR / "reports"

DEFAULT_BASE_URL = "https://salon-backend-staging.up.railway.app"
API_PREFIX = "/api/v1"

# Production backends / databases. The suite creates and deletes data, so it
# refuses these unless --allow-prod / E2E_ALLOW_PROD=1 is given explicitly.
PROD_HOST_SUFFIXES = ("ondigitalocean.app", "lubist.com", "lubist.app")
PROD_SUPABASE_REFS = ("xqtaebvovddqzagnyewo",)


class ProductionTargetError(RuntimeError):
    pass


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class E2EConfig:
    base_url: str
    supabase_url: str | None
    service_role_key: str | None
    anon_key: str | None
    jwt_secret: str | None
    jwt_algorithm: str
    password: str
    razorpay_enabled: bool
    razorpay_key_secret: str | None
    min_interval: float
    keep_data: bool
    allow_prod: bool
    run_id: str = field(default_factory=lambda: "E2E-" + datetime.now().strftime("%Y%m%d%H%M%S"))

    @property
    def api(self) -> str:
        return self.base_url.rstrip("/") + API_PREFIX

    @property
    def run_tag(self) -> str:
        """Lower-case, email/slug-safe form of the run id."""
        return self.run_id.lower()

    def missing_seed_secrets(self) -> list[str]:
        missing = []
        if not self.supabase_url:
            missing.append("E2E_SUPABASE_URL")
        if not self.service_role_key:
            missing.append("E2E_SUPABASE_SERVICE_ROLE_KEY")
        if not self.jwt_secret:
            missing.append("E2E_JWT_SECRET_KEY")
        return missing


def load_config(base_url: str | None = None, keep_data: bool = False, allow_prod: bool = False) -> E2EConfig:
    file_values = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}

    def get(key: str, default: str | None = None) -> str | None:
        value = os.environ.get(key)
        if value not in (None, ""):
            return value
        value = file_values.get(key)
        return value if value not in (None, "") else default

    cfg = E2EConfig(
        base_url=(base_url or get("E2E_BASE_URL", DEFAULT_BASE_URL)).rstrip("/"),
        supabase_url=get("E2E_SUPABASE_URL"),
        service_role_key=get("E2E_SUPABASE_SERVICE_ROLE_KEY"),
        anon_key=get("E2E_SUPABASE_ANON_KEY"),
        jwt_secret=get("E2E_JWT_SECRET_KEY"),
        jwt_algorithm=get("E2E_JWT_ALGORITHM", "HS256"),
        password=get("E2E_PASSWORD", "Test@1234"),
        razorpay_enabled=_truthy(get("E2E_RAZORPAY_ENABLED")),
        razorpay_key_secret=get("E2E_RAZORPAY_KEY_SECRET"),
        # Global slowapi default is 100 req/min per client IP; stay under it.
        min_interval=float(get("E2E_MIN_INTERVAL", "0.65")),
        keep_data=keep_data or _truthy(get("E2E_KEEP_DATA")),
        allow_prod=allow_prod or _truthy(get("E2E_ALLOW_PROD")),
    )
    assert_not_production(cfg)
    return cfg


def assert_not_production(cfg: E2EConfig) -> None:
    if cfg.allow_prod:
        return
    host = (urlparse(cfg.base_url).hostname or "").lower()
    for suffix in PROD_HOST_SUFFIXES:
        if host == suffix or host.endswith("." + suffix):
            raise ProductionTargetError(
                f"Refusing to run the E2E suite against {host!r}: it looks like PRODUCTION "
                f"(matches {suffix!r}). The suite creates and deletes data and sends emails. "
                "Pass --allow-prod / set E2E_ALLOW_PROD=1 only if you really mean it."
            )
    sb_host = (urlparse(cfg.supabase_url or "").hostname or "").lower()
    for ref in PROD_SUPABASE_REFS:
        if sb_host.startswith(ref + "."):
            raise ProductionTargetError(
                "Refusing to run: E2E_SUPABASE_URL points at the PRODUCTION Supabase project. "
                "Use the staging project's URL/service-role key."
            )
