"""
Feature Entitlements — cached flag reads

The single source of truth for "does this deployment expose feature X to the
client?". Lives in core (not services) because app.core.auth depends on it for
the RequireFeature dependency; app.services.feature_service owns the writes and
calls invalidate_feature_cache() after each one.

Three states, from the feature_status enum:
    internal  — built but unsold. Internal staff only. Default for new features.
    enabled   — the client has paid; everyone with the right role sees it.
    disabled  — kill switch. Off for everyone, internal staff included.
"""
import logging
from typing import Dict

from app.core.cache import TTLCache

logger = logging.getLogger(__name__)

# Status constants (mirror the feature_status enum in Postgres)
STATUS_INTERNAL = "internal"
STATUS_ENABLED = "enabled"
STATUS_DISABLED = "disabled"

# Read on essentially every admin request, written roughly never, so a short
# TTL is plenty. Writes invalidate this process immediately; the TTL only
# bounds how long *other* workers can serve a stale value after a flip.
_FEATURE_CACHE = TTLCache(ttl_seconds=60)


def get_feature_statuses(db) -> Dict[str, str]:
    """
    Return {feature_key: status} for every registered feature.

    Fails closed: if the table cannot be read, returns {} so unknown features
    resolve to "not enabled" rather than accidentally exposing an unsold
    feature during a database blip.
    """
    def _load() -> Dict[str, str]:
        try:
            response = db.table("feature_flags").select("key, status").execute()
            return {row["key"]: row["status"] for row in (response.data or [])}
        except Exception as e:
            logger.error(f"Failed to load feature flags, treating all as unavailable: {e}")
            return {}

    return _FEATURE_CACHE.get(_load)


def get_feature_status(db, key: str) -> str:
    """
    Status of a single feature. An unregistered key reports 'disabled' — a
    typo in a RequireFeature("blgo") gate closes the door rather than opening it.
    """
    return get_feature_statuses(db).get(key, STATUS_DISABLED)


def is_feature_visible_to(db, key: str, is_internal: bool) -> bool:
    """
    Whether this caller may use the feature at all.

    Internal staff get 'internal' and 'enabled' but NOT 'disabled' — the kill
    switch has to mean off for everyone, or it is useless for taking a broken
    feature out of production.
    """
    status = get_feature_status(db, key)
    if status == STATUS_ENABLED:
        return True
    return status == STATUS_INTERNAL and is_internal


def invalidate_feature_cache() -> None:
    """Drop the cached flags. Called by FeatureService after every write."""
    _FEATURE_CACHE.clear()
