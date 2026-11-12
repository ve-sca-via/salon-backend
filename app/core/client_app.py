"""
Client identification, minimum-app-version policy and per-app role rules.

Every first-party client identifies itself with three request headers:

    X-Client-App:    customer-app | partner-app | web | admin-panel
    X-App-Version:   semver of the native build, e.g. 1.4.2
    X-App-Platform:  ios | android | web

Three things hang off them, all documented in docs/CLIENT_APPS_AND_VERSIONING.md:

1. The version policy (min supported / latest / store URL / message) per native
   app + platform. It lives in `system_config` rows so an admin can change it
   from the admin panel without a deploy. `GET /api/v1/app-config` serves it.
2. Global enforcement (`ClientVersionMiddleware`): a native app below its
   min_supported_version gets 426 APP_UPDATE_REQUIRED on every API call.
3. Role rules (`enforce_client_app_role`): vendor accounts belong in the
   Lubist Partner app. Off by default, switched on by settings or system_config.

Design rules that keep this a no-op until someone opts in:

* Requests without the headers (web, admin panel, every build shipped before
  this existed) are never blocked by the version check.
* An unparseable version is treated as "not below" and logged - a parse bug
  must never lock real users out.
* If the policy cannot be read (DB blip) we fail OPEN: no 426, flags fall back
  to the env settings.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

from fastapi import status
from jose import jwt
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)

# =====================================================
# HEADERS & VOCABULARY
# =====================================================

CLIENT_APP_HEADER = "X-Client-App"
APP_VERSION_HEADER = "X-App-Version"
APP_PLATFORM_HEADER = "X-App-Platform"

CUSTOMER_APP = "customer-app"
PARTNER_APP = "partner-app"
WEB = "web"
ADMIN_PANEL = "admin-panel"

KNOWN_CLIENT_APPS = (CUSTOMER_APP, PARTNER_APP, WEB, ADMIN_PANEL)
# Apps that have a store build and therefore a version policy.
NATIVE_CLIENT_APPS = (CUSTOMER_APP, PARTNER_APP)

PLATFORM_IOS = "ios"
PLATFORM_ANDROID = "android"
PLATFORM_WEB = "web"
KNOWN_PLATFORMS = (PLATFORM_IOS, PLATFORM_ANDROID, PLATFORM_WEB)
NATIVE_PLATFORMS = (PLATFORM_IOS, PLATFORM_ANDROID)

# Roles that run a salon/business account. Kept out of the customer app.
BUSINESS_ROLES = ("vendor", "regular_buyer")
# Roles the Lubist Partner app supports. regular_buyer is deliberately NOT here:
# regular buyers onboard and buy products on the website (see
# docs/REGULAR_BUYER_WORKFLOW.md), and the partner app only routes `vendor`.
PARTNER_APP_ROLES = ("vendor",)

APP_UPDATE_REQUIRED = "APP_UPDATE_REQUIRED"
USE_PARTNER_APP = "USE_PARTNER_APP"
USE_CUSTOMER_APP = "USE_CUSTOMER_APP"
USE_WEB_PORTAL = "USE_WEB_PORTAL"

USE_PARTNER_APP_MESSAGE = "Salon partner accounts use the Lubist Partner app."
REGULAR_BUYER_MESSAGE = (
    "Business buyer accounts are managed on the Lubist website (www.lubist.com)."
)
USE_CUSTOMER_APP_MESSAGE = (
    "The Lubist Partner app is for salon partner accounts. "
    "Please use the Lubist app instead."
)
DEFAULT_UPDATE_MESSAGE = (
    "A new version of the app is required. Please update to continue."
)

# Paths the version check never blocks: liveness probes and the endpoint an
# outdated app calls to learn that it is outdated.
VERSION_EXEMPT_PATHS = ("/health", "/")


def app_config_path() -> str:
    return f"{settings.API_PREFIX}/app-config"


# Requests the role rule never blocks: a blocked user must still be able to end
# their session server-side.
def _role_exempt_paths() -> Tuple[str, ...]:
    return (
        f"{settings.API_PREFIX}/auth/logout",
        f"{settings.API_PREFIX}/auth/logout-all",
    )


def normalise_client_app(raw: Optional[str]) -> Optional[str]:
    """The known client app named by a header/query value, else None."""
    if not raw:
        return None
    value = raw.strip().lower()
    return value if value in KNOWN_CLIENT_APPS else None


def normalise_platform(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    value = raw.strip().lower()
    return value if value in KNOWN_PLATFORMS else None


# =====================================================
# VERSION PARSING
# =====================================================

_VERSION_RE = re.compile(
    r"^v?(?P<major>\d+)(?:\.(?P<minor>\d+))?(?:\.(?P<patch>\d+))?"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)

ParsedVersion = Tuple[int, int, int, Tuple[Tuple[int, Any], ...]]


def parse_version(raw: Optional[str]) -> Optional[ParsedVersion]:
    """
    Parse a semver-ish string into a comparable tuple, or None if it isn't one.

    Accepts "1", "1.4", "1.4.2", a leading "v", a prerelease ("1.4.2-beta.1")
    and build metadata ("1.4.2+42", ignored). Missing minor/patch count as 0.
    A prerelease sorts before its release, as semver says (1.4.2-beta < 1.4.2).
    """
    if raw is None:
        return None
    match = _VERSION_RE.match(str(raw).strip())
    if not match:
        return None
    major = int(match.group("major"))
    minor = int(match.group("minor") or 0)
    patch = int(match.group("patch") or 0)
    pre = match.group("pre")
    if pre is None:
        # (1,) sorts after any (0, ...) prerelease marker below.
        pre_key: Tuple[Tuple[int, Any], ...] = ((1, ""),)
    else:
        parts = []
        for ident in pre.split("."):
            # Numeric identifiers sort before alphanumeric ones, numerically.
            parts.append((0, int(ident)) if ident.isdigit() else (0.5, ident))
        pre_key = tuple([(0, "")] + parts)
    return (major, minor, patch, pre_key)


def compare_versions(a: Optional[str], b: Optional[str]) -> Optional[int]:
    """-1 / 0 / 1 like cmp(); None when either side is missing or unparseable."""
    pa, pb = parse_version(a), parse_version(b)
    if pa is None or pb is None:
        return None
    return (pa > pb) - (pa < pb)


def is_version_below(current: Optional[str], minimum: Optional[str]) -> bool:
    """
    True only when BOTH versions parse and current < minimum.

    Anything we can't read is "not below": locking a user out because of a
    malformed header or a typo in the admin panel is worse than letting one
    outdated request through.
    """
    if not current or not minimum:
        return False
    result = compare_versions(current, minimum)
    if result is None:
        logger.warning(
            "Unparseable app version in version check; not blocking",
            extra={"current_version": current, "min_version": minimum},
        )
        return False
    return result < 0


# =====================================================
# POLICY (system_config backed, cached)
# =====================================================

FLAG_ENFORCE_PARTNER_APP_FOR_VENDORS = "enforce_partner_app_for_vendors"
FLAG_ENFORCE_PARTNER_APP_ROLES = "enforce_partner_app_roles"
FLAG_REQUIRE_CLIENT_APP_HEADER = "require_client_app_header_for_vendors"
FLAG_KEYS = (
    FLAG_ENFORCE_PARTNER_APP_FOR_VENDORS,
    FLAG_ENFORCE_PARTNER_APP_ROLES,
    FLAG_REQUIRE_CLIENT_APP_HEADER,
)


def _key_prefix(client_app: str, platform: Optional[str] = None) -> str:
    base = client_app.replace("-", "_")
    return f"{base}_{platform}" if platform else base


def min_version_key(client_app: str, platform: str) -> str:
    return f"{_key_prefix(client_app, platform)}_min_version"


def latest_version_key(client_app: str, platform: str) -> str:
    return f"{_key_prefix(client_app, platform)}_latest_version"


def store_url_key(client_app: str, platform: str) -> str:
    return f"{_key_prefix(client_app, platform)}_store_url"


def update_message_key(client_app: str) -> str:
    return f"{_key_prefix(client_app)}_update_message"


def _version_policy_keys() -> List[str]:
    keys = []
    for app_name in NATIVE_CLIENT_APPS:
        for platform in NATIVE_PLATFORMS:
            keys += [
                min_version_key(app_name, platform),
                latest_version_key(app_name, platform),
                store_url_key(app_name, platform),
            ]
        keys.append(update_message_key(app_name))
    return keys


VERSION_POLICY_KEYS = tuple(_version_policy_keys())
CLIENT_POLICY_KEYS = frozenset(VERSION_POLICY_KEYS + FLAG_KEYS)

_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


@dataclass
class ClientPolicy:
    """A snapshot of every client-policy system_config value (key -> raw text)."""

    values: Dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> Optional[str]:
        value = self.values.get(key)
        if value is None:
            return None
        value = str(value).strip()
        return value or None  # config_value is NOT NULL; "" means "unset"

    def min_version(self, client_app: str, platform: str) -> Optional[str]:
        return self.get(min_version_key(client_app, platform))

    def latest_version(self, client_app: str, platform: str) -> Optional[str]:
        return self.get(latest_version_key(client_app, platform))

    def store_url(self, client_app: str, platform: str) -> Optional[str]:
        return self.get(store_url_key(client_app, platform))

    def update_message(self, client_app: str) -> Optional[str]:
        return self.get(update_message_key(client_app))

    def flag(self, key: str, default: bool) -> bool:
        """system_config override if it is a readable boolean, else the env default."""
        raw = self.get(key)
        if raw is None:
            return default
        lowered = raw.lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        logger.warning(f"system_config '{key}' is not a boolean ({raw!r}); using env default")
        return default

    @property
    def enforce_partner_app_for_vendors(self) -> bool:
        return self.flag(FLAG_ENFORCE_PARTNER_APP_FOR_VENDORS, settings.ENFORCE_PARTNER_APP_FOR_VENDORS)

    @property
    def enforce_partner_app_roles(self) -> bool:
        return self.flag(FLAG_ENFORCE_PARTNER_APP_ROLES, settings.ENFORCE_PARTNER_APP_ROLES)

    @property
    def require_client_app_header_for_vendors(self) -> bool:
        return self.flag(FLAG_REQUIRE_CLIENT_APP_HEADER, settings.REQUIRE_CLIENT_APP_HEADER_FOR_VENDORS)


# (expires_at_monotonic, policy)
_policy_cache: Optional[Tuple[float, ClientPolicy]] = None


def clear_client_policy_cache() -> None:
    """Drop the cached policy (called by ConfigService on every config write)."""
    global _policy_cache
    _policy_cache = None


async def _fetch_policy_rows(db) -> List[Dict[str, Any]]:
    """One round trip for every client-policy key. Patched in unit tests."""
    from app.core.database import db_exec

    response = await db_exec(
        db.table("system_config")
        .select("config_key, config_value, is_active")
        .in_("config_key", sorted(CLIENT_POLICY_KEYS))
    )
    return list(getattr(response, "data", None) or [])


async def get_client_policy(db=None) -> ClientPolicy:
    """
    The current policy, cached for CLIENT_POLICY_CACHE_SECONDS.

    Never raises: a failed read logs and returns an empty policy (= no version
    floor, flags from env), which is NOT cached so the next request retries.
    """
    global _policy_cache
    now = monotonic()
    if _policy_cache is not None and _policy_cache[0] > now:
        return _policy_cache[1]

    try:
        if db is None:
            from app.core.database import get_db

            db = get_db()
        rows = await _fetch_policy_rows(db)
    except Exception as exc:
        logger.warning(f"Could not load client policy from system_config; failing open: {exc}")
        return ClientPolicy()

    values = {
        row["config_key"]: row.get("config_value")
        for row in rows
        if row.get("config_key") in CLIENT_POLICY_KEYS and row.get("is_active", True) is not False
    }
    policy = ClientPolicy(values=values)
    _policy_cache = (now + max(settings.CLIENT_POLICY_CACHE_SECONDS, 0), policy)
    return policy


# =====================================================
# APP CONFIG (the GET /app-config payload)
# =====================================================

def build_app_config(
    policy: ClientPolicy, client_app: str, platform: str, current_version: Optional[str]
) -> Dict[str, Any]:
    min_supported = policy.min_version(client_app, platform)
    latest = policy.latest_version(client_app, platform)
    return {
        "success": True,
        "client_app": client_app,
        "platform": platform,
        "current_version": current_version,
        "min_supported_version": min_supported,
        "latest_version": latest,
        "update_required": is_version_below(current_version, min_supported),
        "update_available": is_version_below(current_version, latest),
        "store_url": policy.store_url(client_app, platform),
        "message": policy.update_message(client_app),
    }


# =====================================================
# GLOBAL VERSION ENFORCEMENT (pure ASGI middleware)
# =====================================================

def _is_version_exempt(path: str) -> bool:
    if path in VERSION_EXEMPT_PATHS or path.startswith("/health/"):
        return True
    app_config = app_config_path()
    return path == app_config or path == app_config + "/"


class ClientVersionMiddleware:
    """
    426 APP_UPDATE_REQUIRED for native apps below their min_supported_version.

    Pure ASGI rather than BaseHTTPMiddleware: it runs on every request, and the
    common case (no X-Client-App, or web/admin-panel) must cost one header
    lookup and nothing else - no DB, no body buffering.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        client_app = normalise_client_app(headers.get(CLIENT_APP_HEADER))
        if client_app not in NATIVE_CLIENT_APPS:
            await self.app(scope, receive, send)
            return

        platform = normalise_platform(headers.get(APP_PLATFORM_HEADER))
        version = headers.get(APP_VERSION_HEADER)
        path = scope.get("path", "")
        if platform not in NATIVE_PLATFORMS or not version or _is_version_exempt(path):
            await self.app(scope, receive, send)
            return

        policy = await get_client_policy()
        minimum = policy.min_version(client_app, platform)
        if not is_version_below(version, minimum):
            await self.app(scope, receive, send)
            return

        logger.info(
            f"Blocked outdated {client_app} {platform} {version} (min {minimum}) on {path}",
            extra={
                "client_app": client_app,
                "platform": platform,
                "app_version": version,
                "min_version": minimum,
                "error_code": APP_UPDATE_REQUIRED,
            },
        )
        response = JSONResponse(
            status_code=status.HTTP_426_UPGRADE_REQUIRED,
            content={
                "success": False,
                "message": policy.update_message(client_app) or DEFAULT_UPDATE_MESSAGE,
                "error_code": APP_UPDATE_REQUIRED,
                "errors": None,
                "min_supported_version": minimum,
                "store_url": policy.store_url(client_app, platform),
            },
        )
        await response(scope, receive, send)


# =====================================================
# ROLE RULES
# =====================================================

def client_app_from_request(request) -> Optional[str]:
    if request is None:
        return None
    return normalise_client_app(request.headers.get(CLIENT_APP_HEADER))


def client_role_violation(
    client_app: Optional[str], role: Optional[str], policy: ClientPolicy
) -> Optional[AppException]:
    """The 403 to raise for this app/role pair under the current flags, or None."""
    if not role:
        return None

    if role in BUSINESS_ROLES:
        blocked = (
            (client_app == CUSTOMER_APP and policy.enforce_partner_app_for_vendors)
            or (client_app is None and policy.require_client_app_header_for_vendors)
        )
        if blocked:
            # Regular buyers operate on the website, not the Partner app, so
            # they get their own code (both mobile apps handle USE_WEB_PORTAL).
            if role == "regular_buyer":
                return AppException(status.HTTP_403_FORBIDDEN, REGULAR_BUYER_MESSAGE, error_code=USE_WEB_PORTAL)
            return AppException(status.HTTP_403_FORBIDDEN, USE_PARTNER_APP_MESSAGE, error_code=USE_PARTNER_APP)

    if (
        client_app == PARTNER_APP
        and role not in PARTNER_APP_ROLES
        and policy.enforce_partner_app_roles
    ):
        if role == "regular_buyer":
            return AppException(status.HTTP_403_FORBIDDEN, REGULAR_BUYER_MESSAGE, error_code=USE_WEB_PORTAL)
        return AppException(status.HTTP_403_FORBIDDEN, USE_CUSTOMER_APP_MESSAGE, error_code=USE_CUSTOMER_APP)

    return None


def _rule_could_apply(client_app: Optional[str], role: Optional[str]) -> bool:
    """Cheap pre-check so most requests never touch the policy cache."""
    return role in BUSINESS_ROLES or client_app == PARTNER_APP


async def enforce_client_app_role(request, role: Optional[str], db=None) -> None:
    """
    Raise 403 if this account may not use the client app the request came from.

    Called from every token-issuing endpoint and from get_current_user. A
    request with no Request object (direct calls in tests/scripts) is exempt.
    """
    if request is None or not role:
        return
    if request.url.path in _role_exempt_paths():
        return
    client_app = client_app_from_request(request)
    if not _rule_could_apply(client_app, role):
        return
    policy = await get_client_policy(db)
    violation = client_role_violation(client_app, role, policy)
    if violation is not None:
        logger.info(
            f"Blocked {role} on client app {client_app or 'none'}: {violation.error_code}",
            extra={"client_app": client_app, "user_role": role, "error_code": violation.error_code},
        )
        raise violation


def role_from_auth_result(result: Any) -> Optional[str]:
    """
    The account role inside a token-issuing endpoint's result.

    Login-style results carry `user.user_role`; vendor registration nests it
    under `data.user.role`; refresh carries only tokens, so fall back to the
    claims of the access token we have just minted (no signature check needed
    - it never left this process).
    """
    if not isinstance(result, dict):
        return None
    candidates = [result, result.get("data") if isinstance(result.get("data"), dict) else None]
    for holder in candidates:
        if not holder:
            continue
        user = holder.get("user")
        if isinstance(user, dict):
            role = user.get("user_role") or user.get("role")
            if role:
                return role
        token = holder.get("access_token")
        if token:
            try:
                return jwt.get_unverified_claims(token).get("user_role")
            except Exception:
                return None
    return None
