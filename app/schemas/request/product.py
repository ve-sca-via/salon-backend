"""
Request Pydantic schemas for Product endpoints
Handles validation for product creation and updates
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
import re

# Slug format: lowercase letters/numbers, single hyphens between segments
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validate_slug_format(v):
    """Shared slug validator for product create/update schemas."""
    if v is not None and not _SLUG_PATTERN.match(v):
        raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
    return v


class ProductCreate(BaseModel):
    """Schema for creating a new product"""
    name: str = Field(..., min_length=2, max_length=200, description="Product name")
    slug: Optional[str] = Field(None, max_length=250, description="URL-friendly slug (auto-generated if not provided)")
    description: Optional[str] = Field(None, max_length=5000, description="Full product description")
    short_description: Optional[str] = Field(None, max_length=300, description="Short description for catalog cards")
    price: float = Field(..., gt=0, description="Product price")
    discount_price: Optional[float] = Field(None, ge=0, description="Discounted sale price")
    discount_percentage: Optional[float] = Field(None, ge=0, le=100, description="Discount percentage")
    sku: Optional[str] = Field(None, max_length=50, description="Stock keeping unit")
    category: str = Field(default="general", max_length=100, description="Product category")
    brand: Optional[str] = Field(None, max_length=100, description="Brand name")
    image_urls: List[str] = Field(default_factory=list, description="Array of image URLs")
    stock_quantity: int = Field(default=0, ge=0, description="Available stock quantity")
    is_active: bool = Field(default=True, description="Whether product is visible")
    is_featured: bool = Field(default=False, description="Whether product appears in featured carousel")
    tags: List[str] = Field(default_factory=list, description="Searchable tags")
    weight: Optional[str] = Field(None, max_length=50, description="Weight/volume (e.g. 250ml, 100g)")
    b2b_discount_price: Optional[float] = Field(None, ge=0, description="Wholesale discounted price for vendors")
    b2b_discount_percentage: Optional[float] = Field(None, ge=0, le=100, description="Wholesale discount percentage")

    @field_validator("slug", mode="before")
    @classmethod
    def validate_slug(cls, v):
        return _validate_slug_format(v)

    @field_validator("discount_price", mode="before")
    @classmethod
    def validate_discount_price(cls, v, info):
        if v is not None and info.data.get("price") is not None:
            if v >= info.data["price"]:
                raise ValueError("Discount price must be less than the original price")
        return v

    @field_validator("b2b_discount_price", mode="before")
    @classmethod
    def validate_b2b_discount_price(cls, v, info):
        if v is not None and info.data.get("price") is not None:
            if v >= info.data["price"]:
                raise ValueError("B2B discount price must be less than the original price")
        return v


class ProductUpdate(BaseModel):
    """Schema for updating a product (all fields optional)"""
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    slug: Optional[str] = Field(None, max_length=250)
    description: Optional[str] = Field(None, max_length=5000)
    short_description: Optional[str] = Field(None, max_length=300)
    price: Optional[float] = Field(None, gt=0)
    discount_price: Optional[float] = Field(None, ge=0)
    discount_percentage: Optional[float] = Field(None, ge=0, le=100)
    sku: Optional[str] = Field(None, max_length=50)
    category: Optional[str] = Field(None, max_length=100)
    brand: Optional[str] = Field(None, max_length=100)
    image_urls: Optional[List[str]] = None
    stock_quantity: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    tags: Optional[List[str]] = None
    weight: Optional[str] = Field(None, max_length=50)
    b2b_discount_price: Optional[float] = Field(None, ge=0)
    b2b_discount_percentage: Optional[float] = Field(None, ge=0, le=100)

    @field_validator("slug", mode="before")
    @classmethod
    def validate_slug(cls, v):
        return _validate_slug_format(v)
