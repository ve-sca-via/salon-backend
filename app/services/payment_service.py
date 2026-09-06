"""
Payment Service - Business Logic Layer

Handles all payment-related database operations and business logic:
- Vendor registration fee orders and verification
- Booking convenience fee orders and verification
- Payment refunds
- Payment history tracking

Follows service layer pattern - no direct DB calls in API layer

CREDENTIALS MANAGEMENT:
- Razorpay credentials are fetched fresh from database on each payment request
- Ensures credentials are always up-to-date
- No caching layer - changes take effect immediately
"""

from typing import Dict, Any, Optional
from fastapi import HTTPException, status
import logging

from app.services.payment import RazorpayService, resolve_razorpay_credentials
from app.services.config_service import ConfigService
from app.services.pricing_service import PricingService, LineItem
from app.services.email import email_service

logger = logging.getLogger(__name__)


class PaymentService:
    """Service for managing payment database operations"""
    
    def __init__(self, db_client):
        self.db = db_client
        self.config_service = ConfigService(db_client=db_client)
        self.razorpay = None  # Initialize lazily when needed
        self._razorpay_initialized = False
        self._razorpay_key_id = None
    
    async def _initialize_razorpay(self):
        """
        Initialize Razorpay client with credentials from database.
        Credentials are fetched fresh from database on each payment request.
        """
        if self._razorpay_initialized:
            return

        try:
            # Fetch Razorpay credentials from database (DB-only, no env fallback)
            razorpay_key_id, razorpay_key_secret = await resolve_razorpay_credentials(
                self.config_service
            )
        except Exception as e:
            logger.error(f"Failed to fetch Razorpay credentials from database: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment service is not configured. Please contact support."
            )

        if not razorpay_key_id or not razorpay_key_secret:
            logger.error("Razorpay credentials missing in system configuration")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment service is not configured. Please contact support."
            )

        # Initialize Razorpay service with database credentials only
        self.razorpay = RazorpayService(
            razorpay_key_id=razorpay_key_id,
            razorpay_key_secret=razorpay_key_secret
        )

        if not self.razorpay or not self.razorpay.client:
            logger.error("Razorpay initialization failed with configured database credentials")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment service is not configured. Please contact support."
            )

        self._razorpay_key_id = razorpay_key_id
        self._razorpay_initialized = True
        logger.info("Razorpay initialized with credentials from database")
    
    async def verify_cart_payment(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str
    ) -> bool:
        """
        Verify Razorpay payment signature for cart checkout
        
        This method should be called by CustomerService during checkout
        to verify payment before creating the booking.
        
        Args:
            razorpay_order_id: Order ID from Razorpay
            razorpay_payment_id: Payment ID from Razorpay
            razorpay_signature: Signature from Razorpay
        
        Returns:
            bool: True if signature is valid
            
        Raises:
            HTTPException: If verification fails or service not configured
        """
        # Initialize Razorpay with database credentials
        await self._initialize_razorpay()
        
        if not self.razorpay or not self.razorpay.client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment service not configured"
            )
        
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
            
            logger.info(f"Cart payment signature verified: {razorpay_order_id}")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Payment signature verification failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment verification failed"
            )
    
    async def create_cart_payment_order(
        self,
        user_id: str,
        coupon_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create Razorpay order for cart checkout (convenience fee payment)
        
        This is Step 8 of the cart checkout flow.
        
        Process:
        1. Fetches all cart items for user
        2. Calculates total service price from cart
        3. Calculates booking_fee (config: convenience_fee_percentage)
        4. Creates Razorpay order for convenience fee
        5. Returns order details for frontend to open Razorpay modal
        
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
                - breakdown: Dict with service_price, booking_fee, totals
                
        Raises:
            HTTPException 400: Cart is empty or invalid amount
            HTTPException 500: Failed to create Razorpay order
        """
        # Initialize Razorpay with database credentials
        await self._initialize_razorpay()
        
        try:
            # Get cart items
            cart_response = self.db.table("cart_items")\
                .select(
                    "id, service_id, quantity, "
                    "services(id, name, price, discounted_price, salon_id)"
                )\
                .eq("user_id", user_id)\
                .execute()
            
            if not cart_response.data or len(cart_response.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cart is empty"
                )
            
            # Build normalized line items and the cart snapshot for validation
            salon_id = None
            cart_snapshot = []
            line_items = []

            for item in cart_response.data:
                service = item.get("services", {})
                if salon_id is None:
                    salon_id = service.get("salon_id")

                original_unit_price = float(service.get("price", 0))
                discounted_price = service.get("discounted_price")
                effective_unit_price = float(discounted_price) if discounted_price is not None else original_unit_price
                quantity = item.get("quantity", 1)

                line_items.append(LineItem(original_unit_price, effective_unit_price, quantity))
                cart_snapshot.append({
                    "service_id": item.get("service_id"),
                    "quantity": quantity,
                    "unit_price": effective_unit_price
                })

            # Get convenience fee percentage from config (dynamically set by admin)
            try:
                fee_config = await self.config_service.get_config("convenience_fee_percentage")
                convenience_fee_percentage = float(fee_config.get("config_value"))
                logger.info(f"Using convenience_fee_percentage from config: {convenience_fee_percentage}%")
            except ValueError as e:
                # Config not found in database
                logger.error(f"Configuration missing: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Payment system is not configured. Please contact support."
                )
            except (TypeError, Exception) as e:
                # Other errors (invalid value, database error, etc.)
                logger.error(f"Failed to get convenience_fee_percentage from config: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Unable to process payment at this time. Please try again or contact support."
                )

            # Single source of truth for pricing (applies coupon + best-of vs sale)
            pricing = await PricingService(self.db).compute_booking_pricing(
                line_items=line_items,
                convenience_fee_percentage=convenience_fee_percentage,
                salon_id=salon_id,
                customer_id=user_id,
                coupon_code=coupon_code,
            )

            booking_fee = pricing["convenience_fee_due"]
            if booking_fee < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid payment amount"
                )

            # Razorpay rejects orders below ₹1 (100 paise). Floor the payable
            # convenience fee to the gateway minimum so low-value bookings can
            # still be paid online. (A 100%-off fee coupon still pays the floor.)
            RAZORPAY_MIN_AMOUNT = 1.0
            total_payment = max(booking_fee, RAZORPAY_MIN_AMOUNT)

            # Pin the exact priced breakdown into the order so checkout records
            # what was actually CHARGED, not a fresh recompute that could diverge
            # if coupon/sale/price state changes between now and checkout (D4 /
            # audit C1). convenience_fee_due reflects the floored amount the
            # customer truly pays (M9).
            pinned_pricing = {
                "subtotal_service_price": pricing["subtotal_service_price"],
                "discount_amount": pricing["discount_amount"],
                "service_total_due": pricing["service_total_due"],
                "convenience_fee_base": pricing["convenience_fee_base"],
                "convenience_fee_discount": pricing["convenience_fee_discount"],
                "convenience_fee_due": round(total_payment, 2),
                "total_amount": round(pricing["service_total_due"] + total_payment, 2),
                "coupon_id": pricing["coupon_id"],
                "coupon_code": pricing["coupon_code"],
                "coupon_gross_discount": pricing.get("coupon_gross_discount", 0.0),
            }

            # Create Razorpay order with cart + pinned-pricing snapshot. Checkout
            # trusts these values (after re-validating the cart hasn't changed)
            # instead of recomputing.
            import json
            order = self.razorpay.create_order(
                amount=total_payment,
                currency="INR",
                receipt=f"cart_{user_id[:8]}",
                notes={
                    "customer_id": user_id,
                    "salon_id": salon_id,
                    "type": "cart_checkout",
                    "service_total": pricing["service_total_due"],
                    "original_service_total": pricing["original_service_price"],
                    "booking_fee": booking_fee,
                    "coupon_code": pricing["coupon_code"] or "",
                    "pricing": json.dumps(pinned_pricing),  # Pinned breakdown (authoritative)
                    "cart_snapshot": json.dumps(cart_snapshot),  # Store cart state
                    "cart_item_count": len(cart_snapshot)
                }
            )

            logger.info(f"Created cart payment order: {order['order_id']} for user {user_id}")

            return {
                "order_id": order["order_id"],
                "amount": total_payment,
                "amount_paise": int(round(total_payment * 100)),
                "currency": "INR",
                "key_id": self._razorpay_key_id,
                "breakdown": {
                    "service_price": pricing["service_total_due"],
                    "original_service_price": pricing["original_service_price"],
                    "subtotal_service_price": pricing["subtotal_service_price"],
                    "discount_amount": pricing["discount_amount"],
                    "convenience_fee_base": pricing["convenience_fee_base"],
                    "convenience_fee_discount": pricing["convenience_fee_discount"],
                    "booking_fee": booking_fee,
                    "total_to_pay_now": total_payment,
                    "pay_at_salon": pricing["service_total_due"],
                    "coupon_code": pricing["coupon_code"],
                    "coupon_reason": pricing["coupon_reason"],
                }
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create cart payment order: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to create payment order. Please try again or contact support."
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
        # Initialize Razorpay with database credentials
        await self._initialize_razorpay()
        
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
            
            # Check if payment already completed for this vendor request
            existing_payment = self.db.table("vendor_registration_payments").select(
                "id, razorpay_order_id, status"
            ).eq("vendor_request_id", vendor_request_id).eq("status", "success").execute()
            
            if existing_payment.data and len(existing_payment.data) > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Registration fee already paid for this request"
                )
            
            # Cancel any existing pending orders for this vendor request (prevent duplicates)
            pending_orders = self.db.table("vendor_registration_payments").select(
                "id, razorpay_order_id"
            ).eq("vendor_request_id", vendor_request_id).eq("vendor_id", user_id).eq("status", "pending").execute()
            
            if pending_orders.data and len(pending_orders.data) > 0:
                # Mark old pending orders as failed
                for old_order in pending_orders.data:
                    self.db.table("vendor_registration_payments").update({
                        "status": "failed",
                        "payment_failed_at": "now()",
                        "failure_reason": "Replaced by new payment attempt",
                        "updated_at": "now()"
                    }).eq("id", old_order["id"]).execute()
                    logger.info(f"Cancelled pending order: {old_order['razorpay_order_id']}")
            
            # Get registration fee from config (no fallback - must exist in database)
            registration_fee_config = await self.config_service.get_config("registration_fee_amount")
            registration_fee = float(registration_fee_config.get("config_value"))
            
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
                "vendor_request_id": vendor_request_id,  # Direct column, not metadata
                "amount": registration_fee,
                "razorpay_order_id": order["order_id"],
                "status": "pending",
                "created_at": "now()"
            }
            
            self.db.table("vendor_registration_payments").insert(payment_data).execute()
            
            logger.info(f"Created vendor registration order: {order['order_id']}")
            
            return {
                "order_id": order["order_id"],
                "amount": registration_fee,
                "amount_paise": int(registration_fee * 100),
                "currency": "INR",
                "key_id": self._razorpay_key_id
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
        Verify vendor registration payment and activate salon.
        
        Implements idempotency and race condition protection through:
        1. Atomic UPDATE with status check (prevents double-processing)
        2. Idempotency check for already-completed payments
        
        Args:
            razorpay_order_id: Order ID from Razorpay
            razorpay_payment_id: Payment ID from Razorpay
            razorpay_signature: Signature from Razorpay
            user_id: User ID (for verification)
        
        Returns:
            Success message with salon activation details
        """
        # Initialize Razorpay with database credentials
        await self._initialize_razorpay()
        
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
            
            # IDEMPOTENCY CHECK: Fetch payment record first
            payment_record = self.db.table("vendor_registration_payments").select(
                "*, vendor_id, salon_id, vendor_request_id"
            ).eq("razorpay_order_id", razorpay_order_id).single().execute()
            
            if not payment_record.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Payment record not found"
                )
            
            payment_data = payment_record.data
            
            # Check if payment is already processed (idempotent behavior)
            if payment_data.get("status") == "success":
                logger.warning(f"Vendor registration payment already processed (idempotent return): {razorpay_order_id}")
                return {
                    "success": True,
                    "message": "Payment already verified.",
                    "payment_id": payment_data.get("razorpay_payment_id"),
                    "salon_id": payment_data.get("salon_id")
                }
            
            vendor_request_id = payment_data.get("vendor_request_id")  # Direct column access
            
            # ATOMIC UPDATE with status check to prevent race conditions
            # Only update if status is still 'pending' (optimistic locking pattern)
            payment_update = self.db.table("vendor_registration_payments").update({
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
                "status": "success",
                "payment_completed_at": "now()",
                "updated_at": "now()"
            }).eq("razorpay_order_id", razorpay_order_id).eq("status", "pending").execute()
            
            # Check if update succeeded (no rows affected = payment already processed by concurrent request)
            if not payment_update.data or len(payment_update.data) == 0:
                logger.warning(f"Vendor registration payment already processed by concurrent request: {razorpay_order_id}")
                # Re-fetch the completed payment data
                completed_payment = self.db.table("vendor_registration_payments").select(
                    "*, salon_id"
                ).eq("razorpay_order_id", razorpay_order_id).single().execute()
                
                return {
                    "success": True,
                    "message": "Payment already verified.",
                    "payment_id": completed_payment.data.get("razorpay_payment_id"),
                    "salon_id": completed_payment.data.get("salon_id")
                }
            
            # Get vendor join request to find salon
            salon_data = None
            owner_name = None
            owner_email = None
            if vendor_request_id:
                vendor_request = self.db.table("vendor_join_requests").select(
                    "id, owner_name, owner_email"
                ).eq("id", vendor_request_id).single().execute()

                if vendor_request.data:
                    owner_name = vendor_request.data.get("owner_name")
                    owner_email = vendor_request.data.get("owner_email")

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
                            "updated_at": "now()"
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
            
            if owner_email:
                email_sent = await email_service.send_vendor_registration_receipt_email(
                    to_email=owner_email,
                    owner_name=owner_name or "there",
                    salon_name=salon_data["business_name"],
                    amount=float(payment_data.get("amount") or 0),
                    razorpay_payment_id=razorpay_payment_id,
                    salon_id=salon_id
                )
                if email_sent:
                    logger.info(f"Registration receipt email sent to {owner_email}")
                else:
                    logger.warning(f"Failed to send registration receipt email to {owner_email}")
            else:
                logger.warning(f"No owner_email on file for vendor_request_id={vendor_request_id}; skipping registration receipt email")

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
