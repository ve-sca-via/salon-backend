"""
Response Pydantic schemas for payment endpoints
All payment response models should be defined here for consistency
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from ..domain.common import PaymentStatus


# =====================================================
# PAYMENT RESPONSE SCHEMAS
# =====================================================

class RazorpayOrderResponse(BaseModel):
    order_id: str
    amount: float
    amount_paise: int
    currency: str
    key_id: str  # Razorpay key ID for frontend
    booking_id: Optional[str] = None
    breakdown: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class PaymentVerificationResponse(BaseModel):
    """Response for payment verification endpoints"""
    success: bool
    message: str
    payment_id: str
    booking_id: Optional[str] = None
    salon_name: Optional[str] = None
    booking_date: Optional[str] = None
    time_slots: Optional[List[str]] = None
    amount_paid: Optional[float] = None
    salon_id: Optional[str] = None
    vendor_request_id: Optional[str] = None

    class Config:
        from_attributes = True


class VendorRegistrationVerificationResponse(BaseModel):
    """Response for vendor registration payment verification"""
    success: bool
    message: str
    payment_id: str
    salon_id: Optional[str] = None
    salon_name: Optional[str] = None
    vendor_request_id: Optional[str] = None

    class Config:
        from_attributes = True


class PaymentHistoryResponse(BaseModel):
    """Response for payment history queries"""
    payments: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int

    class Config:
        from_attributes = True


class VendorEarningsResponse(BaseModel):
    """Response for vendor earnings summary"""
    total_service_amount: float
    total_convenience_fee_collected: float
    vendor_earnings: float
    platform_earnings: float
    total_bookings: int

    class Config:
        from_attributes = True

class VendorRegistrationPaymentResponse(BaseModel):
    id: str
    vendor_id: str
    salon_id: Optional[str] = None
    amount: float
    currency: str = "INR"
    status: PaymentStatus
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    payment_method: Optional[str] = None
    payment_metadata: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    error_description: Optional[str] = None
    paid_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class BookingPaymentResponse(BaseModel):
    id: str
    booking_id: str
    customer_id: str
    amount: float
    convenience_fee: float
    service_amount: float
    currency: str = "INR"
    status: PaymentStatus
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    payment_method: Optional[str] = None
    payment_metadata: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    error_description: Optional[str] = None
    paid_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    deleted_at: Optional[str] = None

    class Config:
        from_attributes = True