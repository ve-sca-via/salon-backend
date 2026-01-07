"""
Response schemas for location/city-related endpoints
"""

from pydantic import BaseModel, Field
from typing import List


class PopularCityResponse(BaseModel):
    """Single city with salon count"""
    city: str = Field(..., description="City name (normalized to lowercase)")
    salon_count: int = Field(..., description="Number of salons in this city")

    class Config:
        json_schema_extra = {
            "example": {
                "city": "mumbai",
                "salon_count": 124
            }
        }


class PopularCitiesResponse(BaseModel):
    """Response for popular cities endpoint"""
    cities: List[PopularCityResponse] = Field(..., description="List of cities sorted by salon count")
    total: int = Field(..., description="Total number of cities returned")

    class Config:
        json_schema_extra = {
            "example": {
                "cities": [
                    {"city": "mumbai", "salon_count": 124},
                    {"city": "delhi", "salon_count": 98},
                    {"city": "bangalore", "salon_count": 87}
                ],
                "total": 3
            }
        }
