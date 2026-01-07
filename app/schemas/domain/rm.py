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
    """RM-specific fields only. User data comes from profiles table."""
    assigned_territories: Optional[List[str]] = None
    employee_id: Optional[str] = None
    total_salons_added: Optional[int] = 0
    total_approved_salons: Optional[int] = 0
    joining_date: Optional[str] = None
    manager_notes: Optional[str] = None

class RMProfileCreate(BaseModel):
    """Create RM profile - user data should already exist in profiles table"""
    assigned_territories: Optional[List[str]] = None
    employee_id: Optional[str] = None

class RMProfileResponse(RMProfileBase, TimestampMixin):
    """RM profile response with user profile joined"""
    id: str
    performance_score: int
    profiles: Optional[ProfileResponse] = Field(None, description="User profile data (name, email, phone, etc)")
    
    class Config:
        from_attributes = True

class RMScoreHistoryResponse(BaseModel):
    id: str
    rm_id: str
    action: str
    points: int
    description: Optional[str] = None
    created_at: datetime