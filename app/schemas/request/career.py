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