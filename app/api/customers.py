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
from app.services.customer_service import CustomerService
from app.services.booking_service import BookingService
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


class CartItemCreate(BaseModel):
    salon_id: str
    salon_name: str
    service_id: str
    service_name: str
    plan_name: str
    category: str
    description: Optional[str] = None
    duration: int = Field(..., gt=0)
    price: float = Field(..., gt=0)
    quantity: int = Field(default=1, gt=0)


class CartItemUpdate(BaseModel):
    quantity: int = Field(..., gt=0)


# =====================================================
# SHOPPING CART OPERATIONS
# =====================================================

@router.get("/cart")
async def get_cart(
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get all cart items for the current customer
    Returns items grouped by salon with totals
    """
    try:
        customer_service = CustomerService()
        return await customer_service.get_cart(current_user.user_id)
    
    except Exception as e:
        logger.error(f"Error fetching cart: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cart")
async def add_to_cart(
    cart_item: CartItemCreate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Add item to cart or increment quantity if already exists
    Validates that all items belong to same salon
    """
    try:
        customer_service = CustomerService()
        return await customer_service.add_to_cart(
            customer_id=current_user.user_id,
            salon_id=cart_item.salon_id,
            salon_name=cart_item.salon_name,
            service_id=cart_item.service_id,
            service_name=cart_item.service_name,
            price=cart_item.price,
            quantity=cart_item.quantity,
            plan_name=cart_item.plan_name,
            category=cart_item.category,
            description=cart_item.description,
            duration=cart_item.duration
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding to cart: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/cart/{item_id}")
async def update_cart_item(
    item_id: str,
    cart_update: CartItemUpdate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Update cart item quantity
    """
    try:
        customer_service = CustomerService()
        return await customer_service.update_cart_item(
            customer_id=current_user.user_id,
            item_id=item_id,
            quantity=cart_update.quantity
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating cart item: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cart/{item_id}")
async def remove_from_cart(
    item_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Remove item from cart
    """
    try:
        customer_service = CustomerService()
        return await customer_service.remove_from_cart(
            customer_id=current_user.user_id,
            item_id=item_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing from cart: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cart/clear/all")
async def clear_cart(
    current_user: TokenData = Depends(get_current_user)
):
    """
    Clear all items from cart
    """
    try:
        customer_service = CustomerService()
        return await customer_service.clear_cart(current_user.user_id)
        
    except Exception as e:
        logger.error(f"Error clearing cart: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# BOOKINGS OPERATIONS
# =====================================================

@router.get("/bookings/my-bookings")
async def get_my_bookings(
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get all bookings for the current customer
    Returns bookings with salon and service details
    """
    try:
        customer_service = CustomerService()
        return await customer_service.get_customer_bookings(current_user.user_id)
        
    except Exception as e:
        logger.error(f"Error fetching bookings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Cancel a booking
    Only allows canceling if booking is not already completed or cancelled
    """
    try:
        customer_service = CustomerService()
        return await customer_service.cancel_customer_booking(
            customer_id=current_user.user_id,
            booking_id=booking_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling booking: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


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
        customer_service = CustomerService()
        return await customer_service.browse_salons(
            city=city,
            min_rating=min_rating
        )
        
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
        customer_service = CustomerService()
        return await customer_service.search_salons(
            query=query,
            location=location
        )
        
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
        customer_service = CustomerService()
        return await customer_service.get_salon_details(salon_id)
        
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
        booking_service = BookingService()
        return await booking_service.create_booking(
            customer_id=current_user.user_id,
            salon_id=booking_data.salon_id,
            booking_date=booking_data.booking_date,
            booking_time=booking_data.booking_time,
            services=booking_data.services,
            total_amount=booking_data.total_amount,
            notes=booking_data.notes
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating booking: {str(e)}")
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
        customer_service = CustomerService()
        return await customer_service.get_favorites(current_user.user_id)
        
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
        customer_service = CustomerService()
        return await customer_service.add_favorite(
            customer_id=current_user.user_id,
            salon_id=favorite_data.salon_id
        )
        
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
        customer_service = CustomerService()
        return await customer_service.remove_favorite(
            customer_id=current_user.user_id,
            salon_id=salon_id
        )
        
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
        customer_service = CustomerService()
        return await customer_service.get_customer_reviews(current_user.user_id)
        
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
        customer_service = CustomerService()
        return await customer_service.create_review(
            customer_id=current_user.user_id,
            salon_id=review_data.salon_id,
            booking_id=review_data.booking_id,
            rating=review_data.rating,
            comment=review_data.comment
        )
        
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
        customer_service = CustomerService()
        return await customer_service.update_review(
            customer_id=current_user.user_id,
            review_id=review_id,
            rating=review_data.rating,
            comment=review_data.comment
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating review: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

