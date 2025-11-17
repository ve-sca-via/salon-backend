"""
Admin Salon Management API Endpoints
Handles salon CRUD operations and status management for admins
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import Optional
from app.core.auth import require_admin, TokenData
from app.services.salon_service import SalonService, SalonSearchParams
from app.schemas.request.vendor import SalonUpdate
from app.core.database import get_db_client
from supabase import Client
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_salon_service(db: Client = Depends(get_db_client)) -> SalonService:
    """Dependency injection for SalonService"""
    return SalonService(db_client=db)


# =====================================================
# SALON MANAGEMENT
# =====================================================

@router.get("/", operation_id="admin_get_all_salons")
async def get_all_salons_admin(
    current_user: TokenData = Depends(require_admin),
    city: Optional[str] = None,
    state: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_verified: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    salon_service: SalonService = Depends(get_salon_service)
):
    """Get all salons with optional filtering"""

    params = SalonSearchParams(
        city=city,
        state=state,
        is_active=is_active,
        is_verified=is_verified,
        limit=limit,
        offset=offset
    )

    salons = await salon_service.list_salons(params)

    return {
        "success": True,
        "data": salons,
        "count": len(salons)
    }


@router.put("/{salon_id}", operation_id="admin_update_salon")
async def update_salon(
    salon_id: str,
    updates: SalonUpdate,
    current_user: TokenData = Depends(require_admin),
    salon_service: SalonService = Depends(get_salon_service)
):
    """Update salon (protected fields excluded)"""

    updated_salon = await salon_service.update_salon(
        salon_id=salon_id,
        updates=updates,
        admin_id=current_user.user_id
    )

    return {
        "success": True,
        "message": "Salon updated successfully",
        "data": updated_salon
    }


@router.delete("/{salon_id}", operation_id="admin_delete_salon")
async def delete_salon(
    salon_id: str,
    hard_delete: bool = False,
    current_user: TokenData = Depends(require_admin),
    salon_service: SalonService = Depends(get_salon_service)
):
    """Delete salon (soft delete by default, hard delete if specified)"""

    result = await salon_service.delete_salon(
        salon_id=salon_id,
        hard_delete=hard_delete
    )

    return {
        "success": True,
        "message": result.get("message", "Salon deleted successfully"),
        "data": result
    }


@router.put("/{salon_id}/status", operation_id="admin_toggle_salon_status")
async def toggle_salon_status(
    salon_id: str,
    request_body: 'StatusToggle',
    current_user: TokenData = Depends(require_admin),
    salon_service: SalonService = Depends(get_salon_service)
):
    """Toggle salon active/inactive status"""
    is_active = request_body.is_active

    # Construct a SalonUpdate model for typed service call
    from app.schemas.request.vendor import SalonUpdate as _SalonUpdate
    updated_salon = await salon_service.update_salon(
        salon_id=salon_id,
        updates=_SalonUpdate(is_active=is_active),
        admin_id=current_user.user_id
    )

    return {
        "success": True,
        "message": f"Salon {'activated' if is_active else 'deactivated'} successfully",
        "data": updated_salon
    }