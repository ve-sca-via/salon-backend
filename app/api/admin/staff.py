"""
Admin Staff Management API Endpoints
Handles salon staff CRUD operations for admins
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import Optional
from app.core.auth import require_admin, TokenData
from app.services.salon_service import SalonService
from app.schemas.admin import StaffCreate, StaffUpdate
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# =====================================================
# STAFF MANAGEMENT
# =====================================================

@router.get("", operation_id="admin_get_salon_staff")
async def get_salon_staff_admin(
    salon_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Get all staff for a salon"""
    salon_service = SalonService()
    staff = await salon_service.get_salon_staff(salon_id)

    return {"staff": staff}


@router.post("", operation_id="admin_add_salon_staff")
async def add_salon_staff_admin(
    salon_id: str,
    staff_data: StaffCreate,
    current_user: TokenData = Depends(require_admin)
):
    """Add a new staff member to a salon"""
    salon_service = SalonService()
    result = await salon_service.add_salon_staff(salon_id, staff_data)

    return result


@router.put("/{staff_id}", operation_id="admin_update_salon_staff")
async def update_salon_staff_admin(
    salon_id: str,
    staff_id: str,
    staff_data: StaffUpdate,
    current_user: TokenData = Depends(require_admin)
):
    """Update a salon staff member"""
    salon_service = SalonService()
    result = await salon_service.update_salon_staff(salon_id, staff_id, staff_data)

    return result


@router.delete("/{staff_id}", operation_id="admin_delete_salon_staff")
async def delete_salon_staff_admin(
    salon_id: str,
    staff_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Delete a salon staff member"""
    salon_service = SalonService()
    result = await salon_service.delete_salon_staff(salon_id, staff_id)

    return result