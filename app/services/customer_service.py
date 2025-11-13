"""
Customer Service - Business Logic Layer
Handles all customer-facing operations: cart, bookings, salons, favorites, reviews
Separated from HTTP layer for better testability and reusability
"""
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import HTTPException, status

from app.core.database import get_db

logger = logging.getLogger(__name__)

# Get database client using factory function
db = get_db()


class CustomerService:
    """
    Service class for customer operations.
    Handles cart, bookings, salon browsing, favorites, and reviews.
    """
    
    def __init__(self):
        """Initialize service - uses centralized db client"""
        pass
    
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
            response = db.table("cart_items")\
                .select("*")\
                .eq("customer_id", customer_id)\
                .order("created_at", desc=False)\
                .execute()
            
            cart_items = response.data or []
            
            # Calculate totals
            total_amount = sum(item['price'] * item['quantity'] for item in cart_items)
            item_count = sum(item['quantity'] for item in cart_items)
            
            # Get salon info (assuming all items from same salon)
            salon_id = cart_items[0]['salon_id'] if cart_items else None
            salon_name = cart_items[0]['salon_name'] if cart_items else None
            
            logger.info(f"Retrieved cart for customer {customer_id}: {item_count} items")
            
            return {
                "success": True,
                "items": cart_items,
                "salon_id": salon_id,
                "salon_name": salon_name,
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
        cart_item: Dict[str, Any]
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
            # Check if user has items from different salon
            existing_cart = db.table("cart_items")\
                .select("salon_id")\
                .eq("customer_id", customer_id)\
                .limit(1)\
                .execute()
            
            if existing_cart.data and existing_cart.data[0]['salon_id'] != cart_item['salon_id']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot add services from different salons. Please clear cart first."
                )
            
            # Check if item already exists
            existing_item = db.table("cart_items")\
                .select("*")\
                .eq("customer_id", customer_id)\
                .eq("service_id", cart_item['service_id'])\
                .execute()
            
            if existing_item.data:
                # Increment quantity
                item = existing_item.data[0]
                new_quantity = item['quantity'] + cart_item.get('quantity', 1)
                
                response = db.table("cart_items")\
                    .update({"quantity": new_quantity})\
                    .eq("id", item['id'])\
                    .execute()
                
                logger.info(f"Updated cart item quantity for customer {customer_id}")
                
                return {
                    "success": True,
                    "message": "Cart item quantity updated",
                    "cart_item": response.data[0] if response.data else None
                }
            else:
                # Add new item
                cart_data = {
                    "customer_id": customer_id,
                    **cart_item
                }
                
                response = db.table("cart_items")\
                    .insert(cart_data)\
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
        item_id: str,
        customer_id: str,
        quantity: int
    ) -> Dict[str, Any]:
        """
        Update cart item quantity.
        
        Args:
            item_id: Cart item ID
            customer_id: Customer user ID (for ownership verification)
            quantity: New quantity
            
        Returns:
            Dict with success flag and updated item
            
        Raises:
            HTTPException: If item not found or not owned by customer
        """
        try:
            # Verify ownership
            existing = db.table("cart_items")\
                .select("*")\
                .eq("id", item_id)\
                .eq("customer_id", customer_id)\
                .execute()
            
            if not existing.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cart item not found"
                )
            
            # Update quantity
            response = db.table("cart_items")\
                .update({"quantity": quantity})\
                .eq("id", item_id)\
                .execute()
            
            logger.info(f"Updated cart item {item_id} for customer {customer_id}")
            
            return {
                "success": True,
                "message": "Cart item updated",
                "cart_item": response.data[0] if response.data else None
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update cart item {item_id}: {str(e)}")
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
        Remove item from cart.
        
        Args:
            item_id: Cart item ID
            customer_id: Customer user ID (for ownership verification)
            
        Returns:
            Dict with success flag
            
        Raises:
            HTTPException: If item not found
        """
        try:
            response = db.table("cart_items")\
                .delete()\
                .eq("id", item_id)\
                .eq("customer_id", customer_id)\
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
        Clear all items from cart.
        
        Args:
            customer_id: Customer user ID
            
        Returns:
            Dict with success flag and deleted count
            
        Raises:
            HTTPException: If operation fails
        """
        try:
            response = db.table("cart_items")\
                .delete()\
                .eq("customer_id", customer_id)\
                .execute()
            
            deleted_count = len(response.data) if response.data else 0
            
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
            response = db.table("bookings")\
                .select("*, salons(business_name, city, address, phone), profiles(full_name, phone)")\
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
            existing = db.table("bookings")\
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
            response = db.table("bookings")\
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
            query = db.table("salons").select("*")
            
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
            salon_query = db.table("salons").select("*")
            
            # Text search
            if query:
                salon_query = salon_query.or_(
                    f"name.ilike.%{query}%,description.ilike.%{query}%"
                )
            
            # Location filter
            if location:
                salon_query = salon_query.or_(
                    f"city.ilike.%{location}%,state.ilike.%{location}%,address_line1.ilike.%{location}%"
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
            response = db.table("salons")\
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
            favorites_response = db.table("favorites")\
                .select("salon_id")\
                .eq("user_id", customer_id)\
                .execute()
            
            if not favorites_response.data:
                return {"success": True, "favorites": [], "count": 0}
            
            # Get salon details
            salon_ids = [fav["salon_id"] for fav in favorites_response.data]
            
            salons_response = db.table("salons")\
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
            existing = db.table("favorites")\
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
            response = db.table("favorites")\
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
        review_data: Dict[str, Any]
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
                "salon_id": review_data['salon_id'],
                "booking_id": review_data.get('booking_id'),
                "rating": review_data['rating'],
                "comment": review_data['comment'],
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
        review_data: Dict[str, Any]
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
            
            if review_data.get('rating') is not None:
                update_data["rating"] = review_data['rating']
            
            if review_data.get('comment') is not None:
                update_data["comment"] = review_data['comment']
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
        
        # Parse special_requests JSON to get services and other metadata
        special_requests = booking.get('special_requests', '')
        booking_metadata = {}
        if special_requests:
            try:
                booking_metadata = json.loads(special_requests) if isinstance(special_requests, str) else special_requests
            except:
                pass
        
        return {
            **booking,
            'salon_name': salon_info.get('business_name'),
            'salon_city': salon_info.get('city'),
            'salon_address': salon_info.get('address'),
            'salon_phone': salon_info.get('phone'),
            'customer_name': profile_info.get('full_name'),
            'customer_phone': profile_info.get('phone'),
            'services': booking_metadata.get('services', []),
            'all_booking_times': booking_metadata.get('all_booking_times', booking.get('booking_time')),
            'payment_status': booking_metadata.get('payment_status', 'unknown'),
            'payment_method': booking_metadata.get('payment_method'),
        }
