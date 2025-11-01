"""
Modern Supabase Implementation Example

This file shows how to migrate from SQLAlchemy to Supabase's full feature set.
Compare with the traditional SQLAlchemy approach in app/services/location.py
"""
from supabase import create_client, Client
from app.core.config import settings
from typing import List, Dict, Optional
from typing_extensions import TypedDict


class SalonData(TypedDict):
    """Type definition for salon data"""
    id: int
    name: str
    address_line1: str
    city: str
    state: str
    latitude: float
    longitude: float
    rating: float
    total_reviews: int
    cover_image: Optional[str]
    distance_km: float


class ModernSupabaseService:
    """
    Modern Supabase implementation showing best practices:
    1. Use Supabase client instead of SQLAlchemy
    2. Leverage auto-generated REST APIs
    3. Benefit from built-in security
    """
    
    def __init__(self):
        # Initialize Supabase client
        self.client: Client = create_client(
            settings.SUPABASE_URL, 
            settings.SUPABASE_SERVICE_ROLE_KEY
        )
    
    # ========================================
    # SALON OPERATIONS (Replace SQLAlchemy)
    # ========================================
    
    async def get_salon(self, salon_id: int) -> Optional[Dict]:
        """
        Get single salon - leverages auto-generated API
        Instead of writing SQL, Supabase generates the endpoint
        """
        response = self.client.table("salons")\
            .select("*")\
            .eq("id", salon_id)\
            .single()\
            .execute()
        
        return response.data if response.data else None
    
    async def get_approved_salons(self, limit: int = 50) -> List[Dict]:
        """
        Get approved salons - built-in filtering
        Much simpler than SQLAlchemy queries
        """
        response = self.client.table("salons")\
            .select("*")\
            .eq("status", "approved")\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        
        return response.data if response.data else []
    
    async def get_salons_by_city(self, city: str) -> List[Dict]:
        """
        Filter by city with auto-generated API
        No need to write SQL
        """
        response = self.client.table("salons")\
            .select("*")\
            .eq("city", city)\
            .eq("status", "approved")\
            .execute()
        
        return response.data if response.data else []
    
    async def create_salon(self, salon_data: Dict) -> Dict:
        """
        Create salon with validation
        Supabase handles the database logic
        """
        response = self.client.table("salons")\
            .insert(salon_data)\
            .execute()
        
        return response.data[0] if response.data else None
    
    # ========================================
    # STORAGE OPERATIONS (New Feature)
    # ========================================
    
    async def upload_salon_image(
        self, 
        salon_id: int, 
        image_data: bytes, 
        filename: str
    ) -> str:
        """
        Upload image to Supabase Storage
        Returns public URL
        
        Instead of storing URLs in PostgreSQL,
        use Supabase Storage for automatic CDN delivery
        """
        file_path = f"salons/{salon_id}/{filename}"
        
        # Upload to bucket
        response = self.client.storage\
            .from_("salon-images")\
            .upload(file_path, image_data, {
                "content-type": "image/jpeg",
                "upsert": "true"  # Overwrite if exists
            })
        
        # Get public URL
        url = self.client.storage\
            .from_("salon-images")\
            .get_public_url(file_path)
        
        return url
    
    async def delete_salon_image(self, salon_id: int, filename: str):
        """
        Delete image from Supabase Storage
        """
        file_path = f"salons/{salon_id}/{filename}"
        
        self.client.storage\
            .from_("salon-images")\
            .remove([file_path])
    
    # ========================================
    # REALTIME OPERATIONS (New Feature)
    # ========================================
    
    def subscribe_to_salon_updates(self, salon_id: int, callback):
        """
        Listen for real-time updates to a salon
        Perfect for live booking status updates
        
        Usage in your FastAPI endpoint:
        service.subscribe_to_salon_updates(salon_id, lambda x: print(x))
        """
        channel = self.client.channel(f"salon-{salon_id}")
        
        channel.on(
            "postgres_changes",
            event="UPDATE",
            schema="public",
            table="salons",
            filter=f"id=eq.{salon_id}",
            callback=callback
        ).subscribe()
        
        return channel
    
    def broadcast_booking_update(self, salon_id: int, booking_data: Dict):
        """
        Broadcast booking update to salon in real-time
        """
        channel = self.client.channel(f"salon-{salon_id}")
        
        channel.send({
            "type": "booking_update",
            "payload": booking_data
        })
    
    # ========================================
    # BOOKING OPERATIONS
    # ========================================
    
    async def create_booking(self, booking_data: Dict) -> Dict:
        """
        Create booking with automatic validation
        Supabase enforces foreign keys and constraints
        """
        response = self.client.table("bookings")\
            .insert(booking_data)\
            .execute()
        
        return response.data[0] if response.data else None
    
    async def get_user_bookings(self, user_id: str) -> List[Dict]:
        """
        Get all bookings for a user
        With RLS enabled, users can only see their own bookings
        """
        response = self.client.table("bookings")\
            .select("*, salons(*)")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .execute()
        
        return response.data if response.data else []
    
    async def get_salon_bookings(self, salon_id: int) -> List[Dict]:
        """
        Get all bookings for a salon
        Includes joined data from services table
        """
        response = self.client.table("bookings")\
            .select("*, salon_services(*)")\
            .eq("salon_id", salon_id)\
            .order("booking_date", desc=True)\
            .execute()
        
        return response.data if response.data else []
    
    # ========================================
    # SEARCH & FILTERING
    # ========================================
    
    async def search_salons(
        self,
        query: str,
        city: Optional[str] = None,
        min_rating: float = 0.0
    ) -> List[Dict]:
        """
        Full-text search with Supabase
        Leverages PostgreSQL's powerful search
        """
        supabase_query = self.client.table("salons")\
            .select("*")\
            .eq("status", "approved")\
            .gte("rating", min_rating)\
            .order("rating", desc=True)
        
        # Add city filter if provided
        if city:
            supabase_query = supabase_query.eq("city", city)
        
        # Full-text search
        if query:
            supabase_query = supabase_query.or_(
                f"name.ilike.%{query}%,description.ilike.%{query}%"
            )
        
        response = supabase_query.execute()
        
        return response.data if response.data else []
    
    # ========================================
    # AUTHENTICATION (Already using this)
    # ========================================
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict]:
        """
        Get user profile - already implemented in your auth.py
        This shows the pattern
        """
        response = self.client.table("profiles")\
            .select("*")\
            .eq("id", user_id)\
            .single()\
            .execute()
        
        return response.data if response.data else None


# Singleton instance
modern_supabase_service = ModernSupabaseService()


# ========================================
# COMPARISON: Old vs New
# ========================================
"""
OLD WAY (SQLAlchemy):
    session = await get_db()
    query = select(Salon).where(
        Salon.status == "approved",
        Salon.city == "Mumbai"
    )
    result = await session.execute(query)
    salons = result.scalars().all()
    return [salon.to_dict() for salon in salons]

NEW WAY (Supabase):
    response = client.table("salons")\
        .select("*")\
        .eq("status", "approved")\
        .eq("city", "Mumbai")\
        .execute()
    return response.data

Benefits:
- Less code (50%+ reduction)
- Built-in validation
- Row Level Security
- Auto-generated REST API
- Better error handling
"""


