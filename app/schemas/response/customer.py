"""
Response Pydantic schemas for customer endpoints
All customer response models should be defined here for consistency
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# =====================================================
# CUSTOMER RESPONSE SCHEMAS
# =====================================================

class FavoriteResponse(BaseModel):
    """Favorite salon response"""
    id: str
    user_id: str
    salon_id: str
    created_at: datetime
    salon: Optional[dict] = None  # Salon details if needed

    class Config:
        from_attributes = True


class CartItem(BaseModel):
    """Cart item schema"""
    id: str
    service_id: str
    salon_id: str
    quantity: int
    metadata: Dict[str, Any]
    service_details: Dict[str, Any]
    salon_details: Dict[str, Any]
    unit_price: float
    line_total: float
    created_at: datetime

    class Config:
        from_attributes = True


class CartResponse(BaseModel):
    """Cart response schema"""
    success: bool
    items: List[CartItem]
    salon_id: Optional[str] = None  # UUID string
    salon_name: Optional[str] = None
    salon_details: Optional[Dict[str, Any]] = None
    total_amount: float
    item_count: int

    class Config:
        from_attributes = True


class CartOperationResponse(BaseModel):
    """Response for cart add/update operations"""
    success: bool
    message: str
    cart_item: Optional[Dict[str, Any]] = None  # Changed from 'cart' to 'cart_item'

    class Config:
        from_attributes = True


class CartClearResponse(BaseModel):
    """Response for cart clear operation"""
    success: bool
    message: str
    deleted_count: int

    class Config:
        from_attributes = True


class CustomerBookingsResponse(BaseModel):
    """Customer bookings list response"""
    success: bool
    data: List[Dict[str, Any]]
    count: int

    class Config:
        from_attributes = True


class BookingCancelResponse(BaseModel):
    """Booking cancel response"""
    success: bool
    message: str
    booking: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class SalonsBrowseResponse(BaseModel):
    """Salons browse response"""
    success: bool
    salons: List[Dict[str, Any]]
    count: int

    class Config:
        from_attributes = True


class SalonsSearchResponse(BaseModel):
    """Salons search response"""
    success: bool
    results: List[Dict[str, Any]]
    count: int

    class Config:
        from_attributes = True


class SalonDetailsResponse(BaseModel):
    """Salon details response"""
    success: bool
    salon: Dict[str, Any]

    class Config:
        from_attributes = True


class FavoritesResponse(BaseModel):
    """Customer favorites response"""
    success: bool
    favorites: List[Dict[str, Any]]
    count: int

    class Config:
        from_attributes = True


class FavoriteOperationResponse(BaseModel):
    """Favorite add/remove response"""
    success: bool
    message: str
    favorite: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class CustomerReviewsResponse(BaseModel):
    """Customer reviews response"""
    success: bool
    reviews: List[Dict[str, Any]]
    count: int

    class Config:
        from_attributes = True


class ReviewOperationResponse(BaseModel):
    """Review create/update response"""
    success: bool
    message: str
    review: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True