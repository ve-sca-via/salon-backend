"""
Shared service-taxonomy resolution.

A service is placed in a 3-level taxonomy:
    Category (Hair) -> Subcategory (Haircut) -> Sub-subcategory (Spanish Haircut)

This resolver turns explicit IDs and/or typed names into the stored
(category_id, leaf_subcategory_id) pair, get-or-creating catalog nodes as needed.
It is shared by the vendor service flow and the admin salon-service flow so the
logic lives in one place.
"""
import logging
from typing import Optional, Tuple

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class ServiceTaxonomyResolver:
    def __init__(self, db):
        self.db = db

    async def resolve_fields(
        self,
        category_id: Optional[str] = None,
        subcategory_id: Optional[str] = None,
        sub_subcategory_id: Optional[str] = None,
        category_name: Optional[str] = None,
        subcategory_name: Optional[str] = None,
        sub_subcategory_name: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve the taxonomy a service belongs to from explicit IDs or typed names.

        Typed names match existing catalog entries case-insensitively at their level,
        or create new ones. Each level is resolved independently from its own id-or-name,
        so mixed input is supported (e.g. an existing category_id + existing
        subcategory_id + a newly typed sub_subcategory_name). A typed name at a level
        requires its parent to be resolvable.

        Returns (category_id, leaf_subcategory_id) where leaf_subcategory_id is the
        DEEPEST node selected (sub-subcategory if given, else subcategory, else None).
        This is what gets stored on services.subcategory_id.
        """
        cat_name = (category_name or "").strip()
        sub_name = (subcategory_name or "").strip()
        sub_sub_name = (sub_subcategory_name or "").strip()

        # Level 1 — category: a typed name takes precedence over an explicit id.
        resolved_category_id = category_id
        if cat_name:
            resolved_category_id = await self.get_or_create_category_by_name(cat_name)

        # Level 2 — subcategory (parent_subcategory_id IS NULL).
        resolved_subcategory_id = subcategory_id
        if sub_name:
            if not resolved_category_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A category is required to create a subcategory",
                )
            resolved_subcategory_id = await self.get_or_create_subcategory_by_name(
                resolved_category_id, sub_name
            )

        # Level 3 — sub-subcategory (nested under the resolved subcategory).
        resolved_sub_subcategory_id = sub_subcategory_id
        if sub_sub_name:
            if not resolved_subcategory_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A subcategory is required to create a sub-subcategory",
                )
            # The level-3 row needs a parent_category_id; derive it from the
            # subcategory when the caller only supplied subcategory_id.
            parent_category_for_subsub = resolved_category_id
            if not parent_category_for_subsub:
                parent_row = self.db.table("service_subcategories").select(
                    "parent_category_id"
                ).eq("id", resolved_subcategory_id).execute()
                if not parent_row.data:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid subcategory_id: {resolved_subcategory_id}",
                    )
                parent_category_for_subsub = parent_row.data[0]["parent_category_id"]
            resolved_sub_subcategory_id = await self.get_or_create_subcategory_by_name(
                parent_category_for_subsub, sub_sub_name,
                parent_subcategory_id=resolved_subcategory_id,
            )

        # The deepest resolved node becomes the stored leaf reference.
        leaf_subcategory_id = resolved_sub_subcategory_id or resolved_subcategory_id
        return resolved_category_id, leaf_subcategory_id

    async def get_or_create_category_by_name(self, name: str) -> str:
        normalized = name.strip()
        existing = self.db.table("service_categories").select("id, name").eq(
            "is_active", True
        ).execute()

        for row in existing.data or []:
            if (row.get("name") or "").strip().lower() == normalized.lower():
                return row["id"]

        max_order = self.db.table("service_categories").select("display_order").order(
            "display_order", desc=True
        ).limit(1).execute()
        next_order = (
            (max_order.data[0]["display_order"] + 1) if max_order.data else 1
        )

        inserted = self.db.table("service_categories").insert({
            "name": normalized,
            "description": None,
            "display_order": next_order,
            "is_active": True,
        }).execute()

        if not inserted.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create service category",
            )

        logger.info(f"Created service category from typed name: {normalized}")
        return inserted.data[0]["id"]

    async def get_or_create_subcategory_by_name(
        self,
        parent_category_id: str,
        name: str,
        parent_subcategory_id: Optional[str] = None,
    ) -> str:
        """
        Find (case-insensitively) or create a subcategory node by name.

        - parent_subcategory_id is None -> a level-2 subcategory directly under the
          category (e.g. "Haircut").
        - parent_subcategory_id is set -> a level-3 sub-subcategory under that
          subcategory (e.g. "Spanish Haircut"). Depth is capped at 3.

        Matching is scoped to the same parent so the same name (e.g. "Basic") can
        exist under different branches.
        """
        normalized = name.strip()

        if parent_subcategory_id:
            self.enforce_subcategory_depth(parent_subcategory_id)

        # Scope the lookup/order to the same parent so siblings stay isolated.
        scope = self.db.table("service_subcategories").select(
            "id, name"
        ).eq("parent_category_id", parent_category_id).eq("is_active", True)
        if parent_subcategory_id:
            scope = scope.eq("parent_subcategory_id", parent_subcategory_id)
        else:
            scope = scope.is_("parent_subcategory_id", "null")
        existing = scope.execute()

        for row in existing.data or []:
            if (row.get("name") or "").strip().lower() == normalized.lower():
                return row["id"]

        order_scope = self.db.table("service_subcategories").select("display_order").eq(
            "parent_category_id", parent_category_id
        )
        if parent_subcategory_id:
            order_scope = order_scope.eq("parent_subcategory_id", parent_subcategory_id)
        else:
            order_scope = order_scope.is_("parent_subcategory_id", "null")
        max_order = order_scope.order("display_order", desc=True).limit(1).execute()
        next_order = (
            (max_order.data[0]["display_order"] + 1) if max_order.data else 1
        )

        inserted = self.db.table("service_subcategories").insert({
            "parent_category_id": parent_category_id,
            "parent_subcategory_id": parent_subcategory_id,
            "name": normalized,
            "description": None,
            "display_order": next_order,
            "is_active": True,
        }).execute()

        if not inserted.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create service subcategory",
            )

        logger.info(
            f"Created service subcategory from typed name: {normalized} "
            f"(category {parent_category_id}, parent_subcategory {parent_subcategory_id or 'none'})"
        )
        return inserted.data[0]["id"]

    def enforce_subcategory_depth(self, parent_subcategory_id: str) -> None:
        """
        Reject nesting beyond 3 levels: a sub-subcategory's parent must itself be a
        top-level subcategory (parent_subcategory_id IS NULL).
        """
        parent = self.db.table("service_subcategories").select(
            "id, parent_subcategory_id"
        ).eq("id", parent_subcategory_id).execute()

        if not parent.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid parent subcategory: {parent_subcategory_id}",
            )

        if parent.data[0].get("parent_subcategory_id"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Service taxonomy is limited to 3 levels (category > subcategory > sub-subcategory)",
            )

    async def validate_category(self, category_id: str) -> None:
        """Validate that category_id exists."""
        category_check = self.db.table("service_categories").select("id").eq(
            "id", category_id
        ).execute()

        if not category_check.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category_id: {category_id}"
            )

    async def validate_subcategory(self, subcategory_id: str, category_id: str = None) -> None:
        """
        Validate that subcategory_id exists and optionally belongs to the given category.
        """
        subcategory_check = self.db.table("service_subcategories").select(
            "id, parent_category_id"
        ).eq("id", subcategory_id).execute()

        if not subcategory_check.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid subcategory_id: {subcategory_id}"
            )

        # If category_id is also provided, verify parent-child relationship
        if category_id:
            actual_parent = subcategory_check.data[0].get("parent_category_id")
            if actual_parent != category_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Subcategory {subcategory_id} does not belong to category {category_id}"
                )
