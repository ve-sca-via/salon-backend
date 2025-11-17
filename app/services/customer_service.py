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
        Get all cart items for a customer.
        
        Args:
            customer_id: Customer user ID
            
        Returns:
            Dict with cart items, totals, and salon info
            
        Raises:
            HTTPException: If query fails
        """
        try:
            response = self.db.table("user_carts")\
                .select(
                    "id, user_id, salon_id, items, created_at, updated_at, total_amount, item_count, salon_name"
                )\
                .eq("user_id", customer_id)\
                .execute()
            
            cart_data = response.data[0] if response.data else None
            
            if not cart_data:
                # Return empty cart if no cart exists
                return {
                    "success": True,
                    "items": [],
                    "salon_id": None,
                    "salon_name": None,
                    "salon_details": None,
                    "total_amount": 0.0,
                    "item_count": 0
                }
            
            # Parse items from jsonb
            raw_items = cart_data.get("items", [])
            items_with_details: List[Dict[str, Any]] = []
            total_amount = 0.0
            item_count = 0
            
            for item in raw_items:
                service_details = item.get("service_details", {})
                unit_price = self._get_effective_service_price(service_details)
                quantity = item.get("quantity", 1)
                line_total = unit_price * quantity
                total_amount += line_total
                item_count += quantity
                
                items_with_details.append({
                    **item,
                    "service_details": service_details,
                    "unit_price": unit_price,
                    "line_total": line_total
                })
            
            logger.info(f"Retrieved cart for customer {customer_id}: {item_count} items")
            
            return {
                "success": True,
                "items": items_with_details,
                "salon_id": cart_data.get("salon_id"),
                "salon_name": cart_data.get("salon_name"),
                "salon_details": None,  # Could be populated if needed
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

            # Get service details
            service_response = self.db.table("services")\
                .select("id, name, price, duration_minutes, salon_id, is_active, image_url")\
                .eq("id", service_id)\
                .limit(1)\
                .execute()

            if not service_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Service not available"
                )

            service_details = service_response.data[0]
            if not service_details.get("is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Service is inactive"
                )

            service_salon_id = service_details['salon_id']
            
            # Get or create user cart
            cart_response = self.db.table("user_carts")\
                .select("*")\
                .eq("user_id", customer_id)\
                .execute()
            
            cart_exists = len(cart_response.data) > 0
            cart_data = cart_response.data[0] if cart_exists else None
            
            # Parse quantity (CartItemCreate guarantees integer > 0)
            quantity = cart_item.quantity
            
            # Prepare cart item
            new_item = {
                "service_id": service_id,
                "quantity": quantity,
                "service_details": service_details,
                "added_at": "now()"
            }
            
            if cart_exists:
                # Check salon consistency
                existing_salon_id = cart_data.get("salon_id")
                if existing_salon_id and existing_salon_id != service_salon_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot add services from different salons. Please clear cart first."
                    )
                
                # Update existing cart
                items = cart_data.get("items", [])
                
                # Check if service already exists
                existing_item_index = None
                for i, item in enumerate(items):
                    if item.get("service_id") == service_id:
                        existing_item_index = i
                        break
                
                if existing_item_index is not None:
                    # Update quantity
                    items[existing_item_index]["quantity"] += quantity
                else:
                    # Add new item
                    items.append(new_item)
                
                # Recalculate totals
                total_amount = sum(
                    self._get_effective_service_price(item["service_details"]) * item["quantity"]
                    for item in items
                )
                item_count = sum(item["quantity"] for item in items)
                
                salon_name_value = None
                if getattr(cart_item, 'metadata', None):
                    salon_name_value = cart_item.metadata.get('salon_name')

                update_data = {
                    "items": items,
                    "total_amount": total_amount,
                    "item_count": item_count,
                    "salon_id": service_salon_id,
                    "salon_name": salon_name_value
                }
                
                response = self.db.table("user_carts")\
                    .update(update_data)\
                    .eq("user_id", customer_id)\
                    .execute()
                
                logger.info(f"Updated cart for customer {customer_id}")
                
                return {
                    "success": True,
                    "message": "Cart updated successfully",
                    "cart": response.data[0] if response.data else None
                }
            else:
                # Create new cart
                items = [new_item]
                total_amount = self._get_effective_service_price(service_details) * quantity
                
                salon_name_value = None
                if getattr(cart_item, 'metadata', None):
                    salon_name_value = cart_item.metadata.get('salon_name')

                cart_data = {
                    "user_id": customer_id,
                    "salon_id": service_salon_id,
                    "items": items,
                    "total_amount": total_amount,
                    "item_count": quantity,
                    "salon_name": salon_name_value
                }
                
                response = self.db.table("user_carts")\
                    .insert(cart_data)\
                    .execute()
                
                logger.info(f"Created new cart for customer {customer_id}")
                
                return {
                    "success": True,
                    "message": "Item added to cart",
                    "cart": response.data[0] if response.data else None
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
        Update cart item quantity using proper jsonb operations.

        Args:
            customer_id: Customer user ID
            item_id: Cart item ID to update
            quantity: New quantity (must be > 0)

        Returns:
            Updated cart data

        Raises:
            HTTPException: If cart/item not found or update fails
        """
        try:
            # Validate quantity
            if quantity <= 0:
                from app.core.exceptions import ValidationError
                raise ValidationError("Quantity must be greater than 0", "quantity")

            # Get current cart
            cart_response = self.db.table("user_carts")\
                .select("id, items")\
                .eq("user_id", customer_id)\
                .execute()

            if not cart_response.data:
                from app.core.exceptions import NotFoundError
                raise NotFoundError("Cart", f"for user {customer_id}")

            cart = cart_response.data[0]
            items = cart.get("items", [])

            # Find and update the item
            item_found = False
            updated_items = []

            for item in items:
                if item.get("id") == item_id:
                    # Update this item's quantity
                    item["quantity"] = quantity
                    item_found = True
                updated_items.append(item)

            if not item_found:
                from app.core.exceptions import NotFoundError
                raise NotFoundError("Cart item", item_id)

            # Recalculate totals
            total_amount = sum(
                self._get_effective_service_price(item["service_details"]) * item["quantity"]
                for item in updated_items
            )
            item_count = sum(item["quantity"] for item in updated_items)

            # Update cart in database
            update_data = {
                "items": updated_items,
                "total_amount": total_amount,
                "item_count": item_count,
                "updated_at": "now()"
            }

            response = self.db.table("user_carts")\
                .update(update_data)\
                .eq("user_id", customer_id)\
                .execute()

            if not response.data:
                from app.core.exceptions import DatabaseError
                raise DatabaseError("update", "Failed to update cart item")

            logger.info(f"Updated cart item {item_id} quantity to {quantity} for customer {customer_id}")

            return {
                "success": True,
                "message": "Cart item updated successfully",
                "cart": response.data[0]
            }

        except Exception as e:
            logger.error(f"Failed to update cart item {item_id} for {customer_id}: {str(e)}")
            if isinstance(e, (ValidationError, NotFoundError, DatabaseError)):
                raise
            from app.core.exceptions import DatabaseError
            raise DatabaseError("update", f"Failed to update cart item: {str(e)}")
    
    async def remove_from_cart(
        self,
        item_id: str,
        customer_id: str
    ) -> Dict[str, Any]:
        """
        Remove item from cart.

        Args:
            item_id: Cart item ID (service_id in jsonb structure)
            customer_id: Customer user ID (for ownership verification)

        Returns:
            Dict with success flag

        Raises:
            HTTPException: If item not found
        """
        try:
            # Get current cart
            cart_response = self.db.table("user_carts")\
                .select("items")\
                .eq("user_id", customer_id)\
                .execute()

            if not cart_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cart not found"
                )

            current_items = cart_response.data[0].get("items", [])

            # Find and remove the item
            updated_items = [item for item in current_items if item.get("service_id") != item_id]

            if len(updated_items) == len(current_items):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cart item not found"
                )

            # Update cart with filtered items
            update_response = self.db.table("user_carts")\
                .update({"items": updated_items})\
                .eq("user_id", customer_id)\
                .execute()

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
        Clear all items from cart.

        Args:
            customer_id: Customer user ID

        Returns:
            Dict with success flag and deleted count

        Raises:
            HTTPException: If operation fails
        """
        try:
            # Get current cart to count items before clearing
            cart_response = self.db.table("user_carts")\
                .select("items")\
                .eq("user_id", customer_id)\
                .execute()

            deleted_count = 0
            if cart_response.data:
                current_items = cart_response.data[0].get("items", [])
                deleted_count = len(current_items)

            # Clear cart by setting items to empty array
            update_response = self.db.table("user_carts")\
                .update({"items": []})\
                .eq("user_id", customer_id)\
                .execute()

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
                    "profiles(full_name, phone), "
                    "services(name, price, discounted_price, duration_minutes)"
                )\
                .eq("customer_id", customer_id)\
                .order("booking_date", desc=True)\
                .execute()
            
            bookings = response.data or []
            
            # Transform data to flatten nested objects and parse metadata
            transformed_bookings = []
            for booking in bookings:
                transformed_booking = self._transform_booking_data(booking)
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
                .single()\
                .execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Salon not found"
                )
            
            logger.info(f"Retrieved salon details: {salon_id}")
            
            return {
                "success": True,
                "salon": response.data
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
        Transform booking data to flatten nested objects and parse metadata.
        
        Args:
            booking: Raw booking data from database
            
        Returns:
            Transformed booking dict
        """
        salon_info = booking.pop('salons', {}) or {}
        profile_info = booking.pop('profiles', {}) or {}
        service_info = booking.pop('services', {}) or {}
        effective_price = self._get_effective_service_price(service_info) if service_info else 0.0
        payment_status = self._derive_booking_payment_status(booking)
        services_list = [service_info] if service_info else []

        return {
            **booking,
            'salon_name': salon_info.get('business_name'),
            'salon_city': salon_info.get('city'),
            'salon_address': salon_info.get('address'),
            'salon_phone': salon_info.get('phone'),
            'customer_name': profile_info.get('full_name'),
            'customer_phone': profile_info.get('phone'),
            'services': services_list,
            'service_details': {
                **service_info,
                'effective_price': effective_price
            } if service_info else None,
            'unit_price': effective_price,
            'all_booking_times': booking.get('booking_time'),
            'payment_status': payment_status,
            'payment_method': 'online' if booking.get('convenience_fee_paid') else 'pay_at_salon'
        }

    def _get_effective_service_price(self, service_details: Dict[str, Any]) -> float:
        """Return the service price (discounted_price removed from schema)."""
        price_value = service_details.get('price') or 0
        try:
            return float(price_value)
        except (TypeError, ValueError):
            return 0.0

    def _derive_booking_payment_status(self, booking: Dict[str, Any]) -> str:
        """Map booking payment flags to a readable status string."""
        convenience_fee_paid = booking.get('convenience_fee_paid')
        service_paid = booking.get('service_paid')
        if convenience_fee_paid and service_paid:
            return 'completed'
        if convenience_fee_paid:
            return 'online_paid'
        return 'pending'
