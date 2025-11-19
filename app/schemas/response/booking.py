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
    """Booking response schema with multi-service support"""
    id: str
    booking_number: str
    customer_id: str
    salon_id: str
    service_id: Optional[str] = None  # DEPRECATED: Nullable for multi-service bookings
    booking_date: date
    booking_time: time
    time_slots: Optional[List[str]] = []  # NEW: Multiple time slots support
    services: Optional[List[dict]] = []  # NEW: Multi-service bookings
    notes: Optional[str] = None  # Renamed from customer_notes
    duration_minutes: int = 60
    status: str  # Changed from BookingStatus enum to string
    service_price: float
    convenience_fee: float
    total_amount: float
    gst_rate: Optional[float] = 18.0
    cgst: Optional[float] = 0.0
    sgst: Optional[float] = 0.0
    igst: Optional[float] = 0.0
    convenience_fee_paid: bool = False
    convenience_fee_paid_at: Optional[datetime] = None
    service_price_paid: bool = False  # Renamed from service_paid
    service_price_paid_at: Optional[datetime] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BookingListResponse(BaseModel):
    """Response for booking list endpoints"""
    bookings: List[BookingResponse]
    count: int

    class Config:
        from_attributes = True