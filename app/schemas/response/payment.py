"""
Response Pydantic schemas for payment endpoints
All payment response models should be defined here for consistency
"""
from pydantic import BaseModel
from typing import Optional, Dict, Any


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