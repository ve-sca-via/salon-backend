"""
Product Service - Business Logic Layer
Handles product CRUD operations and queries for the e-commerce catalog.

Follows the same service-layer pattern used by SalonService, CustomerService, etc.
"""
import logging
import re
from typing import Dict, Any, Optional, List
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def _generate_slug(name: str) -> str:
    """
    Generate a URL-friendly slug from product name.

    Args:
        name: Product name

    Returns:
        Lowercase hyphenated slug (e.g. "Hair Serum 250ml" -> "hair-serum-250ml")
    """
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)       # Remove non-alphanumeric chars (keep spaces and hyphens)
    slug = re.sub(r"[\s_]+", "-", slug)         # Replace spaces/underscores with hyphens
    slug = re.sub(r"-+", "-", slug)             # Collapse multiple hyphens
    slug = slug.strip("-")                      # Remove leading/trailing hyphens
    return slug


class ProductService:
    """
    Service class for product operations.
    Handles CRUD, listing, filtering, and slug management.
    """

    def __init__(self, db_client):
        """Initialize service with database client."""
        self.db = db_client

    # =====================================================
    # READ OPERATIONS (Public)
    # =====================================================

    async def list_products(
        self,
        category: Optional[str] = None,
        is_featured: Optional[bool] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        include_inactive: bool = False,
    ) -> Dict[str, Any]:
        """
        List products with filtering and pagination.

        Args:
            category: Filter by category
            is_featured: Filter by featured flag
            search: Search in product name (ILIKE)
            limit: Max results per page
            offset: Pagination offset
            include_inactive: If True, include inactive products (admin use)

        Returns:
            Dict with products list, count, offset, limit, and total
        """
        try:
            # Build query
            query = self.db.table("products").select("*", count="exact")

            # Active filter (public endpoints only show active)
            if not include_inactive:
                query = query.eq("is_active", True)

            # Category filter
            if category:
                query = query.eq("category", category)

            # Featured filter
            if is_featured is not None:
                query = query.eq("is_featured", is_featured)

            # Search by name
            if search:
                query = query.ilike("name", f"%{search}%")

            # Ordering and pagination
            query = query.order("created_at", desc=True)
            query = query.range(offset, offset + limit - 1)

            response = query.execute()
            products = response.data or []
            total = response.count if response.count is not None else len(products)

            logger.info(
                f"Listed {len(products)} products "
                f"(category={category}, featured={is_featured}, search={search}, offset={offset})"
            )

            return {
                "products": products,
                "count": len(products),
                "offset": offset,
                "limit": limit,
                "total": total,
            }

        except Exception as e:
            logger.error(f"Error listing products: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch products",
            )

    async def get_product_by_id(self, product_id: str) -> Dict[str, Any]:
        """
        Get a single product by UUID.

        Args:
            product_id: Product UUID

        Returns:
            Product dict

        Raises:
            HTTPException 404 if not found
        """
        try:
            response = (
                self.db.table("products")
                .select("*")
                .eq("id", product_id)
                .single()
                .execute()
            )

            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product not found: {product_id}",
                )

            return response.data

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching product {product_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch product",
            )

    async def get_product_by_slug(self, slug: str) -> Dict[str, Any]:
        """
        Get a single product by slug.

        Args:
            slug: URL-friendly product slug

        Returns:
            Product dict

        Raises:
            HTTPException 404 if not found
        """
        try:
            response = (
                self.db.table("products")
                .select("*")
                .eq("slug", slug)
                .eq("is_active", True)
                .single()
                .execute()
            )

            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product not found: {slug}",
                )

            return response.data

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching product by slug '{slug}': {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch product",
            )

    async def get_categories(self) -> List[str]:
        """
        Get distinct product categories.

        Returns:
            List of category strings
        """
        try:
            response = (
                self.db.table("products")
                .select("category")
                .eq("is_active", True)
                .execute()
            )

            # Extract unique categories
            categories = sorted(
                {row["category"] for row in (response.data or []) if row.get("category")}
            )

            return categories

        except Exception as e:
            logger.error(f"Error fetching product categories: {e}")
            return []

    # =====================================================
    # WRITE OPERATIONS (Admin)
    # =====================================================

    async def create_product(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new product.

        Auto-generates slug if not provided and ensures uniqueness.

        Args:
            product_data: Product fields from ProductCreate schema

        Returns:
            Created product dict

        Raises:
            HTTPException 400 if slug already exists
            HTTPException 500 on database error
        """
        try:
            # Generate slug if not provided
            if not product_data.get("slug"):
                product_data["slug"] = _generate_slug(product_data["name"])

            # Ensure slug uniqueness by appending a suffix if needed
            base_slug = product_data["slug"]
            product_data["slug"] = await self._ensure_unique_slug(base_slug)

            # Auto-calculate discount_percentage if discount_price is set but percentage is not
            if (
                product_data.get("discount_price") is not None
                and product_data.get("discount_percentage") is None
                and product_data.get("price")
            ):
                price = product_data["price"]
                discount_price = product_data["discount_price"]
                if price > 0:
                    product_data["discount_percentage"] = round(
                        ((price - discount_price) / price) * 100, 2
                    )

            response = self.db.table("products").insert(product_data).execute()

            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create product",
                )

            created = response.data[0]
            logger.info(f"Product created: {created['id']} ({created['name']})")
            return created

        except HTTPException:
            raise
        except Exception as e:
            error_msg = str(e)
            # Handle unique constraint violations
            if "duplicate key" in error_msg.lower() or "unique" in error_msg.lower():
                if "slug" in error_msg.lower():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"A product with slug '{product_data.get('slug')}' already exists",
                    )
                if "sku" in error_msg.lower():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"A product with SKU '{product_data.get('sku')}' already exists",
                    )
            logger.error(f"Error creating product: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create product",
            )

    async def update_product(
        self, product_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update an existing product.

        Args:
            product_id: Product UUID
            updates: Fields to update (only non-None values)

        Returns:
            Updated product dict

        Raises:
            HTTPException 404 if not found
            HTTPException 400 on validation errors
        """
        try:
            # Filter out None values
            safe_updates = {k: v for k, v in updates.items() if v is not None}

            if not safe_updates:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No fields provided for update",
                )

            # Protect immutable fields
            safe_updates.pop("id", None)
            safe_updates.pop("created_at", None)

            # If slug is being updated, ensure uniqueness
            if "slug" in safe_updates:
                existing = await self._get_product_by_slug_raw(safe_updates["slug"])
                if existing and existing["id"] != product_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Slug '{safe_updates['slug']}' is already in use",
                    )

            # Auto-recalculate discount_percentage if needed
            if "discount_price" in safe_updates or "price" in safe_updates:
                # Fetch current product for context
                current = await self.get_product_by_id(product_id)
                price = safe_updates.get("price", current.get("price"))
                discount_price = safe_updates.get("discount_price", current.get("discount_price"))

                if discount_price is not None and price and price > 0:
                    safe_updates["discount_percentage"] = round(
                        ((price - discount_price) / price) * 100, 2
                    )

            response = (
                self.db.table("products")
                .update(safe_updates)
                .eq("id", product_id)
                .execute()
            )

            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product not found: {product_id}",
                )

            updated = response.data[0]
            logger.info(f"Product updated: {product_id} (fields: {list(safe_updates.keys())})")
            return updated

        except HTTPException:
            raise
        except Exception as e:
            error_msg = str(e)
            if "duplicate key" in error_msg.lower() or "unique" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A product with this slug or SKU already exists",
                )
            logger.error(f"Error updating product {product_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update product",
            )

    async def delete_product(self, product_id: str, hard_delete: bool = False) -> Dict[str, Any]:
        """
        Delete a product (soft delete by default).

        Args:
            product_id: Product UUID
            hard_delete: If True, permanently remove from database

        Returns:
            Success message dict

        Raises:
            HTTPException 404 if not found
        """
        try:
            if hard_delete:
                # Verify product exists first
                await self.get_product_by_id(product_id)
                self.db.table("products").delete().eq("id", product_id).execute()
                logger.warning(f"Product permanently deleted: {product_id}")
                return {"message": "Product permanently deleted", "product_id": product_id}
            else:
                # Soft delete — set is_active = false
                response = (
                    self.db.table("products")
                    .update({"is_active": False})
                    .eq("id", product_id)
                    .execute()
                )

                if not response.data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Product not found: {product_id}",
                    )

                logger.info(f"Product soft-deleted: {product_id}")
                return {"message": "Product deactivated", "product_id": product_id}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting product {product_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete product",
            )

    # =====================================================
    # HELPER METHODS
    # =====================================================

    async def _ensure_unique_slug(self, base_slug: str) -> str:
        """
        Ensure slug uniqueness by appending a numeric suffix if needed.

        Args:
            base_slug: Desired slug

        Returns:
            Unique slug string (e.g. "hair-serum", "hair-serum-2", "hair-serum-3")
        """
        slug = base_slug
        suffix = 1

        while True:
            existing = await self._get_product_by_slug_raw(slug)
            if not existing:
                return slug
            suffix += 1
            slug = f"{base_slug}-{suffix}"

            # Safety limit to prevent infinite loops
            if suffix > 100:
                logger.error(f"Slug uniqueness limit reached for base slug: {base_slug}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Unable to generate unique slug",
                )

    async def _get_product_by_slug_raw(self, slug: str) -> Optional[Dict[str, Any]]:
        """
        Internal helper to check if a slug exists (returns None if not found).
        Does NOT raise HTTPException — used for existence checks.
        """
        try:
            response = (
                self.db.table("products")
                .select("id, slug")
                .eq("slug", slug)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception:
            return None
