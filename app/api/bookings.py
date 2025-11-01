"""
Modern Booking API Endpoints using Supabase

These endpoints leverage:
- Row Level Security (users can only see their own bookings)
- Auto-generated REST APIs
- Real-time updates for salon owners
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Body
from typing import List, Dict, Optional
from pydantic import BaseModel
from app.services.supabase_service import supabase_service
from app.services.email import email_service
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


class BookingCreate(BaseModel):
    user_id: str
    salon_id: int
    salon_name: str
    booking_date: str
    booking_time: str
    services: List[Dict]
    total_amount: float
    discount_applied: float = 0
    final_amount: float
    notes: Optional[str] = None


class BookingUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    cancellation_reason: Optional[str] = None


@router.get("/")
async def get_bookings(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    salon_id: Optional[int] = Query(None, description="Filter by salon ID")
):
    """
    Get bookings
    
    RLS automatically enforces:
    - Users can only see their own bookings
    - Salon owners can see bookings for their salons
    - Admins can see all bookings
    """
    try:
        if user_id:
            bookings = supabase_service.get_user_bookings(user_id)
        elif salon_id:
            bookings = supabase_service.get_salon_bookings(salon_id)
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
async def get_user_bookings(user_id: str):
    """
    Get all bookings for a user
    
    RLS ensures users can only see their own bookings
    """
    try:
        bookings = supabase_service.get_user_bookings(user_id)
        return {
            "bookings": bookings,
            "count": len(bookings)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/salon/{salon_id}")
async def get_salon_bookings(salon_id: int):
    """
    Get all bookings for a salon
    
    RLS ensures only salon owner or admin can see these
    """
    try:
        bookings = supabase_service.get_salon_bookings(salon_id)
        return {
            "bookings": bookings,
            "count": len(bookings)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{booking_id}")
async def get_booking(booking_id: str):
    """Get single booking by ID - RLS enforced"""
    try:
        response = supabase_service.client.table("bookings")\
            .select("*, salons(*), salon_services(*)")\
            .eq("id", booking_id)\
            .single()\
            .execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        return response.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_booking(booking: BookingCreate):
    """
    Create new booking
    
    RLS ensures:
    - Users can only create bookings for themselves
    - Field user_id is automatically set to auth.uid()
    """
    try:
        # Convert Pydantic model to dict
        booking_data = booking.model_dump()
        
        # Create booking
        created_booking = supabase_service.create_booking(booking_data)
        
        if not created_booking:
            raise HTTPException(status_code=500, detail="Failed to create booking")
        
        # Get customer details for email
        customer_response = supabase_service.client.table("profiles")\
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
async def update_booking(booking_id: str, updates: BookingUpdate):
    """
    Update booking
    
    RLS ensures:
    - Users can only update their own bookings
    - Admins and salon owners can update bookings
    """
    try:
        update_data = {}
        if updates.status:
            update_data["status"] = updates.status
        if updates.notes is not None:
            update_data["notes"] = updates.notes
        if updates.cancellation_reason:
            update_data["cancellation_reason"] = updates.cancellation_reason
        
        response = supabase_service.client.table("bookings")\
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
    reason: Optional[str] = Body(None)
):
    """
    Cancel booking
    
    RLS ensures users can only cancel their own bookings
    """
    try:
        # Get booking details before cancellation
        booking_response = supabase_service.client.table("bookings")\
            .select("*, profiles(email, full_name)")\
            .eq("id", booking_id)\
            .single()\
            .execute()
        
        if not booking_response.data:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        booking_data = booking_response.data
        
        # Cancel booking
        success = supabase_service.update_booking_status(
            booking_id=booking_id,
            status="cancelled",
            cancellation_reason=reason
        )
        
        if not success:
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
async def complete_booking(booking_id: str):
    """
    Mark booking as completed
    
    RLS ensures only salon owner or admin can complete bookings
    """
    try:
        success = supabase_service.update_booking_status(
            booking_id=booking_id,
            status="completed"
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to complete booking")
        
        return {"success": True, "message": "Booking completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


