"""
Salon Service - Business Logic Layer
Handles salon CRUD operations, activation, verification, and queries
"""
import logging
from typing import Dict, Any, Optional, List, Union
from fastapi import HTTPException, status
from app.schemas.request.vendor import SalonUpdate
from dataclasses import dataclass
from app.utils.location_text import normalize_city_name

logger = logging.getLogger(__name__)


@dataclass
class SalonSearchParams:
    """Parameters for salon search/filter"""
    city: Optional[str] = None
    state: Optional[str] = None
    business_type: Optional[str] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    registration_fee_paid: Optional[bool] = None
    search_term: Optional[str] = None  # Search in name, address
    limit: int = 50
    offset: int = 0


@dataclass
class NearbySearchParams:
    """Parameters for location-based search"""
    latitude: float
    longitude: float
    radius_km: float = 10.0
    max_results: int = 50
    filters: Optional[SalonSearchParams] = None


class SalonService:
    """
    Service class for salon operations.
    Handles CRUD, activation, verification, and queries.
    """
    
    def __init__(self, db_client):
        """Initialize service with database client"""
        self.db = db_client

    def _apply_city_filter(self, query, city: Optional[str]):
        """Apply case-insensitive exact city filter."""
        if not city:
            return query

        normalized_city = normalize_city_name(city)
        if not normalized_city:
            return query

        return query.ilike("city", normalized_city)

    def _normalize_salon_cities(self, salons: List[Dict[str, Any]]) -> None:
        """Ensure salon city values use consistent Title Case in API responses."""
        for salon in salons:
            if salon.get("city"):
                salon["city"] = normalize_city_name(salon["city"])

    async def _attach_discount_flags(self, salons: List[Dict[str, Any]]) -> None:
        """
        Enrich salons with `has_discounted_services`.

        This flag is true when at least one active service for the salon has
        either discounted_price set or discount_percentage > 0.
        """
        if not salons:
            return

        salon_ids = [s.get("id") for s in salons if s.get("id")]
        if not salon_ids:
            return

        discounted_response = self.db.table("services").select(
            "salon_id, discounted_price, discount_percentage"
        ).in_("salon_id", salon_ids).eq("is_active", True).execute()

        discounted_salon_ids = set()
        for service in (discounted_response.data or []):
            has_discount = (
                service.get("discounted_price") is not None
                or (service.get("discount_percentage") is not None and float(service.get("discount_percentage") or 0) > 0)
            )
            if has_discount:
                discounted_salon_ids.add(service.get("salon_id"))

        for salon in salons:
            salon["has_discounted_services"] = salon.get("id") in discounted_salon_ids

    @staticmethod
    def is_publicly_visible(salon: Dict[str, Any]) -> bool:
        """
        The three gates a salon must pass to be shown publicly:
        active, admin-verified, and registration fee paid.
        """
        return bool(
            salon.get("is_active")
            and salon.get("is_verified")
            and salon.get("registration_fee_paid")
        )

    def _public_salons_query(self, select: str = "*, vendor_join_requests(business_type)"):
        """
        Base query for public salon listings: active + verified + paid, and
        excluding regular_buyer (product-only) accounts that don't offer services.
        """
        return (
            self.db.table("salons")
            .select(select)
            .eq("is_active", True)
            .eq("is_verified", True)
            .eq("registration_fee_paid", True)
            .neq("salon_type", "regular_buyer")
        )

    async def _finalize_public_salons(self, salons: List[Dict[str, Any]]) -> None:
        """
        Shared post-processing for public salon lists: flatten the joined
        business_type, normalize city casing, and attach discount flags.
        """
        for salon in salons:
            vjr = salon.pop("vendor_join_requests", None)
            if vjr and isinstance(vjr, dict):
                salon["business_type"] = vjr.get("business_type")

        self._normalize_salon_cities(salons)
        await self._attach_discount_flags(salons)

    async def get_salon(
        self,
        salon_id: str,
        include_services: bool = False
    ) -> Dict[str, Any]:
        """
        Get salon by ID with optional related data.
        
        Args:
            salon_id: Salon ID
            include_services: Include salon services
            
        Returns:
            Salon data with optional relations
        """
        # Build select query
        select_parts = ["*"]
        
        if include_services:
            select_parts.append("services(*)")
        
        select_query = ", ".join(select_parts)
        
        try:
            response = self.db.table("salons").select(select_query).eq("id", salon_id).execute()
            
            # Check if we got results
            if not response.data or len(response.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Salon {salon_id} not found"
                )
            
            # Return first result
            return response.data[0]
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching salon {salon_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch salon details"
            )
    
    async def list_salons(self, params: SalonSearchParams) -> List[Dict[str, Any]]:
        """
        List salons with filtering and pagination.
        
        Args:
            params: Search/filter parameters
            
        Returns:
            List of salons matching criteria
        """
        # Select salon data with related RM and vendor profiles
        # Using simpler approach - fetch profiles separately if needed
        query = self.db.table("salons").select("*")
        
        # Apply filters
        if params.city:
            query = self._apply_city_filter(query, params.city)
        
        if params.state:
            query = query.eq("state", params.state)
        
        if params.business_type:
            query = query.eq("business_type", params.business_type)
        
        if params.is_active is not None:
            query = query.eq("is_active", params.is_active)
        
        if params.is_verified is not None:
            query = query.eq("is_verified", params.is_verified)
        
        if params.registration_fee_paid is not None:
            query = query.eq("registration_fee_paid", params.registration_fee_paid)
        
        # Text search (simple ILIKE for now)
        if params.search_term:
            # Note: Supabase doesn't support OR directly, need to filter client-side
            # or use RPC function. For now, search in business_name only
            query = query.ilike("business_name", f"%{params.search_term}%")
        
        # Pagination
        query = query.range(params.offset, params.offset + params.limit - 1)
        
        # Default ordering
        query = query.order("created_at", desc=True)
        
        response = query.execute()
        salons = response.data or []
        
        # Enrich salons with vendor and RM profile data
        await self._enrich_salon_profiles(salons)
        
        return salons
    
    async def _enrich_salon_profiles(self, salons: List[Dict[str, Any]]) -> None:
        """
        Enrich salons with vendor and RM profile information.
        Modifies salons list in-place.
        """
        if not salons:
            return
        
        # Collect unique vendor and RM IDs
        vendor_ids = [s.get("vendor_id") for s in salons if s.get("vendor_id")]
        rm_ids = [s.get("rm_id") for s in salons if s.get("rm_id")]
        
        # Fetch vendor profiles
        vendor_profiles = {}
        if vendor_ids:
            vendor_response = self.db.table("profiles").select("id, full_name").in_("id", vendor_ids).execute()
            vendor_profiles = {p["id"]: p for p in (vendor_response.data or [])}
        
        # Fetch RM profiles with user data in single query
        rm_profiles = {}
        if rm_ids:
            rm_response = self.db.table("rm_profiles").select(
                "id, employee_id, profiles(id, full_name, email)"
            ).in_("id", rm_ids).execute()
            
            # Map RM ID to profile data
            for rm in (rm_response.data or []):
                rm_profiles[rm["id"]] = rm
        
        # Enrich each salon
        for salon in salons:
            if salon.get("vendor_id") and salon["vendor_id"] in vendor_profiles:
                salon["profiles"] = vendor_profiles[salon["vendor_id"]]
            
            if salon.get("rm_id") and salon["rm_id"] in rm_profiles:
                salon["rm_profiles"] = rm_profiles[salon["rm_id"]]
    
    async def get_nearby_salons(self, params: NearbySearchParams) -> List[Dict[str, Any]]:
        """
        Get salons near a location using PostGIS function.
        
        Args:
            params: Location and search parameters
            
        Returns:
            List of nearby salons with distance
        """
        # Call PostGIS function
        response = self.db.rpc("get_nearby_salons", {
            "user_lat": params.latitude,
            "user_lon": params.longitude,
            "radius_km": params.radius_km,
            "max_results": params.max_results
        }).execute()
        
        salons = response.data or []
        
        # Exclude regular_buyer salons — they can only buy products, not offer services
        # Note: The RPC function doesn't return salon_type, so we do a secondary lookup
        if salons:
            salon_ids = [s["id"] for s in salons if s.get("id")]
            if salon_ids:
                type_response = self.db.table("salons").select("id, salon_type").in_("id", salon_ids).execute()
                regular_buyer_ids = {
                    row["id"] for row in (type_response.data or [])
                    if row.get("salon_type") == "regular_buyer"
                }
                salons = [s for s in salons if s["id"] not in regular_buyer_ids]
        
        # Apply additional filters if provided
        if params.filters:
            if params.filters.is_active is not None:
                salons = [s for s in salons if s["is_active"] == params.filters.is_active]
            
            if params.filters.is_verified is not None:
                salons = [s for s in salons if s["is_verified"] == params.filters.is_verified]
            
            # Note: business_type column doesn't exist in salons table
            # Removed filter for business_type
        
        await self._attach_discount_flags(salons)
        return salons
    
    async def update_salon(
        self,
        salon_id: str,
        updates: Union[Dict[str, Any], SalonUpdate],
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update salon fields (excluding protected fields).
        
        Args:
            salon_id: Salon ID
            updates: Fields to update
            admin_id: Optional admin making the update
            
        Returns:
            Updated salon data
        """
        # Protected fields
        protected_fields = {
            "id", "rm_id", "join_request_id", "created_at",
            "approved_at", "payment_verified_at"
        }
        
        # Normalize updates: accept Pydantic model or raw dict
        if isinstance(updates, SalonUpdate):
            updates_dict = updates.model_dump(exclude_none=True)
        else:
            updates_dict = dict(updates)

        # Filter out protected fields
        safe_updates = {
            k: v for k, v in updates_dict.items()
            if k not in protected_fields
        }
        
        if not safe_updates:
            raise ValueError("No valid fields to update")

        if "city" in safe_updates:
            safe_updates["city"] = normalize_city_name(safe_updates["city"])
        
        response = self.db.table("salons").update(
            safe_updates
        ).eq("id", salon_id).execute()
        
        if not response.data:
            raise ValueError("Salon not found or update failed")
        
        logger.info(f"Salon {salon_id} updated: {list(safe_updates.keys())}")
        
        return response.data[0]
    
    async def deactivate_salon(self, salon_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Deactivate salon (set is_active = False).
        
        Args:
            salon_id: Salon ID
            reason: Optional deactivation reason
            
        Returns:
            Updated salon
        """
        updates = {"is_active": False}
        
        if reason:
            updates["deactivation_reason"] = reason
        
        response = self.db.table("salons").update(updates).eq("id", salon_id).execute()
        
        if not response.data:
            raise ValueError("Salon not found")
        
        logger.info(f"Salon {salon_id} deactivated")
        
        return response.data[0]
    
    async def delete_salon(self, salon_id: str, hard_delete: bool = False) -> Dict[str, Any]:
        """
        Delete salon (soft delete by default, hard delete if specified).
        
        Args:
            salon_id: Salon ID
            hard_delete: If True, permanently delete from database
            
        Returns:
            Success message or deleted salon data
        """
        if hard_delete:
            # Hard delete - remove from database
            self.db.table("salons").delete().eq("id", salon_id).execute()
            
            logger.warning(f"Salon {salon_id} permanently deleted")
            
            return {"message": "Salon permanently deleted", "salon_id": salon_id}
        
        else:
            # Soft delete - deactivate
            return await self.deactivate_salon(salon_id, reason="Deleted by admin")
    
    async def get_public_salons(
        self,
        limit: int = 50,
        offset: int = 0,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all public salons (active, verified, and payment completed).
        
        This is the main endpoint for public salon listing - shows only salons that are:
        - is_active = true (salon is operational)
        - is_verified = true (admin approved)
        - registration_fee_paid = true (payment completed)
        
        Args:
            limit: Maximum number of results (1-100)
            offset: Pagination offset
            city: Optional city filter
            
        Returns:
            List of public salons with basic info
        """
        query = self._public_salons_query()
        query = self._apply_city_filter(query, city)

        # Pagination and ordering
        query = (
            query
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )

        response = query.execute()
        salons = response.data or []

        await self._finalize_public_salons(salons)

        logger.info(f" Retrieved {len(salons)} public salons (offset={offset}, limit={limit}, city={city})")

        return salons
    
    async def search_salons_by_query(
        self,
        query_text: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        service_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Search salons by text query and filters.
        
        Only searches within public salons (active, verified, paid).
        
        Args:
            query_text: Search term for salon name
            city: Filter by city
            state: Filter by state
            service_type: Filter by business type
            limit: Maximum results
            
        Returns:
            List of matching salons
        """
        query = self._public_salons_query()

        # Apply text search if provided
        if query_text:
            query = query.ilike("business_name", f"%{query_text}%")

        query = self._apply_city_filter(query, city)

        if state:
            query = query.eq("state", state)

        if service_type:
            query = query.eq("business_type", service_type)

        # Order and limit
        query = query.order("created_at", desc=True).limit(limit)

        response = query.execute()
        salons = response.data or []

        await self._finalize_public_salons(salons)

        logger.info(f"Search returned {len(salons)} salons (query='{query_text}', city={city})")

        return salons
    
    async def get_related_salons(self, salon_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get salons related to the given salon, for the "Related Salons" section
        on the salon detail page.

        Relevance is tiered so the section is always populated when possible:
          1. Same city (most relevant), ordered by rating.
          2. Same state, ordered by rating (backfill).
          3. Any other public salon, ordered by rating (final backfill).

        The source salon itself is always excluded. Only public-visible salons
        (active + verified + paid, non regular_buyer) are returned.

        Args:
            salon_id: The salon being viewed.
            limit: Maximum number of related salons to return.

        Returns:
            List of public salon dicts (same shape as get_public_salons).
        """
        # Fetch just the fields needed to drive relevance.
        base = await self.get_salon(salon_id)
        city = base.get("city")
        state = base.get("state")

        collected: List[Dict[str, Any]] = []
        seen_ids = {salon_id}

        def _take(salons: List[Dict[str, Any]]) -> None:
            for salon in salons:
                if salon.get("id") in seen_ids:
                    continue
                seen_ids.add(salon["id"])
                collected.append(salon)

        async def _fetch_tier(apply_filter) -> List[Dict[str, Any]]:
            remaining = limit - len(collected)
            if remaining <= 0:
                return []
            query = self._public_salons_query()
            query = apply_filter(query)
            query = query.not_.in_("id", list(seen_ids))
            # Highest-rated first; over-fetch a little so excluded ids don't
            # leave the section short.
            query = query.order("average_rating", desc=True).limit(remaining)
            response = query.execute()
            return response.data or []

        # Tier 1: same city.
        if city:
            _take(await _fetch_tier(lambda q: self._apply_city_filter(q, city)))

        # Tier 2: same state.
        if state and len(collected) < limit:
            _take(await _fetch_tier(lambda q: q.eq("state", state)))

        # Tier 3: any other public salon.
        if len(collected) < limit:
            _take(await _fetch_tier(lambda q: q))

        await self._finalize_public_salons(collected)

        logger.info(f"Retrieved {len(collected)} related salons for {salon_id} (city={city})")

        return collected

    async def get_salon_services(self, salon_id: str) -> List[Dict[str, Any]]:
        """
        Get all active services for a salon with category information.
        
        Args:
            salon_id: Salon ID
            
        Returns:
            List of services with category data
            
        Raises:
            ValueError: If salon not found or not public
        """
        # First verify salon exists and is public
        salon = await self.get_salon(salon_id)

        if not self.is_publicly_visible(salon):
            raise ValueError("Salon not available")
        
        # Get services from database with category and subcategory join.
        # service_subcategories is the DEEPEST taxonomy node the service points at
        # (a level-2 subcategory or a level-3 sub-subcategory).
        response = self.db.table("services").select(
            "*, service_categories(id, name, icon_url), "
            "service_subcategories(id, name, icon_url, parent_category_id, parent_subcategory_id)"
        ).eq("salon_id", salon_id).eq("is_active", True).order("category_id").execute()

        services = response.data or []

        self._attach_taxonomy_path(services)

        logger.info(f"Retrieved {len(services)} services for salon {salon_id}")

        return services

    def _attach_taxonomy_path(self, services: List[Dict[str, Any]]) -> None:
        """
        Add a normalized 3-slot ``taxonomy`` to each service so clients can group
        uniformly regardless of depth:

            {"category": {...}|None,
             "subcategory": {...}|None,        # the level-2 node
             "sub_subcategory": {...}|None}    # the level-3 node, if any

        The embedded ``service_subcategories`` is the deepest node; when it is a
        level-3 node we resolve its level-2 parent so the middle slot is populated.
        """
        if not services:
            return

        def _slim(node):
            if not node:
                return None
            return {
                "id": node.get("id"),
                "name": node.get("name"),
                "icon_url": node.get("icon_url"),
            }

        # Collect level-2 parents we need to resolve for level-3 leaves.
        parent_ids = {
            leaf["parent_subcategory_id"]
            for s in services
            if (leaf := s.get("service_subcategories")) and leaf.get("parent_subcategory_id")
        }
        parents_by_id = {}
        if parent_ids:
            parents = self.db.table("service_subcategories").select(
                "id, name, icon_url"
            ).in_("id", list(parent_ids)).execute()
            parents_by_id = {p["id"]: p for p in (parents.data or [])}

        for s in services:
            leaf = s.get("service_subcategories")
            if leaf and leaf.get("parent_subcategory_id"):
                # Leaf is a level-3 sub-subcategory.
                s["taxonomy"] = {
                    "category": _slim(s.get("service_categories")),
                    "subcategory": _slim(parents_by_id.get(leaf["parent_subcategory_id"])),
                    "sub_subcategory": _slim(leaf),
                }
            else:
                # Leaf is a level-2 subcategory (or absent).
                s["taxonomy"] = {
                    "category": _slim(s.get("service_categories")),
                    "subcategory": _slim(leaf),
                    "sub_subcategory": None,
                }
