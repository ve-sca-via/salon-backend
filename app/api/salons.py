"""
Modern Salon API Endpoints using Service Layer

These endpoints leverage:
- Service Layer Pattern (Business logic separated)
- Dependency Injection (Testable, SOLID)
- PostGIS functions for efficient queries
- Clean Architecture principles
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from supabase import Client
import logging

from app.core.database import get_db_client
from app.services.salon_service import SalonService
from app.utils.scheduling import generate_slots, parse_date
from app.schemas import (
    PublicSalonsResponse,
    SalonDetailResponse,
    SalonServicesResponse,
    AvailableSlotsResponse,
    SearchSalonsResponse,
    PublicConfigResponse,
    PopularCitiesResponse,
    FeedbackReviewCreate,
    ReviewFeedbackContextResponse,
    PublicSalonReviewsResponse,
    ReviewOperationResponse
)
from app.services.customer_service import CustomerService

logger = logging.getLogger(__name__)

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


def get_customer_service(db: Client = Depends(get_db_client)) -> CustomerService:
    """Dependency injection for public review-related customer operations."""
    return CustomerService(db_client=db)


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


@router.get("/{salon_id}", response_model=SalonDetailResponse)
async def get_salon(
    salon_id: str,
    include_services: bool = Query(False, description="Include salon services"),
    salon_service: SalonService = Depends(get_salon_service)
):
    """
    Get single salon by ID (UUID).
    
    Returns detailed salon information including:
    - Basic salon info (name, address, contact, images)
    - Business hours
    - Average rating and review count
    - Optional: Services list
    
    **Visibility:**
    Only returns salons that are:
    - is_active = true
    - is_verified = true
    - registration_fee_paid = true
    
    **Parameters:**
    - salon_id: Salon UUID
    - include_services: Include full services list (default: false)
    
    **Use Cases:**
    - Salon detail page (public view)
    - Booking flow (get salon info before booking)
    - Service selection (with include_services=true)
    
    **Returns:**
    - salon: Complete salon object
    - services: Array (if include_services=true)
    """
    # Use service layer to get salon with optional relations
    salon_data = await salon_service.get_salon(
        salon_id=salon_id,
        include_services=include_services
    )
    
    # Service layer will raise ValueError if not found
    # Check if salon is publicly visible
    if not salon_service.is_publicly_visible(salon_data):
        raise HTTPException(
            status_code=404,
            detail="Salon not available. It may be inactive, unverified, or payment pending."
        )
    
    # Regular buyers can only buy products — they don't offer salon services publicly
    if salon_data.get('salon_type') == 'regular_buyer':
        raise HTTPException(
            status_code=404,
            detail="Salon not available."
        )
    
    # Extract services from the salon data if present
    services = salon_data.pop('services', None) if include_services else None

    # Attach public coupon + discount display data (vendor + platform coupons,
    # max discount %) for the salon-detail offers carousel.
    await salon_service.enrich_salon_detail(salon_data)

    return {
        "salon": salon_data,
        "services": services
    }


@router.get("/{salon_id}/related", response_model=PublicSalonsResponse)
async def get_related_salons(
    salon_id: str,
    limit: int = Query(10, ge=1, le=20, description="Maximum number of related salons"),
    salon_service: SalonService = Depends(get_salon_service)
):
    """
    Get salons related to the given salon, for the "Related Salons" section
    shown at the bottom of the salon detail page.

    Relevance is tiered (same city → same state → any public salon), ordered by
    rating, and always excludes the source salon. Only public-visible salons are
    returned, so the same cards as the public listing can render the results.

    **Returns:**
    - salons: Array of related salon objects
    - count: Number of results returned
    """
    salons = await salon_service.get_related_salons(salon_id=salon_id, limit=limit)

    return {
        "salons": salons,
        "count": len(salons),
        "offset": 0,
        "limit": limit
    }


@router.get("/{salon_id}/reviews", response_model=PublicSalonReviewsResponse)
async def get_salon_reviews(
    salon_id: str,
    customer_service: CustomerService = Depends(get_customer_service)
):
    """Get publicly visible reviews for a salon."""
    return await customer_service.get_public_salon_reviews(salon_id)


@router.get("/{salon_id}/feedback", response_model=ReviewFeedbackContextResponse)
async def get_salon_feedback_context(
    salon_id: str,
    token: str = Query(..., description="Signed review link token"),
    customer_service: CustomerService = Depends(get_customer_service)
):
    """Validate a signed review link and return the feedback page context."""
    return await customer_service.get_feedback_context(salon_id, token)


@router.post("/{salon_id}/feedback", response_model=ReviewOperationResponse)
async def submit_salon_feedback(
    salon_id: str,
    payload: FeedbackReviewCreate,
    customer_service: CustomerService = Depends(get_customer_service)
):
    """Submit a salon review from the public feedback flow."""
    return await customer_service.submit_feedback_review(
        salon_id=salon_id,
        token=payload.token,
        rating=payload.rating,
        comment=payload.comment
    )


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
    - Service duration

    Slots are not consumed by existing bookings: a salon can serve several
    customers at the same time, so the same slot stays offered to everyone.

    
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

    if not salon_service.is_publicly_visible(salon):
        raise HTTPException(status_code=404, detail="Salon not available")
    
    # Parse the requested date (past dates yield no slots).
    try:
        on_date = parse_date(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date. Use YYYY-MM-DD.")

    # Parse service IDs if provided
    service_id_list = [s.strip() for s in service_ids.split(',') if s.strip()] if service_ids else []

    # Calculate total duration if services provided (single query, not N calls)
    total_duration = 0
    if service_id_list:
        svc_resp = db.table("services").select(
            "duration_minutes, is_active"
        ).in_("id", service_id_list).execute()
        for svc in (svc_resp.data or []):
            if svc.get("is_active"):
                total_duration += svc.get("duration_minutes") or 60  # Default 60 minutes
        if total_duration == 0:
            total_duration = 60
    else:
        total_duration = 60  # Default duration if no services specified

    # Slot generation lives in app.utils.scheduling so the public endpoint and
    # the booking-creation guard enforce identical rules: future-only (IST),
    # closed-day aware (business_hours / working_days), within working hours,
    # 30-min grid. Existing bookings do not reduce availability — a salon takes
    # multiple bookings for the same time.
    try:
        slots = generate_slots(
            salon=salon,
            on_date=on_date,
            total_duration_minutes=total_duration,
        )
    except Exception as e:
        logger.error(f"Error calculating slots for salon {salon_id} on {date}: {e}")
        slots = []

    return {
        "salon_id": salon_id,
        "date": date,
        "available_slots": slots
    }


# ========================================
# NEARBY & SEARCH
# ========================================

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
            "cancellation_window_hours",
            "max_booking_advance_days",
            "registration_fee_amount"  # Vendor registration fee
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
    
    except Exception:
        # Fail gracefully with defaults
        return {
            "success": False,
            "configs": {
                "convenience_fee_percentage": 10,
                "cancellation_window_hours": 24,
                "max_booking_advance_days": 30
            },
            "error": "Using default values"
        }





