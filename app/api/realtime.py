"""
Realtime API for Live Updates

Set up real-time subscriptions for:
- Live booking updates
- Salon status changes
- New service additions
"""

from fastapi import APIRouter, HTTPException
from app.core.database import get_db
from app.core.config import settings

router = APIRouter(prefix="/api/realtime", tags=["realtime"])

# Initialize Supabase client for realtime using factory function
supabase_client = get_db()


class RealtimeChannel:
    """Manage realtime channel subscriptions"""
    
    def __init__(self, channel_name: str):
        self.channel_name = channel_name
        self.channel = None
    
    def subscribe(self, event_type: str, table: str, callback):
        """Subscribe to a realtime channel"""
        self.channel = supabase_client.channel(self.channel_name)
        
        self.channel.on(
            "postgres_changes",
            {
                "event": event_type,
                "schema": "public",
                "table": table
            },
            callback
        ).subscribe()
        
        return self.channel
    
    def unsubscribe(self):
        """Unsubscribe from the channel"""
        if self.channel:
            supabase_client.remove_channel(self.channel)


# Global channels
salon_channels = {}
booking_channels = {}


@router.post("/subscribe/salon/{salon_id}")
async def subscribe_to_salon(salon_id: int):
    """
    Subscribe to real-time updates for a salon
    
    This endpoint sets up a subscription to receive:
    - Status changes (pending → approved)
    - New images added
    - Service updates
    """
    try:
        channel_name = f"salon-{salon_id}"
        
        # Create channel if doesn't exist
        if channel_name not in salon_channels:
            channel = RealtimeChannel(channel_name)
            
            # Subscribe to salon updates
            channel.subscribe(
                event_type="UPDATE",
                table="salons",
                callback=lambda payload: print(f"Salon update: {payload}")
            )
            
            salon_channels[channel_name] = channel
        
        return {
            "success": True,
            "message": f"Subscribed to salon {salon_id} updates",
            "channel": channel_name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subscribe/bookings/{salon_id}")
async def subscribe_to_bookings(salon_id: int):
    """
    Subscribe to real-time booking updates for a salon
    
    Perfect for salon owners to see new bookings instantly
    """
    try:
        channel_name = f"salon-{salon_id}-bookings"
        
        # Create channel if doesn't exist
        if channel_name not in booking_channels:
            channel = RealtimeChannel(channel_name)
            
            # Subscribe to new bookings
            channel.subscribe(
                event_type="INSERT",
                table="bookings",
                callback=lambda payload: print(f"New booking: {payload}")
            )
            
            booking_channels[channel_name] = channel
        
        return {
            "success": True,
            "message": f"Subscribed to bookings for salon {salon_id}",
            "channel": channel_name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/unsubscribe")
async def unsubscribe(channel_name: str):
    """Unsubscribe from a realtime channel"""
    try:
        # Remove from salon channels
        if channel_name in salon_channels:
            salon_channels[channel_name].unsubscribe()
            del salon_channels[channel_name]
        
        # Remove from booking channels
        if channel_name in booking_channels:
            booking_channels[channel_name].unsubscribe()
            del booking_channels[channel_name]
        
        return {
            "success": True,
            "message": f"Unsubscribed from {channel_name}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_realtime_status():
    """Get status of active realtime subscriptions"""
    return {
        "active_salon_channels": list(salon_channels.keys()),
        "active_booking_channels": list(booking_channels.keys()),
        "total_channels": len(salon_channels) + len(booking_channels)
    }


