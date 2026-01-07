"""
Response Pydantic schemas for admin endpoints
All admin response models should be defined here for consistency
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# =====================================================
# ADMIN RESPONSE SCHEMAS
# =====================================================

class SystemConfigResponse(BaseModel):
    id: str
    config_key: str
    config_value: str
    config_type: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


class SystemConfigListResponse(BaseModel):
    configs: List[SystemConfigResponse]
    total: int