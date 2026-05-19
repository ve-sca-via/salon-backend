"""
Response Pydantic schemas for Product endpoints
Defines response contracts for product API
"""
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


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
