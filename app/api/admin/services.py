"""
Admin Services Management API Endpoints
Handles salon services CRUD operations for admins
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import Optional
from app.core.auth import require_admin, TokenData
from app.core.database import get_db_client
from app.services.salon_service import SalonService
from app.schemas.admin import ServiceCreate, ServiceUpdate
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# =====================================================
# SERVICES MANAGEMENT
# =====================================================

@router.get("", operation_id="admin_get_all_services")
async def get_all_services_admin(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Get all services across all salons"""
    try:
        # Query all services from all salons
        response = db.table("salon_services").select("*").range(offset, offset + limit - 1).execute()
        
        return {"data": response.data, "total": len(response.data)}
    except Exception as e:
        logger.error(f"Error fetching all services: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch services: {str(e)}"
        )


@router.get("/{service_id}", operation_id="admin_get_service")
async def get_service_admin(
    service_id: str,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Get a specific service by ID"""
    try:
        response = db.table("salon_services").select("*").eq("id", service_id).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found"
            )
        
        return response.data
    except Exception as e:
        logger.error(f"Error fetching service {service_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch service: {str(e)}"
        )


@router.post("", operation_id="admin_create_service")
async def create_service_admin(
    service_data: ServiceCreate,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Create a new service"""
    try:
        response = db.table("salon_services").insert(service_data.model_dump()).execute()
        
        return {"success": True, "data": response.data[0]}
    except Exception as e:
        logger.error(f"Error creating service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create service: {str(e)}"
        )


@router.put("/{service_id}", operation_id="admin_update_service")
async def update_service_admin(
    service_id: str,
    service_data: ServiceUpdate,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Update a service"""
    try:
        update_data = service_data.model_dump(exclude_unset=True)
        response = db.table("salon_services").update(update_data).eq("id", service_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found"
            )
        
        return {"success": True, "data": response.data[0]}
    except Exception as e:
        logger.error(f"Error updating service {service_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update service: {str(e)}"
        )


@router.delete("/{service_id}", operation_id="admin_delete_service")
async def delete_service_admin(
    service_id: str,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Delete a service"""
    try:
        response = db.table("salon_services").delete().eq("id", service_id).execute()
        
        return {"success": True, "message": "Service deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting service {service_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete service: {str(e)}"
        )