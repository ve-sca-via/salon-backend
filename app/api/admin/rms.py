"""
Admin RM Management API Endpoints
Handles Relationship Manager profiles and score management
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from app.core.auth import require_admin, TokenData
from app.core.database import get_db_client
from supabase import Client
from app.schemas import RMProfileResponse
from app.schemas.request.rm import RMProfileUpdate
from app.services.rm_service import RMService
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# =====================================================
# DEPENDENCY INJECTION
# =====================================================

def get_rm_service(db: Client = Depends(get_db_client)) -> RMService:
    """Dependency injection for RMService"""
    return RMService(db_client=db)


# =====================================================
# RM MANAGEMENT
# =====================================================

@router.get("", response_model=List[RMProfileResponse])
async def get_all_rms(
    is_active: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "performance_score",
    order_desc: bool = True,
    current_user: TokenData = Depends(require_admin),
    rm_service: RMService = Depends(get_rm_service)
):
    """Get all Relationship Managers"""
    # is_active is filtered at the DB level (before pagination) by the service.
    rms = await rm_service.list_rm_profiles(
        limit=limit,
        offset=offset,
        order_by=order_by,
        order_desc=order_desc,
        is_active=is_active
    )

    return rms


@router.put("/{rm_id}", response_model=RMProfileResponse)
async def update_rm_profile(
    rm_id: str,
    updates: RMProfileUpdate,
    current_user: TokenData = Depends(require_admin),
    rm_service: RMService = Depends(get_rm_service)
):
    """
    Update RM profile (admin only)

    Updates both profile fields (name, phone, email, is_active) and
    RM-specific fields (territories, joining_date, manager_notes).
    employee_id is system-generated and not editable.
    """
    try:
        updated_profile = await rm_service.update_rm_profile(rm_id, updates)
        logger.info(f"Admin {current_user.user_id} updated RM profile {rm_id}")
        return updated_profile

    except ValueError as e:
        msg = str(e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in msg.lower()
            else status.HTTP_400_BAD_REQUEST,
            detail=msg,
        )
    except Exception as e:
        logger.error(f"Failed to update RM profile {rm_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update RM profile",
        )