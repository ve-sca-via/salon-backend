"""
Response Pydantic schemas for Feature entitlement endpoints.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel


class FeatureMapResponse(BaseModel):
    """
    {key: status} map driving what the admin panel renders.

    For a client admin this contains ONLY entitled features — unsold ones are
    absent rather than present-and-false, so the payload never hints that a
    hidden feature exists.
    """
    success: bool = True
    features: Dict[str, str]
    is_internal: bool = False


class FeatureListResponse(BaseModel):
    """Full registry with metadata. Internal staff only."""
    success: bool = True
    features: List[dict]


class FeatureOperationResponse(BaseModel):
    """Acknowledgement for a status change."""
    success: bool = True
    message: str
    feature: Optional[dict] = None
