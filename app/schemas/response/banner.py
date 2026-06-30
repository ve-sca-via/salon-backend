"""
Response Pydantic schemas for Banner endpoints.
Defines the response contracts for the carousel banner API.
"""
from typing import List, Optional

from pydantic import BaseModel


class BannerResponse(BaseModel):
    """Single banner response."""
    success: bool = True
    banner: dict


class BannerListResponse(BaseModel):
    """Banner list response."""
    success: bool = True
    banners: List[dict]
    count: int


class BannerOperationResponse(BaseModel):
    """Generic create/update/reorder acknowledgement."""
    success: bool = True
    message: str
    banner: Optional[dict] = None


class BannerDeleteResponse(BaseModel):
    """Banner deletion response."""
    success: bool = True
    message: str
    banner_id: str
