"""
Response Pydantic schemas for booking endpoints
All booking response models should be defined here for consistency
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date, time
from ..domain.common import BookingStatus


# =====================================================
# BOOKING RESPONSE SCHEMAS
# =====================================================

class BookingResponse(BaseModel):
    """Legacy booking response schema"""
    id: str
    booking_number: str
    customer_id: str
    salon_id: str
    service_id: str
    staff_id: Optional[str] = None
    booking_date: date
    booking_time: time
    customer_notes: Optional[str] = None
    salon_notes: Optional[str] = None
    duration_minutes: int
    status: BookingStatus
    service_price: float
    convenience_fee: float
    total_amount: float
    convenience_fee_paid: bool
    service_paid: bool
    payment_completed_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    cancelled_by: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # salon: Optional[SalonResponse] = None  # Avoid circular import
    # service: Optional[ServiceResponse] = None  # Avoid circular import
    # staff: Optional[SalonStaffResponse] = None  # Avoid circular import

    class Config:
        from_attributes = True


class BookingListResponse(BaseModel):
    """Response for booking list endpoints"""
    bookings: List[BookingResponse]
    count: int

    class Config:
        from_attributes = True