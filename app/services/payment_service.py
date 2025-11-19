"""
Payment Service - Business Logic Layer

Handles all payment-related database operations and business logic:
- Vendor registration fee orders and verification
- Booking convenience fee orders and verification
- Payment refunds
- Payment history tracking

Follows service layer pattern - no direct DB calls in API layer
"""

from typing import Dict, Any, Optional, List
from fastapi import HTTPException, status
from datetime import datetime
import logging

from app.core.database import get_db
from app.services.payment import RazorpayService
from app.services.config_service import ConfigService
from app.services.email import email_service
from app.core.config import settings

logger = logging.getLogger(__name__)


class PaymentService:
    """Service for managing payment database operations"""
    
    def __init__(self, db_client):
        self.db = db_client
        self.razorpay = RazorpayService()
        self.config_service = ConfigService(db_client=db_client)
    
    # =====================================================
    # BOOKING PAYMENT ORDERS
    # =====================================================
    
    async def create_booking_payment_order(
        self,
        booking_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Create Razorpay order for booking payment
        
        Args:
            booking_id: UUID of the booking
            user_id: Customer user ID (for verification)
        
        Returns:
            Order details with Razorpay order_id, amount, key_id
        """
        try:
            # Get booking details
            booking = self.db.table("bookings").select(
                "id, customer_id, salon_id, service_price, total_amount, convenience_fee"
            ).eq("id", booking_id).eq("customer_id", user_id).single().execute()
            
            if not booking.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found or you don't have access"
                )
            
            booking_data = booking.data
            
            # Check if booking already has a payment order
            existing_payment = self.db.table("booking_payments").select("id, status").eq(
                "booking_id", booking_id
            ).eq("status", "completed").execute()
            
            if existing_payment.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This booking has already been paid"
                )
            
            # Calculate payment amount (convenience_fee already includes GST if applicable)
            convenience_fee = float(booking_data.get("convenience_fee", 0))
            total_payment = convenience_fee
            
            if total_payment <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid payment amount"
                )
            
            # Create Razorpay order
            order = self.razorpay.create_order(
                amount=total_payment,
                currency="INR",
                receipt=f"booking_{booking_id[:8]}",
                notes={
                    "booking_id": booking_id,
                    "customer_id": user_id,
                    "salon_id": booking_data["salon_id"],
                    "type": "booking_payment"
                }
            )
            
            # Store payment record in database
            service_price = float(booking_data.get("service_price", 0))
            payment_data = {
                "booking_id": booking_id,
                "customer_id": user_id,
                "razorpay_order_id": order["order_id"],
                "amount": total_payment,
                "service_amount": service_price,
                "convenience_fee": convenience_fee,
                "status": "pending",
                "payment_type": "convenience_fee",
                "created_at": "now()"
            }
            
            self.db.table("booking_payments").insert(payment_data).execute()
            
            logger.info(f"Created booking payment order: {order['order_id']} for booking {booking_id}")
            
            # Get Razorpay key from config
            razorpay_key_config = await self.config_service.get_config("razorpay_key_id")
            # If config exists but value is None (e.g. decryption failed in dev),
            # fall back to environment setting to avoid returning None to clients.
            razorpay_key_id = (razorpay_key_config.get("config_value") or settings.RAZORPAY_KEY_ID)
            
            return {
                "order_id": order["order_id"],
                "amount": total_payment,
                "amount_paise": int(total_payment * 100),
                "currency": "INR",
                "key_id": razorpay_key_id,
                "booking_id": booking_id,
                "breakdown": {
                    "service_price": service_price,
                    "convenience_fee": convenience_fee,
                    "total_to_pay_now": total_payment,
                    "pay_at_salon": service_price
                }
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create booking payment order: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create payment order: {str(e)}"
            )
    
    async def verify_booking_payment(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Verify Razorpay payment signature and complete booking payment
        
        Args:
            razorpay_order_id: Order ID from Razorpay
            razorpay_payment_id: Payment ID from Razorpay
            razorpay_signature: Signature from Razorpay
            user_id: Customer user ID (for verification)
        
        Returns:
            Success message with payment and booking details
        """
        try:
            # Verify signature first
            is_valid = self.razorpay.verify_payment_signature(
                razorpay_order_id,
                razorpay_payment_id,
                razorpay_signature
            )
            
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid payment signature"
                )
            
            # Use transaction to prevent race conditions
            async with self.db.transaction():
                # Lock the payment record to prevent concurrent updates
                payment_record = self.db.table("booking_payments").select(
                    "*, bookings(id, customer_id, booking_date, booking_time, total_amount, salon_id, salons(business_name))"
                ).eq("razorpay_order_id", razorpay_order_id).with_for_update().single().execute()
                
                if not payment_record.data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Payment record not found"
                    )
                
                payment_data = payment_record.data
                booking_data = payment_data["bookings"]
                
                # Check if payment is already processed
                if payment_data.get("status") == "completed":
                    logger.warning(f"Payment already processed: {razorpay_order_id}")
                    return {
                        "success": True,
                        "message": "Payment already verified.",
                        "payment_id": payment_data.get("razorpay_payment_id"),
                        "booking_id": booking_data["id"],
                        "salon_name": booking_data["salons"]["business_name"],
                        "booking_date": booking_data["booking_date"],
                        "booking_time": booking_data["booking_time"],
                        "amount_paid": payment_data["amount"]
                    }
                
                # Verify user owns this booking
                if booking_data["customer_id"] != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to verify this payment"
                    )
                
                # Update payment record atomically
                self.db.table("booking_payments").update({
                    "razorpay_payment_id": razorpay_payment_id,
                    "razorpay_signature": razorpay_signature,
                    "status": "completed",
                    "paid_at": "now()"
                }).eq("razorpay_order_id", razorpay_order_id).execute()
                
                # Update booking status atomically
                self.db.table("bookings").update({
                    "convenience_fee_paid": True,
                    "status": "confirmed",
                    "confirmed_at": "now()"
                }).eq("id", booking_data["id"]).execute()
            
            logger.info(f"Payment verified: {razorpay_payment_id} for booking {booking_data['id']}")
            
            # TODO: Send booking confirmation email with payment receipt
            
            return {
                "success": True,
                "message": "Payment successful! Your booking is confirmed.",
                "payment_id": razorpay_payment_id,
                "booking_id": booking_data["id"],
                "salon_name": booking_data["salons"]["business_name"],
                "booking_date": booking_data["booking_date"],
                "booking_time": booking_data["booking_time"],
                "amount_paid": payment_data["amount"]
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Payment verification failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Payment verification failed: {str(e)}"
            )
    
    async def create_cart_payment_order(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Create Razorpay order for cart checkout (convenience fee payment)
        
        This is Step 8 of the cart checkout flow.
        
        Process:
        1. Fetches all cart items for user
        2. Calculates total service price from cart
        3. Calculates booking_fee (config: booking_fee_percentage, default 10%)
        4. Calculates GST (18% of booking_fee)
        5. Creates Razorpay order for total payment (booking_fee + GST)
        6. Returns order details for frontend to open Razorpay modal
        
        Important: This does NOT create a booking or payment record.
        It only initiates the payment process with Razorpay.
        The actual booking is created in CustomerService.checkout_cart()
        after payment verification.
        
        Args:
            user_id: Customer user ID
        
        Returns:
            Dict with:
                - order_id: Razorpay order ID
                - amount: Payment amount in rupees
                - amount_paise: Payment amount in paise (for Razorpay)
                - currency: Currency code (INR)
                - key_id: Razorpay public key for frontend
                - breakdown: Dict with service_price, booking_fee, gst_amount, totals
                
        Raises:
            HTTPException 400: Cart is empty or invalid amount
            HTTPException 500: Failed to create Razorpay order
        """
        try:
            # Get cart items
            cart_response = self.db.table("cart_items")\
                .select(
                    "id, service_id, quantity, "
                    "services(id, name, price, salon_id)"
                )\
                .eq("user_id", user_id)\
                .execute()
            
            if not cart_response.data or len(cart_response.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cart is empty"
                )
            
            # Calculate totals
            total_service_price = 0.0
            salon_id = None
            
            for item in cart_response.data:
                service = item.get("services", {})
                if salon_id is None:
                    salon_id = service.get("salon_id")
                
                unit_price = float(service.get("price", 0))
                quantity = item.get("quantity", 1)
                total_service_price += unit_price * quantity
            
            # Get booking fee percentage from config
            booking_fee_percentage = 10.0  # Default 10%
            try:
                booking_fee_config = await self.config_service.get_config("booking_fee_percentage")
                booking_fee_percentage = float(booking_fee_config.get("config_value", 10.0))
            except (ValueError, Exception) as e:
                logger.warning(f"Failed to get booking_fee_percentage from config, using default: {e}")
                booking_fee_percentage = 10.0
            
            booking_fee = total_service_price * (booking_fee_percentage / 100)
            gst_amount = booking_fee * 0.18  # 18% GST
            total_payment = booking_fee + gst_amount
            
            if total_payment <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid payment amount"
                )
            
            # Create Razorpay order
            order = self.razorpay.create_order(
                amount=total_payment,
                currency="INR",
                receipt=f"cart_{user_id[:8]}",
                notes={
                    "customer_id": user_id,
                    "salon_id": salon_id,
                    "type": "cart_checkout",
                    "service_total": total_service_price,
                    "booking_fee": booking_fee,
                    "gst_amount": gst_amount
                }
            )
            
            logger.info(f"Created cart payment order: {order['order_id']} for user {user_id}")
            
            # Get Razorpay key from config
            razorpay_key_config = await self.config_service.get_config("razorpay_key_id")
            razorpay_key_id = (razorpay_key_config.get("config_value") or settings.RAZORPAY_KEY_ID)
            
            return {
                "order_id": order["order_id"],
                "amount": total_payment,
                "amount_paise": int(total_payment * 100),
                "currency": "INR",
                "key_id": razorpay_key_id,
                "breakdown": {
                    "service_price": total_service_price,
                    "booking_fee": booking_fee,
                    "gst_amount": gst_amount,
                    "total_to_pay_now": total_payment,
                    "pay_at_salon": total_service_price
                }
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create cart payment order: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create payment order: {str(e)}"
            )
    
    # =====================================================
    # VENDOR REGISTRATION FEE
    # =====================================================
    
    async def create_vendor_registration_order(
        self,
        vendor_request_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Create Razorpay order for vendor registration fee
        
        Args:
            vendor_request_id: UUID of vendor join request
            user_id: User ID (for verification)
        
        Returns:
            Order details with Razorpay order_id, amount, key_id
        """
        try:
            # Verify vendor request exists
            request_check = self.db.table("vendor_join_requests").select(
                "id, status, rm_id"
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
            
            # Get registration fee from config
            registration_fee_config = await self.config_service.get_config("registration_fee_amount")
            registration_fee = float(registration_fee_config.get("config_value", 1000.0))
            
            # Create Razorpay order
            order = self.razorpay.create_order(
                amount=registration_fee,
                currency="INR",
                receipt=f"vendor_reg_{vendor_request_id[:8]}",
                notes={
                    "vendor_request_id": vendor_request_id,
                    "user_id": user_id,
                    "type": "vendor_registration"
                }
            )
            
            # Store payment record
            payment_data = {
                "vendor_id": user_id,
                "salon_id": None,  # Salon will be created after payment
                "registration_type": "vendor_onboarding",
                "amount": registration_fee,
                "razorpay_order_id": order["order_id"],
                "status": "pending",
                "metadata": {"vendor_request_id": vendor_request_id},
                "created_at": "now()"
            }
            
            self.db.table("vendor_registration_payments").insert(payment_data).execute()
            
            logger.info(f"Created vendor registration order: {order['order_id']}")
            
            # Get Razorpay key from config
            razorpay_key_config = await self.config_service.get_config("razorpay_key_id")
            razorpay_key_id = (razorpay_key_config.get("config_value") or settings.RAZORPAY_KEY_ID)
            
            return {
                "order_id": order["order_id"],
                "amount": registration_fee,
                "amount_paise": int(registration_fee * 100),
                "currency": "INR",
                "key_id": razorpay_key_id
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create vendor registration order: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create payment order: {str(e)}"
            )
    
    async def verify_vendor_registration_payment(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Verify vendor registration payment and activate salon
        
        Args:
            razorpay_order_id: Order ID from Razorpay
            razorpay_payment_id: Payment ID from Razorpay
            razorpay_signature: Signature from Razorpay
            user_id: User ID (for verification)
        
        Returns:
            Success message with salon activation details
        """
        try:
            # Verify signature
            is_valid = self.razorpay.verify_payment_signature(
                razorpay_order_id,
                razorpay_payment_id,
                razorpay_signature
            )
            
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid payment signature"
                )
            
            # Use transaction to prevent race conditions
            async with self.db.transaction():
                # Lock the payment record to prevent concurrent updates
                payment_record = self.db.table("vendor_registration_payments").select(
                    "*, vendor_id, salon_id, metadata"
                ).eq("razorpay_order_id", razorpay_order_id).with_for_update().single().execute()
                
                if not payment_record.data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Payment record not found"
                    )
                
                payment_data = payment_record.data
                
                # Check if payment is already processed
                if payment_data.get("status") == "completed":
                    logger.warning(f"Vendor registration payment already processed: {razorpay_order_id}")
                    return {
                        "success": True,
                        "message": "Payment already verified.",
                        "payment_id": payment_data.get("razorpay_payment_id"),
                        "salon_id": payment_data.get("salon_id")
                    }
                
                vendor_request_id = payment_data.get("metadata", {}).get("vendor_request_id")
                
                # Update payment record atomically
                self.db.table("vendor_registration_payments").update({
                    "razorpay_payment_id": razorpay_payment_id,
                    "razorpay_signature": razorpay_signature,
                    "status": "completed",
                    "paid_at": "now()"
                }).eq("razorpay_order_id", razorpay_order_id).execute()
                
                # Get vendor join request to find salon
                salon_data = None
                if vendor_request_id:
                    vendor_request = self.db.table("vendor_join_requests").select(
                        "id, owner_name, owner_email"
                    ).eq("id", vendor_request_id).single().execute()
                    
                    if vendor_request.data:
                        # Find salon created from this request
                        salon_response = self.db.table("salons").select(
                            "id, business_name, vendor_id"
                        ).eq("join_request_id", vendor_request_id).single().execute()
                        
                        if salon_response.data:
                            salon_data = salon_response.data
                            salon_id = salon_data["id"]
                            
                            # Activate salon and update registration payment atomically
                            self.db.table("salons").update({
                                "is_active": True,
                                "registration_fee_paid": True,
                                "registration_paid_at": "now()"
                            }).eq("id", salon_id).execute()
                            
                            # Link payment to salon
                            self.db.table("vendor_registration_payments").update({
                                "salon_id": salon_id
                            }).eq("razorpay_order_id", razorpay_order_id).execute()
                            
                            logger.info(f"Vendor registration payment verified: {razorpay_payment_id}, salon activated: {salon_id}")
            
            # Get vendor join request to find salon
            salon_data = None
            if vendor_request_id:
                vendor_request = self.db.table("vendor_join_requests").select(
                    "id, owner_name, owner_email"
                ).eq("id", vendor_request_id).single().execute()
                
                if vendor_request.data:
                    # Find salon created from this request
                    salon_response = self.db.table("salons").select(
                        "id, business_name, vendor_id"
                    ).eq("join_request_id", vendor_request_id).single().execute()
                    
                    if salon_response.data:
                        salon_data = salon_response.data
                        salon_id = salon_data["id"]
                        
                        # Activate salon and update registration payment
                        self.db.table("salons").update({
                            "is_active": True,
                            "registration_fee_paid": True,
                            "registration_paid_at": "now()"
                        }).eq("id", salon_id).execute()
                        
                        # Link payment to salon
                        self.db.table("vendor_registration_payments").update({
                            "salon_id": salon_id
                        }).eq("razorpay_order_id", razorpay_order_id).execute()
                        
                        logger.info(f"Vendor registration payment verified: {razorpay_payment_id}, salon activated: {salon_id}")
            
            if not salon_data:
                # Payment successful but salon not yet created
                return {
                    "success": True,
                    "message": "Payment verified successfully! Please complete your salon profile.",
                    "payment_id": razorpay_payment_id,
                    "vendor_request_id": vendor_request_id
                }
            
            # TODO: Send payment receipt and welcome emails
            
            return {
                "success": True,
                "message": "Payment verified successfully! Your salon is now active.",
                "payment_id": razorpay_payment_id,
                "salon_id": salon_data["id"],
                "salon_name": salon_data["business_name"]
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Vendor registration payment verification failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Payment verification failed: {str(e)}"
            )
    
    # =====================================================
    # PAYMENT HISTORY & QUERIES
    # =====================================================
    
    async def get_customer_payment_history(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get payment history for a customer"""
        try:
            payments = self.db.table("booking_payments").select(
                "*, bookings(booking_date, booking_time, salon_id, salons(business_name))"
            ).eq("bookings.customer_id", user_id).order(
                "created_at", desc=True
            ).range(offset, offset + limit - 1).execute()
            
            return {
                "payments": payments.data,
                "total": len(payments.data),
                "limit": limit,
                "offset": offset
            }
        except Exception as e:
            logger.error(f"Failed to fetch payment history: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch payment history"
            )
    
    async def get_vendor_earnings(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """Get earnings summary for vendor"""
        try:
            # Get salon
            salon = self.db.table("salons").select("id").eq("vendor_id", user_id).single().execute()
            
            if not salon.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Salon not found"
                )
            
            salon_id = salon.data["id"]
            
            # Get completed bookings with payments
            bookings = self.db.table("bookings").select(
                "*, booking_payments(service_amount, convenience_fee, paid_at)"
            ).eq("salon_id", salon_id).eq("status", "completed").eq(
                "booking_payments.status", "completed"
            ).execute()
            
            # Calculate earnings
            total_service_amount = sum(
                float(b.get("booking_payments", {}).get("service_amount", 0))
                for b in bookings.data if b.get("booking_payments")
            )
            total_convenience_fee = sum(
                float(b.get("booking_payments", {}).get("convenience_fee", 0))
                for b in bookings.data if b.get("booking_payments")
            )
            total_bookings = len(bookings.data)
            
            return {
                "total_service_amount": total_service_amount,
                "total_convenience_fee_collected": total_convenience_fee,
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
    
    # =====================================================
    # WEBHOOK HANDLERS
    # =====================================================
    
    async def handle_payment_success(
        self,
        razorpay_payment_id: str,
        razorpay_order_id: str,
        amount: int
    ) -> None:
        """
        Handle successful payment webhook
        
        Args:
            razorpay_payment_id: Razorpay payment ID
            razorpay_order_id: Razorpay order ID
            amount: Payment amount in paisa
        """
        try:
            logger.info(f"Processing payment success: {razorpay_payment_id}")
            
            # Find payment record by order ID
            payment_response = self.db.table("payments").select("*").eq(
                "razorpay_order_id", razorpay_order_id
            ).single().execute()
            
            if not payment_response.data:
                logger.warning(f"Payment record not found for order: {razorpay_order_id}")
                return
            
            payment = payment_response.data
            
            # Update payment status
            self.db.table("payments").update({
                "status": "completed",
                "razorpay_payment_id": razorpay_payment_id,
                "completed_at": datetime.utcnow().isoformat()
            }).eq("id", payment["id"]).execute()
            
            # If this is a booking payment, update booking status
            if payment.get("booking_id"):
                self.db.table("bookings").update({
                    "status": "confirmed",
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", payment["booking_id"]).execute()
                
                # Send confirmation email
                await self._send_booking_confirmation_email(payment["booking_id"])
            
            # If this is a vendor registration payment, activate salon
            elif payment.get("vendor_request_id"):
                await self._activate_vendor_salon(payment["vendor_request_id"])
            
            logger.info(f"Payment success processed: {razorpay_payment_id}")
            
        except Exception as e:
            logger.error(f"Failed to process payment success: {str(e)}")
            # Don't raise exception in webhook handler
    
    async def handle_payment_failure(
        self,
        razorpay_payment_id: str,
        razorpay_order_id: str,
        error_code: str,
        error_description: str
    ) -> None:
        """
        Handle failed payment webhook
        
        Args:
            razorpay_payment_id: Razorpay payment ID
            razorpay_order_id: Razorpay order ID
            error_code: Payment failure error code
            error_description: Payment failure description
        """
        try:
            logger.info(f"Processing payment failure: {razorpay_payment_id}")
            
            # Find payment record by order ID
            payment_response = self.db.table("payments").select("*").eq(
                "razorpay_order_id", razorpay_order_id
            ).single().execute()
            
            if not payment_response.data:
                logger.warning(f"Payment record not found for order: {razorpay_order_id}")
                return
            
            payment = payment_response.data
            
            # Update payment status
            self.db.table("payments").update({
                "status": "failed",
                "razorpay_payment_id": razorpay_payment_id,
                "failure_reason": f"{error_code}: {error_description}",
                "completed_at": datetime.utcnow().isoformat()
            }).eq("id", payment["id"]).execute()
            
            # If this is a booking payment, update booking status
            if payment.get("booking_id"):
                self.db.table("bookings").update({
                    "status": "payment_failed",
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", payment["booking_id"]).execute()
            
            logger.info(f"Payment failure processed: {razorpay_payment_id}")
            
        except Exception as e:
            logger.error(f"Failed to process payment failure: {str(e)}")
            # Don't raise exception in webhook handler
    
    async def handle_order_paid(
        self,
        razorpay_order_id: str,
        amount: int
    ) -> None:
        """
        Handle order paid webhook (alternative to payment.captured)
        
        Args:
            razorpay_order_id: Razorpay order ID
            amount: Order amount in paisa
        """
        try:
            logger.info(f"Processing order paid: {razorpay_order_id}")
            
            # Find payment record by order ID
            payment_response = self.db.table("payments").select("*").eq(
                "razorpay_order_id", razorpay_order_id
            ).single().execute()
            
            if not payment_response.data:
                logger.warning(f"Payment record not found for order: {razorpay_order_id}")
                return
            
            payment = payment_response.data
            
            # Update payment status if not already completed
            if payment["status"] != "completed":
                self.db.table("payments").update({
                    "status": "completed",
                    "completed_at": datetime.utcnow().isoformat()
                }).eq("id", payment["id"]).execute()
                
                # Handle booking/vendor activation
                if payment.get("booking_id"):
                    self.db.table("bookings").update({
                        "status": "confirmed",
                        "updated_at": datetime.utcnow().isoformat()
                    }).eq("id", payment["booking_id"]).execute()
                    
                    await self._send_booking_confirmation_email(payment["booking_id"])
                
                elif payment.get("vendor_request_id"):
                    await self._activate_vendor_salon(payment["vendor_request_id"])
            
            logger.info(f"Order paid processed: {razorpay_order_id}")
            
        except Exception as e:
            logger.error(f"Failed to process order paid: {str(e)}")
            # Don't raise exception in webhook handler
    
    async def _send_booking_confirmation_email(self, booking_id: str) -> None:
        """Send booking confirmation email"""
        try:
            # Get booking details with customer info
            booking_response = self.db.table("bookings").select("""
                *,
                customer:profiles!bookings_customer_id_fkey(email, full_name),
                salon:salons(business_name, address_line1, city, phone)
            """).eq("id", booking_id).single().execute()
            
            if booking_response.data:
                booking = booking_response.data
                customer = booking.get("customer", {})
                
                # Send confirmation email
                await email_service.send_booking_confirmation(
                    customer_email=customer.get("email"),
                    customer_name=customer.get("full_name", "Customer"),
                    booking_details=booking
                )
                
        except Exception as e:
            logger.error(f"Failed to send booking confirmation email: {str(e)}")
    
    async def _activate_vendor_salon(self, vendor_request_id: str) -> None:
        """Activate salon after successful vendor registration payment"""
        try:
            # Get vendor request details
            request_response = self.db.table("vendor_requests").select("""
                *,
                salon:salons!vendor_requests_salon_id_fkey(id, business_name)
            """).eq("id", vendor_request_id).single().execute()
            
            if request_response.data:
                vendor_request = request_response.data
                salon_id = vendor_request.get("salon_id")
                
                # Update salon status to active
                self.db.table("salons").update({
                    "is_active": True,
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", salon_id).execute()
                
                # Update vendor request status
                self.db.table("vendor_requests").update({
                    "status": "completed",
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", vendor_request_id).execute()
                
                logger.info(f"Activated salon {salon_id} after vendor payment")
                
        except Exception as e:
            logger.error(f"Failed to activate vendor salon: {str(e)}")
