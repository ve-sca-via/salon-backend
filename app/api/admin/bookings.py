"""
Admin Bookings Management API Endpoints
Handles booking CRUD operations and status management for admins
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import Optional
from app.core.auth import require_admin, TokenData
from app.core.database import get_db_client
from app.services.booking_service import BookingService
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# =====================================================
# BOOKINGS/APPOINTMENTS MANAGEMENT
# =====================================================

@router.get("/", operation_id="admin_get_all_bookings")
async def get_all_bookings_admin(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Results per page (max 100)"),
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Get all bookings with filters"""
    booking_service = BookingService(db_client=db)
    result = await booking_service.get_admin_bookings(
        page=page,
        limit=limit,
        status_filter=status,
        date_from=date_from,
        date_to=date_to
    )

    return result


@router.put("/{booking_id}/status", operation_id="admin_update_booking_status")
async def update_booking_status(
    booking_id: str,
    status: str,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Update booking status"""
    booking_service = BookingService(db_client=db)
    result = await booking_service.update_booking_status_admin(
        booking_id=booking_id,
        new_status=status
    )

    return result