"""
Partner Service - Business Logic for "Partner with us" onboarding inquiries
Handles partner request submissions, status updates, and queries
"""
import logging
from typing import Dict, Any, Optional, get_args
import uuid

from fastapi import HTTPException, status

from app.schemas.request.partner import PartnerRequestStatusUpdate
from app.services.activity_log_service import ActivityLogger

logger = logging.getLogger(__name__)


class PartnerService:
    """
    Service for "Partner with us" request operations.
    Handles public submission and admin review (list, get, status update).
    """

    # Single source of truth: allowed status values derived from the
    # PartnerRequestStatusUpdate.status Literal at runtime.
    VALID_STATUSES = set(
        get_args(PartnerRequestStatusUpdate.model_fields['status'].annotation)
    )

    def __init__(self, db_client):
        self.db = db_client

    async def submit_request(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Submit a new partner request.

        Args:
            data: Dict with owner_name, shop_name, shop_type, email, phone, location

        Returns:
            Dict with id and confirmation message
        """
        try:
            request_id = str(uuid.uuid4())

            request_data = {
                "id": request_id,
                "owner_name": data["owner_name"],
                "shop_name": data["shop_name"],
                "shop_type": data["shop_type"],
                "email": data["email"],
                "phone": data["phone"],
                "location": data["location"],
                "status": "new",
            }

            result = self.db.table("partner_requests").insert(request_data).execute()

            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to save partner request"
                )

            logger.info(f"Partner request {request_id} submitted by {data.get('email')}")

            # Best-effort activity log (public submission, no user_id)
            try:
                await ActivityLogger.log(
                    user_id=None,
                    action="partner_request_submitted",
                    entity_type="partner_request",
                    entity_id=request_id,
                    details={
                        "owner_name": data.get("owner_name"),
                        "shop_name": data.get("shop_name"),
                        "shop_type": data.get("shop_type"),
                        "email": data.get("email"),
                        "phone": data.get("phone"),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to log partner request activity: {str(e)}")

            return {
                "id": request_id,
                "message": "Thank you! Your request has been received. Our team will contact you soon.",
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error submitting partner request: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to submit partner request. Please try again later."
            )

    def get_requests(
        self,
        status_filter: Optional[str] = None,
        shop_type_filter: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Get partner requests with optional filters.

        Args:
            status_filter: Filter by request status
            shop_type_filter: Filter by shop type
            search: Search owner name, shop name, email, or phone
            skip: Pagination offset
            limit: Results per page
        """
        try:
            matching_ids = None
            if search:
                term = search.strip()
                if term:
                    pattern = f"%{term}%"
                    id_set = set()
                    for column in ("owner_name", "shop_name", "email", "phone", "location"):
                        try:
                            rows = (
                                self.db.table("partner_requests")
                                .select("id")
                                .ilike(column, pattern)
                                .execute()
                            )
                            for row in rows.data or []:
                                id_set.add(row["id"])
                        except Exception as col_err:
                            logger.warning(
                                "Partner search skipped column %s: %s", column, col_err
                            )
                    matching_ids = list(id_set)
                    if not matching_ids:
                        return {"requests": [], "count": 0, "total": 0}

            query = self.db.table("partner_requests").select("*", count="exact")

            if matching_ids is not None:
                query = query.in_("id", matching_ids)
            if status_filter:
                query = query.eq("status", status_filter)
            if shop_type_filter:
                query = query.eq("shop_type", shop_type_filter)

            result = (
                query.order("created_at", desc=True)
                .range(skip, skip + limit - 1)
                .execute()
            )

            return {
                "requests": result.data or [],
                "count": len(result.data or []),
                "total": result.count if result.count is not None else len(result.data or []),
            }

        except Exception as e:
            logger.error(f"Error fetching partner requests: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch partner requests"
            )

    def get_request_by_id(self, request_id: str) -> Dict[str, Any]:
        """Get a specific partner request by ID."""
        try:
            result = (
                self.db.table("partner_requests").select("*").eq("id", request_id).execute()
            )

            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Partner request not found"
                )

            return result.data[0]

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching partner request {request_id}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch partner request"
            )

    async def update_request_status(
        self,
        request_id: str,
        new_status: str,
        admin_notes: Optional[str] = None,
        admin_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update a partner request's status and notes."""
        try:
            if new_status not in self.VALID_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status. Must be one of: {', '.join(self.VALID_STATUSES)}"
                )

            update_dict = {"status": new_status}
            if admin_notes is not None:
                update_dict["admin_notes"] = admin_notes

            result = (
                self.db.table("partner_requests")
                .update(update_dict)
                .eq("id", request_id)
                .execute()
            )

            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Partner request not found"
                )

            logger.info(f"Partner request {request_id} updated to {new_status}")

            try:
                request_data = result.data[0]
                await ActivityLogger.log(
                    user_id=admin_user_id,
                    action="partner_request_status_updated",
                    entity_type="partner_request",
                    entity_id=request_id,
                    details={
                        "shop_name": request_data.get("shop_name"),
                        "new_status": new_status,
                        "admin_notes": admin_notes,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to log partner request status update: {str(e)}")

            return result.data[0]

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating partner request {request_id}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update partner request"
            )
