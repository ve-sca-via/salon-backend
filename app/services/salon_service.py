"""
Salon Service - Business Logic Layer
Handles salon CRUD operations, activation, verification, and queries
"""
import logging
from typing import Dict, Any, Optional, List, Union
from app.schemas.request.payment import PaymentDetails
from app.schemas.request.vendor import SalonUpdate
from app.schemas.admin import ServiceCreate, ServiceUpdate, StaffCreate, StaffUpdate
from dataclasses import dataclass
from app.core.config import settings
from app.core.database import get_db

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
    
    async def get_salon(
        self,
        salon_id: str,
        include_services: bool = False,
        include_staff: bool = False
    ) -> Dict[str, Any]:
        """
        Get salon by ID with optional related data.
        
        Args:
            salon_id: Salon ID
            include_services: Include salon services
            include_staff: Include staff members
            
        Returns:
            Salon data with optional relations
        """
        # Build select query
        select_parts = ["*"]
        
        if include_services:
            select_parts.append("services(*)")
        
        if include_staff:
            select_parts.append("salon_staff(*)")
        
        select_query = ", ".join(select_parts)
        
        response = self.db.table("salons").select(select_query).eq("id", salon_id).single().execute()
        
        if not response.data:
            raise ValueError(f"Salon {salon_id} not found")
        
        return response.data
    
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
            query = query.eq("city", params.city)
        
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
        
        # Fetch RM profiles
        # rm_profiles.id is the RM profile ID, which is also a foreign key to profiles.id
        rm_profiles = {}
        if rm_ids:
            # First get RM profile data
            rm_response = self.db.table("rm_profiles").select("id, employee_id").in_("id", rm_ids).execute()
            rm_data = rm_response.data or []
            
            # The rm_profiles.id itself is a foreign key to profiles.id
            # So we can directly fetch the profile using the rm_id
            if rm_ids:
                profile_response = self.db.table("profiles").select("id, full_name").in_("id", rm_ids).execute()
                profile_map = {p["id"]: p for p in (profile_response.data or [])}
                
                # Map RM ID to profile data
                for rm in rm_data:
                    if rm["id"] in profile_map:
                        rm_profiles[rm["id"]] = {
                            "id": rm["id"],
                            "employee_id": rm.get("employee_id"),
                            "profiles": profile_map[rm["id"]]
                        }
        
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
        
        # Apply additional filters if provided
        if params.filters:
            if params.filters.is_active is not None:
                salons = [s for s in salons if s["is_active"] == params.filters.is_active]
            
            if params.filters.is_verified is not None:
                salons = [s for s in salons if s["is_verified"] == params.filters.is_verified]
            
            # Note: business_type column doesn't exist in salons table
            # Removed filter for business_type
        
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
        
        response = self.db.table("salons").update(
            safe_updates
        ).eq("id", salon_id).execute()
        
        if not response.data:
            raise ValueError("Salon not found or update failed")
        
        logger.info(f"✏️ Salon {salon_id} updated: {list(safe_updates.keys())}")
        
        return response.data[0]
    
    async def activate_salon(self, salon_id: str) -> Dict[str, Any]:
        """
        Activate salon (set is_active = True).
        
        Args:
            salon_id: Salon ID
            
        Returns:
            Updated salon
        """
        response = self.db.table("salons").update({
            "is_active": True
        }).eq("id", salon_id).execute()
        
        if not response.data:
            raise ValueError("Salon not found")
        
        logger.info(f"✅ Salon {salon_id} activated")
        
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
        
        logger.info(f"⛔ Salon {salon_id} deactivated")
        
        return response.data[0]
    
    async def verify_salon(self, salon_id: str, admin_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify salon (set is_verified = True).
        
        Args:
            salon_id: Salon ID
            admin_id: Admin performing verification
            
        Returns:
            Updated salon
        """
        updates = {
            "is_verified": True,
            "verified_at": "now()"
        }
        
        if admin_id:
            updates["verified_by"] = admin_id
        
        response = self.db.table("salons").update(updates).eq("id", salon_id).execute()
        
        if not response.data:
            raise ValueError("Salon not found")
        
        logger.info(f"✓ Salon {salon_id} verified")
        
        return response.data[0]
    
    async def mark_payment_verified(
        self,
        salon_id: str,
        payment_details: PaymentDetails
    ) -> Dict[str, Any]:
        """
        Mark registration payment as verified.
        
        Args:
            salon_id: Salon ID
            payment_details: Payment information (transaction_id, etc.)
            
        Returns:
            Updated salon
        """
        updates = {
            "registration_fee_paid": True,
            "payment_verified_at": "now()",
            "payment_details": payment_details.model_dump(exclude_none=True)
        }
        
        response = self.db.table("salons").update(updates).eq("id", salon_id).execute()
        
        if not response.data:
            raise ValueError("Salon not found")
        
        logger.info(f"💰 Payment verified for salon {salon_id}")
        
        return response.data[0]
    
    async def get_salon_stats(self, salon_id: str) -> Dict[str, Any]:
        """
        Get comprehensive stats for a salon.
        
        Args:
            salon_id: Salon ID
            
        Returns:
            Statistics dict
        """
        # Get service count
        services_response = self.db.table("services").select(
            "id", count="exact"
        ).eq("salon_id", salon_id).execute()
        
        service_count = services_response.count or 0
        
        # Get staff count
        staff_response = self.db.table("staff").select(
            "id", count="exact"
        ).eq("salon_id", salon_id).execute()
        
        staff_count = staff_response.count or 0
        
        # Get booking count
        bookings_response = self.db.table("bookings").select(
            "id", count="exact"
        ).eq("salon_id", salon_id).execute()
        
        booking_count = bookings_response.count or 0
        
        # Get average rating (if reviews exist)
        reviews_response = self.db.table("reviews").select(
            "rating"
        ).eq("salon_id", salon_id).execute()
        
        reviews = reviews_response.data or []
        avg_rating = sum(r["rating"] for r in reviews) / len(reviews) if reviews else 0.0
        
        return {
            "services_count": service_count,
            "staff_count": staff_count,
            "bookings_count": booking_count,
            "reviews_count": len(reviews),
            "average_rating": round(avg_rating, 2)
        }
    
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
            response = self.db.table("salons").delete().eq("id", salon_id).execute()
            
            logger.warning(f"🗑️ Salon {salon_id} permanently deleted")
            
            return {"message": "Salon permanently deleted", "salon_id": salon_id}
        
        else:
            # Soft delete - deactivate
            return await self.deactivate_salon(salon_id, reason="Deleted by admin")
    
    async def get_pending_verification_salons(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get salons pending verification (payment done but not verified).
        
        Args:
            limit: Max results
            
        Returns:
            List of salons pending verification
        """
        response = self.db.table("salons").select("*").eq(
            "registration_fee_paid", True
        ).eq("is_verified", False).order("payment_verified_at", desc=True).limit(limit).execute()
        
        return response.data or []
    
    async def get_pending_payment_salons(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get salons pending registration payment.
        
        Args:
            limit: Max results
            
        Returns:
            List of salons with pending payments
        """
        response = self.db.table("salons").select("*").eq(
            "registration_fee_paid", False
        ).order("approved_at", desc=True).limit(limit).execute()
        
        return response.data or []
    
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
        # Build query with all three required conditions
        query = (
            self.db.table("salons")
            .select("*")
            .eq("is_active", True)
            .eq("is_verified", True)
            .eq("registration_fee_paid", True)
        )
        
        # Apply city filter if provided
        if city:
            query = query.eq("city", city)
        
        # Pagination and ordering
        query = (
            query
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        
        response = query.execute()
        salons = response.data or []
        
        logger.info(f"📋 Retrieved {len(salons)} public salons (offset={offset}, limit={limit}, city={city})")
        
        return salons
    
    async def get_approved_salons(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get approved salons (verified and payment completed).
        
        Same as get_public_salons but may include inactive salons.
        Used for admin panels to see all approved salons even if temporarily inactive.
        
        Args:
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            List of approved salons
        """
        query = (
            self.db.table("salons")
            .select("*")
            .eq("is_verified", True)
            .eq("registration_fee_paid", True)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        
        response = query.execute()
        salons = response.data or []
        
        logger.info(f"📋 Retrieved {len(salons)} approved salons")
        
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
        # Start with public salons filter
        query = (
            self.db.table("salons")
            .select("*")
            .eq("is_active", True)
            .eq("is_verified", True)
            .eq("registration_fee_paid", True)
        )
        
        # Apply text search if provided
        if query_text:
            query = query.ilike("business_name", f"%{query_text}%")
        
        # Apply filters
        if city:
            query = query.eq("city", city)
        
        if state:
            query = query.eq("state", state)
        
        if service_type:
            query = query.eq("business_type", service_type)
        
        # Order and limit
        query = query.order("created_at", desc=True).limit(limit)
        
        response = query.execute()
        salons = response.data or []
        
        logger.info(f"🔍 Search returned {len(salons)} salons (query='{query_text}', city={city})")
        
        return salons
    
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
        
        if not (salon.get('is_active') and salon.get('is_verified') and salon.get('registration_fee_paid')):
            raise ValueError("Salon not available")
        
        # Get services from database with category join
        response = self.db.table("services").select(
            "*, service_categories(id, name, icon_url)"
        ).eq("salon_id", salon_id).eq("is_active", True).order("category_id").execute()
        
        services = response.data or []
        
        logger.info(f"📋 Retrieved {len(services)} services for salon {salon_id}")
        
        return services

    async def add_salon_service(self, salon_id: str, service: ServiceCreate) -> Dict[str, Any]:
        """
        Add a new service to a salon (admin action).

        Args:
            salon_id: Salon ID
            service: ServiceCreate Pydantic model

        Returns:
            Created service data
        """
        try:
            # Ensure salon exists
            await self.get_salon(salon_id)

            service_data = service.model_dump()
            service_data["salon_id"] = salon_id

            response = self.db.table("services").insert(service_data).execute()
            created = response.data[0] if response.data else None

            logger.info(f"Admin created service for salon {salon_id}: {service.name}")
            return created

        except Exception as e:
            logger.error(f"Failed to add service to salon {salon_id}: {e}")
            raise

    async def update_salon_service(self, salon_id: str, service_id: str, service: ServiceUpdate) -> Dict[str, Any]:
        """
        Update a salon service (admin action).
        """
        try:
            # Ensure salon exists
            await self.get_salon(salon_id)

            update_data = service.model_dump(exclude_none=True)
            if not update_data:
                raise ValueError("No fields provided for update")

            response = self.db.table("services").update(update_data).eq("id", service_id).eq("salon_id", salon_id).execute()
            if not response.data:
                raise ValueError("Service not found or update failed")

            logger.info(f"Admin updated service {service_id} for salon {salon_id}")
            return response.data[0]

        except Exception as e:
            logger.error(f"Failed to update service {service_id} for salon {salon_id}: {e}")
            raise

    async def delete_salon_service(self, salon_id: str, service_id: str) -> Dict[str, Any]:
        """
        Delete a service from a salon (admin action).
        """
        try:
            # Ensure salon exists
            await self.get_salon(salon_id)

            self.db.table("services").delete().eq("id", service_id).eq("salon_id", salon_id).execute()
            logger.info(f"Admin deleted service {service_id} from salon {salon_id}")
            return {"success": True, "service_id": service_id}

        except Exception as e:
            logger.error(f"Failed to delete service {service_id} from salon {salon_id}: {e}")
            raise
    
    async def get_salon_staff(self, salon_id: str) -> List[Dict[str, Any]]:
        """
        Get all active staff members for a salon.
        
        Args:
            salon_id: Salon ID
            
        Returns:
            List of staff members
            
        Raises:
            ValueError: If salon not found or not public
        """
        # Verify salon exists and is public
        salon = await self.get_salon(salon_id)
        
        if not (salon.get('is_active') and salon.get('is_verified') and salon.get('registration_fee_paid')):
            raise ValueError("Salon not available")
        
        # Get active staff members
        response = self.db.table("staff").select("*").eq(
            "salon_id", salon_id
        ).eq("is_active", True).order("name").execute()
        
        staff = response.data or []
        
        logger.info(f"👥 Retrieved {len(staff)} staff members for salon {salon_id}")
        
        return staff

    async def add_salon_staff(self, salon_id: str, staff: StaffCreate) -> Dict[str, Any]:
        """
        Add a staff member to a salon (admin action).
        """
        try:
            await self.get_salon(salon_id)

            staff_data = staff.model_dump()
            staff_data["salon_id"] = salon_id

            response = self.db.table("salon_staff").insert(staff_data).execute()
            created = response.data[0] if response.data else None

            logger.info(f"Admin added staff to salon {salon_id}: {staff.full_name}")
            return created

        except Exception as e:
            logger.error(f"Failed to add staff to salon {salon_id}: {e}")
            raise

    async def update_salon_staff(self, salon_id: str, staff_id: str, staff: StaffUpdate) -> Dict[str, Any]:
        """
        Update a salon staff member (admin action).
        """
        try:
            await self.get_salon(salon_id)

            update_data = staff.model_dump(exclude_none=True)
            if not update_data:
                raise ValueError("No fields provided for update")

            response = self.db.table("salon_staff").update(update_data).eq("id", staff_id).eq("salon_id", salon_id).execute()
            if not response.data:
                raise ValueError("Staff not found or update failed")

            logger.info(f"Admin updated staff {staff_id} for salon {salon_id}")
            return response.data[0]

        except Exception as e:
            logger.error(f"Failed to update staff {staff_id} for salon {salon_id}: {e}")
            raise

    async def delete_salon_staff(self, salon_id: str, staff_id: str) -> Dict[str, Any]:
        """
        Delete a salon staff member (admin action).
        """
        try:
            await self.get_salon(salon_id)

            self.db.table("salon_staff").delete().eq("id", staff_id).eq("salon_id", salon_id).execute()
            logger.info(f"Admin deleted staff {staff_id} from salon {salon_id}")
            return {"success": True, "staff_id": staff_id}

        except Exception as e:
            logger.error(f"Failed to delete staff {staff_id} from salon {salon_id}: {e}")
            raise
    
    async def get_platform_commission_config(self) -> float:
        """
        Get the platform commission percentage from system config.
        
        Returns:
            Commission percentage (defaults to 10.0 if not found)
        """
        try:
            response = self.db.table("system_config").select("config_value").eq(
                "config_key", "platform_commission_percentage"
            ).eq("is_active", True).single().execute()
            
            if not response.data:
                logger.warning("Platform commission config not found, using default 10%")
                return 10.0
            
            commission = float(response.data["config_value"])
            logger.info(f"💰 Platform commission: {commission}%")
            
            return commission
            
        except Exception as e:
            logger.error(f"Error fetching platform commission: {e}, using default 10%")
            return 10.0

