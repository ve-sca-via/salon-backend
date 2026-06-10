from fastapi import APIRouter, HTTPException, Query, Depends
from supabase import Client

from app.core.database import get_db_client
from app.services.geocoding import geocoding_service
from app.services.salon_service import SalonService, NearbySearchParams
from app.schemas import (
    NearbySalonsResponse,
)


router = APIRouter(prefix="/location", tags=["location"])


def get_salon_service(db: Client = Depends(get_db_client)) -> SalonService:
    """Dependency injection for SalonService"""
    return SalonService(db_client=db)


@router.get("/reverse-geocode")
async def reverse_geocode(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude")
):
    """
    Convert coordinates to address
    """
    address = await geocoding_service.reverse_geocode(lat, lon)

    if not address:
        raise HTTPException(status_code=404, detail="Location not found")

    return {"address": address, "latitude": lat, "longitude": lon}


@router.get("/salons/nearby", response_model=NearbySalonsResponse)
async def get_salons_nearby(
    lat: float = Query(..., description="User latitude"),
    lon: float = Query(..., description="User longitude"),
    radius: float = Query(10.0, description="Search radius in kilometers", ge=0.5, le=50),
    limit: int = Query(50, description="Maximum results", ge=1, le=100),
    salon_service: SalonService = Depends(get_salon_service)
):
    """
    Get salons near the specified location (canonical nearby-salons endpoint).

    Delegates to SalonService.get_nearby_salons, which uses the PostGIS
    `get_nearby_salons` function, excludes regular_buyer salons, and attaches
    discount flags.
    """
    salons = await salon_service.get_nearby_salons(
        NearbySearchParams(
            latitude=lat,
            longitude=lon,
            radius_km=radius,
            max_results=limit,
        )
    )

    return {
        "salons": salons,
        "count": len(salons),
        "query": {
            "latitude": lat,
            "longitude": lon,
            "radius_km": radius
        }
    }
