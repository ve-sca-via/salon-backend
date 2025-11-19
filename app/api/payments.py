"""
Payment API Endpoints - Thin Layer

Handles Razorpay payment routing:
- Booking payment orders and verification
- Vendor registration fee orders and verification
- Payment history and earnings

All business logic in PaymentService (service layer pattern)
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query, Request
from typing import Optional

from app.core.auth import get_current_user_id, TokenData, get_current_user
from app.core.database import get_db_client
from supabase import Client
from app.services.payment_service import PaymentService
from app.schemas import (
    PaymentVerification, BookingOrderCreate, RazorpayOrderResponse,
    PaymentVerificationResponse, VendorRegistrationVerificationResponse,
    PaymentHistoryResponse, VendorEarningsResponse
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Payments"])


def get_payment_service(db: Client = Depends(get_db_client)) -> PaymentService:
    """Dependency injection for payment service"""
    return PaymentService(db_client=db)


# =====================================================
# BOOKING PAYMENT (Main Flow)
# =====================================================

@router.post("/booking/create-order", response_model=RazorpayOrderResponse)
async def create_booking_payment_order(
    request: BookingOrderCreate,
    user_id: str = Depends(get_current_user_id),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """
    Create Razorpay order for booking payment
    
    Flow:
    1. Frontend calls this with booking_id
    2. Returns order_id, amount, key_id
    3. Frontend opens Razorpay Checkout
    4. After payment, frontend calls /verify endpoint
    """
    return await payment_service.create_booking_payment_order(request.booking_id, user_id)


@router.post("/booking/verify", response_model=PaymentVerificationResponse)
async def verify_booking_payment(
    payment: PaymentVerification,
    user_id: str = Depends(get_current_user_id),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """
    Verify Razorpay payment signature and complete booking
    
    Called after successful payment on frontend
    Verifies signature, updates payment record, confirms booking
    """
    return await payment_service.verify_booking_payment(
        razorpay_order_id=payment.razorpay_order_id,
        razorpay_payment_id=payment.razorpay_payment_id,
        razorpay_signature=payment.razorpay_signature,
        user_id=user_id
    )


@router.post("/cart/create-order", response_model=RazorpayOrderResponse)
async def create_cart_payment_order(
    current_user: TokenData = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """
    Create Razorpay order for cart checkout (convenience fee payment)
    
    Cart Payment Flow - Step 5 of checkout:
    1. Frontend calls this endpoint before opening Razorpay modal
    2. Backend calculates total from cart items
    3. Backend calculates booking_fee (10% of service total) + GST (18% of booking_fee)
    4. Backend creates Razorpay order for total payment amount
    5. Backend returns order_id, amount, key_id
    6. Frontend uses this data to open Razorpay checkout modal
    7. After payment, frontend calls /customers/cart/checkout with payment details
    
    Note: This does NOT create a booking. It only initiates the payment.
    The booking is created in /customers/cart/checkout after payment verification.
    """
    return await payment_service.create_cart_payment_order(current_user.user_id)


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
    user_id: str = Depends(get_current_user_id),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """Verify vendor registration payment and activate salon"""
    return await payment_service.verify_vendor_registration_payment(
        razorpay_order_id=payment.razorpay_order_id,
        razorpay_payment_id=payment.razorpay_payment_id,
        razorpay_signature=payment.razorpay_signature,
        user_id=user_id
    )


# =====================================================
# PAYMENT HISTORY & EARNINGS
# =====================================================

@router.get("/history", response_model=PaymentHistoryResponse)
async def get_payment_history(
    limit: int = Query(50, ge=1, le=100, description="Results per page (max 100)"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    user_id: str = Depends(get_current_user_id),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """Get payment history for current user"""
    return await payment_service.get_customer_payment_history(user_id, limit, offset)


@router.get("/vendor/earnings", response_model=VendorEarningsResponse)
async def get_vendor_earnings(
    user_id: str = Depends(get_current_user_id),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """Get vendor earnings summary"""
    return await payment_service.get_vendor_earnings(user_id)


# =====================================================
# WEBHOOKS
# =====================================================

@router.post("/webhook/razorpay")
async def razorpay_webhook(
    request: Request,
    payment_service: PaymentService = Depends(get_payment_service)
):
    """
    Handle Razorpay payment webhooks
    
    Processes payment confirmations and failures
    Verifies webhook signature for security
    """
    try:
        # Get raw body for signature verification
        body = await request.body()
        body_str = body.decode('utf-8')
        
        # Get signature from headers
        signature = request.headers.get('X-Razorpay-Signature')
        if not signature:
            logger.warning("Webhook received without signature")
            raise HTTPException(status_code=400, detail="Missing webhook signature")
        
        # Verify webhook signature
        if not payment_service.verify_webhook_signature(body_str, signature):
            logger.warning("Webhook signature verification failed")
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
        
        # Parse webhook data
        import json
        webhook_data = json.loads(body_str)
        
        event = webhook_data.get('event')
        payment_entity = webhook_data.get('payload', {}).get('payment', {}).get('entity', {})
        
        logger.info(f"Received Razorpay webhook: {event}")
        
        # Handle different webhook events
        if event == 'payment.captured':
            # Payment was successfully captured
            await payment_service.handle_payment_success(
                razorpay_payment_id=payment_entity.get('id'),
                razorpay_order_id=payment_entity.get('order_id'),
                amount=payment_entity.get('amount')
            )
            
        elif event == 'payment.failed':
            # Payment failed
            await payment_service.handle_payment_failure(
                razorpay_payment_id=payment_entity.get('id'),
                razorpay_order_id=payment_entity.get('order_id'),
                error_code=payment_entity.get('error_code'),
                error_description=payment_entity.get('error_description')
            )
            
        elif event == 'order.paid':
            # Order was paid (alternative to payment.captured)
            order_entity = webhook_data.get('payload', {}).get('order', {}).get('entity', {})
            await payment_service.handle_order_paid(
                razorpay_order_id=order_entity.get('id'),
                amount=order_entity.get('amount')
            )
        
        else:
            logger.info(f"Ignored webhook event: {event}")
        
        # Return 200 OK to acknowledge receipt
        return {"status": "ok"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        # Still return 200 to prevent Razorpay from retrying with invalid data
        return {"status": "error", "message": "Processing failed but acknowledged"}
