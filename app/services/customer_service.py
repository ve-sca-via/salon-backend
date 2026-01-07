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

from app.core.database import get_db

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
                    "services(id, name, price, duration_minutes, image_url, is_active), "
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
                detail=f"Failed to retrieve cart: {str(e)}"
            )
    
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
                .single()\
                .execute()

            if not service_response.data:
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
                .single()\
                .execute()
            
            if not salon_response.data:
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
                detail=f"Failed to add to cart: {str(e)}"
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
                detail=f"Failed to update cart item: {str(e)}"
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
                detail=f"Failed to remove cart item: {str(e)}"
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
            delete_response = self.db.table("cart_items")\
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
                detail=f"Failed to clear cart: {str(e)}"
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
            
            # Calculate totals
            total_amount = cart_response["total_amount"]
            
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
            
            booking_fee = total_amount * (convenience_fee_percentage / 100)
            gst_amount = booking_fee * 0.18  # 18% GST on booking fee
            
            # Verify Razorpay payment signature if payment details provided
            if checkout_data.get("razorpay_payment_id") and checkout_data.get("razorpay_signature"):
                from app.services.payment import RazorpayService
                razorpay_service = RazorpayService()
                
                # Verify signature to ensure payment authenticity
                try:
                    razorpay_service.verify_payment_signature(
                        razorpay_order_id=checkout_data["razorpay_order_id"],
                        razorpay_payment_id=checkout_data["razorpay_payment_id"],
                        razorpay_signature=checkout_data["razorpay_signature"]
                    )
                    logger.info(f"Payment signature verified for customer {customer_id}")
                except Exception as e:
                    logger.error(f"Payment signature verification failed: {str(e)}")
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
                notes=checkout_data.get("notes")
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
                detail=f"Failed to complete checkout: {str(e)}"
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
                    "salons(business_name, city, address, phone), "
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
                detail=f"Failed to retrieve bookings: {str(e)}"
            )
    
    async def cancel_customer_booking(
        self,
        booking_id: str,
        customer_id: str
    ) -> Dict[str, Any]:
        """
        Cancel a booking (only if not completed or already cancelled).
        
        Args:
            booking_id: Booking ID
            customer_id: Customer user ID (for ownership verification)
            
        Returns:
            Dict with success flag and updated booking
            
        Raises:
            HTTPException: If booking not found or cannot be cancelled
        """
        try:
            # Verify ownership and get booking details
            existing = self.db.table("bookings")\
                .select("*")\
                .eq("id", booking_id)\
                .eq("customer_id", customer_id)\
                .execute()
            
            if not existing.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found"
                )
            
            booking = existing.data[0]
            
            # Check if booking can be cancelled
            if booking['status'] in ['completed', 'cancelled']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot cancel {booking['status']} booking"
                )
            
            # Update booking status
            response = self.db.table("bookings")\
                .update({"status": "cancelled"})\
                .eq("id", booking_id)\
                .execute()
            
            logger.info(f"Cancelled booking {booking_id} for customer {customer_id}")
            
            return {
                "success": True,
                "message": "Booking cancelled successfully",
                "booking": response.data[0] if response.data else None
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to cancel booking {booking_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to cancel booking: {str(e)}"
            )
    
    # =====================================================
    # SALON BROWSING
    # =====================================================
    
    async def browse_salons(
        self,
        city: Optional[str] = None,
        min_rating: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Get all active salons with optional filters.
        
        Args:
            city: Filter by city
            min_rating: Minimum rating filter
            
        Returns:
            Dict with salons list and count
            
        Raises:
            HTTPException: If query fails
        """
        try:
            query = self.db.table("salons").select("*")
            
            # Apply filters
            if city:
                query = query.ilike("city", f"%{city}%")
            
            if min_rating:
                query = query.gte("rating", min_rating)
            
            # Only show active salons
            query = query.eq("status", "active")
            
            # Order by rating
            query = query.order("rating", desc=True)
            
            response = query.execute()
            
            salons = response.data or []
            
            logger.info(f"Browsed salons: {len(salons)} results (city={city}, min_rating={min_rating})")
            
            return {
                "success": True,
                "salons": salons,
                "count": len(salons)
            }
        
        except Exception as e:
            logger.error(f"Failed to browse salons: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve salons: {str(e)}"
            )
    
    async def search_salons(
        self,
        query: Optional[str] = None,
        location: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search salons by name, description, or location.
        
        Args:
            query: Search term for name/description
            location: Location search term
            
        Returns:
            Dict with search results and count
            
        Raises:
            HTTPException: If query fails
        """
        try:
            salon_query = self.db.table("salons").select("*")
            
            # Text search
            if query:
                salon_query = salon_query.or_(
                    f"name.ilike.%{query}%,description.ilike.%{query}%"
                )
            
            # Location filter
            if location:
                salon_query = salon_query.or_(
                    f"city.ilike.%{location}%,state.ilike.%{location}%,address.ilike.%{location}%"
                )
            
            # Only active salons
            salon_query = salon_query.eq("status", "active")
            
            # Order by rating
            salon_query = salon_query.order("rating", desc=True)
            
            response = salon_query.execute()
            
            results = response.data or []
            
            logger.info(f"Searched salons: {len(results)} results (query={query}, location={location})")
            
            return {
                "success": True,
                "results": results,
                "count": len(results)
            }
        
        except Exception as e:
            logger.error(f"Failed to search salons: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to search salons: {str(e)}"
            )
    
    async def get_salon_details(self, salon_id: int) -> Dict[str, Any]:
        """
        Get detailed information about a specific salon.
        
        Args:
            salon_id: Salon ID
            
        Returns:
            Dict with salon details
            
        Raises:
            HTTPException: If salon not found
        """
        try:
            response = self.db.table("salons")\
                .select("*")\
                .eq("id", salon_id)\
                .execute()
            
            if not response.data or len(response.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Salon not found"
                )
            
            logger.info(f"Retrieved salon details: {salon_id}")
            
            return {
                "success": True,
                "salon": response.data[0]
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get salon {salon_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve salon: {str(e)}"
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
                .eq("status", "active")\
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
                detail=f"Failed to retrieve favorites: {str(e)}"
            )
    
    async def add_favorite(
        self,
        customer_id: str,
        salon_id: int
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
                detail=f"Failed to add favorite: {str(e)}"
            )
    
    async def remove_favorite(
        self,
        customer_id: str,
        salon_id: int
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
            response = db.table("favorites")\
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
                detail=f"Failed to remove favorite: {str(e)}"
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
            response = db.table("reviews")\
                .select("*, salons(name)")\
                .eq("user_id", customer_id)\
                .order("created_at", desc=True)\
                .execute()
            
            # Format reviews
            reviews = []
            if response.data:
                for review in response.data:
                    review["salon_name"] = review.get("salons", {}).get("name", "Unknown Salon")
                    reviews.append(review)
            
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
                detail=f"Failed to retrieve reviews: {str(e)}"
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
            review = {
                "user_id": customer_id,
                "salon_id": review_data.salon_id,
                "booking_id": getattr(review_data, 'booking_id', None),
                "rating": review_data.rating,
                "comment": review_data.comment,
                "status": "pending",  # Reviews need approval
                "created_at": datetime.utcnow().isoformat()
            }
            
            response = db.table("reviews")\
                .insert(review)\
                .execute()
            
            logger.info(f"Created review for salon {review_data['salon_id']} by customer {customer_id}")
            
            if response.data:
                return {
                    "success": True,
                    "message": "Review submitted successfully. It will be published after approval.",
                    "review": response.data[0]
                }
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create review"
            )
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create review for {customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create review: {str(e)}"
            )
    
    async def update_review(
        self,
        review_id: int,
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
            # Verify review belongs to user
            review_response = db.table("reviews")\
                .select("*")\
                .eq("id", review_id)\
                .eq("user_id", customer_id)\
                .single()\
                .execute()
            
            if not review_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Review not found"
                )
            
            # Prepare update data
            update_data = {"updated_at": datetime.utcnow().isoformat()}
            
            if getattr(review_data, 'rating', None) is not None:
                update_data["rating"] = review_data.rating
            
            if getattr(review_data, 'comment', None) is not None:
                update_data["comment"] = review_data.comment
                update_data["status"] = "pending"  # Re-approval needed after edit
            
            # Update review
            response = db.table("reviews")\
                .update(update_data)\
                .eq("id", review_id)\
                .execute()
            
            logger.info(f"Updated review {review_id} for customer {customer_id}")
            
            if response.data:
                return {
                    "success": True,
                    "message": "Review updated successfully",
                    "review": response.data[0]
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
                detail=f"Failed to update review: {str(e)}"
            )
    
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
            'customer_name': profile_info.get('full_name'),
            'customer_phone': profile_info.get('phone'),
            'all_booking_times': booking.get('booking_time')
        }
    
    def _get_effective_service_price(self, service_details: Dict[str, Any]) -> float:
        """
        Get the effective price for a service.
        Currently returns the base price, but can be extended for discounts/promotions.
        
        Args:
            service_details: Service data from database
            
        Returns:
            Effective price as float
        """
        return float(service_details.get('price', 0.0))
