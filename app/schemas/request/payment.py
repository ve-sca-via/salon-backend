"""
Request Pydantic schemas for payment endpoints
All payment request models should be defined here for consistency
"""
from pydantic import BaseModel


# =====================================================
# PAYMENT REQUEST SCHEMAS
# =====================================================

class PaymentVerification(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
