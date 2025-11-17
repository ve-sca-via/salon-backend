"""
Response Pydantic schemas for career endpoints
All career response models should be defined here for consistency
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# =====================================================
# CAREER RESPONSE SCHEMAS
# =====================================================

class CareerApplicationResponse(BaseModel):
    """Response after successful career application submission"""
    id: str
    message: str
    application_number: str