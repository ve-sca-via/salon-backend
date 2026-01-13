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
    """Schema for creating a new booking - supports multiple time slots"""
    salon_id: str  # UUID string
    booking_date: str
    booking_time: str  # DEPRECATED: For backward compatibility only, use time_slots
    time_slots: Optional[List[str]] = Field(None, max_length=3, min_length=1)  # Up to 3 time slots
    services: List[ServiceItem]  # List of service items
    payment_status: Optional[str] = 'pending'  # Payment status
    payment_method: Optional[str] = None  # Payment method
    razorpay_order_id: Optional[str] = None  # Razorpay order ID
    razorpay_payment_id: Optional[str] = None  # Razorpay payment ID
    razorpay_signature: Optional[str] = None  # Razorpay signature
    notes: Optional[str] = None

class BookingUpdate(BaseModel):
    """Schema for updating a booking - matches current API"""
    status: Optional[str] = None
    notes: Optional[str] = None
    cancellation_reason: Optional[str] = None

class BookingCancellation(BaseModel):
    cancellation_reason: str = Field(..., min_length=10)


class CartCheckoutCreate(BaseModel):
    """Schema for creating a booking from cart items"""
    booking_date: str = Field(..., description="Booking date (YYYY-MM-DD)")
    time_slots: List[str] = Field(..., max_length=3, min_length=1, description="Time slots (max 3)")
    razorpay_order_id: Optional[str] = None  # From payment initiation
    razorpay_payment_id: Optional[str] = None  # After payment success
    razorpay_signature: Optional[str] = None  # For verification
    payment_method: Optional[str] = 'razorpay'
    notes: Optional[str] = Field(None, max_length=500)


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
    time_slots: Optional[List[str]] = None
    convenience_fee: Optional[float] = 0.0
    profiles: Optional[ProfileSummary] = None
    services: Optional[ServiceNameSummary] = None
    salons: Optional[SalonSummary] = None
    class Config:
        from_attributes = True
        extra = 'ignore'