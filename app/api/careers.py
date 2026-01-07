"""
Career Applications API
Handles job application submissions for RM and other positions
"""
from fastapi import APIRouter, UploadFile, File, Form, Depends
from typing import Optional, List
from pydantic import BaseModel, EmailStr
from datetime import datetime
import logging

from app.core.database import get_db_client
from app.services.career_service import CareerService
from app.schemas import (
    CareerApplicationResponse,
    ApplicationStatusUpdate,
)

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
    current_city: Optional[str] = Form(None),
    current_address: Optional[str] = Form(None),
    willing_to_relocate: bool = Form(False),
    
    # Job Details
    position: str = Form("Relationship Manager"),
    experience_years: int = Form(0),
    previous_company: Optional[str] = Form(None),
    current_salary: Optional[float] = Form(None),
    expected_salary: Optional[float] = Form(None),
    notice_period_days: Optional[int] = Form(None),
    
    # Educational Background
    highest_qualification: Optional[str] = Form(None),
    university_name: Optional[str] = Form(None),
    graduation_year: Optional[int] = Form(None),
    
    # Additional Info
    cover_letter: Optional[str] = Form(None),
    linkedin_url: Optional[str] = Form(None),
    portfolio_url: Optional[str] = Form(None),
    
    # Required Documents
    resume: UploadFile = File(...),
    aadhaar_card: UploadFile = File(...),
    pan_card: UploadFile = File(...),
    photo: UploadFile = File(...),
    address_proof: UploadFile = File(...),
    
    # Optional Documents
    educational_certificates: Optional[List[UploadFile]] = File(None),
    experience_letter: Optional[UploadFile] = File(None),
    salary_slip: Optional[UploadFile] = File(None),
    
    # Dependency Injection
    career_service: CareerService = Depends(get_career_service)
):
    """
    Submit a career application for RM or other positions
    
    Accepts:
    - Personal and job details as form fields
    - Required documents: resume, aadhaar, PAN, photo, address proof
    - Optional documents: educational certificates, experience letter, salary slip
    
    Returns:
    - Application ID, application number, and confirmation message
    """
    # Organize data into logical groups
    personal_info = {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "current_city": current_city,
        "current_address": current_address,
        "willing_to_relocate": willing_to_relocate
    }
    
    job_details = {
        "position": position,
        "experience_years": experience_years,
        "previous_company": previous_company,
        "current_salary": current_salary,
        "expected_salary": expected_salary,
        "notice_period_days": notice_period_days
    }
    
    education = {
        "highest_qualification": highest_qualification,
        "university_name": university_name,
        "graduation_year": graduation_year
    }
    
    additional_info = {
        "cover_letter": cover_letter,
        "linkedin_url": linkedin_url,
        "portfolio_url": portfolio_url
    }
    
    required_documents = {
        "resume": resume,
        "aadhaar_card": aadhaar_card,
        "pan_card": pan_card,
        "photo": photo,
        "address_proof": address_proof
    }
    
    optional_documents = {
        "educational_certificates": educational_certificates,
        "experience_letter": experience_letter,
        "salary_slip": salary_slip
    }
    
    # Delegate to service layer
    result = await career_service.submit_application(
        personal_info=personal_info,
        job_details=job_details,
        education=education,
        additional_info=additional_info,
        required_documents=required_documents,
        optional_documents=optional_documents
    )
    
    return CareerApplicationResponse(**result)


@router.get("/applications")
async def get_career_applications(
    status: Optional[str] = None,
    position: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    career_service: CareerService = Depends(get_career_service)
):
    """
    Get all career applications (Admin/RM only)
    
    Query params:
    - status: Filter by status (pending, under_review, etc.)
    - position: Filter by position
    - skip: Pagination offset
    - limit: Results per page
    """
    return career_service.get_applications(
        status_filter=status,
        position_filter=position,
        skip=skip,
        limit=limit
    )


@router.get("/applications/{application_id}")
async def get_career_application(
    application_id: str,
    career_service: CareerService = Depends(get_career_service)
):
    """Get a specific career application by ID (Admin/RM only)"""
    return career_service.get_application_by_id(application_id)


@router.patch("/applications/{application_id}")
async def update_career_application_status(
    application_id: str,
    update_data: ApplicationStatusUpdate,
    career_service: CareerService = Depends(get_career_service)
):
    """
    Update career application status (Admin/RM only)
    
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
        interview_location=update_data.interview_location
    )
    
    return {
        "message": "Application updated successfully",
        "application": application
    }


@router.get("/applications/{application_id}/download/{document_type}")
async def download_document(
    application_id: str,
    document_type: str,
    career_service: CareerService = Depends(get_career_service)
):
    """
    Download a specific document from career application (Admin/RM only)
    
    document_type: resume, aadhaar, pan, photo, address_proof, 
                   experience_letter, salary_slip
    """
    download_url = career_service.get_document_download_url(
        application_id=application_id,
        document_type=document_type
    )
    
    return {"download_url": download_url}
