"""
Request schemas for RM endpoints
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class RMProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = None
    assigned_territories: Optional[List[str]] = None
    is_active: Optional[bool] = None
