"""
Payment API Endpoints
Handles Razorpay payments for registration fees, convenience fees, and vendor payouts
"""
from fastapi import APIRouter, HTTPException, Depends, Header, status, Request
from typing import Optional

from app.core.config import settings
from app.core.database import get_db
from app.core.auth import get_current_user_id, TokenData, get_current_user

# Get database client using factory function
db = get_db()
from app.services.payment import RazorpayService
from app.services.email import email_service
from app.schemas import (
    PaymentOrderCreate,
    PaymentOrderResponse,
    PaymentVerification,
    SuccessResponse
)
import logging
import hmac
import hashlib
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Payments"])

# Initialize db client


# Initialize Razorpay service
razorpay = RazorpayService()


# =====================================================
# VENDOR REGISTRATION FEE
# =====================================================

@router.post("/registration/create-order", response_model=PaymentOrderResponse)
async def create_registration_order(
    vendor_request_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Create Razorpay order for vendor registration fee
    """
    try:
        # Verify vendor request exists and belongs to user
        request_check = db.table("vendor_join_requests").select(
            "id, status, salon_id"
        ).eq("id", vendor_request_id).single().execute()
        
        if not request_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendor request not found"
            )
        
        request_data = request_check.data
        
        # Verify request is approved
        if request_data["status"] != "approved":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vendor request must be approved before payment"
            )
        
        # Get registration fee from system_config
        config = db.table("system_config").select("value").eq("key", "vendor_registration_fee").single().execute()
        
        registration_fee = float(config.data["value"]) if config.data else 1000.0
        
        # Create Razorpay order
        order = razorpay.create_order(
            amount=registration_fee,
            currency="INR",
            receipt=f"reg_{vendor_request_id}",
            notes={
                "vendor_request_id": vendor_request_id,
                "salon_id": request_data["salon_id"],
                "type": "registration_fee"
            }
        )
        
        # Store order in vendor_payments table
        payment_data = {
            "vendor_request_id": vendor_request_id,
            "payment_type": "registration_fee",
            "amount": registration_fee,
            "razorpay_order_id": order["id"],
            "status": "pending"
        }
        
        db.table("vendor_payments").insert(payment_data).execute()
        
        logger.info(f"Created registration payment order: {order['id']}")
        
        return {
            "order_id": order["id"],
            "amount": registration_fee,
            "currency": "INR",
            "key_id": settings.RAZORPAY_KEY_ID
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create registration order: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create payment order"
        )


@router.post("/registration/verify")
async def verify_registration_payment(
    payment: PaymentVerification,
    user_id: str = Depends(get_current_user_id)
):
    """
    Verify Razorpay payment signature and activate vendor account
    """
    try:
        # Verify signature
        is_valid = razorpay.verify_payment_signature(
            payment.razorpay_order_id,
            payment.razorpay_payment_id,
            payment.razorpay_signature
        )
        
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payment signature"
            )
        
        # Get payment details from Razorpay
        payment_details = razorpay.get_payment_details(payment.razorpay_payment_id)
        
        # Update vendor_payments table
        payment_update = db.table("vendor_payments").update({
            "razorpay_payment_id": payment.razorpay_payment_id,
            "razorpay_signature": payment.razorpay_signature,
            "status": "completed",
            "paid_at": "now()"
        }).eq("razorpay_order_id", payment.razorpay_order_id).execute()
        
        if not payment_update.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment record not found"
            )
        
        payment_record = payment_update.data[0]
        
        # Get salon and vendor details for emails
        salon_response = db.table("salons").select(
            "*, vendor_join_requests(owner_name, owner_email)"
        ).eq("id", payment_record["salon_id"]).single().execute()
        
        if not salon_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        salon_data = salon_response.data
        
        # Activate salon with all required fields
        db.table("salons").update({
            "is_active": True,
            "registration_fee_paid": True,
            "registration_paid_at": "now()"
        }).eq("id", payment_record["salon_id"]).execute()
        
        logger.info(f"Registration payment verified: {payment.razorpay_payment_id}")
        
        # Send payment receipt email
        owner_email = salon_data["vendor_join_requests"]["owner_email"]
        owner_name = salon_data["vendor_join_requests"]["owner_name"]
        
        receipt_sent = await email_service.send_payment_receipt_email(
            to_email=owner_email,
            customer_name=owner_name,
            payment_id=payment.razorpay_payment_id,
            payment_type="Registration Fee",
            amount=payment_record["amount"],
            service_amount=payment_record["amount"],
            convenience_fee=0.0,
            payment_date=datetime.now().strftime("%B %d, %Y %I:%M %p"),
            salon_name=salon_data["business_name"]
        )
        
        if not receipt_sent:
            logger.warning(f"Failed to send payment receipt to {owner_email}")
        
        # Send welcome email
        vendor_portal_url = f"{settings.VENDOR_PORTAL_URL}/login"
        
        welcome_sent = await email_service.send_welcome_vendor_email(
            to_email=owner_email,
            owner_name=owner_name,
            salon_name=salon_data["business_name"],
            vendor_portal_url=vendor_portal_url
        )
        
        if not welcome_sent:
            logger.warning(f"Failed to send welcome email to {owner_email}")
        
        return {
            "success": True,
            "message": "Payment verified successfully. Your salon is now active!",
            "payment_id": payment.razorpay_payment_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Payment verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment verification failed"
        )


# =====================================================
# BOOKING CONVENIENCE FEE
# =====================================================

@router.post("/booking/create-order", response_model=PaymentOrderResponse)
async def create_booking_order(
    booking_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Create Razorpay order for booking with convenience fee
    """
    try:
        # Get booking details
        booking = db.table("bookings").select(
            "*, services(price, is_free)"
        ).eq("id", booking_id).eq("customer_id", user_id).single().execute()
        
        if not booking.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )
        
        booking_data = booking.data
        service = booking_data["services"]
        
        # Calculate total amount
        service_price = 0 if service["is_free"] else float(service["price"])
        
        # Get convenience fee from system_config
        config = db.table("system_config").select("value").eq("key", "booking_convenience_fee").single().execute()
        
        convenience_fee = float(config.data["value"]) if config.data else 10.0
        
        total_amount = service_price + convenience_fee
        
        # Create Razorpay order
        order = razorpay.create_order(
            amount=total_amount,
            currency="INR",
            receipt=f"booking_{booking_id}",
            notes={
                "booking_id": booking_id,
                "service_price": service_price,
                "convenience_fee": convenience_fee,
                "type": "booking_payment"
            }
        )
        
        # Store order in booking_payments table
        payment_data = {
            "booking_id": booking_id,
            "amount": total_amount,
            "service_amount": service_price,
            "convenience_fee": convenience_fee,
            "razorpay_order_id": order["id"],
            "status": "pending"
        }
        
        db.table("booking_payments").insert(payment_data).execute()
        
        logger.info(f"Created booking payment order: {order['id']}")
        
        return {
            "order_id": order["id"],
            "amount": total_amount,
            "currency": "INR",
            "key_id": settings.RAZORPAY_KEY_ID,
            "breakdown": {
                "service_price": service_price,
                "convenience_fee": convenience_fee,
                "total": total_amount
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create booking order: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create payment order"
        )


@router.post("/booking/verify")
async def verify_booking_payment(
    payment: PaymentVerification,
    user_id: str = Depends(get_current_user_id)
):
    """
    Verify booking payment signature and confirm booking
    """
    try:
        # Verify signature
        is_valid = razorpay.verify_payment_signature(
            payment.razorpay_order_id,
            payment.razorpay_payment_id,
            payment.razorpay_signature
        )
        
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payment signature"
            )
        
        # Update booking_payments table
        payment_update = db.table("booking_payments").update({
            "razorpay_payment_id": payment.razorpay_payment_id,
            "razorpay_signature": payment.razorpay_signature,
            "status": "completed",
            "paid_at": "now()"
        }).eq("razorpay_order_id", payment.razorpay_order_id).execute()
        
        if not payment_update.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment record not found"
            )
        
        payment_record = payment_update.data[0]
        
        # Confirm booking
        db.table("bookings").update({
            "status": "confirmed",
            "confirmed_at": "now()"
        }).eq("id", payment_record["booking_id"]).execute()
        
        logger.info(f"Booking payment verified: {payment.razorpay_payment_id}")
        
        # TODO: Send booking confirmation email
        
        return {
            "success": True,
            "message": "Payment successful. Your booking is confirmed!",
            "payment_id": payment.razorpay_payment_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Booking payment verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment verification failed"
        )


# =====================================================
# REFUNDS
# =====================================================

@router.post("/refund/{payment_id}")
async def refund_payment(
    payment_id: str,
    reason: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """
    Process refund for a payment
    """
    try:
        # Get payment details
        payment = db.table("booking_payments").select(
            "*, bookings(customer_id)"
        ).eq("razorpay_payment_id", payment_id).single().execute()
        
        if not payment.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found"
            )
        
        payment_data = payment.data
        
        # Verify user is customer or admin
        # TODO: Add admin role check
        if payment_data["bookings"]["customer_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to refund this payment"
            )
        
        # Process refund
        refund = razorpay.refund_payment(
            payment_id=payment_id,
            amount=int(float(payment_data["amount"]) * 100),  # Convert to paise
            notes={"reason": reason or "Customer requested refund"}
        )
        
        # Update payment status
        db.table("booking_payments").update({
            "status": "refunded",
            "refund_id": refund["id"]
        }).eq("razorpay_payment_id", payment_id).execute()
        
        # Update booking status
        db.table("bookings").update({
            "status": "cancelled"
        }).eq("id", payment_data["booking_id"]).execute()
        
        logger.info(f"Refund processed: {refund['id']}")
        
        # TODO: Send refund confirmation email
        
        return {
            "success": True,
            "message": "Refund processed successfully",
            "refund_id": refund["id"]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Refund failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Refund processing failed"
        )


# =====================================================
# WEBHOOKS
# =====================================================

@router.post("/webhook")
async def handle_webhook(
    request: Request,
    x_razorpay_signature: str = Header(None)
):
    """
    Handle Razorpay webhooks for payment status updates
    """
    try:
        # Get raw body
        body = await request.body()
        
        # Verify webhook signature
        is_valid = razorpay.verify_webhook_signature(
            body.decode(),
            x_razorpay_signature
        )
        
        if not is_valid:
            logger.warning("Invalid webhook signature")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature"
            )
        
        # Parse webhook data
        webhook_data = await request.json()
        event = webhook_data.get("event")
        payload = webhook_data.get("payload", {}).get("payment", {}).get("entity", {})
        
        payment_id = payload.get("id")
        order_id = payload.get("order_id")
        status_value = payload.get("status")
        
        logger.info(f"Webhook received: {event} for payment {payment_id}")
        
        # Handle different events
        if event == "payment.captured":
            # Payment successful
            # Update payment status (if not already done via verify endpoint)
            pass
        
        elif event == "payment.failed":
            # Payment failed
            db.table("booking_payments").update({
                "status": "failed"
            }).eq("razorpay_order_id", order_id).execute()
            
            db.table("vendor_payments").update({
                "status": "failed"
            }).eq("razorpay_order_id", order_id).execute()
        
        elif event == "refund.processed":
            # Refund completed
            pass
        
        return {"status": "ok"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing failed: {str(e)}")
        # Return 200 to prevent Razorpay from retrying
        return {"status": "error", "message": str(e)}


# =====================================================
# PAYMENT HISTORY
# =====================================================

@router.get("/history")
async def get_payment_history(
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get payment history for current user
    """
    try:
        # Get booking payments
        booking_payments = db.table("booking_payments").select(
            "*, bookings(booking_date, booking_time, services(name))"
        ).eq("bookings.customer_id", user_id).order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        
        return {
            "payments": booking_payments.data,
            "total": len(booking_payments.data)
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch payment history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch payment history"
        )


# =====================================================
# VENDOR EARNINGS
# =====================================================

@router.get("/vendor/earnings")
async def get_vendor_earnings(
    user_id: str = Depends(get_current_user_id)
):
    """
    Get vendor earnings summary
    """
    try:
        # Get salon
        salon = db.table("salons").select("id").eq("vendor_id", user_id).single().execute()
        
        if not salon.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        salon_id = salon.data["id"]
        
        # Get completed bookings with payments
        bookings = db.table("bookings").select(
            "*, booking_payments(service_amount, convenience_fee, paid_at)"
        ).eq("salon_id", salon_id).eq("status", "completed").eq("booking_payments.status", "completed").execute()
        
        # Calculate earnings
        total_service_amount = sum(b["booking_payments"]["service_amount"] for b in bookings.data if b.get("booking_payments"))
        total_convenience_fee = sum(b["booking_payments"]["convenience_fee"] for b in bookings.data if b.get("booking_payments"))
        total_bookings = len(bookings.data)
        
        return {
            "total_service_amount": total_service_amount,
            "total_convenience_fee": total_convenience_fee,
            "vendor_earnings": total_service_amount,  # Vendor gets service amount
            "platform_earnings": total_convenience_fee,  # Platform gets convenience fee
            "total_bookings": total_bookings
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch vendor earnings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch vendor earnings"
        )
