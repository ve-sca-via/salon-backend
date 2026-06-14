"""
Request Pydantic schemas for payment endpoints
All payment request models should be defined here for consistency
"""
from pydantic import BaseModel, Field
from typing import Optional


# =====================================================
# PAYMENT REQUEST SCHEMAS
# =====================================================

class PaymentVerification(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class CartOrderCreate(BaseModel):
    """Optional body for creating a cart convenience-fee order."""
    coupon_code: Optional[str] = Field(None, max_length=40, description="Optional coupon code to apply")
