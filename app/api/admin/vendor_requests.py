"""
Admin Vendor Request Management API Endpoints
Handles vendor join request approvals, rejections, and management
"""
from fastapi import APIRouter, HTTPException, Depends, status
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
from app.services.vendor_approval_service import VendorApprovalService
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


@router.get("/{request_id}", response_model=VendorJoinRequestResponse, operation_id="admin_get_vendor_request")
async def get_vendor_request(
    request_id: str,
    current_user: TokenData = Depends(require_admin),
    admin_service: AdminService = Depends(get_admin_service)
):
    """Get specific vendor request details"""
    request = await admin_service.get_vendor_request(request_id)

    return request


@router.post("/{request_id}/approve")
async def approve_vendor_request(
    request_id: str,
    request_body: VendorApprovalRequest,
    current_user: TokenData = Depends(require_admin),
    approval_service: VendorApprovalService = Depends(get_approval_service)
):
    """
    Approve vendor join request
    - Creates salon entry
    - Updates RM score
    - Sends email to vendor with registration link
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
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

    return {
        "success": True,
        "message": "Vendor request approved successfully",
        "data": {
            "salon_id": result.salon_id,
            "rm_score_awarded": result.rm_score_awarded,
            "warnings": result.warnings
        }
    }


@router.post("/{request_id}/reject")
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
    result = await approval_service.reject_vendor_request(
        request_id=request_id,
        admin_notes=request_body.admin_notes,
        admin_id=current_user.user_id
    )

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