"""
Customer Service - Business Logic Layer
Handles all customer-facing operations: cart, bookings, salons, favorites, reviews
Separated from HTTP layer for better testability and reusability
"""
import logging
from typing import Dict, Any, Optional, List
from app.schemas.request.customer import CartItemCreate, ReviewCreate, ReviewUpdate
from datetime import datetime
from fastapi import HTTPException, status

from app.core.auth import verify_review_feedback_token

logger = logging.getLogger(__name__)


class CustomerService:
    """
    Service class for customer operations.
    Handles cart, bookings, salon browsing, favorites, and reviews.
    """
    
    def __init__(self, db_client):
        """Initialize service with database client"""
        self.db = db_client
    
    # =====================================================
    # CART OPERATIONS
    # =====================================================
    
    async def get_cart(self, customer_id: str) -> Dict[str, Any]:
        """
        Get all cart items for a customer from normalized cart_items table.
        
        Args:
            customer_id: Customer user ID
            
        Returns:
            Dict with cart items, totals, and salon info
            
        Raises:
            HTTPException: If query fails
        """
        try:
            # Query cart_items with service and salon details
            response = self.db.table("cart_items")\
                .select(
                    "id, service_id, salon_id, quantity, metadata, created_at, "
                    "services(id, name, price, discounted_price, discount_percentage, duration_minutes, image_url, is_active), "
                    "salons(id, business_name, city, state)"
                )\
                .eq("user_id", customer_id)\
                .execute()
            
            if not response.data:
                # Return empty cart if no cart items exist
                return {
                    "success": True,
                    "items": [],
                    "salon_id": None,
                    "salon_name": None,
                    "salon_details": None,
                    "total_amount": 0.0,
                    "item_count": 0
                }
            
            # Process cart items
            items_with_details: List[Dict[str, Any]] = []
            total_amount = 0.0
            item_count = 0
            salon_id = None
            salon_name = None
            
            for item in response.data:
                service_details = item.get("services", {})
                salon_details = item.get("salons", {})
                
                # Set salon info from first item
                if salon_id is None:
                    salon_id = item.get("salon_id")
                    salon_name = salon_details.get("business_name")
                
                unit_price = self._get_effective_service_price(service_details)
                quantity = item.get("quantity", 1)
                line_total = unit_price * quantity
                total_amount += line_total
                item_count += quantity
                
                items_with_details.append({
                    "id": item.get("id"),
                    "service_id": item.get("service_id"),
                    "salon_id": item.get("salon_id"),
                    "quantity": quantity,
                    "metadata": item.get("metadata", {}),
                    "service_details": service_details,
                    "salon_details": salon_details,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "created_at": item.get("created_at")
                })
            
            logger.info(f"Retrieved cart for customer {customer_id}: {item_count} items")
            
            return {
                "success": True,
                "items": items_with_details,
                "salon_id": salon_id,
                "salon_name": salon_name,
                "salon_details": None,
                "total_amount": total_amount,
                "item_count": item_count
            }
        
        except Exception as e:
            logger.error(f"Failed to get cart for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve cart"
            )

    async def validate_coupon(self, customer_id: str, code: str) -> Dict[str, Any]:
        """
        Preview a coupon against the customer's current cart (the "Apply coupon" button).

        Returns a CouponValidationResult-shaped dict: {valid, reason, coupon_id,
        coupon_code, breakdown}. Uses the same PricingService as checkout, so the
        previewed discount matches what will actually be charged.
        """
        from app.services.pricing_service import PricingService, LineItem

        cart = await self.get_cart(customer_id)
        if not cart.get("items"):
            return {"valid": False, "reason": "Your cart is empty.", "coupon_id": None,
                    "coupon_code": None, "breakdown": None}

        salon_id = cart["salon_id"]
        line_items = [
            LineItem(
                float(item["service_details"].get("price", 0) or 0),
                float(item["unit_price"]),
                item["quantity"],
            )
            for item in cart["items"]
        ]

        # Convenience fee % (admin-managed; required)
        config_response = self.db.table("system_config")\
            .select("config_value")\
            .eq("config_key", "convenience_fee_percentage")\
            .single()\
            .execute()
        try:
            convenience_fee_percentage = float(config_response.data["config_value"])
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Payment configuration not available. Please contact support."
            )

        pricing = await PricingService(self.db).compute_booking_pricing(
            line_items=line_items,
            convenience_fee_percentage=convenience_fee_percentage,
            salon_id=salon_id,
            customer_id=customer_id,
            coupon_code=code,
        )

        breakdown = {
            "subtotal_service_price": pricing["subtotal_service_price"],
            "discount_amount": pricing["discount_amount"],
            "service_total_due": pricing["service_total_due"],
            "convenience_fee_base": pricing["convenience_fee_base"],
            "convenience_fee_discount": pricing["convenience_fee_discount"],
            "convenience_fee_due": pricing["convenience_fee_due"],
            "total_amount": pricing["total_amount"],
            "discount_source": pricing["discount_source"],
        }

        if pricing["coupon_id"]:
            return {"valid": True, "reason": None, "coupon_id": pricing["coupon_id"],
                    "coupon_code": pricing["coupon_code"], "breakdown": breakdown}

        return {"valid": False, "reason": pricing["coupon_reason"] or "This coupon could not be applied.",
                "coupon_id": None, "coupon_code": None, "breakdown": breakdown}

    async def add_to_cart(
        self,
        customer_id: str,
        cart_item: CartItemCreate
    ) -> Dict[str, Any]:
        """
        Add item to cart or increment quantity if already exists.
        Validates that all items belong to same salon.
        
        Args:
            customer_id: Customer user ID
            cart_item: Dict with salon_id, service_id, etc.
            
        Returns:
            Dict with success flag and cart item data
            
        Raises:
            HTTPException: If validation fails or different salon
        """
        try:
            service_id = cart_item.service_id
            if not service_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="service_id is required"
                )

            # Get service details to validate and get salon_id
            service_response = self.db.table("services")\
                .select("id, name, price, duration_minutes, salon_id, is_active, image_url")\
                .eq("id", service_id)\
                .maybe_single()\
                .execute()

            if not service_response or not service_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Service not available"
                )

            service_details = service_response.data
            if not service_details.get("is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Service is inactive"
                )

            service_salon_id = service_details['salon_id']
            
            # Check if salon is accepting bookings
            salon_response = self.db.table("salons")\
                .select("id, business_name, accepting_bookings, is_active")\
                .eq("id", service_salon_id)\
                .maybe_single()\
                .execute()

            if not salon_response or not salon_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Salon not found"
                )
            
            salon = salon_response.data
            if not salon.get("is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Salon is currently inactive"
                )
            
            if not salon.get("accepting_bookings", True):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This salon is not accepting bookings at this time"
                )
            
            # Check if user has cart items from a different salon
            existing_cart = self.db.table("cart_items")\
                .select("salon_id")\
                .eq("user_id", customer_id)\
                .limit(1)\
                .execute()
            
            if existing_cart.data:
                existing_salon_id = existing_cart.data[0].get("salon_id")
                if existing_salon_id != service_salon_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot add services from different salons. Please clear cart first."
                    )
            
            # Check if item already exists in cart
            check_response = self.db.table("cart_items")\
                .select("id, quantity")\
                .eq("user_id", customer_id)\
                .eq("service_id", service_id)\
                .execute()
            
            quantity = cart_item.quantity
            
            if check_response.data:
                # Item exists - update quantity
                existing_item = check_response.data[0]
                new_quantity = existing_item.get("quantity", 1) + quantity
                
                response = self.db.table("cart_items")\
                    .update({"quantity": new_quantity})\
                    .eq("id", existing_item["id"])\
                    .execute()
                
                logger.info(f"Updated cart item quantity for customer {customer_id}")
                
                return {
                    "success": True,
                    "message": "Cart item quantity updated",
                    "cart_item": response.data[0] if response.data else None
                }
            else:
                # Item doesn't exist - insert new
                cart_item_data = {
                    "user_id": customer_id,
                    "salon_id": service_salon_id,
                    "service_id": service_id,
                    "quantity": quantity,
                    "metadata": cart_item.metadata or {}
                }
                
                response = self.db.table("cart_items")\
                    .insert(cart_item_data)\
                    .execute()
                
                logger.info(f"Added new item to cart for customer {customer_id}")
                
                return {
                    "success": True,
                    "message": "Item added to cart",
                    "cart_item": response.data[0] if response.data else None
                }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to add to cart for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add to cart"
            )
    
    async def update_cart_item(
        self,
        customer_id: str,
        item_id: str,
        quantity: int
    ) -> Dict[str, Any]:
        """
        Update cart item quantity in normalized cart_items table.

        Args:
            customer_id: Customer user ID
            item_id: Cart item ID to update
            quantity: New quantity (must be > 0)

        Returns:
            Updated cart item data

        Raises:
            HTTPException: If cart/item not found or update fails
        """
        try:
            # Validate quantity
            if quantity <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Quantity must be greater than 0"
                )

            # Verify cart item exists and belongs to user
            check_response = self.db.table("cart_items")\
                .select("id")\
                .eq("id", item_id)\
                .eq("user_id", customer_id)\
                .execute()

            if not check_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cart item not found"
                )

            # Update quantity
            response = self.db.table("cart_items")\
                .update({"quantity": quantity})\
                .eq("id", item_id)\
                .eq("user_id", customer_id)\
                .execute()

            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update cart item"
                )

            logger.info(f"Updated cart item {item_id} quantity to {quantity} for customer {customer_id}")

            return {
                "success": True,
                "message": "Cart item updated successfully",
                "cart_item": response.data[0]
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update cart item {item_id} for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update cart item"
            )
    
    async def remove_from_cart(
        self,
        item_id: str,
        customer_id: str
    ) -> Dict[str, Any]:
        """
        Remove item from cart using normalized cart_items table.

        Args:
            item_id: Cart item ID to remove
            customer_id: Customer user ID (for ownership verification)

        Returns:
            Dict with success flag

        Raises:
            HTTPException: If item not found
        """
        try:
            # Delete cart item (user_id ensures ownership)
            response = self.db.table("cart_items")\
                .delete()\
                .eq("id", item_id)\
                .eq("user_id", customer_id)\
                .execute()

            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cart item not found"
                )

            logger.info(f"Removed cart item {item_id} for customer {customer_id}")

            return {
                "success": True,
                "message": "Item removed from cart"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to remove cart item {item_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to remove cart item"
            )
    
    async def clear_cart(self, customer_id: str) -> Dict[str, Any]:
        """
        Clear all items from cart using normalized cart_items table.

        Args:
            customer_id: Customer user ID

        Returns:
            Dict with success flag and deleted count

        Raises:
            HTTPException: If operation fails
        """
        try:
            # Count items before deletion
            count_response = self.db.table("cart_items")\
                .select("id", count="exact")\
                .eq("user_id", customer_id)\
                .execute()

            # Delete all cart items for user
            self.db.table("cart_items")\
                .delete()\
                .eq("user_id", customer_id)\
                .execute()

            deleted_count = count_response.count if count_response.count else 0

            logger.info(f"Cleared cart for customer {customer_id}: {deleted_count} items")

            return {
                "success": True,
                "message": "Cart cleared",
                "deleted_count": deleted_count
            }

        except Exception as e:
            logger.error(f"Failed to clear cart for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to clear cart"
            )
    
    async def checkout_cart(
        self,
        customer_id: str,
        checkout_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create booking from cart items with payment verification.
        
        This is the final step (Step 9-14) of the cart checkout flow:
        - Receives payment details from Razorpay
        - Verifies payment signature for security
        - Creates booking with all cart services
        - Creates booking_payment record in database
        - Clears cart after successful booking
        
        Payment Verification:
        - If razorpay_payment_id provided: Verifies signature with Razorpay API
        - If signature invalid: Rejects checkout (prevents fraud)
        - If signature valid: Proceeds to create booking
        
        Args:
            customer_id: Customer user ID
            checkout_data: Dict with:
                - booking_date: Date for appointment (YYYY-MM-DD)
                - time_slots: List of time slots (max 3) e.g. ["2:30 PM", "2:45 PM"]
                - razorpay_order_id: Order ID from payment/cart/create-order
                - razorpay_payment_id: Payment ID from Razorpay after payment
                - razorpay_signature: Signature from Razorpay for verification
                - payment_method: Payment method (default: 'razorpay')
                - notes: Optional booking notes
            
        Returns:
            Dict with:
                - success: True if booking created
                - message: Success message
                - booking: Complete booking data
                - booking_id: UUID of created booking
                - booking_number: Human-readable booking number
            
        Raises:
            HTTPException 400: Cart empty, salon inactive, or payment verification failed
            HTTPException 404: Salon not found
            HTTPException 500: Booking creation failed
        """
        try:
            # Get cart items
            cart_response = await self.get_cart(customer_id)
            
            if not cart_response.get("items") or len(cart_response["items"]) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cart is empty"
                )
            
            cart_items = cart_response["items"]
            salon_id = cart_response["salon_id"]
            
            # Check if salon is accepting bookings
            salon_response = self.db.table("salons")\
                .select("id, business_name, accepting_bookings, is_active")\
                .eq("id", salon_id)\
                .single()\
                .execute()
            
            if not salon_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Salon not found"
                )
            
            salon = salon_response.data
            
            if not salon.get("is_active"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Salon is currently inactive"
                )
            
            if not salon.get("accepting_bookings", True):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Salon is not accepting bookings at this time"
                )
            
            # Prepare services for booking
            from app.schemas.request.booking import ServiceItem
            services = [
                ServiceItem(
                    service_id=item["service_id"],
                    quantity=item["quantity"]
                )
                for item in cart_items
            ]
            
            # Get system config for convenience fee percentage (dynamically set by admin)
            # Use actual column names `config_key` / `config_value` (not `key`/`value`)
            config_response = self.db.table("system_config")\
                .select("config_key, config_value")\
                .eq("config_key", "convenience_fee_percentage")\
                .single()\
                .execute()

            convenience_fee_percentage = None
            if config_response.data:
                # When using single(), response.data is a dict
                raw_value = config_response.data.get("config_value")
                try:
                    convenience_fee_percentage = float(raw_value)
                    logger.info(f"Using convenience_fee_percentage from config: {convenience_fee_percentage}%")
                except Exception:
                    logger.error(f"Invalid convenience_fee_percentage config value: {raw_value}")
            
            if convenience_fee_percentage is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Payment configuration not available. Please contact support."
                )

            # IDEMPOTENCY CHECK: Check if payment already used for a booking
            if checkout_data.get("razorpay_payment_id"):
                existing_booking = self.db.table("bookings").select(
                    "id, booking_number, status, booking_date, time_slots, total_amount, salon_id, salons(business_name)"
                ).eq("razorpay_payment_id", checkout_data["razorpay_payment_id"]).execute()
                
                if existing_booking.data:
                    logger.warning(f"Payment {checkout_data['razorpay_payment_id']} already used for booking. Returning existing booking (idempotent).")
                    existing = existing_booking.data[0]
                    return {
                        "success": True,
                        "message": "Booking already created with this payment",
                        "booking": existing,
                        "booking_id": existing.get("id"),
                        "booking_number": existing.get("booking_number")
                    }
            
            # Coupon applied at order-creation time is the authoritative one (it's
            # what the convenience fee was charged on). Read it from the order notes
            # below; fall back to whatever the client sent.
            applied_coupon_code = checkout_data.get("coupon_code")

            # CART VALIDATION: Verify cart hasn't changed since payment order creation
            # This prevents race conditions where cart is modified between payment and checkout
            if checkout_data.get("razorpay_order_id"):
                try:
                    # Fetch the Razorpay order to get the cart snapshot
                    from app.services.payment_service import PaymentService
                    payment_service = PaymentService(db_client=self.db)
                    await payment_service._initialize_razorpay()
                    
                    import json
                    razorpay_order = payment_service.razorpay.client.order.fetch(checkout_data["razorpay_order_id"])
                    stored_snapshot = razorpay_order.get("notes", {}).get("cart_snapshot")
                    stored_item_count = razorpay_order.get("notes", {}).get("cart_item_count")
                    # Use the coupon that was actually priced into this order
                    note_coupon = razorpay_order.get("notes", {}).get("coupon_code")
                    if note_coupon:
                        applied_coupon_code = note_coupon
                    
                    if stored_snapshot and stored_item_count:
                        stored_cart = json.loads(stored_snapshot)
                        current_item_count = len(cart_response["items"])
                        
                        # Quick check: item count mismatch
                        if int(stored_item_count) != current_item_count:
                            logger.warning(f"Cart modified: expected {stored_item_count} items, found {current_item_count}")
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Your cart has been modified since payment. Please try checkout again."
                            )
                        
                        # Detailed validation: compare service IDs and quantities
                        current_cart = {item["service_id"]: item["quantity"] for item in cart_response["items"]}
                        stored_cart_dict = {item["service_id"]: item["quantity"] for item in stored_cart}
                        
                        if current_cart != stored_cart_dict:
                            logger.warning("Cart contents changed since payment order creation")
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Your cart contents have changed since payment. Please try checkout again."
                            )
                        
                        logger.info("Cart validation passed: snapshot matches current cart")
                except HTTPException:
                    raise
                except Exception as e:
                    # Don't fail checkout if cart validation fails (log warning only)
                    logger.warning(f"Cart validation skipped due to error: {str(e)}")
            
            # Verify Razorpay payment signature if payment details provided
            if checkout_data.get("razorpay_payment_id") and checkout_data.get("razorpay_signature"):
                from app.services.payment_service import PaymentService
                
                # Use PaymentService to verify payment (proper separation of concerns)
                payment_service = PaymentService(db_client=self.db)
                
                try:
                    await payment_service.verify_cart_payment(
                        razorpay_order_id=checkout_data["razorpay_order_id"],
                        razorpay_payment_id=checkout_data["razorpay_payment_id"],
                        razorpay_signature=checkout_data["razorpay_signature"]
                    )
                    logger.info(f"Payment verified for customer {customer_id}")
                except HTTPException:
                    # Re-raise HTTPException as-is
                    raise
                except Exception as e:
                    logger.error(f"Payment verification failed: {str(e)}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Payment verification failed. Please contact support."
                    )
            
            # Create booking using BookingService
            from app.services.booking_service import BookingService
            from app.schemas import BookingCreate
            
            booking_service = BookingService(self.db)
            
            # Prepare booking data
            booking_data = BookingCreate(
                salon_id=salon_id,
                booking_date=checkout_data["booking_date"],
                booking_time=checkout_data["time_slots"][0],  # Primary time slot
                time_slots=checkout_data["time_slots"],
                services=services,
                payment_status="paid" if checkout_data.get("razorpay_payment_id") else "pending",
                payment_method=checkout_data.get("payment_method", "razorpay"),
                razorpay_order_id=checkout_data.get("razorpay_order_id"),
                razorpay_payment_id=checkout_data.get("razorpay_payment_id"),
                razorpay_signature=checkout_data.get("razorpay_signature"),
                notes=checkout_data.get("notes"),
                coupon_code=applied_coupon_code
            )
            
            # Create booking
            booking = await booking_service.create_booking(
                booking=booking_data,
                current_user_id=customer_id
            )
            
            # Clear cart after successful booking
            await self.clear_cart(customer_id)
            
            logger.info(f"Checkout completed for customer {customer_id}, booking created: {booking.get('id')}")
            
            return {
                "success": True,
                "message": "Booking created successfully",
                "booking": booking,
                "booking_id": booking.get("id"),
                "booking_number": booking.get("booking_number")
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to checkout cart for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to complete checkout"
            )
    
    # =====================================================
    # BOOKING OPERATIONS
    # =====================================================
    
    async def get_customer_bookings(self, customer_id: str) -> Dict[str, Any]:
        """
        Get all bookings for a customer with salon and service details.
        
        Args:
            customer_id: Customer user ID
            
        Returns:
            Dict with bookings list and count
            
        Raises:
            HTTPException: If query fails
        """
        try:
            response = self.db.table("bookings")\
                .select(
                    "*, "
                    "salons(business_name, city, address, phone, logo_url), "
                    "profiles(full_name, phone)"
                )\
                .eq("customer_id", customer_id)\
                .order("booking_date", desc=True)\
                .execute()
            
            bookings = response.data or []
            
            # Transform data to flatten nested objects and parse services JSONB
            transformed_bookings = []
            for booking in bookings:
                # Parse services JSONB array BEFORE transforming (since transform removes it)
                services_array = booking.get("services", [])
                if not services_array or not isinstance(services_array, list):
                    services_array = []
                
                # Transform booking data
                transformed_booking = self._transform_booking_data(booking)
                
                # Add services array to transformed booking
                transformed_booking["services"] = services_array
                
                transformed_bookings.append(transformed_booking)
            
            logger.info(f"Retrieved {len(transformed_bookings)} bookings for customer {customer_id}")
            
            return {
                "success": True,
                "data": transformed_bookings,
                "count": len(transformed_bookings)
            }
        
        except Exception as e:
            logger.error(f"Failed to get bookings for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve bookings"
            )
    
    # =====================================================
    # FAVORITES
    # =====================================================
    
    async def get_favorites(self, customer_id: str) -> Dict[str, Any]:
        """
        Get customer's favorite salons.
        
        Args:
            customer_id: Customer user ID
            
        Returns:
            Dict with favorite salons list and count
            
        Raises:
            HTTPException: If query fails
        """
        try:
            # Get favorite salon IDs
            favorites_response = self.db.table("favorites")\
                .select("salon_id")\
                .eq("user_id", customer_id)\
                .execute()
            
            if not favorites_response.data:
                return {"success": True, "favorites": [], "count": 0}
            
            # Get salon details
            salon_ids = [fav["salon_id"] for fav in favorites_response.data]
            
            salons_response = self.db.table("salons")\
                .select("*")\
                .in_("id", salon_ids)\
                .eq("is_active", True)\
                .eq("is_verified", True)\
                .eq("registration_fee_paid", True)\
                .execute()
            
            favorites = salons_response.data or []
            
            logger.info(f"Retrieved {len(favorites)} favorites for customer {customer_id}")
            
            return {
                "success": True,
                "favorites": favorites,
                "count": len(favorites)
            }
        
        except Exception as e:
            logger.error(f"Failed to get favorites for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve favorites"
            )
    
    async def add_favorite(
        self,
        customer_id: str,
        salon_id: str
    ) -> Dict[str, Any]:
        """
        Add salon to favorites (idempotent).
        
        Args:
            customer_id: Customer user ID
            salon_id: Salon ID to favorite
            
        Returns:
            Dict with success flag and favorite data
            
        Raises:
            HTTPException: If operation fails
        """
        try:
            # Check if already favorited
            existing = self.db.table("favorites")\
                .select("id")\
                .eq("user_id", customer_id)\
                .eq("salon_id", salon_id)\
                .execute()
            
            if existing.data:
                logger.info(f"Salon {salon_id} already favorited by customer {customer_id}")
                return {
                    "success": True,
                    "message": "Salon already in favorites",
                    "favorite": existing.data[0]
                }
            
            # Add to favorites
            response = self.db.table("favorites")\
                .insert({
                    "user_id": customer_id,
                    "salon_id": salon_id,
                    "created_at": datetime.utcnow().isoformat()
                })\
                .execute()
            
            logger.info(f"Added salon {salon_id} to favorites for customer {customer_id}")
            
            if response.data:
                return {
                    "success": True,
                    "message": "Added to favorites",
                    "favorite": response.data[0]
                }
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to add favorite"
            )
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to add favorite for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add favorite"
            )
    
    async def remove_favorite(
        self,
        customer_id: str,
        salon_id: str
    ) -> Dict[str, Any]:
        """
        Remove salon from favorites.
        
        Args:
            customer_id: Customer user ID
            salon_id: Salon ID to unfavorite
            
        Returns:
            Dict with success flag
            
        Raises:
            HTTPException: If operation fails
        """
        try:
            self.db.table("favorites")\
                .delete()\
                .eq("user_id", customer_id)\
                .eq("salon_id", salon_id)\
                .execute()
            
            logger.info(f"Removed salon {salon_id} from favorites for customer {customer_id}")

            return {
                "success": True,
                "message": "Removed from favorites"
            }

        except Exception as e:
            logger.error(f"Failed to remove favorite for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to remove favorite"
            )

    # =====================================================
    # PRODUCT FAVORITES
    # =====================================================

    async def get_favorite_products(self, customer_id: str) -> Dict[str, Any]:
        """
        Get customer's favorite (saved) products.

        Args:
            customer_id: Customer user ID

        Returns:
            Dict with favorite products list and count

        Raises:
            HTTPException: If query fails
        """
        try:
            # Get favorite product IDs
            favorites_response = self.db.table("product_favorites")\
                .select("product_id")\
                .eq("user_id", customer_id)\
                .execute()

            if not favorites_response.data:
                return {"success": True, "favorites": [], "count": 0}

            # Get product details (only active products)
            product_ids = [fav["product_id"] for fav in favorites_response.data]

            products_response = self.db.table("products")\
                .select("*")\
                .in_("id", product_ids)\
                .eq("is_active", True)\
                .execute()

            favorites = products_response.data or []

            logger.info(f"Retrieved {len(favorites)} favorite products for customer {customer_id}")

            return {
                "success": True,
                "favorites": favorites,
                "count": len(favorites)
            }

        except Exception as e:
            logger.error(f"Failed to get favorite products for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve favorite products"
            )

    async def add_favorite_product(
        self,
        customer_id: str,
        product_id: str
    ) -> Dict[str, Any]:
        """
        Add product to favorites (idempotent).

        Args:
            customer_id: Customer user ID
            product_id: Product ID to favorite

        Returns:
            Dict with success flag and favorite data

        Raises:
            HTTPException: If operation fails
        """
        try:
            # Reject unknown/inactive products so the saved tab stays clean
            product = self.db.table("products")\
                .select("id")\
                .eq("id", product_id)\
                .eq("is_active", True)\
                .execute()

            if not product.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Product not found"
                )

            # Check if already favorited
            existing = self.db.table("product_favorites")\
                .select("id")\
                .eq("user_id", customer_id)\
                .eq("product_id", product_id)\
                .execute()

            if existing.data:
                logger.info(f"Product {product_id} already favorited by customer {customer_id}")
                return {
                    "success": True,
                    "message": "Product already in favorites",
                    "favorite": existing.data[0]
                }

            # Add to favorites
            response = self.db.table("product_favorites")\
                .insert({
                    "user_id": customer_id,
                    "product_id": product_id,
                    "created_at": datetime.utcnow().isoformat()
                })\
                .execute()

            logger.info(f"Added product {product_id} to favorites for customer {customer_id}")

            if response.data:
                return {
                    "success": True,
                    "message": "Added to favorites",
                    "favorite": response.data[0]
                }

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to add favorite product"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to add favorite product for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add favorite product"
            )

    async def remove_favorite_product(
        self,
        customer_id: str,
        product_id: str
    ) -> Dict[str, Any]:
        """
        Remove product from favorites.

        Args:
            customer_id: Customer user ID
            product_id: Product ID to unfavorite

        Returns:
            Dict with success flag

        Raises:
            HTTPException: If operation fails
        """
        try:
            self.db.table("product_favorites")\
                .delete()\
                .eq("user_id", customer_id)\
                .eq("product_id", product_id)\
                .execute()

            logger.info(f"Removed product {product_id} from favorites for customer {customer_id}")

            return {
                "success": True,
                "message": "Removed from favorites"
            }

        except Exception as e:
            logger.error(f"Failed to remove favorite product for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to remove favorite product"
            )

    # =====================================================
    # REVIEWS
    # =====================================================
    
    async def get_customer_reviews(self, customer_id: str) -> Dict[str, Any]:
        """
        Get customer's reviews.
        
        Args:
            customer_id: Customer user ID
            
        Returns:
            Dict with reviews list and count
            
        Raises:
            HTTPException: If query fails
        """
        try:
            response = self.db.table("reviews")\
                .select("id, rating, review_text, created_at, updated_at, is_verified, salons(business_name)")\
                .eq("customer_id", customer_id)\
                .is_("deleted_at", "null")\
                .order("created_at", desc=True)\
                .execute()
            
            reviews = []
            for review in response.data or []:
                reviews.append({
                    "id": review.get("id"),
                    "rating": review.get("rating"),
                    "comment": review.get("review_text") or "",
                    "created_at": review.get("created_at"),
                    "updated_at": review.get("updated_at"),
                    "status": "approved",
                    "is_verified": review.get("is_verified", False),
                    "salon_name": (review.get("salons") or {}).get("business_name", "Unknown Salon")
                })
            
            logger.info(f"Retrieved {len(reviews)} reviews for customer {customer_id}")
            
            return {
                "success": True,
                "reviews": reviews,
                "count": len(reviews)
            }
        
        except Exception as e:
            logger.error(f"Failed to get reviews for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve reviews"
            )
    
    async def create_review(
        self,
        customer_id: str,
        review_data: ReviewCreate
    ) -> Dict[str, Any]:
        """
        Create a new review.
        
        Args:
            customer_id: Customer user ID
            review_data: Dict with salon_id, rating, comment, etc.
            
        Returns:
            Dict with success flag and review data
            
        Raises:
            HTTPException: If creation fails
        """
        try:
            if not review_data.booking_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="booking_id is required to submit a review"
                )

            return await self._create_review_from_booking(
                booking_id=review_data.booking_id,
                customer_id=customer_id,
                salon_id=review_data.salon_id,
                rating=review_data.rating,
                comment=review_data.comment
            )
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create review for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create review"
            )
    
    async def update_review(
        self,
        review_id: str,
        customer_id: str,
        review_data: ReviewUpdate
    ) -> Dict[str, Any]:
        """
        Update a review (requires re-approval).
        
        Args:
            review_id: Review ID
            customer_id: Customer user ID (for ownership verification)
            review_data: Dict with rating and/or comment
            
        Returns:
            Dict with success flag and updated review
            
        Raises:
            HTTPException: If review not found or update fails
        """
        try:
            review_response = self.db.table("reviews")\
                .select("id")\
                .eq("id", review_id)\
                .eq("customer_id", customer_id)\
                .is_("deleted_at", "null")\
                .maybe_single()\
                .execute()

            if not review_response or not review_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Review not found"
                )
            
            update_data = {"updated_at": datetime.utcnow().isoformat()}
            
            if getattr(review_data, 'rating', None) is not None:
                update_data["rating"] = review_data.rating
            
            if getattr(review_data, 'comment', None) is not None:
                update_data["review_text"] = review_data.comment
             
            response = self.db.table("reviews")\
                .update(update_data)\
                .eq("id", review_id)\
                .execute()
            
            logger.info(f"Updated review {review_id} for customer {customer_id}")
            
            if response.data:
                updated_review = response.data[0]
                return {
                    "success": True,
                    "message": "Review updated successfully",
                    "review": {
                        "id": updated_review.get("id"),
                        "rating": updated_review.get("rating"),
                        "comment": updated_review.get("review_text") or "",
                        "created_at": updated_review.get("created_at"),
                        "updated_at": updated_review.get("updated_at"),
                        "status": "approved"
                    }
                }
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update review"
            )
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update review {review_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update review"
            )

    async def get_public_salon_reviews(self, salon_id: str) -> Dict[str, Any]:
        """Get publicly visible reviews for a salon."""
        try:
            response = self.db.table("reviews").select(
                "id, rating, review_text, created_at, is_verified, vendor_response, "
                "profiles!reviews_customer_id_fkey(full_name), services(name)"
            ).eq("salon_id", salon_id).eq("is_hidden", False).is_("deleted_at", "null").order(
                "created_at", desc=True
            ).execute()

            reviews = []
            for review in response.data or []:
                reviews.append({
                    "id": review.get("id"),
                    "rating": review.get("rating"),
                    "comment": review.get("review_text") or "",
                    "created_at": review.get("created_at"),
                    "customer_name": ((review.get("profiles") or {}).get("full_name") or "Verified Customer").strip(),
                    "service_name": (review.get("services") or {}).get("name"),
                    "is_verified": review.get("is_verified", False),
                    "vendor_response": review.get("vendor_response")
                })

            return {
                "success": True,
                "reviews": reviews,
                "count": len(reviews)
            }
        except Exception as e:
            logger.error(f"Failed to retrieve public reviews for salon {salon_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve salon reviews"
            )

    async def get_feedback_context(self, salon_id: str, token: str) -> Dict[str, Any]:
        """Validate a feedback link and return the booking/salon context."""
        token_data = verify_review_feedback_token(token)
        if token_data["salon_id"] != salon_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Feedback link does not match this salon"
            )

        booking = await self._get_reviewable_booking(
            booking_id=token_data["booking_id"],
            customer_id=token_data["customer_id"],
            salon_id=salon_id
        )
        existing_review = self._get_existing_review(token_data["booking_id"])

        return {
            "success": True,
            "booking": {
                "id": booking["id"],
                "booking_number": booking.get("booking_number"),
                "booking_date": booking.get("booking_date"),
                "services": booking.get("services") or [],
                "customer_name": ((booking.get("profiles") or {}).get("full_name") or "Customer")
            },
            "salon": {
                "id": booking["salon_id"],
                "business_name": (booking.get("salons") or {}).get("business_name", "Salon"),
                "logo_url": (booking.get("salons") or {}).get("logo_url"),
                "city": (booking.get("salons") or {}).get("city")
            },
            "existing_review": existing_review
        }

    async def submit_feedback_review(self, salon_id: str, token: str, rating: int, comment: str) -> Dict[str, Any]:
        """Submit a review from the public feedback link."""
        token_data = verify_review_feedback_token(token)
        if token_data["salon_id"] != salon_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Feedback link does not match this salon"
            )

        return await self._create_review_from_booking(
            booking_id=token_data["booking_id"],
            customer_id=token_data["customer_id"],
            salon_id=salon_id,
            rating=rating,
            comment=comment
        )

    async def _create_review_from_booking(
        self,
        booking_id: str,
        customer_id: str,
        salon_id: str,
        rating: int,
        comment: str
    ) -> Dict[str, Any]:
        booking = await self._get_reviewable_booking(booking_id, customer_id, salon_id)
        if self._get_existing_review(booking_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A review has already been submitted for this booking"
            )

        services = booking.get("services") or []
        primary_service = services[0] if services else None
        service_id = primary_service.get("service_id") if primary_service else None
        if not service_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking does not contain a reviewable service"
            )

        review_payload = {
            "booking_id": booking_id,
            "customer_id": customer_id,
            "salon_id": salon_id,
            "service_id": service_id,
            "rating": rating,
            "review_text": comment,
            "is_verified": True,
            "created_by": customer_id,
            "updated_by": customer_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        response = self.db.table("reviews").insert(review_payload).execute()
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create review"
            )

        created_review = response.data[0]
        logger.info(f"Created review for booking {booking_id} by customer {customer_id}")
        return {
            "success": True,
            "message": "Thank you for sharing your feedback.",
            "review": {
                "id": created_review.get("id"),
                "rating": created_review.get("rating"),
                "comment": created_review.get("review_text") or "",
                "created_at": created_review.get("created_at"),
                "status": "approved"
            }
        }

    async def _get_reviewable_booking(self, booking_id: str, customer_id: str, salon_id: str) -> Dict[str, Any]:
        booking_response = self.db.table("bookings").select(
            "id, booking_number, booking_date, status, customer_id, salon_id, services, "
            "profiles!customer_id(full_name, email), salons(business_name, logo_url, city)"
        ).eq("id", booking_id).eq("customer_id", customer_id).eq("salon_id", salon_id).single().execute()

        booking = booking_response.data
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found for this feedback link"
            )

        if booking.get("status") != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reviews can only be submitted after the service is marked completed"
            )

        return booking

    def _get_existing_review(self, booking_id: str) -> Optional[Dict[str, Any]]:
        response = self.db.table("reviews").select(
            "id, rating, review_text, created_at"
        ).eq("booking_id", booking_id).is_("deleted_at", "null").execute()

        if not response.data:
            return None

        review = response.data[0]
        return {
            "id": review.get("id"),
            "rating": review.get("rating"),
            "comment": review.get("review_text") or "",
            "created_at": review.get("created_at")
        }
    
    # =====================================================
    # HELPER METHODS
    # =====================================================
    
    def _transform_booking_data(self, booking: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform booking data to flatten nested objects.
        
        Args:
            booking: Raw booking data from database
            
        Returns:
            Transformed booking dict
        """
        salon_info = booking.pop('salons', {}) or {}
        profile_info = booking.pop('profiles', {}) or {}
        
        # Remove services from booking dict (will be added separately by caller)
        # This avoids conflict between JSONB array and old service table join
        booking.pop('services', None)

        return {
            **booking,
            'salon_name': salon_info.get('business_name'),
            'salon_city': salon_info.get('city'),
            'salon_address': salon_info.get('address'),
            'salon_phone': salon_info.get('phone'),
            'salon_logo_url': salon_info.get('logo_url'),
            'customer_name': profile_info.get('full_name'),
            'customer_phone': profile_info.get('phone'),
            'all_booking_times': booking.get('booking_time')
        }
    
    def _get_effective_service_price(self, service_details: Dict[str, Any]) -> float:
        """
        Get the effective price for a service.
        Uses discounted_price when present, otherwise returns the base price.
        
        Args:
            service_details: Service data from database
            
        Returns:
            Effective price as float
        """
        discounted_price = service_details.get('discounted_price')
        if discounted_price is not None:
            return float(discounted_price)
        return float(service_details.get('price', 0.0))
