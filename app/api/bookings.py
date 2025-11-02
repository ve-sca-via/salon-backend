"""
Modern Booking API Endpoints using Supabase

These endpoints leverage:
- Row Level Security (users can only see their own bookings)
- Auto-generated REST APIs
- Real-time updates for salon owners
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Body
from typing import List, Dict, Optional
from supabase import create_client, Client
from app.core.config import settings
from app.core.auth import get_current_user, TokenData
from app.services.email import email_service
from app.schemas import BookingCreate, BookingUpdate
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bookings", tags=["bookings"])

# Initialize Supabase client
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


@router.get("/")
async def get_bookings(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    salon_id: Optional[int] = Query(None, description="Filter by salon ID"),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get bookings - PROTECTED
    
    Authorization:
    - Users can only see their own bookings
    - Salon vendors can see bookings for their salon
    - Admins can see all bookings
    """
    try:
        if user_id:
            # Users can only access their own bookings unless admin
            if current_user.role not in ["admin"] and current_user.user_id != user_id:
                raise HTTPException(
                    status_code=403, 
                    detail="Cannot access other users' bookings"
                )
            
            response = supabase.table("bookings").select("*").eq("user_id", user_id).order("booking_date", desc=True).execute()
            bookings = response.data
        elif salon_id:
            # Verify salon ownership for vendors
            if current_user.role == "vendor":
                salon_check = supabase.table("salons").select("vendor_id").eq("id", salon_id).single().execute()
                if not salon_check.data or salon_check.data["vendor_id"] != current_user.user_id:
                    raise HTTPException(
                        status_code=403,
                        detail="Cannot access other salons' bookings"
                    )
            elif current_user.role not in ["admin"]:
                raise HTTPException(
                    status_code=403,
                    detail="Insufficient permissions to view salon bookings"
                )
            
            response = supabase.table("bookings").select("*").eq("salon_id", salon_id).order("booking_date", desc=True).execute()
            bookings = response.data
        else:
            raise HTTPException(status_code=400, detail="Must provide user_id or salon_id")
        
        return {
            "bookings": bookings,
            "count": len(bookings)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{user_id}")
async def get_user_bookings(
    user_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get all bookings for a user - PROTECTED
    
    Authorization:
    - Users can only see their own bookings
    - Admins can see any user's bookings
    """
    try:
        # Verify ownership
        if current_user.role != "admin" and current_user.user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Cannot access other users' bookings"
            )
        
        response = supabase.table("bookings").select("*").eq("user_id", user_id).order("booking_date", desc=True).execute()
        bookings = response.data
        return {
            "bookings": bookings,
            "count": len(bookings)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/salon/{salon_id}")
async def get_salon_bookings(
    salon_id: int,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get all bookings for a salon - PROTECTED
    
    Authorization:
    - Salon vendors can only see their own salon's bookings
    - Admins can see any salon's bookings
    """
    try:
        # Verify salon ownership for vendors
        if current_user.role == "vendor":
            salon_check = supabase.table("salons").select("vendor_id").eq("id", salon_id).single().execute()
            if not salon_check.data or salon_check.data["vendor_id"] != current_user.user_id:
                raise HTTPException(
                    status_code=403,
                    detail="Cannot access other salons' bookings"
                )
        elif current_user.role not in ["admin"]:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions to view salon bookings"
            )
        
        response = supabase.table("bookings").select("*").eq("salon_id", salon_id).order("booking_date", desc=True).execute()
        bookings = response.data
        return {
            "bookings": bookings,
            "count": len(bookings)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{booking_id}")
async def get_booking(
    booking_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Get single booking by ID - PROTECTED"""
    try:
        response = supabase.table("bookings")\
            .select("*, salons(*), salon_services(*)")\
            .eq("id", booking_id)\
            .single()\
            .execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        booking = response.data
        
        # Verify access - user owns booking, or is admin, or is salon vendor
        is_owner = booking["user_id"] == current_user.user_id
        is_admin = current_user.role == "admin"
        is_vendor = False
        
        if current_user.role == "vendor":
            salon_check = supabase.table("salons").select("vendor_id").eq("id", booking["salon_id"]).single().execute()
            is_vendor = salon_check.data and salon_check.data["vendor_id"] == current_user.user_id
        
        if not (is_owner or is_admin or is_vendor):
            raise HTTPException(
                status_code=403,
                detail="Cannot access this booking"
            )
        
        return booking
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_booking(
    booking: BookingCreate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Create new booking - PROTECTED
    
    Authorization:
    - Users can only create bookings for themselves
    - Admins can create bookings for any user
    """
    try:
        # Verify user is creating booking for themselves (unless admin)
        if current_user.role != "admin" and booking.user_id != current_user.user_id:
            raise HTTPException(
                status_code=403,
                detail="Cannot create bookings for other users"
            )
        
        # Convert Pydantic model to dict
        booking_data = booking.model_dump()
        
        # Create booking
        response = supabase.table("bookings").insert(booking_data).execute()
        created_booking = response.data[0] if response.data else None
        
        if not created_booking:
            raise HTTPException(status_code=500, detail="Failed to create booking")
        
        # Get customer details for email
        customer_response = supabase.table("profiles")\
            .select("email, full_name")\
            .eq("id", booking.user_id)\
            .single()\
            .execute()
        
        if customer_response.data:
            customer_email = customer_response.data.get("email")
            customer_name = customer_response.data.get("full_name", "Customer")
            
            # Get primary service name (first service in list)
            service_name = booking.services[0].get("name", "Service") if booking.services else "Service"
            
            # Get staff name if available
            staff_name = "Our Team"
            if booking.services and len(booking.services) > 0:
                staff_name = booking.services[0].get("staff_name", "Our Team")
            
            # Send booking confirmation email
            email_sent = await email_service.send_booking_confirmation_email(
                to_email=customer_email,
                customer_name=customer_name,
                salon_name=booking.salon_name,
                service_name=service_name,
                booking_date=booking.booking_date,
                booking_time=booking.booking_time,
                staff_name=staff_name,
                total_amount=booking.final_amount,
                booking_id=created_booking.get("id", "N/A")
            )
            
            if not email_sent:
                logger.warning(f"Failed to send booking confirmation email to {customer_email}")
        
        return created_booking
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{booking_id}")
async def update_booking(
    booking_id: str,
    updates: BookingUpdate,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Update booking - PROTECTED
    
    Authorization:
    - Users can update their own bookings
    - Salon vendors can update bookings for their salon
    - Admins can update any booking
    """
    try:
        # Get booking to verify ownership
        booking_check = supabase.table("bookings").select("user_id, salon_id").eq("id", booking_id).single().execute()
        
        if not booking_check.data:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        booking = booking_check.data
        
        # Verify access
        is_owner = booking["user_id"] == current_user.user_id
        is_admin = current_user.role == "admin"
        is_vendor = False
        
        if current_user.role == "vendor":
            salon_check = supabase.table("salons").select("vendor_id").eq("id", booking["salon_id"]).single().execute()
            is_vendor = salon_check.data and salon_check.data["vendor_id"] == current_user.user_id
        
        if not (is_owner or is_admin or is_vendor):
            raise HTTPException(
                status_code=403,
                detail="Cannot update this booking"
            )
        
        update_data = {}
        if updates.status:
            update_data["status"] = updates.status
        if updates.notes is not None:
            update_data["notes"] = updates.notes
        if updates.cancellation_reason:
            update_data["cancellation_reason"] = updates.cancellation_reason
        
        response = supabase.table("bookings")\
            .update(update_data)\
            .eq("id", booking_id)\
            .execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{booking_id}/cancel")
async def cancel_booking(
    booking_id: str,
    reason: Optional[str] = Body(None),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Cancel booking - PROTECTED
    
    Authorization:
    - Users can cancel their own bookings
    - Admins can cancel any booking
    """
    try:
        # Get booking details before cancellation
        booking_response = supabase.table("bookings")\
            .select("*, profiles(email, full_name)")\
            .eq("id", booking_id)\
            .single()\
            .execute()
        
        if not booking_response.data:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        booking_data = booking_response.data
        
        # Verify ownership
        if current_user.role != "admin" and booking_data["user_id"] != current_user.user_id:
            raise HTTPException(
                status_code=403,
                detail="Cannot cancel other users' bookings"
            )
        
        # Cancel booking
        update_data = {
            "status": "cancelled",
            "cancellation_reason": reason
        }
        response = supabase.table("bookings").update(update_data).eq("id", booking_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to cancel booking")
        
        # Get refund amount (if applicable)
        refund_amount = 0.0
        if booking_data.get("final_amount"):
            # Calculate refund based on cancellation policy
            # For now, assume full refund
            refund_amount = booking_data["final_amount"]
        
        # Send cancellation email
        if booking_data.get("profiles"):
            customer_email = booking_data["profiles"].get("email")
            customer_name = booking_data["profiles"].get("full_name", "Customer")
            
            # Get service name from booking data
            services = booking_data.get("services", [])
            service_name = services[0].get("name", "Service") if services else "Service"
            
            email_sent = await email_service.send_booking_cancellation_email(
                to_email=customer_email,
                customer_name=customer_name,
                salon_name=booking_data.get("salon_name", "Salon"),
                service_name=service_name,
                booking_date=booking_data.get("booking_date", "N/A"),
                booking_time=booking_data.get("booking_time", "N/A"),
                refund_amount=refund_amount,
                cancellation_reason=reason
            )
            
            if not email_sent:
                logger.warning(f"Failed to send cancellation email to {customer_email}")
        
        return {"success": True, "message": "Booking cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{booking_id}/complete")
async def complete_booking(
    booking_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Mark booking as completed - PROTECTED
    
    Authorization:
    - Only salon vendors can complete bookings for their salon
    - Admins can complete any booking
    """
    try:
        # Get booking to verify salon
        booking_check = supabase.table("bookings").select("salon_id").eq("id", booking_id).single().execute()
        
        if not booking_check.data:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        # Verify vendor owns the salon
        if current_user.role == "vendor":
            salon_check = supabase.table("salons").select("vendor_id").eq("id", booking_check.data["salon_id"]).single().execute()
            if not salon_check.data or salon_check.data["vendor_id"] != current_user.user_id:
                raise HTTPException(
                    status_code=403,
                    detail="Cannot complete bookings for other salons"
                )
        elif current_user.role not in ["admin"]:
            raise HTTPException(
                status_code=403,
                detail="Only salon vendors and admins can complete bookings"
            )
        
        update_data = {"status": "completed"}
        response = supabase.table("bookings").update(update_data).eq("id", booking_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to complete booking")
        
        return {"success": True, "message": "Booking completed"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


