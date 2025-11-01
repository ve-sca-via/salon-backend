"""
Vendor API Endpoints
Handles vendor registration completion, salon management, services, staff, and bookings
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from supabase import create_client, Client
from app.core.config import settings
from app.core.auth import (
    require_vendor,
    TokenData,
    get_current_user_id,
    verify_registration_token,
    create_access_token,
    create_refresh_token
)
from app.schemas import (
    SalonResponse,
    SalonUpdate,
    ServiceCreate,
    ServiceUpdate,
    ServiceResponse,
    SalonStaffCreate,
    SalonStaffUpdate,
    SalonStaffResponse,
    BookingResponse,
    SuccessResponse
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vendors", tags=["Vendors"])

# Initialize Supabase client
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


# =====================================================
# REGISTRATION COMPLETION
# =====================================================

@router.post("/complete-registration")
async def complete_registration(
    token: str,
    password: str,
    confirm_password: str
):
    """
    Complete vendor registration after admin approval
    - Verify token
    - Create auth user
    - Link to salon
    """
    try:
        # Verify JWT registration token
        token_data = verify_registration_token(token)
        salon_id = token_data["salon_id"]
        request_id = token_data["request_id"]
        vendor_email = token_data["email"]
        
        if password != confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )
        
        # Create Supabase auth user
        auth_response = supabase.auth.admin.create_user({
            "email": vendor_email,
            "password": password,
            "email_confirm": True  # Auto-confirm email
        })
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user account"
            )
        
        user_id = auth_response.user.id
        
        # TODO: Create vendor profile
        # profile_data = {
        #     "id": auth_response.user.id,
        #     "email": vendor_email,
        #     "full_name": owner_name,
        #     "role": "vendor"
        # }
        
        # TODO: Link vendor to salon
        # supabase.table("salons").update({
        #     "vendor_id": auth_response.user.id
        # }).eq("id", salon_id).execute()
        
        logger.info(f"Vendor registration completed")
        
        return {
            "success": True,
            "message": "Registration completed. Please pay registration fee to activate account."
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration completion failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration completion failed"
        )


# =====================================================
# SALON MANAGEMENT
# =====================================================

@router.get("/salon", response_model=SalonResponse)
async def get_own_salon(current_user: TokenData = Depends(require_vendor)):
    """Get own salon details"""
    try:
        response = supabase.table("salons").select("*").eq("vendor_id", vendor_id).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        return response.data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch salon: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch salon"
        )


@router.put("/salon", response_model=SalonResponse)
async def update_own_salon(
    update: SalonUpdate,
    current_user: TokenData = Depends(require_vendor)
):
    """Update own salon details"""
    try:
        # Verify salon exists and belongs to vendor
        check_response = supabase.table("salons").select("id").eq("vendor_id", vendor_id).single().execute()
        
        if not check_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        # Update salon
        update_data = update.model_dump(exclude_unset=True)
        
        response = supabase.table("salons").update(update_data).eq("vendor_id", vendor_id).execute()
        
        logger.info(f"Vendor {vendor_id} updated salon")
        
        return response.data[0] if response.data else None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update salon: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update salon"
        )


# =====================================================
# SERVICE MANAGEMENT
# =====================================================

@router.get("/services", response_model=List[ServiceResponse])
async def get_own_services(
    current_user: TokenData = Depends(require_vendor)
):
    """Get all services for own salon"""
    try:
        # Get salon ID
        salon_response = supabase.table("salons").select("id").eq("vendor_id", vendor_id).single().execute()
        
        if not salon_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        salon_id = salon_response.data["id"]
        
        # Get services
        response = supabase.table("services").select(
            "*, service_categories(*)"
        ).eq("salon_id", salon_id).order("created_at", desc=True).execute()
        
        return response.data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch services: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch services"
        )


@router.post("/services", response_model=ServiceResponse)
async def create_service(
    service: ServiceCreate,
    current_user: TokenData = Depends(require_vendor)
):
    """Create new service"""
    try:
        # Get salon ID and verify ownership
        salon_response = supabase.table("salons").select("id").eq("vendor_id", vendor_id).single().execute()
        
        if not salon_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        salon_id = salon_response.data["id"]
        
        # Verify service is for own salon
        if service.salon_id != salon_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot create service for other salons"
            )
        
        # Create service
        service_data = service.model_dump()
        
        response = supabase.table("services").insert(service_data).execute()
        
        logger.info(f"Vendor {vendor_id} created service: {service.name}")
        
        return response.data[0] if response.data else None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create service"
        )


@router.put("/services/{service_id}", response_model=ServiceResponse)
async def update_service(
    service_id: str,
    update: ServiceUpdate,
    current_user: TokenData = Depends(require_vendor)
):
    """Update service"""
    try:
        # Get salon ID
        salon_response = supabase.table("salons").select("id").eq("vendor_id", vendor_id).single().execute()
        
        if not salon_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        salon_id = salon_response.data["id"]
        
        # Verify service belongs to vendor's salon
        service_check = supabase.table("services").select("salon_id").eq("id", service_id).single().execute()
        
        if not service_check.data or service_check.data["salon_id"] != salon_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found or access denied"
            )
        
        # Update service
        update_data = update.model_dump(exclude_unset=True)
        
        response = supabase.table("services").update(update_data).eq("id", service_id).execute()
        
        logger.info(f"Vendor {vendor_id} updated service {service_id}")
        
        return response.data[0] if response.data else None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update service"
        )


@router.delete("/services/{service_id}")
async def delete_service(
    service_id: str,
    current_user: TokenData = Depends(require_vendor)
):
    """Delete service"""
    try:
        # Get salon ID
        salon_response = supabase.table("salons").select("id").eq("vendor_id", vendor_id).single().execute()
        
        if not salon_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        salon_id = salon_response.data["id"]
        
        # Verify service belongs to vendor's salon
        service_check = supabase.table("services").select("salon_id").eq("id", service_id).single().execute()
        
        if not service_check.data or service_check.data["salon_id"] != salon_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found or access denied"
            )
        
        # Delete service
        supabase.table("services").delete().eq("id", service_id).execute()
        
        logger.info(f"Vendor {vendor_id} deleted service {service_id}")
        
        return {
            "success": True,
            "message": "Service deleted successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete service"
        )


# =====================================================
# STAFF MANAGEMENT
# =====================================================

@router.get("/staff", response_model=List[SalonStaffResponse])
async def get_own_staff(current_user: TokenData = Depends(require_vendor)):
    """Get all staff for own salon"""
    try:
        # Get salon ID
        salon_response = supabase.table("salons").select("id").eq("vendor_id", vendor_id).single().execute()
        
        if not salon_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        salon_id = salon_response.data["id"]
        
        # Get staff
        response = supabase.table("salon_staff").select("*").eq("salon_id", salon_id).order("created_at", desc=True).execute()
        
        return response.data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch staff: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch staff"
        )


@router.post("/staff", response_model=SalonStaffResponse)
async def create_staff(
    staff: SalonStaffCreate,
    current_user: TokenData = Depends(require_vendor)
):
    """Add new staff member"""
    try:
        # Get salon ID and verify ownership
        salon_response = supabase.table("salons").select("id").eq("vendor_id", vendor_id).single().execute()
        
        if not salon_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        salon_id = salon_response.data["id"]
        
        # Verify staff is for own salon
        if staff.salon_id != salon_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot add staff to other salons"
            )
        
        # Create staff
        staff_data = staff.model_dump()
        
        response = supabase.table("salon_staff").insert(staff_data).execute()
        
        logger.info(f"Vendor {vendor_id} added staff: {staff.full_name}")
        
        return response.data[0] if response.data else None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create staff: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create staff"
        )


@router.put("/staff/{staff_id}", response_model=SalonStaffResponse)
async def update_staff(
    staff_id: str,
    update: SalonStaffUpdate,
    current_user: TokenData = Depends(require_vendor)
):
    """Update staff member"""
    try:
        # Get salon ID
        salon_response = supabase.table("salons").select("id").eq("vendor_id", vendor_id).single().execute()
        
        if not salon_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        salon_id = salon_response.data["id"]
        
        # Verify staff belongs to vendor's salon
        staff_check = supabase.table("salon_staff").select("salon_id").eq("id", staff_id).single().execute()
        
        if not staff_check.data or staff_check.data["salon_id"] != salon_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Staff not found or access denied"
            )
        
        # Update staff
        update_data = update.model_dump(exclude_unset=True)
        
        response = supabase.table("salon_staff").update(update_data).eq("id", staff_id).execute()
        
        logger.info(f"Vendor {vendor_id} updated staff {staff_id}")
        
        return response.data[0] if response.data else None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update staff: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update staff"
        )


@router.delete("/staff/{staff_id}")
async def delete_staff(
    staff_id: str,
    current_user: TokenData = Depends(require_vendor)
):
    """Delete staff member"""
    try:
        # Get salon ID
        salon_response = supabase.table("salons").select("id").eq("vendor_id", vendor_id).single().execute()
        
        if not salon_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        salon_id = salon_response.data["id"]
        
        # Verify staff belongs to vendor's salon
        staff_check = supabase.table("salon_staff").select("salon_id").eq("id", staff_id).single().execute()
        
        if not staff_check.data or staff_check.data["salon_id"] != salon_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Staff not found or access denied"
            )
        
        # Delete staff
        supabase.table("salon_staff").delete().eq("id", staff_id).execute()
        
        logger.info(f"Vendor {vendor_id} deleted staff {staff_id}")
        
        return {
            "success": True,
            "message": "Staff deleted successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete staff: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete staff"
        )


# =====================================================
# BOOKINGS VIEW
# =====================================================

@router.get("/bookings", response_model=List[BookingResponse])
async def get_salon_bookings(
    status_filter: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(require_vendor)
):
    """Get all bookings for own salon"""
    try:
        # Get salon ID
        salon_response = supabase.table("salons").select("id").eq("vendor_id", vendor_id).single().execute()
        
        if not salon_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        salon_id = salon_response.data["id"]
        
        # Build query
        query = supabase.table("bookings").select(
            "*, services(*), salon_staff(*), profiles(*)"
        ).eq("salon_id", salon_id)
        
        if status_filter:
            query = query.eq("status", status_filter)
        
        if date_from:
            query = query.gte("booking_date", date_from)
        
        if date_to:
            query = query.lte("booking_date", date_to)
        
        response = query.order("booking_date", desc=True).order("booking_time", desc=True).range(offset, offset + limit - 1).execute()
        
        return response.data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch bookings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch bookings"
        )


@router.put("/bookings/{booking_id}/status")
async def update_booking_status(
    booking_id: str,
    new_status: str,
    current_user: TokenData = Depends(require_vendor)
):
    """Update booking status (confirm, complete, no-show)"""
    try:
        # Validate status
        valid_statuses = ["confirmed", "completed", "no_show"]
        if new_status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {valid_statuses}"
            )
        
        # Get salon ID
        salon_response = supabase.table("salons").select("id").eq("vendor_id", vendor_id).single().execute()
        
        if not salon_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        salon_id = salon_response.data["id"]
        
        # Verify booking belongs to vendor's salon
        booking_check = supabase.table("bookings").select("salon_id, status").eq("id", booking_id).single().execute()
        
        if not booking_check.data or booking_check.data["salon_id"] != salon_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found or access denied"
            )
        
        # Update status
        update_data = {"status": new_status}
        
        if new_status == "confirmed":
            update_data["confirmed_at"] = "now()"
        elif new_status == "completed":
            update_data["completed_at"] = "now()"
        
        response = supabase.table("bookings").update(update_data).eq("id", booking_id).execute()
        
        logger.info(f"Vendor {vendor_id} updated booking {booking_id} status to {new_status}")
        
        return {
            "success": True,
            "message": f"Booking status updated to {new_status}",
            "data": response.data[0] if response.data else None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update booking status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update booking status"
        )


# =====================================================
# DASHBOARD
# =====================================================

@router.get("/dashboard")
async def get_vendor_dashboard(current_user: TokenData = Depends(require_vendor)):
    """Get vendor dashboard statistics"""
    try:
        # Get salon
        salon_response = supabase.table("salons").select("*").eq("vendor_id", vendor_id).single().execute()
        
        if not salon_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        salon_id = salon_response.data["id"]
        salon = salon_response.data
        
        # Get counts
        total_services = supabase.table("services").select("id", count="exact").eq("salon_id", salon_id).execute()
        total_staff = supabase.table("salon_staff").select("id", count="exact").eq("salon_id", salon_id).execute()
        total_bookings = supabase.table("bookings").select("id", count="exact").eq("salon_id", salon_id).execute()
        pending_bookings = supabase.table("bookings").select("id", count="exact").eq("salon_id", salon_id).eq("status", "pending").execute()
        
        # Today's bookings
        today_bookings = supabase.table("bookings").select("id", count="exact").eq("salon_id", salon_id).gte("booking_date", "today").execute()
        
        return {
            "salon": salon,
            "statistics": {
                "total_services": total_services.count if total_services else 0,
                "total_staff": total_staff.count if total_staff else 0,
                "total_bookings": total_bookings.count if total_bookings else 0,
                "pending_bookings": pending_bookings.count if pending_bookings else 0,
                "today_bookings": today_bookings.count if today_bookings else 0,
                "average_rating": salon.get("average_rating", 0),
                "total_reviews": salon.get("total_reviews", 0)
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch vendor dashboard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch vendor dashboard"
        )

