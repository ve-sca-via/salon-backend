"""
Request schemas for RM endpoints
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class RMProfileUpdate(BaseModel):
    """Update RM profile. Profile fields (name, phone, email, is_active) update profiles table.
    RM-specific fields update rm_profiles table."""
    # Profile table fields (will be routed to profiles table)
    full_name: Optional[str] = Field(None, min_length=2, max_length=255, description="Updates profiles.full_name")
    phone: Optional[str] = Field(None, max_length=20, description="Updates profiles.phone")
    email: Optional[str] = Field(None, description="Updates profiles.email")
    is_active: Optional[bool] = Field(None, description="Updates profiles.is_active")
    
    # RM-specific fields (will be routed to rm_profiles table)
    employee_id: Optional[str] = Field(None, max_length=50, description="Updates rm_profiles.employee_id - Company employee ID")
    assigned_territories: Optional[List[str]] = Field(None, description="Updates rm_profiles.assigned_territories")
    joining_date: Optional[str] = Field(None, description="Updates rm_profiles.joining_date - ISO date string (YYYY-MM-DD)")
    manager_notes: Optional[str] = Field(None, description="Updates rm_profiles.manager_notes")
