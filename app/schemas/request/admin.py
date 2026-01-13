"""
Request Pydantic schemas for admin endpoints
All admin request models should be defined here for consistency
"""
from pydantic import BaseModel, Field
from typing import Optional


# =====================================================
# ADMIN REQUEST SCHEMAS
# =====================================================

class SystemConfigCreate(BaseModel):
    config_key: str = Field(..., description="Unique configuration key")
    config_value: str = Field(..., description="Configuration value")
    config_type: str = Field(default="string", description="Type: string, number, boolean, json")
    description: Optional[str] = Field(None, description="Optional description")
    is_active: Optional[bool] = Field(default=True, description="Whether config is active")

class SystemConfigUpdate(BaseModel):
    config_value: Optional[str] = None
    config_type: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None