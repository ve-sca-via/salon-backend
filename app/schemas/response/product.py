"""
Response Pydantic schemas for Product endpoints
Defines response contracts for product API
"""
from pydantic import BaseModel
from typing import Optional, List


# =====================================================
# PRODUCT RESPONSE SCHEMAS
# =====================================================

class ProductResponse(BaseModel):
    """Single product response"""
    success: bool = True
    product: dict


class ProductListResponse(BaseModel):
    """Product list response with pagination"""
    success: bool = True
    products: List[dict]
    count: int
    offset: int = 0
    limit: int = 50
    total: Optional[int] = None


class ProductOperationResponse(BaseModel):
    """Generic product operation response"""
    success: bool = True
    message: str
    product: Optional[dict] = None


class ProductDeleteResponse(BaseModel):
    """Product deletion response"""
    success: bool = True
    message: str
    product_id: str


# =====================================================
# PRODUCT CART RESPONSE SCHEMAS
# =====================================================

class ProductCartItem(BaseModel):
    """A single processed product-cart line item."""
    id: str
    product_id: str
    name: Optional[str] = None
    price: float
    quantity: int
    image_url: Optional[str] = None
    image_urls: List[str] = []
    total: float
    is_b2b_price: bool = False


class ProductCartResponse(BaseModel):
    """Full product cart with computed totals."""
    success: bool = True
    items: List[ProductCartItem]
    total_amount: float
    item_count: int


class ProductCartOperationResponse(BaseModel):
    """Generic add/update/remove/clear acknowledgement."""
    success: bool = True
    message: str
