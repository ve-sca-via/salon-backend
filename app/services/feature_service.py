"""
Feature Service

CRUD for the feature entitlement registry (feature_flags). Reads for gating go
through app.core.features, which is cached; this module owns the writes and
invalidates that cache after each one.

All endpoints backed by this service are internal-staff-only. A feature-flag
screen visible to the client would list every feature built but not yet sold,
which defeats the purpose of the gate entirely.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.core.features import (
    STATUS_DISABLED,
    STATUS_ENABLED,
    STATUS_INTERNAL,
    get_feature_statuses,
    invalidate_feature_cache,
)

logger = logging.getLogger(__name__)

VALID_STATUSES = {STATUS_INTERNAL, STATUS_ENABLED, STATUS_DISABLED}


class FeatureService:
    """Manage the feature_flags registry."""

    def __init__(self, db_client):
        self.db = db_client

    # ========================================
    # READS
    # ========================================

    async def list_features(self) -> List[Dict[str, Any]]:
        """Full registry with metadata, for the internal flags screen."""
        try:
            response = (
                self.db.table("feature_flags")
                .select("*")
                .order("name")
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to list feature flags: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch feature flags",
            )

    async def get_visible_features(self, is_internal: bool) -> Dict[str, str]:
        """
        The {key: status} map the admin panel uses to decide what to render.

        For a client admin this deliberately omits 'internal' features
        entirely, rather than returning them marked unavailable — the response
        must not disclose that an unsold feature exists. Internal staff get the
        full map so their sidebar shows work in progress.
        """
        statuses = get_feature_statuses(self.db)

        if is_internal:
            return dict(statuses)

        return {
            key: value
            for key, value in statuses.items()
            if value == STATUS_ENABLED
        }

    # ========================================
    # WRITES
    # ========================================

    async def set_status(
        self,
        key: str,
        new_status: str,
        updated_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Change a feature's entitlement status.

        enabled_at / enabled_by are stamped by the update trigger in the
        migration, so the audit trail stays correct no matter who writes.
        """
        if new_status not in VALID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
            )

        try:
            existing = (
                self.db.table("feature_flags")
                .select("key, status")
                .eq("key", key)
                .maybe_single()
                .execute()
            )

            if not getattr(existing, "data", None):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Feature '{key}' is not registered",
                )

            previous_status = existing.data["status"]

            updates: Dict[str, Any] = {"status": new_status}
            if new_status == STATUS_ENABLED and updated_by:
                updates["enabled_by"] = updated_by

            response = (
                self.db.table("feature_flags")
                .update(updates)
                .eq("key", key)
                .execute()
            )

            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update feature flag",
                )

            logger.info(
                f"Feature '{key}' status changed {previous_status} -> {new_status} by {updated_by}"
            )
            return response.data[0]

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update feature flag '{key}': {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update feature flag",
            )
        finally:
            # Always invalidate, even on a failed write: a partial success that
            # raised on the way back would otherwise leave this worker serving
            # a stale value until the TTL expires.
            invalidate_feature_cache()
