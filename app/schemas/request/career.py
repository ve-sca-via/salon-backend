"""
Request Pydantic schemas for career endpoints
All career request models should be defined here for consistency
"""
from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime


# =====================================================
# CAREER REQUEST SCHEMAS
# =====================================================

class ApplicationStatusUpdate(BaseModel):
    """Schema for updating application status"""
    status: Literal['pending', 'under_review', 'shortlisted', 'interview_scheduled', 'rejected', 'hired']
    admin_notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    interview_scheduled_at: Optional[datetime] = None
    interview_location: Optional[str] = None


# Additional request models used by the service layer
class PersonalInfo(BaseModel):
    full_name: str
    email: str
    phone: str  # Required - matches API and DB schema
    address: Optional[str] = None


class JobDetails(BaseModel):
    position: str
    experience_years: Optional[int] = None
    expected_salary: Optional[float] = None


class Education(BaseModel):
    highest_qualification: Optional[str] = None
    university: Optional[str] = None
    graduation_year: Optional[int] = None


class AdditionalInfo(BaseModel):
    cover_letter: Optional[str] = None
    linkedin: Optional[str] = None
    portfolio: Optional[str] = None