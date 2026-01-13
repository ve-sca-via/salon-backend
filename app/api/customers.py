"""
Customer Portal API Endpoints

Handles all customer-facing operations:
- Browse and search salons
- View salon details
- Manage bookings
- Cart operations
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from supabase import Client
from app.core.auth import get_current_user, TokenData
from app.core.database import get_db_client
from app.services.customer_service import CustomerService
from app.schemas import (
    CartResponse, CartOperationResponse, SuccessResponse, CartClearResponse,
    CustomerBookingsResponse, BookingCancelResponse, SalonsBrowseResponse,
    SalonsSearchResponse, SalonDetailsResponse, BookingResponse,
    CartItemCreate, CartItemUpdate,
    BookingCreate, BookingCancellation,
    CartCheckoutCreate
)

router = APIRouter(prefix="/customers", tags=["Customer Portal"])


def get_customer_service(db: Client = Depends(get_db_client)) -> CustomerService:
    """Dependency injection for CustomerService"""
    return CustomerService(db_client=db)


# =====================================================
# SHOPPING CART OPERATIONS
# =====================================================

@router.get("/cart", response_model=CartResponse)
async def get_cart(
    current_user: TokenData = Depends(get_current_user),
    customer_service: CustomerService = Depends(get_customer_service)
):
    """
    Get all cart items for the current customer
    Returns items grouped by salon with totals
    """
    return await customer_service.get_cart(current_user.user_id)


@router.post("/cart", response_model=CartOperationResponse)
async def add_to_cart(
    cart_item: CartItemCreate,
    current_user: TokenData = Depends(get_current_user),
    customer_service: CustomerService = Depends(get_customer_service)
):
    """
    Add item to cart or increment quantity if already exists
    Fetches salon/service details from database, no denormalization
    """
    return await customer_service.add_to_cart(
        customer_id=current_user.user_id,
        cart_item=cart_item
    )


@router.put("/cart/{item_id}", response_model=CartOperationResponse)
async def update_cart_item(
    item_id: str,
    cart_update: CartItemUpdate,
    current_user: TokenData = Depends(get_current_user),
    customer_service: CustomerService = Depends(get_customer_service)
):
    """
    Update cart item quantity
    """
    return await customer_service.update_cart_item(
        customer_id=current_user.user_id,
        item_id=item_id,
        quantity=cart_update.quantity
    )


@router.delete("/cart/{item_id}", response_model=SuccessResponse)
async def remove_from_cart(
    item_id: str,
    current_user: TokenData = Depends(get_current_user),
    customer_service: CustomerService = Depends(get_customer_service)
):
    """
    Remove item from cart
    """
    return await customer_service.remove_from_cart(
        customer_id=current_user.user_id,
        item_id=item_id
    )


@router.delete("/cart/clear/all", response_model=CartClearResponse)
async def clear_cart(
    current_user: TokenData = Depends(get_current_user),
    customer_service: CustomerService = Depends(get_customer_service)
):
    """
    Clear all items from cart
    """
    return await customer_service.clear_cart(current_user.user_id)


@router.post("/cart/checkout", response_model=BookingResponse)
async def checkout_cart(
    checkout_data: CartCheckoutCreate,
    current_user: TokenData = Depends(get_current_user),
    customer_service: CustomerService = Depends(get_customer_service)
):
    """
    Create booking from cart items with date/time selection and payment verification.
    
    Complete Cart Checkout Flow:
    1. Frontend: User adds services to cart (POST /customers/cart)
    2. Frontend: User proceeds to checkout page
    3. Frontend: User selects date and time slots (max 3)
    4. Frontend: Clicks "Proceed to Payment"
    5. Frontend: Calls POST /payments/cart/create-order
       - Backend creates Razorpay order with convenience_fee + GST
       - Returns order_id, amount, key_id
    6. Frontend: Opens Razorpay modal with order_id
    7. Customer: Completes payment on Razorpay
    8. Razorpay: Returns payment_id, signature to frontend
    9. Frontend: Calls this endpoint (POST /customers/cart/checkout) with:
       - booking_date, time_slots
       - razorpay_order_id, razorpay_payment_id, razorpay_signature
    10. Backend: Verifies payment signature with Razorpay
    11. Backend: Creates booking with all cart services
    12. Backend: Creates booking_payment record
    13. Backend: Clears cart
    14. Backend: Returns booking details
    
    Payment Split Model:
    - Convenience Fee (10% + GST): Paid ONLINE during checkout
    - Service Amount (100%): Paid AT SALON after service completion
    
    Validates salon is accepting bookings and clears cart after successful booking.
    """
    result = await customer_service.checkout_cart(
        customer_id=current_user.user_id,
        checkout_data={
            "booking_date": checkout_data.booking_date,
            "time_slots": checkout_data.time_slots,
            "razorpay_order_id": checkout_data.razorpay_order_id,
            "razorpay_payment_id": checkout_data.razorpay_payment_id,
            "razorpay_signature": checkout_data.razorpay_signature,
            "payment_method": checkout_data.payment_method,
            "notes": checkout_data.notes
        }
    )
    # Return only the booking data, not the wrapper dict
    return result["booking"]


# =====================================================
# BOOKINGS OPERATIONS
# =====================================================

@router.get("/bookings/my-bookings", response_model=CustomerBookingsResponse)
async def get_my_bookings(
    current_user: TokenData = Depends(get_current_user),
    customer_service: CustomerService = Depends(get_customer_service)
):
    """
    Get all bookings for the current customer
    Returns bookings with salon and service details
    """
    return await customer_service.get_customer_bookings(current_user.user_id)


@router.put("/bookings/{booking_id}/cancel", response_model=BookingCancelResponse, operation_id="customer_cancel_booking")
async def cancel_booking(
    booking_id: str,
    current_user: TokenData = Depends(get_current_user),
    customer_service: CustomerService = Depends(get_customer_service)
):
    """
    Cancel a booking
    Only allows canceling if booking is not already completed or cancelled
    """
    return await customer_service.cancel_customer_booking(
        customer_id=current_user.user_id,
        booking_id=booking_id
    )


# =====================================================
# SALON BROWSING & SEARCH
# =====================================================

@router.get("/salons", response_model=SalonsBrowseResponse)
async def get_salons(
    city: Optional[str] = Query(None, description="Filter by city"),
    service_type: Optional[str] = Query(None, description="Filter by service type"),
    min_rating: Optional[float] = Query(None, description="Minimum rating"),
    customer_service: CustomerService = Depends(get_customer_service)
):
    """
    Browse salons with optional filters
    Public endpoint - no authentication required
    """
    return await customer_service.browse_salons(
        city=city,
        min_rating=min_rating
    )


@router.get("/salons/search", response_model=SalonsSearchResponse)
async def search_salons(
    query: Optional[str] = Query(None, description="Search query"),
    location: Optional[str] = Query(None, description="Location filter"),
    service_type: Optional[str] = Query(None, description="Service type filter"),
    customer_service: CustomerService = Depends(get_customer_service)
):
    """
    Search salons by name, location, or services
    Public endpoint - no authentication required
    """
    return await customer_service.search_salons(
        query=query,
        location=location
    )


@router.get("/salons/{salon_id}", response_model=SalonDetailsResponse)
async def get_salon_details(
    salon_id: int,
    customer_service: CustomerService = Depends(get_customer_service)
):
    """
    Get detailed information about a specific salon
    Includes services
    Public endpoint - no authentication required
    """
    return await customer_service.get_salon_details(salon_id)


# =====================================================
# BOOKINGS
# =====================================================

@router.post("/bookings", response_model=BookingResponse, operation_id="customer_create_booking")
async def create_booking(
    booking_data: BookingCreate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Create a new booking
    Requires authentication
    """
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




