"""
Vendor API Endpoints
Handles vendor registration completion, salon management, services, staff, and bookings
"""
from fastapi import APIRouter, HTTPException, Depends, status, Body
from typing import List, Optional
from supabase import Client

from app.core.config import settings
from app.core.auth import (
    require_vendor,
    TokenData,
    get_current_user_id
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
    CompleteRegistrationRequest,
    CompleteRegistrationResponse,
    SalonResponse,
    VendorDashboardResponse,
    VendorAnalyticsResponse
)
from app.core.database import get_db_client
from app.services.vendor_service import VendorService

router = APIRouter(prefix="/vendors", tags=["Vendor Management"])

# DEPENDENCY INJECTION
# =====================================================

def get_vendor_service(db: Client = Depends(get_db_client)) -> VendorService:
    """
    Dependency injection for VendorService.
    
    Allows for easy mocking in tests and follows SOLID principles.
    """
    return VendorService(db_client=db)



# =====================================================
# REGISTRATION COMPLETION
# =====================================================

@router.post("/complete-registration", response_model=CompleteRegistrationResponse)
async def complete_registration(
    request: CompleteRegistrationRequest,
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Complete vendor registration after admin approval
    - Verify token
    - Create auth user
    - Create profile
    - Link to salon
    """
    return await vendor_service.complete_registration(
        token=request.token,
        full_name=request.full_name,
        password=request.password,
        confirm_password=request.confirm_password
    )
# =====================================================
# PAYMENT PROCESSING (DEMO)
# =====================================================

@router.post("/process-payment", response_model=SuccessResponse)
async def process_payment(
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Process vendor payment and activate salon (DEMO MODE)
    In production, this would integrate with actual payment gateway
    """
    vendor_id = current_user.user_id
    
    # Process payment through service
    payment_result = await vendor_service.process_vendor_payment(vendor_id)
    
    return {
        "success": True,
        "message": "Payment processed successfully! Your salon is now active.",
        "data": payment_result
    }


# =====================================================
# SALON MANAGEMENT
# =====================================================

@router.get("/salon", response_model=SalonResponse)
async def get_own_salon(
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Get own salon details.
    
    Returns complete salon information including verification status and subscription.
    """
    return await vendor_service.get_vendor_salon(vendor_id=current_user.user_id)


@router.put("/salon", response_model=SalonResponse)
async def update_own_salon(
    update: SalonUpdate,
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Update own salon details.
    
    Allows updating salon information like name, address, contact details, etc.
    """
    return await vendor_service.update_vendor_salon(
        vendor_id=current_user.user_id,
        update=update
    )


# =====================================================
# SERVICE MANAGEMENT
# =====================================================

@router.get("/service-categories", operation_id="vendor_get_service_categories")
async def get_service_categories(
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """Get all active service categories"""
    categories = await vendor_service.get_service_categories()
    
    return {
        "success": True,
        "data": categories
    }


@router.get("/services", response_model=List[ServiceResponse])
async def get_own_services(
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Get all services for own salon.
    
    Returns services with category details, ordered by creation date (newest first).
    """
    return await vendor_service.get_services(vendor_id=current_user.user_id)


@router.post("/services", response_model=ServiceResponse)
async def create_service(
    service: ServiceCreate,
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Create new service for vendor's salon.
    
    **Required Fields:**
    - name: Service name (2-255 chars)
    - duration_minutes: Duration in minutes (> 0)
    - price: Price (>= 0)
    
    **Optional Fields:**
    - description: Service description
    - category_id: Service category UUID (recommended for category grouping)
    - image_url: Service image URL
    
    **Note:** category_id is optional but highly recommended.
    Services without categories won't appear in category-grouped displays.
    """
    return await vendor_service.create_service(
        vendor_id=current_user.user_id,
        service=service
    )


@router.put("/services/{service_id}", response_model=ServiceResponse)
async def update_service(
    service_id: str,
    update: ServiceUpdate,
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Update existing service.
    
    **Updatable Fields:**
    - name: Service name
    - description: Service description
    - duration_minutes: Duration
    - price: Price
    - category_id: Service category UUID
    - image_url: Image URL
    - is_active: Active status
    - available_for_booking: Booking availability
    
    **Note:** All fields are optional. Only provided fields will be updated.
    """
    return await vendor_service.update_service(
        vendor_id=current_user.user_id,
        service_id=service_id,
        update=update
    )


@router.delete("/services/{service_id}", response_model=SuccessResponse)
async def delete_service(
    service_id: str,
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Delete service.
    
    Returns success message on successful deletion.
    """
    return await vendor_service.delete_service(
        vendor_id=current_user.user_id,
        service_id=service_id
    )


# =====================================================
# STAFF MANAGEMENT
# =====================================================

@router.get("/staff", response_model=List[SalonStaffResponse])
async def get_own_staff(
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Get all staff for own salon.
    
    Returns staff members ordered by creation date (newest first).
    """
    return await vendor_service.get_staff(vendor_id=current_user.user_id)


@router.post("/staff", response_model=SalonStaffResponse)
async def create_staff(
    staff: SalonStaffCreate,
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Add new staff member to your salon.
    
    Automatically associates staff with your salon.
    """
    return await vendor_service.create_staff(
        vendor_id=current_user.user_id,
        staff=staff
    )


@router.put("/staff/{staff_id}", response_model=SalonStaffResponse)
async def update_staff(
    staff_id: str,
    update: SalonStaffUpdate,
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Update staff member details.
    
    Can update name, role, phone, availability, etc.
    """
    return await vendor_service.update_staff(
        vendor_id=current_user.user_id,
        staff_id=staff_id,
        update=update
    )


@router.delete("/staff/{staff_id}", response_model=SuccessResponse)
async def delete_staff(
    staff_id: str,
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Delete staff member.
    
    Returns success message on successful deletion.
    """
    return await vendor_service.delete_staff(
        vendor_id=current_user.user_id,
        staff_id=staff_id
    )


# =====================================================
# BOOKINGS VIEW
# =====================================================

@router.get("/bookings", response_model=List[BookingResponse], operation_id="vendor_get_salon_bookings")
async def get_salon_bookings(
    status_filter: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Get all bookings for own salon.
    
    Supports filtering by status, date range, and pagination.
    """
    return await vendor_service.get_salon_bookings(
        vendor_id=current_user.user_id,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset
    )


@router.put("/bookings/{booking_id}/status", response_model=SuccessResponse, operation_id="vendor_update_booking_status")
async def update_booking_status(
    booking_id: str,
    new_status: str,
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Update booking status (confirm, complete, no-show).
    
    Valid statuses: confirmed, completed, no_show
    """
    return await vendor_service.update_booking_status(
        vendor_id=current_user.user_id,
        booking_id=booking_id,
        new_status=new_status
    )


# =====================================================
# DASHBOARD
# =====================================================

@router.get("/dashboard", response_model=VendorDashboardResponse)
async def get_vendor_dashboard(
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Get vendor dashboard statistics.
    
    Returns salon info, service counts, booking stats, and ratings.
    """
    return await vendor_service.get_dashboard_stats(vendor_id=current_user.user_id)


@router.get("/analytics", response_model=VendorAnalyticsResponse)
async def get_vendor_analytics(
    current_user: TokenData = Depends(require_vendor),
    vendor_service: VendorService = Depends(get_vendor_service)
):
    """
    Get vendor analytics for dashboard.
    
    Returns bookings, revenue, active services, staff, and ratings.
    """
    return await vendor_service.get_analytics(vendor_id=current_user.user_id)

