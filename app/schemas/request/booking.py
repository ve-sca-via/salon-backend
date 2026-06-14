"""
Request Pydantic schemas for booking endpoints
All booking request models should be defined here for consistency
"""
from pydantic import BaseModel, Field
from typing import Optional, List


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
    coupon_code: Optional[str] = None  # Optional coupon applied to this booking

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
    coupon_code: Optional[str] = Field(None, max_length=40, description="Optional coupon code applied to this booking")