"""
Minimal Supabase service - provides direct client access
All API files should migrate to using direct Supabase client
"""

from supabase import create_client, Client
from app.core.config import settings

# Create single Supabase client instance with service role key
# Service role bypasses RLS automatically
client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

class SupabaseService:
    """Legacy wrapper - provides client access for backward compatibility"""
    
    def __init__(self):
        self.client = client
    
    # Direct query methods - just delegate to client
    def get_approved_salons(self, limit: int = 50, offset: int = 0):
        response = self.client.table("salons").select("*").eq("status", "approved").range(offset, offset + limit - 1).execute()
        return response.data
    
    def get_pending_salons(self, limit: int = 50):
        response = self.client.table("salons").select("*").eq("status", "pending").limit(limit).execute()
        return response.data
    
    def get_salon(self, salon_id: int):
        response = self.client.table("salons").select("*").eq("id", salon_id).single().execute()
        return response.data
    
    def get_salon_services(self, salon_id: int):
        response = self.client.table("salon_services").select("*").eq("salon_id", salon_id).execute()
        return response.data
    
    def create_salon(self, salon_data: dict):
        response = self.client.table("salons").insert(salon_data).execute()
        return response.data[0] if response.data else None
    
    def update_salon(self, salon_id: int, updates: dict):
        response = self.client.table("salons").update(updates).eq("id", salon_id).execute()
        return response.data[0] if response.data else None
    
    def approve_salon(self, salon_id: int, is_approved: bool, admin_id: str = None):
        status = "approved" if is_approved else "rejected"
        response = self.client.table("salons").update({"status": status, "approved_by": admin_id}).eq("id", salon_id).execute()
        return len(response.data) > 0
    
    def get_nearby_salons(self, lat: float, lon: float, radius: float, limit: int):
        # Use PostGIS RPC function if available, otherwise basic query
        try:
            response = self.client.rpc('get_nearby_salons', {
                'user_lat': lat,
                'user_lon': lon,
                'radius_km': radius,
                'max_results': limit
            }).execute()
            return response.data
        except:
            # Fallback to basic query
            response = self.client.table("salons").select("*").eq("status", "approved").limit(limit).execute()
            return response.data
    
    def search_salons(self, query: str = None, city: str = None, min_rating: float = None, limit: int = 50):
        q = self.client.table("salons").select("*").eq("status", "approved")
        
        if query:
            q = q.or_(f"name.ilike.%{query}%,description.ilike.%{query}%")
        if city:
            q = q.eq("city", city)
        if min_rating:
            q = q.gte("rating", min_rating)
        
        response = q.limit(limit).execute()
        return response.data
    
    def upload_salon_image(self, bucket: str, file_path: str, file_data: bytes):
        # Storage not implemented yet - return None
        return None
    
    def create_booking(self, booking_data: dict):
        response = self.client.table("bookings").insert(booking_data).execute()
        return response.data[0] if response.data else None
    
    def get_user_bookings(self, user_id: str):
        response = self.client.table("bookings").select("*").eq("user_id", user_id).order("booking_date", desc=True).execute()
        return response.data
    
    def get_salon_bookings(self, salon_id: int):
        response = self.client.table("bookings").select("*").eq("salon_id", salon_id).order("booking_date", desc=True).execute()
        return response.data
    
    def update_booking_status(self, booking_id: str, status: str, cancellation_reason: str = None):
        updates = {"status": status}
        if cancellation_reason:
            updates["cancellation_reason"] = cancellation_reason
        response = self.client.table("bookings").update(updates).eq("id", booking_id).execute()
        return len(response.data) > 0


# Create singleton instance
supabase_service = SupabaseService()
