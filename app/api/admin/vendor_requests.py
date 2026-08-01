"""
Admin Vendor Request Management API Endpoints
Handles vendor join request approvals, rejections, and management
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, status
from typing import List, Optional
from app.core.auth import require_admin, TokenData
from app.core.database import get_db_client
from supabase import Client
from app.schemas import (
    VendorJoinRequestResponse,
    VendorApprovalRequest,
    VendorRejectionRequest
)
from app.services.admin_service import AdminService
from app.services.vendor_approval_service import (
    VendorApprovalService,
    RequestAlreadyReviewedError,
    RequestNotFoundError,
)
from app.services.activity_log_service import ActivityLogger
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_admin_service(db: Client = Depends(get_db_client)) -> AdminService:
    """Dependency injection for AdminService"""
    return AdminService(db_client=db)


def get_approval_service(db: Client = Depends(get_db_client)) -> VendorApprovalService:
    """Dependency injection for VendorApprovalService"""
    return VendorApprovalService(db_client=db)


# =====================================================
# VENDOR REQUEST MANAGEMENT
# =====================================================

@router.get("", response_model=List[VendorJoinRequestResponse], operation_id="admin_get_vendor_requests")
async def get_vendor_requests(
    status_filter: Optional[str] = "pending",
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(require_admin),
    admin_service: AdminService = Depends(get_admin_service)
):
    """
    Get vendor join requests
    - Admin only
    - Filter by status: pending, approved, rejected
    """
    requests = await admin_service.get_vendor_requests(
        status_filter=status_filter,
        limit=limit,
        offset=offset
    )

    return requests


APPROVAL_ERROR_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "already_reviewed": status.HTTP_409_CONFLICT,
}


@router.post("/{request_id}/approve", operation_id="admin_approve_vendor_request")
async def approve_vendor_request(
    request_id: str,
    request_body: VendorApprovalRequest,
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(require_admin),
    approval_service: VendorApprovalService = Depends(get_approval_service)
):
    """
    Approve vendor join request
    - Creates salon entry
    - Updates RM score
    - Queues the vendor registration email and RM notification

    Emails are sent *after* the response so that a slow or failing email provider
    can no longer hold the request open past the admin panel's timeout (which made a
    successful approval look like a failure). Delivery failures are recorded as
    `email_failed` activity and can be retried via `/resend-approval-email`.
    """
    logger.info(f"Admin {current_user.user_id} approving vendor request: {request_id}")
    # Avoid logging potentially sensitive or PII-containing admin notes.
    notes_preview = (request_body.admin_notes or "")[:120]
    logger.info(f"Admin notes length={len(request_body.admin_notes or '')}; preview='{notes_preview}'")

    # Use service layer for approval
    result = await approval_service.approve_vendor_request(
        request_id=request_id,
        admin_notes=request_body.admin_notes,
        admin_id=current_user.user_id
    )

    if not result.success:
        raise HTTPException(
            status_code=APPROVAL_ERROR_STATUS.get(
                result.error_code, status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=result.error
        )

    # Log warnings if any
    if result.warnings:
        for warning in result.warnings:
            logger.warning(f"Warning: {warning}")

    # Log activity
    try:
        await ActivityLogger.salon_approved(
            user_id=current_user.user_id,
            salon_id=result.salon_id,
            salon_name=result.salon_name or "Unknown"
        )
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")

    background_tasks.add_task(
        approval_service.send_approval_notifications,
        request_id=request_id,
        salon_id=result.salon_id,
        rm_new_score=result.rm_new_score
    )

    return {
        "success": True,
        "message": "Vendor request approved successfully",
        "data": {
            "salon_id": result.salon_id,
            "rm_score_awarded": result.rm_score_awarded,
            "warnings": result.warnings,
            "emails_queued": True
        }
    }


@router.post("/{request_id}/resend-approval-email", operation_id="admin_resend_approval_email")
async def resend_approval_email(
    request_id: str,
    current_user: TokenData = Depends(require_admin),
    approval_service: VendorApprovalService = Depends(get_approval_service),
    db: Client = Depends(get_db_client)
):
    """
    Re-send the registration-link email for an already approved vendor request.

    Unlike `/approve`, this waits for the Resend result and reports the real error,
    so it doubles as the way to diagnose "the vendor never got the email".
    """
    salon_response = db.table("salons").select("id, business_name, email").eq(
        "join_request_id", request_id
    ).limit(1).execute()

    if not salon_response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No salon found for this request - approve it first"
        )

    salon = salon_response.data[0]

    logger.info(
        f"Admin {current_user.user_id} resending approval email for request {request_id} "
        f"(salon {salon['id']})"
    )

    result = await approval_service.send_approval_notifications(
        request_id=request_id,
        salon_id=salon["id"],
        vendor_only=True,
        force_vendor_email=True
    )

    if not result["vendor_email_sent"]:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Could not send the approval email: "
                + ("; ".join(result["errors"]) if result["errors"]
                   else "Resend rejected or dropped the message. Check the server logs and the Resend dashboard.")
            )
        )

    return {
        "success": True,
        "message": f"Approval email sent to {salon.get('email')}",
        "data": {
            "salon_id": salon["id"],
            "salon_name": salon.get("business_name"),
            "owner_email": salon.get("email")
        }
    }


@router.post("/{request_id}/reject", operation_id="admin_reject_vendor_request")
async def reject_vendor_request(
    request_id: str,
    request_body: VendorRejectionRequest,
    current_user: TokenData = Depends(require_admin),
    approval_service: VendorApprovalService = Depends(get_approval_service)
):
    """
    Reject vendor join request
    - Updates status
    - Sends rejection email
    """
    logger.info(f"Admin {current_user.user_id} rejecting vendor request: {request_id}")
    notes_preview = (request_body.admin_notes or "")[:120]
    logger.info(f"Rejection notes length={len(request_body.admin_notes or '')}; preview='{notes_preview}'")

    # Use service layer for rejection
    try:
        result = await approval_service.reject_vendor_request(
            request_id=request_id,
            admin_notes=request_body.admin_notes,
            admin_id=current_user.user_id
        )
    except RequestNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RequestAlreadyReviewedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    # Log activity
    try:
        await ActivityLogger.salon_rejected(
            user_id=current_user.user_id,
            salon_id=result.get("salon_id", request_id),
            salon_name=result.get("salon_name", "Unknown"),
            reason=request_body.admin_notes or "No reason provided"
        )
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")

    return result