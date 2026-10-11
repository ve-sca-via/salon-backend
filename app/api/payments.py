"""
Payment API Endpoints - Thin Layer

Handles Razorpay payment routing:
- Cart checkout convenience fee orders
- Vendor registration fee orders and verification

All business logic in PaymentService (service layer pattern)
"""
from fastapi import APIRouter, BackgroundTasks, Depends

from app.core.auth import get_current_user_id, TokenData, get_current_user
from app.core.database import get_db_client
from supabase import Client
from app.services.payment_service import PaymentService
from app.schemas import (
    PaymentVerification, RazorpayOrderResponse,
    VendorRegistrationVerificationResponse, CartOrderCreate,
)
from typing import Optional

router = APIRouter(prefix="/payments", tags=["Payments"])


def get_payment_service(db: Client = Depends(get_db_client)) -> PaymentService:
    """Dependency injection for payment service"""
    return PaymentService(db_client=db)


# =====================================================
# CART CHECKOUT PAYMENT (Main Flow)
# =====================================================

@router.post("/cart/create-order", response_model=RazorpayOrderResponse)
async def create_cart_payment_order(
    body: Optional[CartOrderCreate] = None,
    current_user: TokenData = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """
    Create Razorpay order for cart checkout (convenience fee payment)

    Cart Payment Flow - Step 5 of checkout:
    1. Frontend calls this endpoint before opening Razorpay modal
    2. Backend calculates total from cart items
    3. Backend calculates booking_fee (% of service total - configured by admin)
    4. Backend creates Razorpay order for total payment amount
    5. Backend returns order_id, amount, key_id
    6. Frontend uses this data to open Razorpay checkout modal
    7. After payment, frontend calls /customers/cart/checkout with payment details

    Note: This does NOT create a booking. It only initiates the payment.
    The booking is created in /customers/cart/checkout after payment verification.

    Optional body: {"coupon_code": "SAVE20"} to apply a coupon to this order,
    and `booking_date` / `time_slots` for the appointment already chosen on the
    page. The appointment is not priced or validated here — it is pinned onto the
    payment intent so the `payment.captured` webhook can finish the booking if
    the browser never returns with the success callback (audit C-3).
    """
    return await payment_service.create_cart_payment_order(
        current_user.user_id,
        coupon_code=body.coupon_code if body else None,
        booking_date=body.booking_date if body else None,
        time_slots=body.time_slots if body else None,
    )


# =====================================================
# VENDOR REGISTRATION FEE
# =====================================================

@router.post("/registration/create-order", response_model=RazorpayOrderResponse)
async def create_vendor_registration_order(
    vendor_request_id: str,
    user_id: str = Depends(get_current_user_id),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """Create Razorpay order for vendor registration fee"""
    return await payment_service.create_vendor_registration_order(vendor_request_id, user_id)


@router.post("/registration/verify", response_model=VendorRegistrationVerificationResponse)
async def verify_vendor_registration_payment(
    payment: PaymentVerification,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """
    Verify vendor registration payment and activate salon.

    Safe to call again: activation is idempotent and a repeat call will complete
    an activation that a previous one couldn't (audit H-6). The receipt email is
    queued, not awaited — the vendor has already paid.
    """
    return await payment_service.verify_vendor_registration_payment(
        razorpay_order_id=payment.razorpay_order_id,
        razorpay_payment_id=payment.razorpay_payment_id,
        razorpay_signature=payment.razorpay_signature,
        user_id=user_id,
        background_tasks=background_tasks
    )
