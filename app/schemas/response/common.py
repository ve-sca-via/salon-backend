"""
Response Pydantic schemas for API endpoints
All response models should be defined here for consistency
"""
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


# =====================================================
# COMMON RESPONSE SCHEMAS
# =====================================================

class SuccessResponse(BaseModel):
    success: bool = True
    message: str
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    errors: Optional[List[str]] = None
    error_code: Optional[str] = None


class ErrorDetail(BaseModel):
    field: str
    message: str


class ValidationErrorResponse(BaseModel):
    success: bool = False
    message: str = "Validation failed"
    errors: List[ErrorDetail]
    error_code: str = "VALIDATION_ERROR"