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
        # Get customer details first
        customer_response = supabase.table("profiles")\
            .select("email, full_name, phone")\
            .eq("id", current_user.user_id)\
            .single()\
            .execute()
        
        if not customer_response.data:
            raise HTTPException(status_code=404, detail="Customer profile not found")
        
        customer_data = customer_response.data
        customer_name = customer_data.get("full_name", "Customer")
        customer_email = customer_data.get("email", "")
        customer_phone = customer_data.get("phone", "")
        
        # Get salon details to populate salon_name
        salon_response = supabase.table("salons")\
            .select("id, business_name")\
            .eq("id", booking.salon_id)\
            .single()\
            .execute()
        
        if not salon_response.data:
            raise HTTPException(status_code=404, detail="Salon not found")
        
        salon_name = salon_response.data.get("business_name", "Unknown Salon")
        
        # Calculate final amount and total duration
        final_amount = booking.amount_paid + booking.remaining_amount if booking.amount_paid and booking.remaining_amount else booking.total_amount
        total_duration = sum(service.get("duration", 0) for service in booking.services)
        
        # Parse booking time - handle multiple time slots
        # Frontend sends: "2:45 PM, 4:00 PM" but database accepts single time
        # We'll use the first time slot and store all times in metadata
        all_booking_times = booking.booking_time
        first_time_slot = booking.booking_time.split(",")[0].strip() if "," in booking.booking_time else booking.booking_time
        
        # Convert 12-hour format to 24-hour format for database
        try:
            from datetime import datetime as dt
            parsed_time = dt.strptime(first_time_slot, "%I:%M %p")
            db_time = parsed_time.strftime("%H:%M:%S")
        except:
            # Fallback - assume it's already in correct format
            db_time = first_time_slot
        
        # Generate booking number
        import random
        import string
        booking_number = f"BK{datetime.now().strftime('%Y%m%d')}{random.randint(1000, 9999)}"
        
        # Prepare booking data for database
        import json
        
        booking_metadata = {
            "services": booking.services,
            "booking_fee": booking.booking_fee,
            "gst_amount": booking.gst_amount,
            "amount_paid": booking.amount_paid,
            "remaining_amount": booking.remaining_amount,
            "payment_status": booking.payment_status,
            "payment_method": booking.payment_method,
            "total_amount": booking.total_amount,
            "final_amount": final_amount,
            "salon_name": salon_name,
            "all_booking_times": all_booking_times,  # Store all time slots
        }
        
        # Add original notes if provided
        if booking.notes:
            booking_metadata["original_notes"] = booking.notes
        
        # Get first service for the basic schema requirement
        first_service_id = None
        service_price = booking.total_amount
        if booking.services and len(booking.services) > 0:
            first_service_id = booking.services[0].get("service_id")
        
        # Prepare data for database schema (matches schema.sql)
        db_booking_data = {
            "booking_number": booking_number,
            "customer_id": current_user.user_id,
            "salon_id": booking.salon_id,
            "service_id": first_service_id,  # Use first service for schema compatibility
            "booking_date": booking.booking_date,
            "booking_time": db_time,  # Use first time slot in 24-hour format
            "duration_minutes": total_duration if total_duration > 0 else 60,  # Default to 60 if not specified
            "status": "confirmed" if booking.payment_status == "paid" else "pending",
            "service_price": service_price,
            "convenience_fee": booking.booking_fee if booking.booking_fee else 0,
            "total_amount": final_amount,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_email": customer_email,
            "special_requests": json.dumps(booking_metadata),  # Store all extra data as JSON
        }
        
        # Create booking
        response = supabase.table("bookings").insert(db_booking_data).execute()
        created_booking = response.data[0] if response.data else None
        
        if not created_booking:
            raise HTTPException(status_code=500, detail="Failed to create booking")
        
        # Enhance response with metadata
        if created_booking.get("special_requests"):
            try:
                metadata = json.loads(created_booking["special_requests"])
                created_booking.update(metadata)
            except:
                pass
        
        # Send booking confirmation email
        if customer_email:
            # Get primary service name (first service in list)
            service_name = booking.services[0].get("service_name", "Service") if booking.services else "Service"
            
            try:
                email_sent = await email_service.send_booking_confirmation_email(
                    to_email=customer_email,
                    customer_name=customer_name,
                    salon_name=salon_name,
                    service_name=service_name,
                    booking_date=booking.booking_date,
                    booking_time=booking.booking_time,
                    staff_name="Our Team",
                    total_amount=final_amount,
                    booking_id=created_booking.get("id", "N/A")
                )
                
                if not email_sent:
                    logger.warning(f"Failed to send booking confirmation email to {customer_email}")
            except Exception as e:
                logger.warning(f"Error sending booking confirmation email: {str(e)}")
        
        return created_booking
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating booking: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
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


