"""
Request Pydantic schemas for admin endpoints
All admin request models should be defined here for consistency
"""
from pydantic import BaseModel, Field
from typing import Optional


# =====================================================
# ADMIN REQUEST SCHEMAS
# =====================================================

class SystemConfigUpdate(BaseModel):
    config_value: str
    description: Optional[str] = None
    is_active: Optional[bool] = None