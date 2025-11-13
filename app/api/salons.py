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

from app.core.config import settings
from app.services.salon_service import SalonService

router = APIRouter(prefix="/salons", tags=["salons"])


# ========================================
# DEPENDENCY INJECTION
# ========================================

def get_salon_service() -> SalonService:
    """
    Dependency injection for SalonService.
    
    Allows for easy mocking in tests and follows SOLID principles.
    """
    return SalonService()


# ========================================
# GET ENDPOINTS
# ========================================

@router.get("/public")
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
    try:
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch public salons: {str(e)}")


@router.get("/")
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
    try:
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch salons: {str(e)}")


@router.get("/{salon_id}")
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
    try:
        # Use service layer to get salon with optional relations
        salon = await salon_service.get_salon(
            salon_id=salon_id,
            include_services=include_services,
            include_staff=include_staff
        )
        
        # Service layer will raise ValueError if not found
        # Check if salon is publicly visible
        if not (salon.get('is_active') and salon.get('is_verified') and salon.get('registration_fee_paid')):
            raise HTTPException(
                status_code=404, 
                detail="Salon not available. It may be inactive, unverified, or payment pending."
            )
        
        return {"salon": salon}
        
    except ValueError as e:
        # Salon not found
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch salon: {str(e)}")


@router.get("/{salon_id}/services")
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
    try:
        # Get services through service layer
        services = await salon_service.get_salon_services(salon_id)
        
        return {
            "services": services,
            "count": len(services)
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch services: {str(e)}")


@router.get("/{salon_id}/staff")
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
    try:
        # Get staff through service layer
        staff = await salon_service.get_salon_staff(salon_id)
        
        return {
            "staff": staff,
            "count": len(staff)
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch staff: {str(e)}")


@router.get("/{salon_id}/available-slots")
async def get_available_slots(
    salon_id: str,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    service_ids: Optional[str] = Query(None, description="Comma-separated service IDs"),
    salon_service: SalonService = Depends(get_salon_service)
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
    try:
        # Verify salon exists and is public
        salon = await salon_service.get_salon(salon_id)
        
        if not (salon.get('is_active') and salon.get('is_verified') and salon.get('registration_fee_paid')):
            raise HTTPException(status_code=404, detail="Salon not available")
        
        # Parse service IDs if provided
        service_id_list = service_ids.split(',') if service_ids else []
        
        # TODO: Implement slot calculation logic
        # For now, return sample slots
        slots = [
            "09:00 AM", "10:00 AM", "11:00 AM", 
            "02:00 PM", "03:00 PM", "04:00 PM"
        ]
        
        return {
            "slots": slots,
            "date": date,
            "salon_id": salon_id
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# NEARBY & SEARCH
# ========================================

@router.get("/search/nearby")
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
    try:
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
                "latitude": lat,
                "longitude": lon,
                "radius_km": radius,
                "search_term": q
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch nearby salons: {str(e)}")


@router.get("/search/query")
async def search_salons(
    q: Optional[str] = Query(None, description="Search term for salon name"),
    city: Optional[str] = Query(None, description="Filter by city"),
    state: Optional[str] = Query(None, description="Filter by state"),
    service_type: Optional[str] = Query(None, description="Filter by business type"),
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
    try:
        salons = await salon_service.search_salons_by_query(
            query_text=q,
            city=city,
            state=state,
            service_type=service_type,
            limit=limit
        )
        
        return {
            "salons": salons,
            "count": len(salons),
            "query": {
                "search_term": q,
                "city": city,
                "state": state,
                "service_type": service_type
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")



# ========================================
# CREATE & UPDATE (Admin Only - RLS Enforced)
# ========================================

@router.post("/")
async def create_salon(
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
    Create new salon
    
    RLS ensures only admins/HMR agents can create salons
    If cover_image provided, uploads to db Storage
    """
    try:
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
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{salon_id}")
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
    try:
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{salon_id}/approve")
async def approve_salon(
    salon_id: int,
    reviewed_by: str = Form(...),
    rejection_reason: Optional[str] = Form(None)
):
    """
    Approve or reject salon
    
    RLS ensures only admins can approve/reject
    """
    try:
        success = db.approve_salon(
            salon_id=salon_id,
            reviewed_by=reviewed_by,
            rejection_reason=rejection_reason
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to approve salon")
        
        return {"success": True, "message": "Salon approved" if not rejection_reason else "Salon rejected"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# IMAGE OPERATIONS
# ========================================

@router.post("/{salon_id}/images")
async def upload_salon_image(
    salon_id: int,
    image: UploadFile = File(...),
    image_type: str = Form("gallery")
):
    """
    Upload image for salon to db Storage
    
    RLS ensures only salon owner or admin can upload
    """
    try:
        image_data = await image.read()
        
        # Upload to db Storage
        url = db.upload_salon_image(
            salon_id=salon_id,
            image_data=image_data,
            filename=f"{image_type}_{image.filename}",
            content_type=image.content_type
        )
        
        return {"url": url, "message": "Image uploaded successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# SYSTEM CONFIG
# ========================================

@router.get("/config/booking-fee-percentage")
async def get_booking_fee_percentage(
    salon_service: SalonService = Depends(get_salon_service)
):
    """
    Get the platform commission percentage used for calculating booking fees
    
    This is a public endpoint that returns the booking fee percentage
    from system_config table
    """
    commission = await salon_service.get_platform_commission_config()
    return {"booking_fee_percentage": commission}

