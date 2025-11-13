"""
Modern Booking API Endpoints using Service Layer

Clean Architecture - All business logic in BookingService
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
import logging

from app.core.auth import get_current_user, TokenData
from app.schemas import BookingCreate, BookingUpdate
from app.services.booking_service import BookingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bookings", tags=["bookings"])


def get_booking_service() -> BookingService:
    """Dependency injection for booking service"""
    return BookingService()


@router.get("/")
async def get_bookings(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    salon_id: Optional[int] = Query(None, description="Filter by salon ID"),
    current_user: TokenData = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service)
):
    """Get bookings - users see their own, vendors see salon bookings, admins see all"""
    return await booking_service.get_bookings(
        user_id=user_id,
        salon_id=salon_id,
        current_user_id=current_user.user_id,
        current_user_role=current_user.role
    )


@router.get("/user/{user_id}")
async def get_user_bookings(
    user_id: str,
    current_user: TokenData = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service)
):
    """Get all bookings for a user - ownership verified"""
    return await booking_service.get_bookings(
        user_id=user_id,
        current_user_id=current_user.user_id,
        current_user_role=current_user.role
    )


@router.get("/salon/{salon_id}")
async def get_salon_bookings(
    salon_id: int,
    current_user: TokenData = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service)
):
    """Get all bookings for a salon - vendor ownership verified"""
    return await booking_service.get_bookings(
        salon_id=salon_id,
        current_user_id=current_user.user_id,
        current_user_role=current_user.role
    )


@router.get("/{booking_id}")
async def get_booking(
    booking_id: str,
    current_user: TokenData = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service)
):
    """Get single booking by ID with access verification"""
    return await booking_service.get_booking(
        booking_id=booking_id,
        current_user_id=current_user.user_id,
        current_user_role=current_user.role
    )


@router.post("/")
async def create_booking(
    booking: BookingCreate,
    current_user: TokenData = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service)
):
    """Create new booking with automatic email confirmation"""
    return await booking_service.create_booking(
        booking=booking,
        current_user_id=current_user.user_id
    )


@router.patch("/{booking_id}")
async def update_booking(
    booking_id: str,
    updates: BookingUpdate,
    current_user: TokenData = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service)
):
    """Update booking details with ownership verification"""
    return await booking_service.update_booking(
        booking_id=booking_id,
        updates=updates,
        current_user_id=current_user.user_id,
        current_user_role=current_user.role
    )


@router.post("/{booking_id}/cancel")
async def cancel_booking(
    booking_id: str,
    reason: Optional[str] = Query(None, description="Cancellation reason"),
    current_user: TokenData = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service)
):
    """Cancel booking with automatic email notification"""
    return await booking_service.cancel_booking(
        booking_id=booking_id,
        reason=reason,
        current_user_id=current_user.user_id,
        current_user_role=current_user.role
    )


@router.post("/{booking_id}/complete")
async def complete_booking(
    booking_id: str,
    current_user: TokenData = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service)
):
    """Mark booking as completed - vendor only"""
    return await booking_service.complete_booking(
        booking_id=booking_id,
        current_user_id=current_user.user_id,
        current_user_role=current_user.role
    )
