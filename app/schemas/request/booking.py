"""
Request Pydantic schemas for booking endpoints
All booking request models should be defined here for consistency
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime


# =====================================================
# BOOKING REQUEST SCHEMAS
# =====================================================

# Module-level small service item for BookingCreate.services
class ServiceItem(BaseModel):
    service_id: str
    quantity: int = 1
    class Config:
        from_attributes = True

class BookingCreate(BaseModel):
    """Schema for creating a new booking - matches current API"""
    salon_id: str  # UUID string
    booking_date: str
    booking_time: str
    services: List[ServiceItem]  # List of service items
    total_amount: float  # Total service amount before fees
    booking_fee: Optional[float] = 0  # Booking fee (percentage of total)
    gst_amount: Optional[float] = 0  # GST on booking fee
    amount_paid: Optional[float] = 0  # Amount paid online
    remaining_amount: Optional[float] = 0  # Amount to pay at salon
    payment_status: Optional[str] = 'pending'  # Payment status
    payment_method: Optional[str] = None  # Payment method
    notes: Optional[str] = None

class BookingUpdate(BaseModel):
    """Schema for updating a booking - matches current API"""
    status: Optional[str] = None
    notes: Optional[str] = None
    cancellation_reason: Optional[str] = None

class BookingCancellation(BaseModel):
    cancellation_reason: str = Field(..., min_length=10)


# =====================================================
# SMALL DTOS USED INTERNALLY BY BOOKING SERVICE
# =====================================================


class ServiceSummary(BaseModel):
    service_id: str
    quantity: int
    unit_price: float
    line_total: float
    duration_minutes: Optional[int] = None
    class Config:
        from_attributes = True


class Totals(BaseModel):
    service_price: float
    convenience_fee: float
    total_amount: float
    convenience_fee_paid: bool
    service_paid: bool
    payment_completed_at: Optional[datetime] = None
    class Config:
        from_attributes = True


class BookingForUpdate(BaseModel):
    id: str
    customer_id: str
    salon_id: int
    class Config:
        from_attributes = True
        extra = 'ignore'


class ProfileSummary(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    class Config:
        from_attributes = True


class SalonSummary(BaseModel):
    business_name: Optional[str] = None
    class Config:
        from_attributes = True


class ServiceNameSummary(BaseModel):
    name: Optional[str] = None
    class Config:
        from_attributes = True


class BookingForCancellation(BaseModel):
    id: Optional[str]
    booking_date: Optional[str]
    booking_time: Optional[str]
    convenience_fee: Optional[float] = 0.0
    profiles: Optional[ProfileSummary] = None
    services: Optional[ServiceNameSummary] = None
    salons: Optional[SalonSummary] = None
    class Config:
        from_attributes = True
        extra = 'ignore'