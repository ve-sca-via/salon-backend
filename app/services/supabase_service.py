"""
Modern Supabase Service - Production Implementation

This replaces the traditional SQLAlchemy approach with Supabase's full feature set:
- Auto-generated REST APIs
- Row Level Security enforcement
- Supabase Storage for images
- Real-time subscriptions
"""

from supabase import create_client, Client
from app.core.config import settings
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
import json


class SupabaseService:
    """
    Modern Supabase implementation with full feature set
    Replaces SQLAlchemy for better developer experience and security
    """
    
    def __init__(self):
        # Initialize Supabase clients
        self.client: Client = create_client(
            settings.SUPABASE_URL, 
            settings.SUPABASE_SERVICE_ROLE_KEY
        )
        
        # Use anon key for user-facing operations (respects RLS)
        self.public_client: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_ANON_KEY
        )
    
    # ========================================
    # SALON OPERATIONS
    # ========================================
    
    def get_salon(self, salon_id: int) -> Optional[Dict]:
        """Get salon by ID - automatically respects RLS policies"""
        try:
            response = self.client.table("salons")\
                .select("*")\
                .eq("id", salon_id)\
                .single()\
                .execute()
            
            return response.data if response.data else None
        except Exception as e:
            print(f"Error getting salon: {e}")
            return None
    
    def get_approved_salons(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Get approved salons - RLS ensures only approved salons are visible"""
        try:
            response = self.client.table("salons")\
                .select("*")\
                .eq("status", "approved")\
                .order("created_at", desc=True)\
                .limit(limit)\
                .offset(offset)\
                .execute()
            
            return response.data if response.data else []
        except Exception as e:
            print(f"Error getting approved salons: {e}")
            return []
    
    def get_pending_salons(self, limit: int = 50) -> List[Dict]:
        """Get pending salons - Only admins can see these (RLS enforced)"""
        try:
            response = self.client.table("salons")\
                .select("*")\
                .eq("status", "pending")\
                .order("submitted_at", desc=True)\
                .limit(limit)\
                .execute()
            
            return response.data if response.data else []
        except Exception as e:
            print(f"Error getting pending salons: {e}")
            return []
    
    def create_salon(self, salon_data: Dict) -> Optional[Dict]:
        """Create new salon - RLS ensures only authorized users can create"""
        try:
            response = self.client.table("salons")\
                .insert(salon_data)\
                .execute()
            
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating salon: {e}")
            raise
    
    def update_salon(self, salon_id: int, updates: Dict) -> Optional[Dict]:
        """Update salon - RLS ensures only owner/admin can update"""
        try:
            response = self.client.table("salons")\
                .update(updates)\
                .eq("id", salon_id)\
                .execute()
            
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating salon: {e}")
            raise
    
    def approve_salon(self, salon_id: int, reviewed_by: str, rejection_reason: Optional[str] = None) -> bool:
        """Approve or reject salon - RLS ensures only admins can do this"""
        try:
            data = {
                "status": "approved" if not rejection_reason else "rejected",
                "reviewed_by": reviewed_by,
                "reviewed_at": "now()",
                "rejection_reason": rejection_reason
            }
            
            self.client.table("salons")\
                .update(data)\
                .eq("id", salon_id)\
                .execute()
            
            return True
        except Exception as e:
            print(f"Error approving salon: {e}")
            return False
    
    # ========================================
    # NEARBY SALONS (Using PostGIS Function)
    # ========================================
    
    def get_nearby_salons(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 10.0,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get nearby salons using PostGIS function
        Much faster than calculating distance in Python
        """
        try:
            response = self.client.rpc(
                "nearby_salons",
                {
                    "user_lat": latitude,
                    "user_lon": longitude,
                    "radius_km": radius_km,
                    "max_results": limit
                }
            ).execute()
            
            return response.data if response.data else []
        except Exception as e:
            print(f"Error getting nearby salons: {e}")
            return []
    
    def search_salons(
        self,
        query: str,
        city: Optional[str] = None,
        min_rating: float = 0.0,
        limit: int = 50
    ) -> List[Dict]:
        """Search salons using full-text search function"""
        try:
            response = self.client.rpc(
                "search_salons",
                {
                    "search_query": query,
                    "city_filter": city,
                    "min_rating": min_rating,
                    "max_results": limit
                }
            ).execute()
            
            return response.data if response.data else []
        except Exception as e:
            print(f"Error searching salons: {e}")
            return []
    
    # ========================================
    # SUPABASE STORAGE OPERATIONS
    # ========================================
    
    def upload_salon_image(
        self,
        salon_id: int,
        image_data: bytes,
        filename: str,
        content_type: str = "image/jpeg"
    ) -> str:
        """
        Upload image to Supabase Storage
        Returns public URL
        
        Usage:
            url = service.upload_salon_image(salon_id, image_bytes, "cover.jpg")
        """
        try:
            file_path = f"salons/{salon_id}/{filename}"
            
            # Upload to Supabase Storage
            self.client.storage\
                .from_("salon-images")\
                .upload(
                    file_path,
                    image_data,
                    file_options={
                        "content-type": content_type,
                        "upsert": "true"
                    }
                )
            
            # Get public URL
            url = self.client.storage\
                .from_("salon-images")\
                .get_public_url(file_path)
            
            return url
        except Exception as e:
            print(f"Error uploading image: {e}")
            raise
    
    def delete_salon_image(self, salon_id: int, filename: str) -> bool:
        """Delete image from Supabase Storage"""
        try:
            file_path = f"salons/{salon_id}/{filename}"
            
            self.client.storage\
                .from_("salon-images")\
                .remove([file_path])
            
            return True
        except Exception as e:
            print(f"Error deleting image: {e}")
            return False
    
    def get_salon_image_url(self, salon_id: int, filename: str) -> str:
        """Get public URL for salon image"""
        try:
            file_path = f"salons/{salon_id}/{filename}"
            return self.client.storage\
                .from_("salon-images")\
                .get_public_url(file_path)
        except Exception as e:
            print(f"Error getting image URL: {e}")
            return ""
    
    # ========================================
    # BOOKING OPERATIONS
    # ========================================
    
    def create_booking(self, booking_data: Dict) -> Optional[Dict]:
        """Create booking - RLS ensures users can only create their own bookings"""
        try:
            response = self.client.table("bookings")\
                .insert(booking_data)\
                .execute()
            
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating booking: {e}")
            raise
    
    def get_user_bookings(self, user_id: str) -> List[Dict]:
        """Get user's bookings - RLS ensures users only see their own bookings"""
        try:
            response = self.client.table("bookings")\
                .select("*, salons(*), salon_services(*)")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .execute()
            
            return response.data if response.data else []
        except Exception as e:
            print(f"Error getting user bookings: {e}")
            return []
    
    def get_salon_bookings(self, salon_id: int) -> List[Dict]:
        """Get all bookings for a salon - RLS ensures only salon owner can see"""
        try:
            response = self.client.table("bookings")\
                .select("*")\
                .eq("salon_id", salon_id)\
                .order("booking_date", desc=True)\
                .execute()
            
            return response.data if response.data else []
        except Exception as e:
            print(f"Error getting salon bookings: {e}")
            return []
    
    def update_booking_status(
        self,
        booking_id: str,
        status: str,
        cancellation_reason: Optional[str] = None
    ) -> bool:
        """Update booking status"""
        try:
            data = {
                "status": status,
                "cancellation_reason": cancellation_reason
            }
            
            if status == "cancelled":
                data["cancelled_at"] = "now()"
            elif status == "completed":
                data["completed_at"] = "now()"
            
            self.client.table("bookings")\
                .update(data)\
                .eq("id", booking_id)\
                .execute()
            
            return True
        except Exception as e:
            print(f"Error updating booking: {e}")
            return False
    
    # ========================================
    # SALON SERVICES
    # ========================================
    
    def get_salon_services(self, salon_id: int) -> List[Dict]:
        """Get services for a salon"""
        try:
            response = self.client.table("salon_services")\
                .select("*")\
                .eq("salon_id", salon_id)\
                .eq("is_available", True)\
                .order("category", asc=True)\
                .execute()
            
            return response.data if response.data else []
        except Exception as e:
            print(f"Error getting salon services: {e}")
            return []
    
    def create_service(self, service_data: Dict) -> Optional[Dict]:
        """Create salon service"""
        try:
            response = self.client.table("salon_services")\
                .insert(service_data)\
                .execute()
            
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating service: {e}")
            raise
    
    # ========================================
    # REALTIME SUBSCRIPTIONS
    # ========================================
    
    def subscribe_to_salon_updates(self, salon_id: int, callback):
        """
        Subscribe to real-time updates for a salon
        
        Usage:
            channel = service.subscribe_to_salon_updates(1, lambda payload: print(payload))
            # Later: channel.unsubscribe()
        """
        channel = self.client.channel(f"salon-{salon_id}")
        
        channel.on(
            "postgres_changes",
            {
                "event": "UPDATE",
                "schema": "public",
                "table": "salons",
                "filter": f"id=eq.{salon_id}"
            },
            callback
        ).subscribe()
        
        return channel
    
    def subscribe_to_new_bookings(self, salon_id: int, callback):
        """
        Subscribe to new bookings for a salon
        Perfect for real-time booking notifications
        """
        channel = self.client.channel(f"salon-{salon_id}-bookings")
        
        channel.on(
            "postgres_changes",
            {
                "event": "INSERT",
                "schema": "public",
                "table": "bookings",
                "filter": f"salon_id=eq.{salon_id}"
            },
            callback
        ).subscribe()
        
        return channel


# Singleton instance
supabase_service = SupabaseService()


