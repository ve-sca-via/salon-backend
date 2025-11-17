"""
Request Pydantic schemas for API endpoints
All request models should be defined here for consistency
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime


# =====================================================
# CUSTOMER REQUEST SCHEMAS
# =====================================================

class SalonFilters(BaseModel):
    city: Optional[str] = None
    service_type: Optional[str] = None
    min_rating: Optional[float] = None


class ReviewCreate(BaseModel):
    salon_id: int
    booking_id: Optional[int] = None
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(..., min_length=10, max_length=500)


class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = Field(None, min_length=10, max_length=500)


class CartItemCreate(BaseModel):
    """Normalized cart item - no denormalized fields"""
    salon_id: str
    service_id: str
    quantity: int = Field(default=1, gt=0)
    metadata: Optional[Dict] = None


class CartItemUpdate(BaseModel):
    quantity: int = Field(..., gt=0)


class FavoriteCreate(BaseModel):
    """Add salon to favorites"""
    salon_id: str