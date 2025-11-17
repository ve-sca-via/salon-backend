"""
Request Pydantic schemas for location endpoints
All location request models should be defined here for consistency
"""
from pydantic import BaseModel


# =====================================================
# LOCATION REQUEST SCHEMAS
# =====================================================

class GeocodeRequest(BaseModel):
    """Request to geocode an address"""
    address: str