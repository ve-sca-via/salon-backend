"""
Admin Services Management API Endpoints
Handles salon services CRUD operations for admins
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import Optional
from app.core.auth import require_admin, TokenData
from app.services.salon_service import SalonService
from app.schemas.admin import ServiceCreate, ServiceUpdate
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# =====================================================
# SERVICES MANAGEMENT
# =====================================================

@router.get("", operation_id="admin_get_salon_services")
async def get_salon_services_admin(
    salon_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Get all services for a salon"""
    salon_service = SalonService()
    services = await salon_service.get_salon_services(salon_id)

    return {"services": services}


@router.post("", operation_id="admin_add_salon_service")
async def add_salon_service_admin(
    salon_id: str,
    service_data: ServiceCreate,
    current_user: TokenData = Depends(require_admin)
):
    """Add a new service to a salon"""
    salon_service = SalonService()
    result = await salon_service.add_salon_service(salon_id, service_data)

    return result


@router.put("/{service_id}", operation_id="admin_update_salon_service")
async def update_salon_service_admin(
    salon_id: str,
    service_id: str,
    service_data: ServiceUpdate,
    current_user: TokenData = Depends(require_admin)
):
    """Update a salon service"""
    salon_service = SalonService()
    result = await salon_service.update_salon_service(salon_id, service_id, service_data)

    return result


@router.delete("/{service_id}", operation_id="admin_delete_salon_service")
async def delete_salon_service_admin(
    salon_id: str,
    service_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Delete a salon service"""
    salon_service = SalonService()
    result = await salon_service.delete_salon_service(salon_id, service_id)

    return result