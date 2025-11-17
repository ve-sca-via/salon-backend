"""
Admin RM Management API Endpoints
Handles Relationship Manager profiles and score management
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from app.core.auth import require_admin, TokenData
from app.core.database import get_db_client
from supabase import Client
from app.schemas import (
    RMProfileResponse,
    RMScoreHistoryResponse
)
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
    # Use service layer for RM listing
    rms = await rm_service.list_rm_profiles(
        limit=limit,
        offset=offset,
        order_by=order_by,
        order_desc=order_desc
    )

    # Apply active filter if specified
    if is_active is not None:
        rms = [rm for rm in rms if rm.get("profiles", {}).get("is_active") == is_active]

    return rms


@router.get("/{rm_id}", response_model=RMProfileResponse)
async def get_rm_profile(
    rm_id: str,
    current_user: TokenData = Depends(require_admin),
    rm_service: RMService = Depends(get_rm_service)
):
    """Get specific RM profile"""
    # Use service layer
    rm_profile = await rm_service.get_rm_profile(rm_id)

    return rm_profile


@router.get("/{rm_id}/score-history", response_model=List[RMScoreHistoryResponse])
async def get_rm_score_history(
    rm_id: str,
    limit: int = 50,
    current_user: TokenData = Depends(require_admin),
    rm_service: RMService = Depends(get_rm_service)
):
    """Get RM score history"""
    # Use service layer
    history = await rm_service.get_rm_score_history(rm_id, limit=limit)

    return history