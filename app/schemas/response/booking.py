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
    """
    Booking response schema with multi-service support.
    
    Notes on removed fields:
    - booking_time: Removed (use time_slots array)
    - customer_name/phone/email: Removed (fetched via profiles JOIN)
    
    Customer data is returned in nested 'profiles' object when using JOIN query.
    """
    id: str
    booking_number: str
    customer_id: str
    salon_id: str
    booking_date: date
    time_slots: List[str] = Field(default_factory=list, description="Appointment time slots (1-3)")
    services: List[dict] = Field(default_factory=list, description="Services JSONB array")
    notes: Optional[str] = None
    duration_minutes: int = 60
    status: str
    service_price: float
    convenience_fee: float
    total_amount: float
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    # Optional nested objects from JOINs
    profiles: Optional[dict] = Field(None, description="Customer profile data from JOIN")
    salons: Optional[dict] = Field(None, description="Salon data from JOIN")
    customer: Optional[dict] = Field(None, description="Customer profile data (aliased JOIN)")
    payments: Optional[List[dict]] = Field(None, description="Payment records from JOIN")
    
    # Enriched customer fields (populated by service layer)
    customer_name: Optional[str] = Field(None, description="Customer full name (enriched)")
    customer_email: Optional[str] = Field(None, description="Customer email (enriched)")
    customer_phone: Optional[str] = Field(None, description="Customer phone (enriched)")
    payment_status: Optional[str] = Field(None, description="Payment status (enriched)")
    payment_method: Optional[str] = Field(None, description="Payment method (enriched)")

    class Config:
        from_attributes = True


class BookingListResponse(BaseModel):
    """Response for booking list endpoints"""
    bookings: List[BookingResponse]
    count: int

    class Config:
        from_attributes = True