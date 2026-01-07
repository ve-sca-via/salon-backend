"""
Response Pydantic schemas for location endpoints
All location response models should be defined here for consistency
"""
from pydantic import BaseModel
from typing import List, Dict, Any


# =====================================================
# LOCATION RESPONSE SCHEMAS
# =====================================================

class GeocodeResponse(BaseModel):
    """Response containing geocoded coordinates"""
    latitude: float
    longitude: float
    address: str


class NearbySalonsResponse(BaseModel):
    """Response containing nearby salons"""
    salons: List[Dict[str, Any]]
    count: int
    query: Dict[str, Any]