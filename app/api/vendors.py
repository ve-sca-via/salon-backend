"""
Vendor API Endpoints
Handles vendor registration completion, salon management, services, staff, and bookings
"""
from fastapi import APIRouter, HTTPException, Depends, status, Body
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
    SalonUpdate,
    ServiceCreate,
    ServiceUpdate,
    ServiceResponse,
    SalonStaffCreate,
    SalonStaffUpdate,
    SalonStaffResponse,
    BookingResponse,
    SuccessResponse,
    CompleteRegistrationRequest
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
async def complete_registration(request: CompleteRegistrationRequest):
    """
    Complete vendor registration after admin approval
    - Verify token
    - Create auth user
    - Create profile
    - Link to salon
    """
    try:
        logger.info(f"🔍 Starting vendor registration completion...")
        
        # Verify JWT registration token
        token_data = verify_registration_token(request.token)
        salon_id = token_data["salon_id"]
        request_id = token_data["request_id"]
        vendor_email = token_data["email"]
        
        logger.info(f"✅ Token verified for {vendor_email}, salon_id: {salon_id}")
        
        # Use full_name from registration request (provided by vendor)
        vendor_full_name = request.full_name.strip()
        
        logger.info(f"📝 Vendor name: {vendor_full_name}")
        
        if request.password != request.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )
        
        logger.info(f"🔐 Creating Supabase auth user for {vendor_email}...")
        
        # Create Supabase auth user using admin API
        try:
            auth_response = supabase.auth.admin.create_user({
                "email": vendor_email,
                "password": request.password,
                "email_confirm": True,  # Auto-confirm email
                "user_metadata": {
                    "role": "vendor",
                    "full_name": vendor_full_name
                }
            })
            logger.info(f"✅ Auth user created successfully")
        except Exception as auth_error:
            logger.error(f"❌ Auth user creation failed: {str(auth_error)}")
            # Try alternative approach: sign up the user
            logger.info(f"🔄 Attempting alternative signup method...")
            auth_response = supabase.auth.sign_up({
                "email": vendor_email,
                "password": request.password,
                "options": {
                    "data": {
                        "role": "vendor",
                        "full_name": vendor_full_name
                    }
                }
            })
            logger.info(f"✅ User signed up successfully")
        
        # Extract user ID from response
        if hasattr(auth_response, 'user') and auth_response.user:
            user_id = auth_response.user.id
        elif isinstance(auth_response, dict) and 'user' in auth_response:
            user_id = auth_response['user']['id']
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user account"
            )
        
        logger.info(f"👤 User ID: {user_id}")
        
        # Create vendor profile
        profile_data = {
            "id": user_id,
            "email": vendor_email,
            "full_name": vendor_full_name,
            "role": "vendor",
            "is_active": True,
            "email_verified": True
        }
        
        supabase.table("profiles").insert(profile_data).execute()
        
        logger.info(f"✅ Profile created for {vendor_email}")
        
        # Link vendor to salon
        supabase.table("salons").update({
            "vendor_id": user_id
        }).eq("id", salon_id).execute()
        
        logger.info(f"🔗 Vendor linked to salon {salon_id}")
        
        # Generate access and refresh tokens
        token_data = {
            "sub": user_id,
            "email": vendor_email,
            "role": "vendor"
        }
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        logger.info(f"🎉 Vendor registration completed successfully for {vendor_email}")
        
        return {
            "success": True,
            "message": "Registration completed successfully!",
            "data": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": {
                    "id": user_id,
                    "email": vendor_email,
                    "full_name": vendor_full_name,
                    "role": "vendor"
                }
            }
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
# PAYMENT PROCESSING (DEMO)
# =====================================================

@router.post("/process-payment")
async def process_payment(current_user: TokenData = Depends(require_vendor)):
    """
    Process vendor payment and activate salon (DEMO MODE)
    In production, this would integrate with actual payment gateway
    """
    try:
        vendor_id = current_user.user_id
        
        logger.info(f"💳 Processing payment for vendor: {vendor_id}")
        
        # Get vendor's salon
        salon_response = supabase.table("salons").select("id, business_name").eq(
            "vendor_id", vendor_id
        ).single().execute()
        
        if not salon_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        salon_id = salon_response.data["id"]
        business_name = salon_response.data.get("business_name", "Salon")
        
        logger.info(f"🏪 Found salon: {business_name} (ID: {salon_id})")
        
        # Update salon subscription status
        from datetime import datetime, timedelta
        
        payment_data = {
            "subscription_status": "active",
            "subscription_start_date": datetime.utcnow().isoformat(),
            "subscription_end_date": (datetime.utcnow() + timedelta(days=365)).isoformat(),  # 1 year
            "payment_amount": 5000.00,
            "payment_date": datetime.utcnow().isoformat(),
            "registration_fee_paid": True,
            "registration_paid_at": datetime.utcnow().isoformat(),
            "is_active": True  # Activate salon after successful payment
        }
        
        # Update salon with payment info
        supabase.table("salons").update(payment_data).eq("id", salon_id).execute()
        
        logger.info(f"✅ Payment processed successfully for salon: {business_name}")
        logger.info(f"📅 Subscription active until: {payment_data['subscription_end_date']}")
        
        return {
            "success": True,
            "message": "Payment processed successfully! Your salon is now active.",
            "data": {
                "subscription_status": "active",
                "subscription_start_date": payment_data["subscription_start_date"],
                "subscription_end_date": payment_data["subscription_end_date"],
                "payment_amount": payment_data["payment_amount"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Payment processing failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment processing failed: {str(e)}"
        )


# =====================================================
# SALON MANAGEMENT
# =====================================================

@router.get("/salon")
async def get_own_salon(current_user: TokenData = Depends(require_vendor)):
    """Get own salon details"""
    try:
        vendor_id = current_user.user_id
        
        logger.info(f"🏪 Fetching salon for vendor: {vendor_id}")
        
        response = supabase.table("salons").select("*").eq("vendor_id", vendor_id).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        logger.info(f"✅ Salon found: {response.data.get('business_name')}")
        return response.data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch salon: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch salon"
        )


@router.put("/salon")
async def update_own_salon(
    update: SalonUpdate,
    current_user: TokenData = Depends(require_vendor)
):
    """Update own salon details"""
    try:
        vendor_id = current_user.user_id
        
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
        vendor_id = current_user.user_id
        
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
        vendor_id = current_user.user_id
        
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
        vendor_id = current_user.user_id
        
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
        import traceback
        logger.error(f"Failed to update service: {str(e)}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
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
        vendor_id = current_user.user_id
        
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
        vendor_id = current_user.user_id
        
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
        vendor_id = current_user.user_id
        
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
        vendor_id = current_user.user_id
        
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
        vendor_id = current_user.user_id
        
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
        import traceback
        logger.error(f"Failed to delete staff: {str(e)}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
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
        vendor_id = current_user.user_id
        
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
        vendor_id = current_user.user_id
        
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
        vendor_id = current_user.user_id
        
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


@router.get("/analytics")
async def get_vendor_analytics(current_user: TokenData = Depends(require_vendor)):
    """Get vendor analytics for dashboard"""
    try:
        vendor_id = current_user.user_id
        
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
        services_response = supabase.table("services").select("id", count="exact").eq("salon_id", salon_id).eq("is_active", True).execute()
        staff_response = supabase.table("salon_staff").select("id", count="exact").eq("salon_id", salon_id).eq("is_active", True).execute()
        bookings_response = supabase.table("bookings").select("id, total_amount", count="exact").eq("salon_id", salon_id).execute()
        pending_response = supabase.table("bookings").select("id", count="exact").eq("salon_id", salon_id).eq("status", "pending").execute()
        
        # Calculate total revenue from completed bookings
        completed_bookings = supabase.table("bookings").select("total_amount").eq("salon_id", salon_id).eq("status", "completed").execute()
        total_revenue = sum([b.get("total_amount", 0) for b in completed_bookings.data]) if completed_bookings.data else 0
        
        return {
            "total_bookings": bookings_response.count if bookings_response else 0,
            "total_revenue": total_revenue,
            "active_services": services_response.count if services_response else 0,
            "total_staff": staff_response.count if staff_response else 0,
            "average_rating": salon.get("average_rating", 0.0),
            "pending_bookings": pending_response.count if pending_response else 0
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch vendor analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch vendor analytics"
        )

