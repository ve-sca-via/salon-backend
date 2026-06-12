"""
Career Applications API
Handles job application submissions for RM and other positions
"""
from fastapi import APIRouter, UploadFile, File, Form, Depends
from typing import Optional
from pydantic import EmailStr
import logging

from app.core.database import get_db_client
from app.core.auth import require_admin, TokenData
from app.services.career_service import CareerService
from app.schemas import (
    CareerApplicationResponse,
    ApplicationStatusUpdate,
)
from app.schemas.response.career import CareerApplicationUpdateResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# =====================================================
# DEPENDENCY INJECTION
# =====================================================

def get_career_service(db=Depends(get_db_client)) -> CareerService:
    """Dependency injection for CareerService"""
    return CareerService(db_client=db)

# =====================================================
# API ENDPOINTS
# =====================================================

@router.post("/apply", response_model=CareerApplicationResponse)
async def submit_career_application(
    # Personal Information
    full_name: str = Form(...),
    email: EmailStr = Form(...),
    phone: str = Form(...),
    age: Optional[int] = Form(None),
    permanent_address: Optional[str] = Form(None),
    current_address: Optional[str] = Form(None),

    # Job Details
    position: str = Form("Relationship Manager"),
    experience_years: int = Form(0, ge=0, le=50),

    # Educational Background
    highest_qualification: Optional[str] = Form(None),

    # Additional Info
    cover_letter: Optional[str] = Form(None),

    # Required Documents
    resume: UploadFile = File(...),
    aadhaar_card: UploadFile = File(...),
    photo: UploadFile = File(...),

    # Dependency Injection
    career_service: CareerService = Depends(get_career_service)
):
    """
    Submit a career application for RM or other positions

    Accepts:
    - Personal and job details as form fields
    - Required documents: resume, aadhaar, photo

    Returns:
    - Application ID, application number, and confirmation message
    """
    # Organize data into logical groups
    personal_info = {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "age": age,
        "permanent_address": permanent_address,
        "current_address": current_address,
    }

    job_details = {
        "position": position,
        "experience_years": experience_years,
    }

    education = {
        "highest_qualification": highest_qualification,
    }

    additional_info = {
        "cover_letter": cover_letter,
    }

    required_documents = {
        "resume": resume,
        "aadhaar_card": aadhaar_card,
        "photo": photo,
    }

    # Delegate to service layer
    result = await career_service.submit_application(
        personal_info=personal_info,
        job_details=job_details,
        education=education,
        additional_info=additional_info,
        required_documents=required_documents,
    )

    return CareerApplicationResponse(**result)


@router.get("/applications")
async def get_career_applications(
    status: Optional[str] = None,
    position: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    admin: TokenData = Depends(require_admin),
    career_service: CareerService = Depends(get_career_service)
):
    """
    Get all career applications (Admin only)
    
    Requires: Admin authentication
    
    Query params:
    - status: Filter by status (pending, under_review, etc.)
    - position: Filter by position
    - search: Search name, email, phone, application number, or city
    - skip: Pagination offset
    - limit: Results per page
    """
    return career_service.get_applications(
        status_filter=status,
        position_filter=position,
        search=search,
        skip=skip,
        limit=limit
    )


@router.get("/applications/{application_id}")
async def get_career_application(
    application_id: str,
    admin: TokenData = Depends(require_admin),
    career_service: CareerService = Depends(get_career_service)
):
    """
    Get a specific career application by ID (Admin only)
    
    Requires: Admin authentication
    """
    return career_service.get_application_by_id(application_id)


@router.patch("/applications/{application_id}", response_model=CareerApplicationUpdateResponse)
async def update_career_application_status(
    application_id: str,
    update_data: ApplicationStatusUpdate,
    admin: TokenData = Depends(require_admin),
    career_service: CareerService = Depends(get_career_service)
):
    """
    Update career application status (Admin only)
    
    Requires: Admin authentication
    
    Can update:
    - status
    - admin_notes
    - rejection_reason
    - interview details
    """
    application = await career_service.update_application_status(
        application_id=application_id,
        new_status=update_data.status,
        admin_notes=update_data.admin_notes,
        rejection_reason=update_data.rejection_reason,
        interview_scheduled_at=update_data.interview_scheduled_at,
        interview_location=update_data.interview_location,
        admin_user_id=admin.user_id
    )
    
    return CareerApplicationUpdateResponse(
        message="Application updated successfully",
        application=application
    )


@router.get("/applications/{application_id}/download/{document_type}")
async def download_document(
    application_id: str,
    document_type: str,
    admin: TokenData = Depends(require_admin),
    career_service: CareerService = Depends(get_career_service)
):
    """
    Download a specific document from career application (Admin only)
    
    Requires: Admin authentication

    document_type: resume, aadhaar_card, photo
    """
    download_url = career_service.get_document_download_url(
        application_id=application_id,
        document_type=document_type,
        admin_user_id=admin.user_id
    )
    
    return {"download_url": download_url}
