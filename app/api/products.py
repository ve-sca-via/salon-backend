"""
Product API Endpoints

Public endpoints:
    GET  /products              — List/search products (paginated, filterable)
    GET  /products/categories   — Get distinct product categories
    GET  /products/slug/{slug}  — Get product by URL slug
    GET  /products/{product_id} — Get product by UUID

Admin endpoints (require_admin):
    GET    /products/admin/all         — List all products (including inactive)
    POST   /products                   — Create product
    PUT    /products/{product_id}      — Update product
    DELETE /products/{product_id}      — Soft-delete product

IMPORTANT: Static path segments (/categories, /slug, /admin) MUST be defined
before the catch-all /{product_id} to avoid incorrect route matching.
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from supabase import Client

from app.core.database import get_db_client
from app.core.auth import require_admin, TokenData
from app.services.product_service import ProductService
from app.schemas.request.product import ProductCreate, ProductUpdate
from app.schemas.response.product import (
    ProductResponse,
    ProductListResponse,
    ProductOperationResponse,
    ProductDeleteResponse,
)

router = APIRouter(prefix="/products", tags=["products"])


# ========================================
# DEPENDENCY INJECTION
# ========================================

def get_product_service(db: Client = Depends(get_db_client)) -> ProductService:
    """Dependency injection for ProductService."""
    return ProductService(db_client=db)


# ========================================
# PUBLIC ENDPOINTS (static paths first)
# ========================================

@router.get("", response_model=ProductListResponse)
async def list_products(
    category: Optional[str] = Query(None, description="Filter by category"),
    is_featured: Optional[bool] = Query(None, description="Filter by featured flag"),
    search: Optional[str] = Query(None, description="Search in product name"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    product_service: ProductService = Depends(get_product_service),
):
    """
    List products with optional filtering and pagination.

    **Public endpoint** — only returns active products.

    **Filters:**
    - category: Exact match on product category
    - is_featured: Filter featured/non-featured products
    - search: Case-insensitive partial match on product name
    - limit/offset: Pagination controls

    **Returns:**
    - products: Array of product objects
    - count: Number of results in current page
    - total: Total matching products (for pagination UI)
    """
    result = await product_service.list_products(
        category=category,
        is_featured=is_featured,
        search=search,
        limit=limit,
        offset=offset,
        include_inactive=False,
    )

    return {
        "success": True,
        "products": result["products"],
        "count": result["count"],
        "offset": result["offset"],
        "limit": result["limit"],
        "total": result["total"],
    }


@router.get("/categories", response_model=dict)
async def get_product_categories(
    product_service: ProductService = Depends(get_product_service),
):
    """
    Get all distinct product categories.

    **Public endpoint** — returns categories from active products only.
    Useful for filter dropdowns on frontend.
    """
    categories = await product_service.get_categories()
    return {"success": True, "categories": categories}


@router.get("/slug/{slug}", response_model=ProductResponse)
async def get_product_by_slug(
    slug: str,
    product_service: ProductService = Depends(get_product_service),
):
    """
    Get a single product by its URL-friendly slug.

    **Public endpoint** — only returns active products.

    **Use Cases:**
    - Product detail page (SEO-friendly URL)
    - e.g. /products/slug/hair-serum-250ml
    """
    product = await product_service.get_product_by_slug(slug)
    return {"success": True, "product": product}


# ========================================
# ADMIN ENDPOINTS (static paths before catch-all)
# ========================================

@router.get("/admin/all", response_model=ProductListResponse)
async def admin_list_all_products(
    category: Optional[str] = Query(None, description="Filter by category"),
    is_featured: Optional[bool] = Query(None, description="Filter by featured flag"),
    search: Optional[str] = Query(None, description="Search in product name"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: TokenData = Depends(require_admin),
    product_service: ProductService = Depends(get_product_service),
):
    """
    List ALL products including inactive ones.

    **Admin only** — for product management panel.
    """
    result = await product_service.list_products(
        category=category,
        is_featured=is_featured,
        search=search,
        limit=limit,
        offset=offset,
        include_inactive=True,
    )

    return {
        "success": True,
        "products": result["products"],
        "count": result["count"],
        "offset": result["offset"],
        "limit": result["limit"],
        "total": result["total"],
    }


@router.post("", response_model=ProductOperationResponse)
async def create_product(
    payload: ProductCreate,
    current_user: TokenData = Depends(require_admin),
    product_service: ProductService = Depends(get_product_service),
):
    """
    Create a new product.

    **Admin only** — requires admin authentication.

    **Features:**
    - Auto-generates slug from name if not provided
    - Ensures slug uniqueness (appends suffix if needed)
    - Auto-calculates discount_percentage from price/discount_price
    """
    product_data = payload.model_dump(exclude_none=True)
    product = await product_service.create_product(product_data)

    return {
        "success": True,
        "message": f"Product '{product['name']}' created successfully",
        "product": product,
    }


# ========================================
# CATCH-ALL PARAMETRIC ROUTES (must be last)
# ========================================

@router.get("/{product_id}", response_model=ProductResponse)
async def get_product_by_id(
    product_id: str,
    product_service: ProductService = Depends(get_product_service),
):
    """
    Get a single product by UUID.

    **Public endpoint** — returns product regardless of is_active status
    (admin may need to view inactive products by ID).
    """
    product = await product_service.get_product_by_id(product_id)
    return {"success": True, "product": product}


@router.put("/{product_id}", response_model=ProductOperationResponse)
async def update_product(
    product_id: str,
    payload: ProductUpdate,
    current_user: TokenData = Depends(require_admin),
    product_service: ProductService = Depends(get_product_service),
):
    """
    Update an existing product.

    **Admin only** — requires admin authentication.

    Only provided (non-None) fields are updated.
    Auto-recalculates discount_percentage when price or discount_price changes.
    """
    update_data = payload.model_dump(exclude_none=True)
    product = await product_service.update_product(product_id, update_data)

    return {
        "success": True,
        "message": f"Product '{product['name']}' updated successfully",
        "product": product,
    }


@router.delete("/{product_id}", response_model=ProductDeleteResponse)
async def delete_product(
    product_id: str,
    hard: bool = Query(False, description="If true, permanently delete instead of soft-delete"),
    current_user: TokenData = Depends(require_admin),
    product_service: ProductService = Depends(get_product_service),
):
    """
    Delete a product.

    **Admin only** — requires admin authentication.

    **Behavior:**
    - Default: Soft-delete (sets is_active = false, product still exists in DB)
    - hard=true: Permanently removes from database (irreversible)
    """
    result = await product_service.delete_product(product_id, hard_delete=hard)

    return {
        "success": True,
        "message": result["message"],
        "product_id": result["product_id"],
    }
