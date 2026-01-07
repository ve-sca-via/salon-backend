"""
Relationship Manager (RM) API Endpoints using Service Layer
All business logic in RMService for testability
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional
import logging
from supabase import Client

logger = logging.getLogger(__name__)

from app.core.auth import require_rm, TokenData, get_current_user_id
from app.schemas.user import UserProfileUpdate
from app.schemas import (
    VendorJoinRequestCreate,
    VendorJoinRequestResponse,
    RMProfileResponse,
    RMScoreHistoryResponse,
    SuccessResponse,
    # RM Response Models
    VendorRequestOperationResponse,
    VendorRequestsListResponse,
    RMSalonsListResponse,
    RMProfileUpdateResponse,
    RMDashboardResponse,
    RMLeaderboardResponse,
    ServiceCategoriesResponse,
)
from app.core.database import get_db_client
from app.services.rm_service import RMService
from fastapi import APIRouter

router = APIRouter(prefix="/rm", tags=["Relationship Manager"])


def get_rm_service(db: Client = Depends(get_db_client)) -> RMService:
    """Dependency injection for RM service"""
    return RMService(db_client=db)


# =====================================================
# VENDOR REQUEST SUBMISSION
# =====================================================

@router.post("/vendor-requests", response_model=VendorJoinRequestResponse)
async def create_vendor_request(
    request: VendorJoinRequestCreate,
    is_draft: bool = False,
    current_user: TokenData = Depends(require_rm),
    rm_service: RMService = Depends(get_rm_service)
):
    """Create new vendor join request - can be draft or submitted for approval"""
    return await rm_service.create_vendor_request(
        rm_id=current_user.user_id,
        request_data=request,
        is_draft=is_draft
    )


@router.put("/vendor-requests/{request_id}", response_model=VendorRequestOperationResponse)
async def update_vendor_request(
    request_id: str,
    request: VendorJoinRequestCreate,
    submit_for_approval: bool = False,
    current_user: TokenData = Depends(require_rm),
    rm_service: RMService = Depends(get_rm_service)
):
    """Update draft vendor request or submit it for approval"""
    return await rm_service.update_vendor_request(
        request_id=request_id,
        rm_id=current_user.user_id,
        request_data=request,
        submit_for_approval=submit_for_approval
    )


@router.delete("/vendor-requests/{request_id}", response_model=VendorRequestOperationResponse)
async def delete_vendor_request(
    request_id: str,
    current_user: TokenData = Depends(require_rm),
    rm_service: RMService = Depends(get_rm_service)
):
    """Delete draft vendor request with automatic image cleanup"""
    return await rm_service.delete_vendor_request(
        request_id=request_id,
        rm_id=current_user.user_id
    )


# =====================================================
# OWN REQUESTS VIEWING
# =====================================================

@router.get("/vendor-requests", response_model=VendorRequestsListResponse)
async def get_own_vendor_requests(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(require_rm),
    rm_service: RMService = Depends(get_rm_service)
):
    """Get all vendor requests submitted by this RM"""
    requests = await rm_service.get_rm_vendor_requests(
        rm_id=current_user.user_id,
        status=status_filter,
        limit=limit,
        offset=offset
    )
    
    return {
        "success": True,
        "message": "Vendor requests fetched successfully",
        "data": requests,
        "count": len(requests)
    }


@router.get("/vendor-requests/{request_id}", response_model=VendorJoinRequestResponse, operation_id="rm_get_vendor_request")
async def get_vendor_request(
    request_id: str,
    current_user: TokenData = Depends(require_rm),
    rm_service: RMService = Depends(get_rm_service)
):
    """Get single vendor request by ID"""
    return await rm_service.get_vendor_request(
        request_id=request_id,
        rm_id=current_user.user_id
    )


@router.get("/salons", response_model=RMSalonsListResponse)
async def get_rm_salons(
    include_inactive: bool = False,
    current_user: TokenData = Depends(require_rm),
    rm_service: RMService = Depends(get_rm_service)
):
    """Get all salons associated with this RM"""
    salons = await rm_service.get_rm_salons(
        rm_id=current_user.user_id,
        include_inactive=include_inactive
    )
    
    return {
        "success": True,
        "data": salons,
        "count": len(salons)
    }


# =====================================================
# PROFILE & SCORE MANAGEMENT
# =====================================================

@router.get("/profile", response_model=RMProfileResponse)
async def get_own_profile(
    current_user: TokenData = Depends(require_rm),
    rm_service: RMService = Depends(get_rm_service)
):
    """Get own RM profile with scores"""
    return await rm_service.get_rm_profile(current_user.user_id)


@router.put("/profile", response_model=RMProfileUpdateResponse)
async def update_own_profile(
    profile_data: UserProfileUpdate,
    current_user: TokenData = Depends(require_rm),
    rm_service: RMService = Depends(get_rm_service)
):
    """Update own RM profile - limited fields allowed"""
    # Validate allowed fields
    allowed_fields = {"full_name", "phone", "address", "city", "state", "pincode"}
    update_data = profile_data.model_dump(exclude_none=True)
    update_data = {k: v for k, v in update_data.items() if k in allowed_fields}
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid fields to update"
        )
    
    await rm_service.update_rm_profile(
        rm_id=current_user.user_id,
        updates=update_data
    )
    
    # Return updated profile
    updated_profile = await rm_service.get_rm_profile(current_user.user_id)
    
    return {
        "success": True,
        "message": "Profile updated successfully",
        "data": updated_profile
    }


@router.get("/score-history", response_model=List[RMScoreHistoryResponse])
async def get_own_score_history(
    limit: int = 50,
    current_user: TokenData = Depends(require_rm),
    rm_service: RMService = Depends(get_rm_service)
):
    """Get own score history"""
    return await rm_service.get_rm_score_history(
        rm_id=current_user.user_id,
        limit=limit
    )


# =====================================================
# DASHBOARD
# =====================================================

@router.get("/dashboard", response_model=RMDashboardResponse)
async def get_rm_dashboard(
    current_user: TokenData = Depends(require_rm),
    rm_service: RMService = Depends(get_rm_service)
):
    """Get RM dashboard statistics with comprehensive metrics"""
    return await rm_service.get_rm_dashboard(current_user.user_id)


# =====================================================
# LEADERBOARD
# =====================================================

@router.get("/leaderboard", response_model=RMLeaderboardResponse)
async def get_rm_leaderboard(
    limit: int = Query(20, ge=1, le=100, description="Results per page (max 100)"),
    rm_service: RMService = Depends(get_rm_service)
):
    """Get RM leaderboard - top RMs by score"""
    leaderboard = await rm_service.get_leaderboard(limit=limit)
    
    return {
        "success": True,
        "message": "RM leaderboard retrieved successfully",
        "data": leaderboard,
        "total": len(leaderboard)
    }


# =====================================================
# SERVICE CATEGORIES
# =====================================================

@router.get("/service-categories", response_model=ServiceCategoriesResponse, operation_id="rm_get_service_categories")
async def get_service_categories(
    current_user: TokenData = Depends(require_rm),
    rm_service: RMService = Depends(get_rm_service)
):
    """Get all active service categories for salon submission forms"""
    categories = await rm_service.get_service_categories()
    
    logger.info(f"RM {current_user.user_id} fetched {len(categories)} service categories")
    
    return {
        "success": True,
        "message": "Service categories fetched successfully",
        "data": categories
    }
