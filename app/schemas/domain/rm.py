"""
Domain models for Relationship Manager entities
Core business entities for RM management
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from .user import TimestampMixin, ProfileResponse


# =====================================================
# RM DOMAIN MODELS
# =====================================================

class RMProfileBase(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    phone: str = Field(..., max_length=20)
    email: EmailStr
    assigned_territories: Optional[List[str]] = None

class RMProfileCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    phone: str = Field(..., max_length=20)
    assigned_territories: Optional[List[str]] = None

class RMProfileResponse(RMProfileBase, TimestampMixin):
    id: str
    performance_score: int
    is_active: bool
    profile: Optional[ProfileResponse] = None

class RMScoreHistoryResponse(BaseModel):
    id: str
    rm_id: str
    action: str
    points: int
    description: Optional[str] = None
    created_at: datetime