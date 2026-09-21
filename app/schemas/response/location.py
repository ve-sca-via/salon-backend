"""
Response Pydantic schemas for location endpoints
All location response models should be defined here for consistency
"""
from pydantic import BaseModel
from typing import List, Dict, Any

from .vendor import SalonListResponse


# =====================================================
# LOCATION RESPONSE SCHEMAS
# =====================================================

class GeocodeResponse(BaseModel):
    """Response containing geocoded coordinates"""
    latitude: float
    longitude: float
    address: str


class NearbySalonsResponse(BaseModel):
    """
    Response containing nearby salons.

    Rows are typed as SalonListResponse so this endpoint publishes the same
    vetted public field set as the other listings — the PostGIS
    `get_nearby_salons` function selects whole salon rows (vendor_id and
    assigned_rm included), which untyped dict rows would have passed straight
    through to anonymous callers.
    """
    salons: List[SalonListResponse]
    count: int
    query: Dict[str, Any]