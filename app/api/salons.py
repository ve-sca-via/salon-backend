"""
Modern Salon API Endpoints using Service Layer

These endpoints leverage:
- Service Layer Pattern (Business logic separated)
- Dependency Injection (Testable, SOLID)
- PostGIS functions for efficient queries
- Clean Architecture principles
"""

from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from typing import Optional, List
from decimal import Decimal
from supabase import Client

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import require_admin, TokenData
from app.services.salon_service import SalonService
from app.schemas import (
    PublicSalonsResponse,
    SalonDetailResponse,
    SalonServicesResponse,
    SalonStaffListResponse,
    AvailableSlotsResponse,
    NearbySalonsResponse,
    SearchSalonsResponse,
    SalonResponse,
    SuccessResponse,
    PublicConfigResponse,
    CommissionConfigResponse,
    PopularCitiesResponse
)

router = APIRouter(prefix="/salons", tags=["salons"])


# ========================================
# DEPENDENCY INJECTION
# ========================================

def get_salon_service(db: Client = Depends(get_db_client)) -> SalonService:
    """
    Dependency injection for SalonService.
    
    Allows for easy mocking in tests and follows SOLID principles.
    """
    return SalonService(db_client=db)


# ========================================
# GET ENDPOINTS
# ========================================

@router.get("/public", response_model=PublicSalonsResponse)
async def get_public_salons(
    city: Optional[str] = Query(None, description="Filter by city name"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    salon_service: SalonService = Depends(get_salon_service)
):
    """
    Get all public salons (active, verified, and registration fee paid).
    
    This endpoint returns only salons that are:
    - is_active = true (salon is operational)
    - is_verified = true (admin approved)
    - registration_fee_paid = true (payment completed)
    
    **Use Cases:**
    - Public salon listing page
    - Customer browsing salons
    - Marketplace display
    
    **Filters:**
    - city: Optional city filter
    - limit: Results per page (1-100)
    - offset: Pagination offset
    
    **Returns:**
    - salons: Array of salon objects
    - count: Number of results returned
    - offset: Current offset
    - limit: Current limit
    """
    salons = await salon_service.get_public_salons(
        limit=limit,
        offset=offset,
        city=city
    )
    
    return {
        "salons": salons,
        "count": len(salons),
        "offset": offset,
        "limit": limit
    }


@router.get("/popular-cities", response_model=PopularCitiesResponse)
async def get_popular_cities(
    limit: int = Query(8, ge=1, le=20, description="Number of cities to return"),
    db: Client = Depends(get_db_client)
):
    """
    Get top cities by salon count (aggregated at database level).
    
    **Performance:**
    - Uses database-level aggregation (efficient for large datasets)
    - Returns only aggregated counts, not full salon data
    - Case-insensitive city matching (Mumbai = mumbai = MUMBAI)
    - Automatic whitespace trimming
    
    **Use Cases:**
    - Homepage popular locations section
    - City filter dropdowns
    - Analytics dashboards
    
    **Only includes salons that are:**
    - is_active = true
    - is_verified = true
    - registration_fee_paid = true
    
    **Returns:**
    - cities: Array of {city: string, salon_count: int}
    - total: Number of cities returned
    """
    # Call database function for efficient aggregation
    response = db.rpc('get_popular_cities', {'result_limit': limit}).execute()
    
    cities = response.data if response.data else []
    
    return {
        "cities": cities,
        "total": len(cities)
    }


@router.get("/", response_model=PublicSalonsResponse, operation_id="public_get_salons")
async def get_salons(
    status: Optional[str] = Query(None, description="Filter by status: 'approved' or 'pending'"),
    city: Optional[str] = Query(None, description="Filter by city"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    salon_service: SalonService = Depends(get_salon_service)
):
    """
    Get salons with optional status filter.
    
    **Status Options:**
    - approved: Verified and payment completed salons
    - pending: Salons awaiting admin approval
    - none: Returns approved salons by default
    
    **Note:** 
    This endpoint may be protected by RLS policies depending on user role.
    Public users see only approved salons.
    Admins can see pending salons.
    """
    if status == "approved" or not status:
        salons = await salon_service.get_approved_salons(limit, offset)
    elif status == "pending":
        # This should be protected by auth middleware for admin-only access
        salons = await salon_service.get_pending_verification_salons(limit)
    else:
        raise HTTPException(status_code=400, detail="Invalid status. Use 'approved' or 'pending'")
    
    return {
        "salons": salons,
        "count": len(salons),
        "offset": offset,
        "limit": limit
    }


@router.get("/{salon_id}", response_model=SalonDetailResponse)
async def get_salon(
    salon_id: str,
    include_services: bool = Query(False, description="Include salon services"),
    include_staff: bool = Query(False, description="Include staff members"),
    salon_service: SalonService = Depends(get_salon_service)
):
    """
    Get single salon by ID (UUID).
    
    Returns detailed salon information including:
    - Basic salon info (name, address, contact, images)
    - Business hours
    - Average rating and review count
    - Optional: Services list
    - Optional: Staff members
    
    **Visibility:**
    Only returns salons that are:
    - is_active = true
    - is_verified = true
    - registration_fee_paid = true
    
    **Parameters:**
    - salon_id: Salon UUID
    - include_services: Include full services list (default: false)
    - include_staff: Include staff members (default: false)
    
    **Use Cases:**
    - Salon detail page (public view)
    - Booking flow (get salon info before booking)
    - Service selection (with include_services=true)
    
    **Returns:**
    - salon: Complete salon object
    - services: Array (if include_services=true)
    - staff: Array (if include_staff=true)
    """
    # Use service layer to get salon with optional relations
    salon_data = await salon_service.get_salon(
        salon_id=salon_id,
        include_services=include_services,
        include_staff=include_staff
    )
    
    # Service layer will raise ValueError if not found
    # Check if salon is publicly visible
    if not (salon_data.get('is_active') and salon_data.get('is_verified') and salon_data.get('registration_fee_paid')):
        raise HTTPException(
            status_code=404, 
            detail="Salon not available. It may be inactive, unverified, or payment pending."
        )
    
    # Extract services and staff from the salon data if present
    services = salon_data.pop('services', None) if include_services else None
    staff = salon_data.pop('salon_staff', None) if include_staff else None
    
    return {
        "salon": salon_data,
        "services": services,
        "staff": staff
    }


@router.get("/{salon_id}/services", response_model=SalonServicesResponse)
async def get_salon_services(
    salon_id: str,
    salon_service: SalonService = Depends(get_salon_service)
):
    """
    Get all services for a specific salon.
    
    Returns services grouped by category with pricing and duration.
    Includes category information (name, icon_url) via join.
    
    **Use Cases:**
    - Salon detail page service listing
    - Service selection for booking
    - Service browsing
    
    **Returns:**
    - services: Array of service objects with category info
    - count: Total number of services
    """
    # Get services through service layer
    services = await salon_service.get_salon_services(salon_id)
    
    return {
        "services": services,
        "count": len(services)
    }


@router.get("/{salon_id}/staff", response_model=SalonStaffListResponse)
async def get_salon_staff(
    salon_id: str,
    salon_service: SalonService = Depends(get_salon_service)
):
    """
    Get all staff members for a specific salon.
    
    **Use Cases:**
    - Staff selection during booking
    - Salon detail page staff display
    
    **Returns:**
    - staff: Array of staff member objects
    - count: Total number of staff
    """
    # Get staff through service layer
    staff = await salon_service.get_salon_staff(salon_id)
    
    return {
        "staff": staff,
        "count": len(staff)
    }


@router.get("/{salon_id}/available-slots", response_model=AvailableSlotsResponse)
async def get_available_slots(
    salon_id: str,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    service_ids: Optional[str] = Query(None, description="Comma-separated service IDs"),
    salon_service: SalonService = Depends(get_salon_service),
    db = Depends(get_db_client)
):
    """
    Get available time slots for booking.
    
    Calculates available slots based on:
    - Salon business hours for the given date
    - Existing bookings
    - Service duration
    - Staff availability
    
    **Parameters:**
    - salon_id: Salon UUID
    - date: Booking date (YYYY-MM-DD)
    - service_ids: Optional comma-separated service IDs for duration calculation
    
    **Returns:**
    - slots: Array of available time slots
    - date: Echo of requested date
    """
    # Verify salon exists and is public
    salon = await salon_service.get_salon(salon_id)
    
    if not (salon.get('is_active') and salon.get('is_verified') and salon.get('registration_fee_paid')):
        raise HTTPException(status_code=404, detail="Salon not available")
    
    # Parse service IDs if provided
    service_id_list = service_ids.split(',') if service_ids else []
    
    # Calculate total duration if services provided
    total_duration = 0
    if service_id_list:
        from app.services.vendor_service import VendorService
        vendor_service = VendorService(db_client=db)
        for service_id in service_id_list:
            service = await vendor_service.get_service(service_id.strip())
            if service and service.get('is_active'):
                total_duration += service.get('duration_minutes', 60)  # Default 60 minutes
    else:
        total_duration = 60  # Default duration if no services specified
    
    # Get existing bookings for this date
    try:
        bookings_result = await db.table('bookings').select('booking_time, duration_minutes, status').eq('salon_id', salon_id).eq('booking_date', date).neq('status', 'cancelled').execute()
        existing_bookings = bookings_result.data
    except Exception as e:
        logger.warning(f"Could not fetch existing bookings: {e}")
        existing_bookings = []
    
    # Parse business hours
    opening_time = salon.get('opening_time')
    closing_time = salon.get('closing_time')
    
    if not opening_time or not closing_time:
        # Default business hours if not set
        opening_time = "09:00:00"
        closing_time = "18:00:00"
    
    # Generate available slots (1-hour intervals by default)
    from datetime import datetime, timedelta
    slots = []
    
    try:
        opening = datetime.strptime(opening_time, "%H:%M:%S").time()
        closing = datetime.strptime(closing_time, "%H:%M:%S").time()
        
        current = datetime.combine(datetime.today(), opening)
        closing_datetime = datetime.combine(datetime.today(), closing)
        
        while current + timedelta(minutes=total_duration) <= closing_datetime:
            slot_time = current.time()
            slot_str = slot_time.strftime("%I:%M %p")
            
            # Check if this slot conflicts with existing bookings
            conflict = False
            slot_end = current + timedelta(minutes=total_duration)
            
            for booking in existing_bookings:
                booking_time = datetime.strptime(booking['booking_time'], "%H:%M:%S").time()
                booking_start = datetime.combine(datetime.today(), booking_time)
                booking_end = booking_start + timedelta(minutes=booking['duration_minutes'])
                
                # Check for overlap
                if (current < booking_end and slot_end > booking_start):
                    conflict = True
                    break
            
            if not conflict:
                slots.append(slot_str)
            
            # Move to next slot (1 hour intervals)
            current += timedelta(hours=1)
            
    except Exception as e:
        logger.error(f"Error calculating slots: {e}")
        # Fallback to sample slots
        slots = [
            "09:00 AM", "10:00 AM", "11:00 AM", 
            "02:00 PM", "03:00 PM", "04:00 PM"
        ]
    
    return {
        "salon_id": salon_id,
        "date": date,
        "available_slots": slots
    }


# ========================================
# NEARBY & SEARCH
# ========================================

@router.get("/search/nearby", response_model=NearbySalonsResponse, operation_id="public_get_nearby_salons")
async def get_nearby_salons(
    lat: float = Query(..., description="User's latitude"),
    lon: float = Query(..., description="User's longitude"),
    radius: float = Query(10.0, ge=0.5, le=50, description="Search radius in kilometers"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
    q: Optional[str] = Query(None, description="Optional search term"),
    salon_service: SalonService = Depends(get_salon_service)
):
    """
    Get nearby salons using PostGIS spatial queries.
    
    **Uses:**
    - PostGIS ST_Distance for accurate distance calculation
    - Database-level filtering for performance
    - Only returns active, verified, paid salons
    
    **Parameters:**
    - lat: User's current latitude (required)
    - lon: User's current longitude (required)
    - radius: Search radius in kilometers (0.5-50 km, default: 10)
    - limit: Maximum number of results (1-100, default: 50)
    - q: Optional search term to filter by salon name
    
    **Returns:**
    - salons: Array with distance_km field added
    - count: Number of results
    - query: Echo of search parameters
    """
    from app.services.salon_service import NearbySearchParams, SalonSearchParams
    
    # Build search params
    filters = None
    if q:
        filters = SalonSearchParams(search_term=q)
    
    params = NearbySearchParams(
        latitude=lat,
        longitude=lon,
        radius_km=radius,
        max_results=limit,
        filters=filters
    )
    
    salons = await salon_service.get_nearby_salons(params)
    
    return {
        "salons": salons,
        "count": len(salons),
        "query": {
            "lat": lat,
            "lon": lon,
            "radius": radius,
            "limit": limit,
            "q": q
        }
    }


@router.get("/search/query", response_model=SearchSalonsResponse, operation_id="public_search_salons")
async def search_salons(
    q: Optional[str] = Query(None, description="Search term for salon name"),
    city: Optional[str] = Query(None, description="Filter by city"),
    state: Optional[str] = Query(None, description="Filter by state"),
    service_type: Optional[str] = Query(None, description="Filter by service type"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
    salon_service: SalonService = Depends(get_salon_service)
):
    """
    Search salons by text query and filters.
    
    **Search Criteria:**
    - Only active, verified, and paid salons
    - Text search in business_name field (case-insensitive)
    - Multiple filters can be combined
    
    **Parameters:**
    - q: Search term (searches in salon name)
    - city: Filter by city name (exact match)
    - state: Filter by state name
    - service_type: Filter by business type (salon, spa, etc.)
    - limit: Maximum results (1-100)
    
    **Examples:**
    - Search: `/search/query?q=glamour`
    - Filter: `/search/query?city=Aligarh`
    - Combined: `/search/query?q=spa&city=Mumbai&limit=20`
    
    **Returns:**
    - salons: Array of matching salons
    - count: Number of results
    - query: Echo of search term
    """
    salons = await salon_service.search_salons_by_query(
        query_text=q,
        city=city,
        state=state,
        service_type=service_type,
        limit=limit
    )
    
    return {
        "salons": salons,
        "query": q or "",
        "count": len(salons),
        "offset": 0,  # Not implemented in service
        "limit": limit
    }



# ========================================
# CREATE & UPDATE (Admin Only - RLS Enforced)
# ========================================

@router.post("/", response_model=SalonResponse)
async def create_salon(
    current_user: TokenData = Depends(require_admin),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    phone: str = Form(...),
    email: Optional[str] = Form(None),
    address_line1: str = Form(...),
    city: str = Form(...),
    state: str = Form(...),
    pincode: str = Form(...),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    cover_image: Optional[UploadFile] = File(None),
    owner_id: Optional[str] = Form(None),
    status: str = Form("pending")
):
    """
    Create new salon - Admin only
    
    Authorization handled in Python via require_admin dependency
    If cover_image provided, uploads to db Storage
    """
    # Prepare salon data
    salon_data = {
        "name": name,
        "description": description,
        "phone": phone,
        "email": email,
        "address_line1": address_line1,
        "city": city,
        "state": state,
        "pincode": pincode,
        "latitude": str(latitude) if latitude else None,
        "longitude": str(longitude) if longitude else None,
        "owner_id": owner_id,
        "status": status
    }
    
    # Create salon
    salon = db.create_salon(salon_data)
    
    if not salon:
        raise HTTPException(status_code=500, detail="Failed to create salon")
    
    # Upload cover image if provided
    if cover_image:
        try:
            image_data = await cover_image.read()
            cover_url = db.upload_salon_image(
                salon_id=salon["id"],
                image_data=image_data,
                filename=f"cover.{cover_image.filename.split('.')[-1]}"
            )
            
            # Update salon with cover image URL
            salon = db.update_salon(salon["id"], {"cover_image": cover_url})
        except Exception as img_error:
            print(f"Warning: Failed to upload cover image: {img_error}")
            # Don't fail the entire request if image upload fails
    
    return salon


@router.patch("/{salon_id}", response_model=SalonResponse)
async def update_salon(
    salon_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    phone: Optional[str] = None,
    # ... other optional fields
):
    """
    Update salon
    
    RLS ensures only salon owner or admin can update
    """
    updates = {}
    if name is not None:
        updates["name"] = name
    if description is not None:
        updates["description"] = description
    if phone is not None:
        updates["phone"] = phone
    
    salon = db.update_salon(salon_id, updates)
    
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found")
    
    return salon


@router.post("/{salon_id}/approve", response_model=SuccessResponse)
async def approve_salon(
    salon_id: int,
    admin: TokenData = Depends(require_admin),
    reviewed_by: str = Form(...),
    rejection_reason: Optional[str] = Form(None)
):
    """
    Approve or reject salon - Admin only
    
    Authorization handled in Python via require_admin dependency
    """
    success = db.approve_salon(
        salon_id=salon_id,
        reviewed_by=reviewed_by,
        rejection_reason=rejection_reason
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to approve salon")
    
    return {"success": True, "message": "Salon approved" if not rejection_reason else "Salon rejected"}


# ========================================
# IMAGE OPERATIONS
# ========================================

@router.post("/{salon_id}/images", response_model=SuccessResponse, operation_id="salons_upload_salon_image")
async def upload_salon_image(
    salon_id: int,
    image: UploadFile = File(...),
    image_type: str = Form("gallery")
):
    """
    Upload image for salon to db Storage
    
    RLS ensures only salon owner or admin can upload
    """
    image_data = await image.read()
    
    # Upload to db Storage
    url = db.upload_salon_image(
        salon_id=salon_id,
        image_data=image_data,
        filename=f"{image_type}_{image.filename}",
        content_type=image.content_type
    )
    
    return {
        "success": True,
        "message": "Image uploaded successfully",
        "data": {"url": url}
    }


# ========================================
# PUBLIC SYSTEM CONFIG
# ========================================

@router.get("/config/public", response_model=PublicConfigResponse)
async def get_public_configs(db: Client = Depends(get_db_client)):
    """
    Get public system configurations (non-sensitive values)
    
    Returns configuration values that are safe to expose to frontend:
    - Fee percentages
    - Booking limits
    - Cancellation policies
    
    Does NOT return sensitive values like API keys
    """
    from app.services.config_service import ConfigService
    
    try:
        config_service = ConfigService(db_client=db)
        
        # Define which configs are safe to expose publicly
        public_config_keys = [
            "convenience_fee_percentage",
            "platform_commission_percentage",
            "cancellation_window_hours",
            "max_booking_advance_days"
        ]
        
        # Fetch all configs and filter to public ones
        all_configs = await config_service.get_all_configs()
        
        public_configs = {}
        for config in all_configs:
            if config.get("config_key") in public_config_keys and config.get("is_active"):
                key = config["config_key"]
                value = config["config_value"]
                
                # Convert to appropriate type
                if config.get("config_type") == "number":
                    try:
                        value = float(value) if '.' in str(value) else int(value)
                    except (ValueError, TypeError):
                        pass
                elif config.get("config_type") == "boolean":
                    value = value in [True, "true", "True", "1", 1]
                
                public_configs[key] = value
        
        return {
            "success": True,
            "configs": public_configs
        }
    
    except Exception as e:
        # Fail gracefully with defaults
        return {
            "success": False,
            "configs": {
                "convenience_fee_percentage": 10,
                "platform_commission_percentage": 10,
                "cancellation_window_hours": 24,
                "max_booking_advance_days": 30
            },
            "error": "Using default values"
        }


@router.get("/config/booking-fee-percentage", response_model=CommissionConfigResponse)
async def get_booking_fee_percentage(
    salon_service: SalonService = Depends(get_salon_service)
):
    """
    Get the platform commission percentage used for calculating booking fees
    
    This is a public endpoint that returns the booking fee percentage
    from system_config table
    
    DEPRECATED: Use /salons/config/public instead
    """
    commission = await salon_service.get_platform_commission_config()
    return {"commission_percentage": commission}


