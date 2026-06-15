"""
Response Pydantic schemas for partner ("Partner with us") endpoints
All partner response models should be defined here for consistency
"""
from pydantic import BaseModel
from typing import Optional, Any, Dict


# =====================================================
# PARTNER RESPONSE SCHEMAS
# =====================================================

class PartnerRequestResponse(BaseModel):
    """Response after a successful partner request submission"""
    id: str
    message: str


class PartnerRequestUpdateResponse(BaseModel):
    """Response after updating a partner request (admin)"""
    message: str
    request: Dict[str, Any]  # Full partner request data
