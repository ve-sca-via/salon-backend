"""
Admin Staff Management API Endpoints
Handles salon staff CRUD operations for admins
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import Optional
from app.core.auth import require_admin, TokenData
from app.core.database import get_db_client
from app.services.salon_service import SalonService
from app.schemas.admin import StaffCreate, StaffUpdate
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# =====================================================
# STAFF MANAGEMENT
# =====================================================

@router.get("", operation_id="admin_get_all_staff")
async def get_all_staff_admin(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Get all staff members across all salons"""
    try:
        # Query all staff from all salons
        response = db.table("staff").select("*").range(offset, offset + limit - 1).execute()
        
        return {"data": response.data, "total": len(response.data)}
    except Exception as e:
        logger.error(f"Error fetching all staff: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch staff: {str(e)}"
        )


@router.get("/{staff_id}", operation_id="admin_get_staff")
async def get_staff_admin(
    staff_id: str,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Get a specific staff member by ID"""
    try:
        response = db.table("staff").select("*").eq("id", staff_id).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Staff member not found"
            )
        
        return response.data
    except Exception as e:
        logger.error(f"Error fetching staff {staff_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch staff: {str(e)}"
        )


@router.post("", operation_id="admin_create_staff")
async def create_staff_admin(
    staff_data: StaffCreate,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Create a new staff member"""
    try:
        response = db.table("staff").insert(staff_data.model_dump()).execute()
        
        return {"success": True, "data": response.data[0]}
    except Exception as e:
        logger.error(f"Error creating staff: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create staff: {str(e)}"
        )


@router.put("/{staff_id}", operation_id="admin_update_staff")
async def update_staff_admin(
    staff_id: str,
    staff_data: StaffUpdate,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Update a staff member"""
    try:
        update_data = staff_data.model_dump(exclude_unset=True)
        response = db.table("staff").update(update_data).eq("id", staff_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Staff member not found"
            )
        
        return {"success": True, "data": response.data[0]}
    except Exception as e:
        logger.error(f"Error updating staff {staff_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update staff: {str(e)}"
        )


@router.delete("/{staff_id}", operation_id="admin_delete_staff")
async def delete_staff_admin(
    staff_id: str,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Delete a staff member"""
    try:
        response = db.table("staff").delete().eq("id", staff_id).execute()
        
        return {"success": True, "message": "Staff member deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting staff {staff_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete staff: {str(e)}"
        )