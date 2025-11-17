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
    config_key: str
    config_value: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SystemConfigListResponse(BaseModel):
    configs: List[SystemConfigResponse]
    total: int