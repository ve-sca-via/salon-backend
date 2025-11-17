from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional
from supabase import Client

from app.core.config import settings
from app.core.database import get_db_client
from app.services.geocoding import geocoding_service
from app.schemas import (
    GeocodeRequest,
    GeocodeResponse,
    NearbySalonsResponse,
)


router = APIRouter(prefix="/api/location", tags=["location"])


@router.post("/geocode", response_model=GeocodeResponse)
async def geocode_address(request: GeocodeRequest):
    """
    Convert address to coordinates
    Keeps API key secure on backend
    """
    coordinates = await geocoding_service.geocode_address(request.address)
    
    if not coordinates:
        raise HTTPException(status_code=404, detail="Address not found")
    
    lat, lon = coordinates
    return {
        "latitude": lat,
        "longitude": lon,
        "address": request.address
    }


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
    db: Client = Depends(get_db_client)
):
    """
    Get salons near the specified location
    Uses PostGIS function for efficient distance calculation
    Much faster than Python-based Haversine calculation
    """
    # Query approved salons within radius using PostGIS
    response = db.rpc(
        'get_nearby_salons',
        {
            'user_lat': lat,
            'user_lon': lon,
            'radius_km': radius,
            'result_limit': limit
        }
    ).execute()
    
    salons = response.data if response.data else []
    
    return {
        "salons": salons,
        "count": len(salons),
        "query": {
            "latitude": lat,
            "longitude": lon,
            "radius_km": radius
        }
    }
