from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import Salon
from typing import List, Dict
import math


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two points using Haversine formula
    Returns distance in kilometers
    """
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat / 2) ** 2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


async def get_nearby_salons(
    db: AsyncSession,
    latitude: float,
    longitude: float,
    radius_km: float = 10.0,
    limit: int = 50
) -> List[Dict]:
    """
    Get salons within specified radius, sorted by distance
    Uses bounding box for initial filter, then Haversine for precise distance
    """
    # Calculate bounding box (approximate)
    lat_delta = radius_km / 111.0  # ~111 km per degree latitude
    lon_delta = radius_km / (111.0 * math.cos(math.radians(latitude)))
    
    # Query with bounding box filter
    query = select(Salon).where(
        Salon.status == "approved",
        Salon.latitude.isnot(None),
        Salon.longitude.isnot(None),
        Salon.latitude >= latitude - lat_delta,
        Salon.latitude <= latitude + lat_delta,
        Salon.longitude >= longitude - lon_delta,
        Salon.longitude <= longitude + lon_delta
    )
    
    result = await db.execute(query)
    salons = result.scalars().all()
    
    # Calculate precise distance and filter by radius
    salons_with_distance = []
    for salon in salons:
        distance = haversine_distance(
            latitude, longitude,
            float(salon.latitude), float(salon.longitude)
        )
        
        if distance <= radius_km:
            salon_dict = {
                "id": salon.id,
                "name": salon.name,
                "address_line1": salon.address_line1,
                "address_line2": salon.address_line2,
                "city": salon.city,
                "state": salon.state,
                "pincode": salon.pincode,
                "latitude": float(salon.latitude),
                "longitude": float(salon.longitude),
                "rating": float(salon.rating) if salon.rating else 0,
                "total_reviews": salon.total_reviews,
                "cover_image": salon.cover_image,
                "distance_km": round(distance, 2)
            }
            salons_with_distance.append(salon_dict)
    
    # Sort by distance
    salons_with_distance.sort(key=lambda x: x["distance_km"])
    
    return salons_with_distance[:limit]
