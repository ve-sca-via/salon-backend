"""
Customer Portal API Endpoints

Handles all customer-facing operations:
- Browse and search salons
- View salon details
- Manage bookings
- Favorites
- Reviews
- Cart operations
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from app.core.auth import get_current_user, TokenData
from app.services.supabase_service import supabase_service
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customers", tags=["customers"])


# =====================================================
# PYDANTIC MODELS
# =====================================================

class SalonFilters(BaseModel):
    city: Optional[str] = None
    service_type: Optional[str] = None
    min_rating: Optional[float] = None


class BookingCreate(BaseModel):
    salon_id: int
    booking_date: str
    booking_time: str
    services: List[Dict]
    total_amount: float
    notes: Optional[str] = None


class FavoriteCreate(BaseModel):
    salon_id: int


class ReviewCreate(BaseModel):
    salon_id: int
    booking_id: Optional[int] = None
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(..., min_length=10, max_length=500)


class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = Field(None, min_length=10, max_length=500)


# =====================================================
# SALON BROWSING & SEARCH
# =====================================================

@router.get("/salons")
async def get_salons(
    city: Optional[str] = Query(None, description="Filter by city"),
    service_type: Optional[str] = Query(None, description="Filter by service type"),
    min_rating: Optional[float] = Query(None, description="Minimum rating")
):
    """
    Get all active salons with optional filters
    Public endpoint - no authentication required
    """
    try:
        # Start with base query
        query = supabase_service.client.table("salons").select("*")
        
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
        
        if response.data:
            return {
                "success": True,
                "salons": response.data,
                "count": len(response.data)
            }
        
        return {"success": True, "salons": [], "count": 0}
        
    except Exception as e:
        logger.error(f"Error fetching salons: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/salons/search")
async def search_salons(
    query: Optional[str] = Query(None, description="Search query"),
    location: Optional[str] = Query(None, description="Location filter"),
    service_type: Optional[str] = Query(None, description="Service type filter")
):
    """
    Search salons by name, location, or services
    Public endpoint - no authentication required
    """
    try:
        salon_query = supabase_service.client.table("salons").select("*")
        
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
        
        return {
            "success": True,
            "results": response.data if response.data else [],
            "count": len(response.data) if response.data else 0
        }
        
    except Exception as e:
        logger.error(f"Error searching salons: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/salons/{salon_id}")
async def get_salon_details(salon_id: int):
    """
    Get detailed information about a specific salon
    Includes services, staff, and reviews
    Public endpoint - no authentication required
    """
    try:
        # Get salon details
        salon_response = supabase_service.client.table("salons")\
            .select("*")\
            .eq("id", salon_id)\
            .single()\
            .execute()
        
        if not salon_response.data:
            raise HTTPException(status_code=404, detail="Salon not found")
        
        salon = salon_response.data
        
        # Get services
        services_response = supabase_service.client.table("services")\
            .select("*")\
            .eq("salon_id", salon_id)\
            .eq("is_active", True)\
            .execute()
        
        # Get staff
        staff_response = supabase_service.client.table("staff")\
            .select("*")\
            .eq("salon_id", salon_id)\
            .eq("is_active", True)\
            .execute()
        
        # Get reviews
        reviews_response = supabase_service.client.table("reviews")\
            .select("*, profiles(full_name)")\
            .eq("salon_id", salon_id)\
            .eq("status", "approved")\
            .order("created_at", desc=True)\
            .limit(10)\
            .execute()
        
        # Combine data
        salon["services"] = services_response.data if services_response.data else []
        salon["staff"] = staff_response.data if staff_response.data else []
        salon["reviews"] = reviews_response.data if reviews_response.data else []
        
        return {
            "success": True,
            "salon": salon
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching salon details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# BOOKINGS
# =====================================================

@router.post("/bookings")
async def create_booking(
    booking_data: BookingCreate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Create a new booking
    Requires authentication
    """
    try:
        # Prepare booking data
        booking = {
            "customer_id": current_user.user_id,
            "salon_id": booking_data.salon_id,
            "booking_date": booking_data.booking_date,
            "booking_time": booking_data.booking_time,
            "services": booking_data.services,
            "total_amount": booking_data.total_amount,
            "final_amount": booking_data.total_amount,
            "status": "pending",
            "payment_status": "pending",
            "payment_method": "pay_after_service",
            "notes": booking_data.notes,
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Get salon name
        salon_response = supabase_service.client.table("salons")\
            .select("name")\
            .eq("id", booking_data.salon_id)\
            .single()\
            .execute()
        
        if salon_response.data:
            booking["salon_name"] = salon_response.data["name"]
        
        # Insert booking
        response = supabase_service.client.table("bookings")\
            .insert(booking)\
            .execute()
        
        if response.data:
            return {
                "success": True,
                "message": "Booking created successfully",
                "booking": response.data[0]
            }
        
        raise HTTPException(status_code=400, detail="Failed to create booking")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating booking: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bookings/my-bookings")
async def get_my_bookings(
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get all bookings for the current customer
    Requires authentication
    """
    try:
        response = supabase_service.client.table("bookings")\
            .select("*")\
            .eq("customer_id", current_user.user_id)\
            .order("created_at", desc=True)\
            .execute()
        
        return {
            "success": True,
            "bookings": response.data if response.data else [],
            "count": len(response.data) if response.data else 0
        }
        
    except Exception as e:
        logger.error(f"Error fetching bookings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: int,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Cancel a booking
    Requires authentication
    """
    try:
        # Verify booking belongs to user
        booking_response = supabase_service.client.table("bookings")\
            .select("*")\
            .eq("id", booking_id)\
            .eq("customer_id", current_user.user_id)\
            .single()\
            .execute()
        
        if not booking_response.data:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        # Update status
        response = supabase_service.client.table("bookings")\
            .update({
                "status": "cancelled",
                "cancellation_reason": "Cancelled by customer",
                "updated_at": datetime.utcnow().isoformat()
            })\
            .eq("id", booking_id)\
            .execute()
        
        if response.data:
            return {
                "success": True,
                "message": "Booking cancelled successfully",
                "booking": response.data[0]
            }
        
        raise HTTPException(status_code=400, detail="Failed to cancel booking")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling booking: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# FAVORITES
# =====================================================

@router.get("/favorites")
async def get_favorites(
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get customer's favorite salons
    Requires authentication
    """
    try:
        # Get favorite salon IDs
        favorites_response = supabase_service.client.table("favorites")\
            .select("salon_id")\
            .eq("user_id", current_user.user_id)\
            .execute()
        
        if not favorites_response.data:
            return {"success": True, "favorites": [], "count": 0}
        
        # Get salon details
        salon_ids = [fav["salon_id"] for fav in favorites_response.data]
        
        salons_response = supabase_service.client.table("salons")\
            .select("*")\
            .in_("id", salon_ids)\
            .eq("status", "active")\
            .execute()
        
        return {
            "success": True,
            "favorites": salons_response.data if salons_response.data else [],
            "count": len(salons_response.data) if salons_response.data else 0
        }
        
    except Exception as e:
        logger.error(f"Error fetching favorites: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/favorites")
async def add_favorite(
    favorite_data: FavoriteCreate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Add salon to favorites
    Requires authentication
    """
    try:
        # Check if already favorited
        existing = supabase_service.client.table("favorites")\
            .select("id")\
            .eq("user_id", current_user.user_id)\
            .eq("salon_id", favorite_data.salon_id)\
            .execute()
        
        if existing.data:
            return {
                "success": True,
                "message": "Salon already in favorites",
                "favorite": existing.data[0]
            }
        
        # Add to favorites
        response = supabase_service.client.table("favorites")\
            .insert({
                "user_id": current_user.user_id,
                "salon_id": favorite_data.salon_id,
                "created_at": datetime.utcnow().isoformat()
            })\
            .execute()
        
        if response.data:
            return {
                "success": True,
                "message": "Added to favorites",
                "favorite": response.data[0]
            }
        
        raise HTTPException(status_code=400, detail="Failed to add favorite")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding favorite: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/favorites/{salon_id}")
async def remove_favorite(
    salon_id: int,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Remove salon from favorites
    Requires authentication
    """
    try:
        response = supabase_service.client.table("favorites")\
            .delete()\
            .eq("user_id", current_user.user_id)\
            .eq("salon_id", salon_id)\
            .execute()
        
        return {
            "success": True,
            "message": "Removed from favorites"
        }
        
    except Exception as e:
        logger.error(f"Error removing favorite: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# REVIEWS
# =====================================================

@router.get("/reviews/my-reviews")
async def get_my_reviews(
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get customer's reviews
    Requires authentication
    """
    try:
        response = supabase_service.client.table("reviews")\
            .select("*, salons(name)")\
            .eq("user_id", current_user.user_id)\
            .order("created_at", desc=True)\
            .execute()
        
        # Format reviews
        reviews = []
        if response.data:
            for review in response.data:
                review["salon_name"] = review.get("salons", {}).get("name", "Unknown Salon")
                reviews.append(review)
        
        return {
            "success": True,
            "reviews": reviews,
            "count": len(reviews)
        }
        
    except Exception as e:
        logger.error(f"Error fetching reviews: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reviews")
async def create_review(
    review_data: ReviewCreate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Create a new review
    Requires authentication
    """
    try:
        # Prepare review data
        review = {
            "user_id": current_user.user_id,
            "salon_id": review_data.salon_id,
            "booking_id": review_data.booking_id,
            "rating": review_data.rating,
            "comment": review_data.comment,
            "status": "pending",  # Reviews need approval
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Insert review
        response = supabase_service.client.table("reviews")\
            .insert(review)\
            .execute()
        
        if response.data:
            return {
                "success": True,
                "message": "Review submitted successfully. It will be published after approval.",
                "review": response.data[0]
            }
        
        raise HTTPException(status_code=400, detail="Failed to create review")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating review: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/reviews/{review_id}")
async def update_review(
    review_id: int,
    review_data: ReviewUpdate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Update a review
    Requires authentication
    """
    try:
        # Verify review belongs to user
        review_response = supabase_service.client.table("reviews")\
            .select("*")\
            .eq("id", review_id)\
            .eq("user_id", current_user.user_id)\
            .single()\
            .execute()
        
        if not review_response.data:
            raise HTTPException(status_code=404, detail="Review not found")
        
        # Prepare update data
        update_data = {"updated_at": datetime.utcnow().isoformat()}
        
        if review_data.rating is not None:
            update_data["rating"] = review_data.rating
        
        if review_data.comment is not None:
            update_data["comment"] = review_data.comment
            update_data["status"] = "pending"  # Re-approval needed after edit
        
        # Update review
        response = supabase_service.client.table("reviews")\
            .update(update_data)\
            .eq("id", review_id)\
            .execute()
        
        if response.data:
            return {
                "success": True,
                "message": "Review updated successfully",
                "review": response.data[0]
            }
        
        raise HTTPException(status_code=400, detail="Failed to update review")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating review: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# CART (Optional - if you want backend-based cart)
# =====================================================

@router.get("/cart")
async def get_cart(
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get customer's cart items
    Requires authentication
    """
    try:
        response = supabase_service.client.table("cart_items")\
            .select("*")\
            .eq("user_id", current_user.user_id)\
            .execute()
        
        return {
            "success": True,
            "items": response.data if response.data else [],
            "count": len(response.data) if response.data else 0
        }
        
    except Exception as e:
        logger.error(f"Error fetching cart: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cart")
async def add_to_cart(
    cart_item: Dict,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Add item to cart
    Requires authentication
    """
    try:
        cart_item["user_id"] = current_user.user_id
        cart_item["created_at"] = datetime.utcnow().isoformat()
        
        response = supabase_service.client.table("cart_items")\
            .insert(cart_item)\
            .execute()
        
        if response.data:
            return {
                "success": True,
                "message": "Item added to cart",
                "item": response.data[0]
            }
        
        raise HTTPException(status_code=400, detail="Failed to add to cart")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding to cart: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cart/{item_id}")
async def remove_from_cart(
    item_id: int,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Remove item from cart
    Requires authentication
    """
    try:
        response = supabase_service.client.table("cart_items")\
            .delete()\
            .eq("id", item_id)\
            .eq("user_id", current_user.user_id)\
            .execute()
        
        return {
            "success": True,
            "message": "Item removed from cart"
        }
        
    except Exception as e:
        logger.error(f"Error removing from cart: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cart/checkout")
async def checkout_cart(
    checkout_data: Dict,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Checkout cart and create booking
    Requires authentication
    """
    try:
        # Get cart items
        cart_response = supabase_service.client.table("cart_items")\
            .select("*")\
            .eq("user_id", current_user.user_id)\
            .execute()
        
        if not cart_response.data:
            raise HTTPException(status_code=400, detail="Cart is empty")
        
        # Create booking from cart
        booking_data = BookingCreate(
            salon_id=checkout_data["salon_id"],
            booking_date=checkout_data["booking_date"],
            booking_time=checkout_data["booking_time"],
            services=cart_response.data,
            total_amount=checkout_data["total_amount"],
            notes=checkout_data.get("notes")
        )
        
        # Create booking
        booking = await create_booking(booking_data, current_user)
        
        # Clear cart after successful booking
        supabase_service.client.table("cart_items")\
            .delete()\
            .eq("user_id", current_user.user_id)\
            .execute()
        
        return booking
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during checkout: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

