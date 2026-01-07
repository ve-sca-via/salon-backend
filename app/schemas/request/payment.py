"""
Request Pydantic schemas for payment endpoints
All payment request models should be defined here for consistency
"""
from pydantic import BaseModel, Field
from typing import Optional
from ..domain.common import PaymentType
from typing import Dict, Any


# =====================================================
# PAYMENT REQUEST SCHEMAS
# =====================================================

class PaymentBase(BaseModel):
    amount: float = Field(..., gt=0)

class BookingOrderCreate(BaseModel):
    """Request body for creating booking payment order"""
    booking_id: str

class RazorpayOrderCreate(BaseModel):
    amount: float = Field(..., gt=0)
    currency: str = Field(default="INR")
    payment_type: PaymentType
    booking_id: Optional[str] = None
    salon_id: Optional[str] = None

class PaymentVerification(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentDetails(BaseModel):
    transaction_id: Optional[str] = None
    provider: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None