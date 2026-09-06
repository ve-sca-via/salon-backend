"""
Partner ("Partner with us") API
Handles vendor onboarding inquiries: public submission + admin review.
"""
from fastapi import APIRouter, Depends
from typing import Optional
import logging

from app.core.database import get_db_client
from app.core.auth import require_admin, TokenData
from app.services.partner_service import PartnerService
from app.schemas import (
    PartnerRequestCreate,
    PartnerRequestStatusUpdate,
    PartnerRequestResponse,
    PartnerRequestUpdateResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# =====================================================
# DEPENDENCY INJECTION
# =====================================================

def get_partner_service(db=Depends(get_db_client)) -> PartnerService:
    """Dependency injection for PartnerService"""
    return PartnerService(db_client=db)


# =====================================================
# API ENDPOINTS
# =====================================================

@router.post("/apply", response_model=PartnerRequestResponse)
async def submit_partner_request(
    payload: PartnerRequestCreate,
    partner_service: PartnerService = Depends(get_partner_service),
):
    """
    Submit a 'Partner with us' onboarding inquiry (public).

    Collects basic vendor info: owner name, shop name, shop type,
    email, phone, and location.
    """
    result = await partner_service.submit_request(payload.model_dump())
    return PartnerRequestResponse(**result)


@router.get("/requests")
async def get_partner_requests(
    status: Optional[str] = None,
    shop_type: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    admin: TokenData = Depends(require_admin),
    partner_service: PartnerService = Depends(get_partner_service),
):
    """
    Get all partner requests (Admin only).

    Query params:
    - status: Filter by status (new, contacted, approved, rejected)
    - shop_type: Filter by shop type
    - search: Search owner name, shop name, email, phone, or location
    - skip / limit: Pagination
    """
    return partner_service.get_requests(
        status_filter=status,
        shop_type_filter=shop_type,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.patch("/requests/{request_id}", response_model=PartnerRequestUpdateResponse)
async def update_partner_request(
    request_id: str,
    update_data: PartnerRequestStatusUpdate,
    admin: TokenData = Depends(require_admin),
    partner_service: PartnerService = Depends(get_partner_service),
):
    """Update a partner request's status and admin notes (Admin only)."""
    request = await partner_service.update_request_status(
        request_id=request_id,
        new_status=update_data.status,
        admin_notes=update_data.admin_notes,
        admin_user_id=admin.user_id,
    )

    return PartnerRequestUpdateResponse(
        message="Partner request updated successfully",
        request=request,
    )
