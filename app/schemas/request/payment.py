"""
Request Pydantic schemas for payment endpoints
All payment request models should be defined here for consistency
"""
from pydantic import BaseModel, Field
from typing import List, Optional


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

    # The appointment the customer has already chosen on the checkout page.
    # Optional, and not used to price or validate anything: they are pinned onto
    # the payment intent so that the `payment.captured` webhook can complete the
    # booking if the browser never comes back with the success callback (audit
    # C-3). Checkout itself still takes the date and slots from its own request.
    booking_date: Optional[str] = Field(
        None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Chosen appointment date (YYYY-MM-DD), for webhook recovery only",
    )
    time_slots: Optional[List[str]] = Field(
        None,
        max_length=3,
        description="Chosen time slots (max 3), for webhook recovery only",
    )
