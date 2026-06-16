"""
Banner Service - Business Logic Layer
Handles CRUD + ordering for the admin-managed home-screen carousel banners.

Follows the same service-layer pattern as ProductService: a thin class wrapping a
Supabase client, raising HTTPException for API-facing errors.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def _is_in_window(banner: Dict[str, Any], now: datetime) -> bool:
    """
    Whether a banner is currently within its optional schedule window.

    starts_at/ends_at are optional; a missing bound means "no bound on that side".
    Stored as ISO strings by PostgREST — parsed leniently, and any unparseable
    value is treated as "no bound" so a bad timestamp never hides a banner.
    """
    def _parse(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None

    starts_at = _parse(banner.get("starts_at"))
    ends_at = _parse(banner.get("ends_at"))
    if starts_at and now < starts_at:
        return False
    if ends_at and now > ends_at:
        return False
    return True


class BannerService:
    """Service class for carousel banner operations."""

    def __init__(self, db_client):
        self.db = db_client

    # =====================================================
    # READ
    # =====================================================

    async def list_banners(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        List banners ordered by sort_order (then newest first as a tiebreak).

        Public callers get only active banners that are currently within their
        schedule window. Admin callers (include_inactive=True) get everything,
        unfiltered by window, for management.
        """
        try:
            query = self.db.table("banners").select("*")
            if not include_inactive:
                query = query.eq("is_active", True)

            # Primary sort by sort_order asc; created_at desc breaks ties.
            query = query.order("sort_order", desc=False).order("created_at", desc=True)
            response = query.execute()
            banners = response.data or []

            if not include_inactive:
                now = datetime.now(timezone.utc)
                banners = [b for b in banners if _is_in_window(b, now)]

            logger.info(f"Listed {len(banners)} banners (include_inactive={include_inactive})")
            return banners

        except Exception as e:
            logger.error(f"Error listing banners: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch banners",
            )

    async def get_banner_by_id(self, banner_id: str) -> Dict[str, Any]:
        """Get a single banner by UUID. Raises 404 if not found."""
        try:
            response = (
                self.db.table("banners")
                .select("*")
                .eq("id", banner_id)
                .maybe_single()
                .execute()
            )
            if not response or not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Banner not found: {banner_id}",
                )
            return response.data

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching banner {banner_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch banner",
            )

    # =====================================================
    # WRITE (Admin)
    # =====================================================

    async def create_banner(self, banner_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new banner. Datetimes are serialized to ISO strings for PostgREST."""
        try:
            payload = self._serialize(banner_data)
            response = self.db.table("banners").insert(payload).execute()
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create banner",
                )
            created = response.data[0]
            logger.info(f"Banner created: {created['id']}")
            return created

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating banner: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create banner",
            )

    async def update_banner(self, banner_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update a banner. Only provided fields are changed. Raises 404 if not found."""
        try:
            safe_updates = {k: v for k, v in updates.items() if v is not None}
            if not safe_updates:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No fields provided for update",
                )
            safe_updates.pop("id", None)
            safe_updates.pop("created_at", None)
            payload = self._serialize(safe_updates)

            response = (
                self.db.table("banners")
                .update(payload)
                .eq("id", banner_id)
                .execute()
            )
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Banner not found: {banner_id}",
                )
            updated = response.data[0]
            logger.info(f"Banner updated: {banner_id} (fields: {list(payload.keys())})")
            return updated

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating banner {banner_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update banner",
            )

    async def reorder_banners(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Bulk-update sort_order for a set of banners (one UPDATE per banner).

        Unknown ids are skipped rather than failing the whole batch, so a banner
        deleted in another tab doesn't break a reorder the admin already started.
        """
        updated: List[Dict[str, Any]] = []
        try:
            for item in orders:
                response = (
                    self.db.table("banners")
                    .update({"sort_order": item["sort_order"]})
                    .eq("id", item["id"])
                    .execute()
                )
                if response.data:
                    updated.append(response.data[0])
            logger.info(f"Reordered {len(updated)}/{len(orders)} banners")
            return updated

        except Exception as e:
            logger.error(f"Error reordering banners: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reorder banners",
            )

    async def delete_banner(self, banner_id: str, hard_delete: bool = False) -> Dict[str, Any]:
        """Delete a banner. Soft-delete (is_active=false) by default; hard purges the row."""
        try:
            if hard_delete:
                await self.get_banner_by_id(banner_id)  # 404 if missing
                self.db.table("banners").delete().eq("id", banner_id).execute()
                logger.warning(f"Banner permanently deleted: {banner_id}")
                return {"message": "Banner permanently deleted", "banner_id": banner_id}

            response = (
                self.db.table("banners")
                .update({"is_active": False})
                .eq("id", banner_id)
                .execute()
            )
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Banner not found: {banner_id}",
                )
            logger.info(f"Banner soft-deleted: {banner_id}")
            return {"message": "Banner deactivated", "banner_id": banner_id}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting banner {banner_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete banner",
            )

    # =====================================================
    # HELPERS
    # =====================================================

    @staticmethod
    def _serialize(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert datetime values to ISO strings so PostgREST/JSON accepts them."""
        out: Dict[str, Any] = {}
        for k, v in data.items():
            out[k] = v.isoformat() if isinstance(v, datetime) else v
        return out
