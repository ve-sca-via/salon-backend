"""
Request Pydantic schemas for API endpoints
All request models should be defined here for consistency
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict

from app.core.validators import UUIDStr, BlankableUUIDStr
from .base import PartialUpdateModel


# =====================================================
# CUSTOMER REQUEST SCHEMAS
# =====================================================

class SalonFilters(BaseModel):
    city: Optional[str] = None
    service_type: Optional[str] = None
    min_rating: Optional[float] = None


class ReviewCreate(BaseModel):
    salon_id: UUIDStr
    booking_id: BlankableUUIDStr = None
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(..., min_length=10, max_length=500)


class ReviewUpdate(PartialUpdateModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = Field(None, min_length=10, max_length=500)


class FeedbackReviewCreate(BaseModel):
    token: str = Field(..., min_length=20)
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(..., min_length=10, max_length=500)


class CartItemCreate(BaseModel):
    """
    Normalized cart item - no denormalized fields.
    Note: salon_id is optional since it's derived from the service.
    """
    salon_id: BlankableUUIDStr = None  # Optional - derived from service
    service_id: UUIDStr
    quantity: int = Field(default=1, gt=0)
    metadata: Optional[Dict] = None


class CartItemUpdate(BaseModel):
    quantity: int = Field(..., gt=0)


class FavoriteCreate(BaseModel):
    """Add salon to favorites"""
    salon_id: UUIDStr


class ProductFavoriteCreate(BaseModel):
    """Add product to favorites"""
    product_id: UUIDStr
