"""
Career Service - Business Logic for Job Applications
Handles career application submissions, status updates, and queries
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
from fastapi import HTTPException, status, UploadFile
from app.core.database import get_db
from app.services.storage_service import StorageService
from app.services.email import EmailService
from app.services.activity_log_service import ActivityLogger

logger = logging.getLogger(__name__)


class CareerService:
    """
    Service for career application operations.
    Handles submission, status updates, document management, and queries.
    """
    
    VALID_STATUSES = {
        'pending', 'under_review', 'shortlisted', 
        'interview_scheduled', 'rejected', 'hired'
    }
    
    STORAGE_BUCKET = 'career-documents'
    
    def __init__(self, db_client):
        """Initialize career service with storage and email services"""
        self.db = db_client
        self.storage = StorageService(db_client=db_client)
        self.email = EmailService()
    
    async def submit_application(
        self,
        personal_info: Dict[str, Any],
        job_details: Dict[str, Any],
        education: Dict[str, Any],
        additional_info: Dict[str, Any],
        required_documents: Dict[str, UploadFile],
        optional_documents: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Submit a new career application
        
        Args:
            personal_info: Dict with name, email, phone, address, etc.
            job_details: Dict with position, experience, salary expectations, etc.
            education: Dict with qualifications, university, graduation year
            additional_info: Dict with cover letter, LinkedIn, portfolio
            required_documents: Dict with keys: resume, aadhaar_card, pan_card, photo, address_proof
            optional_documents: Dict with keys: educational_certificates (list), experience_letter, salary_slip
        
        Returns:
            Dict with application_id, application_number, message
        
        Raises:
            HTTPException on validation or processing errors
        """
        try:
            logger.info(f"📝 Processing application from {personal_info.get('email', 'unknown')}")
            
            # Generate application ID
            application_id = str(uuid.uuid4())
            folder = f"applications/{application_id}"
            
            # Validate all required documents
            for doc_name, doc_file in required_documents.items():
                if doc_file:
                    self.storage.validate_file(doc_file)
            
            # Validate optional documents
            if optional_documents.get('educational_certificates'):
                for cert in optional_documents['educational_certificates']:
                    self.storage.validate_file(cert)
            if optional_documents.get('experience_letter'):
                self.storage.validate_file(optional_documents['experience_letter'])
            if optional_documents.get('salary_slip'):
                self.storage.validate_file(optional_documents['salary_slip'])
            
            # Upload required documents
            logger.info(f"📤 Uploading documents for application {application_id}")
            document_urls = {}
            
            # Map form field names to database column names
            doc_name_mapping = {
                'resume': 'resume_url',
                'aadhaar_card': 'aadhaar_url',
                'pan_card': 'pan_url',
                'photo': 'photo_url',
                'address_proof': 'address_proof_url'
            }
            
            for doc_type, doc_file in required_documents.items():
                if doc_file:
                    url = await self.storage.upload_file(
                        file=doc_file,
                        bucket=self.STORAGE_BUCKET,
                        folder=folder,
                        custom_filename=f"{doc_type}.{doc_file.filename.split('.')[-1]}"
                    )
                    # Use mapped column name
                    column_name = doc_name_mapping.get(doc_type, f"{doc_type}_url")
                    document_urls[column_name] = url
            
            # Upload optional documents
            educational_certs_urls = []
            if optional_documents.get('educational_certificates'):
                for idx, cert in enumerate(optional_documents['educational_certificates']):
                    url = await self.storage.upload_file(
                        file=cert,
                        bucket=self.STORAGE_BUCKET,
                        folder=folder,
                        custom_filename=f"educational_cert_{idx}.{cert.filename.split('.')[-1]}"
                    )
                    educational_certs_urls.append(url)
            
            if educational_certs_urls:
                document_urls['educational_certificates_url'] = educational_certs_urls
            
            if optional_documents.get('experience_letter'):
                url = await self.storage.upload_file(
                    file=optional_documents['experience_letter'],
                    bucket=self.STORAGE_BUCKET,
                    folder=folder,
                    custom_filename=f"experience_letter.{optional_documents['experience_letter'].filename.split('.')[-1]}"
                )
                document_urls['experience_letter_url'] = url
            
            if optional_documents.get('salary_slip'):
                url = await self.storage.upload_file(
                    file=optional_documents['salary_slip'],
                    bucket=self.STORAGE_BUCKET,
                    folder=folder,
                    custom_filename=f"salary_slip.{optional_documents['salary_slip'].filename.split('.')[-1]}"
                )
                document_urls['salary_slip_url'] = url
            
            # Prepare application data by merging dicts
            application_data = {
                "id": application_id,
                **{k: v for k, v in personal_info.items() if v is not None},
                **{k: v for k, v in job_details.items() if v is not None},
                **{k: v for k, v in education.items() if v is not None},
                **{k: v for k, v in additional_info.items() if v is not None},
                **document_urls,
                "status": "pending"
            }
            
            # Insert into database
            result = self.db.table("career_applications").insert(application_data).execute()
            
            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to save application"
                )
            
            # Generate application number
            created_at = datetime.now()
            application_number = f"CA-{created_at.strftime('%Y%m%d')}-{application_id[:8].upper()}"
            
            # Send confirmation email to applicant
            try:
                await self.email.send_career_application_confirmation(
                    to_email=personal_info.get('email'),
                    applicant_name=personal_info.get('full_name'),
                    position=job_details.get('position'),
                    application_number=application_number
                )
            except Exception as e:
                logger.warning(f"Failed to send confirmation email: {str(e)}")
            
            # Send notification to admin
            try:
                await self.email.send_new_career_application_notification(
                    applicant_name=personal_info.get('full_name'),
                    position=job_details.get('position'),
                    email=personal_info.get('email'),
                    phone=personal_info.get('phone'),
                    experience_years=job_details.get('experience_years') or 0,
                    application_id=application_id
                )
            except Exception as e:
                logger.warning(f"Failed to send admin notification: {str(e)}")
            
            logger.info(f"✅ Application {application_id} submitted successfully")
            
            # Log activity for career application submission
            try:
                await ActivityLogger.log(
                    user_id=None,  # No user_id for public applications
                    action="career_application_submitted",
                    entity_type="career_application",
                    entity_id=application_id,
                    details={
                        "applicant_name": personal_info.get('full_name'),
                        "position": job_details.get('position'),
                        "email": personal_info.get('email'),
                        "phone": personal_info.get('phone'),
                        "application_number": application_number
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to log career application activity: {str(e)}")
            
            return {
                "id": application_id,
                "application_number": application_number,
                "message": "Application submitted successfully! We'll review and get back to you soon."
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error submitting application: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to submit application: {str(e)}"
            )
    
    def get_applications(
        self,
        status_filter: Optional[str] = None,
        position_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get career applications with optional filters
        
        Args:
            status_filter: Filter by application status
            position_filter: Filter by position
            skip: Pagination offset
            limit: Results per page
        
        Returns:
            Dict with applications list and count
        """
        try:
            query = self.db.table("career_applications").select("*")
            
            if status_filter:
                query = query.eq("status", status_filter)
            if position_filter:
                query = query.eq("position", position_filter)
            
            query = query.order("created_at", desc=True).range(skip, skip + limit - 1)
            
            result = query.execute()
            
            return {
                "applications": result.data,
                "count": len(result.data)
            }
            
        except Exception as e:
            logger.error(f"Error fetching applications: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch applications"
            )
    
    def get_application_by_id(self, application_id: str) -> Dict[str, Any]:
        """
        Get a specific career application by ID
        
        Args:
            application_id: UUID of the application
        
        Returns:
            Application data dict
        
        Raises:
            HTTPException if not found
        """
        try:
            result = self.db.table("career_applications").select("*").eq("id", application_id).execute()
            
            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Application not found"
                )
            
            return result.data[0]
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching application: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch application"
            )
    
    async def update_application_status(
        self,
        application_id: str,
        new_status: str,
        admin_notes: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        interview_scheduled_at: Optional[datetime] = None,
        interview_location: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update application status and related fields
        
        Args:
            application_id: UUID of the application
            new_status: New status value
            admin_notes: Optional admin notes
            rejection_reason: Reason for rejection (if status is 'rejected')
            interview_scheduled_at: Interview date/time
            interview_location: Interview location
        
        Returns:
            Updated application data
        
        Raises:
            HTTPException on validation or update errors
        """
        try:
            # Validate status
            if new_status not in self.VALID_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status. Must be one of: {', '.join(self.VALID_STATUSES)}"
                )
            
            update_dict = {
                "status": new_status
            }
            
            if admin_notes:
                update_dict["admin_notes"] = admin_notes
            if rejection_reason:
                update_dict["rejection_reason"] = rejection_reason
            if interview_scheduled_at:
                update_dict["interview_scheduled_at"] = interview_scheduled_at.isoformat()
            if interview_location:
                update_dict["interview_location"] = interview_location
            
            result = self.db.table("career_applications").update(update_dict).eq("id", application_id).execute()
            
            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Application not found"
                )
            
            logger.info(f"✅ Application {application_id} updated to {new_status}")
            
            # Log activity for status update
            try:
                application_data = result.data[0]
                await ActivityLogger.log(
                    user_id=None,  # Will be updated when we have user context
                    action="career_application_status_updated",
                    entity_type="career_application",
                    entity_id=application_id,
                    details={
                        "applicant_name": application_data.get("full_name"),
                        "new_status": new_status,
                        "admin_notes": admin_notes,
                        "rejection_reason": rejection_reason
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to log career application status update: {str(e)}")
            
            return result.data[0]
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating application: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update application"
            )
    
    def get_document_download_url(self, application_id: str, document_type: str) -> str:
        """
        Generate a signed URL for document download
        
        Args:
            application_id: UUID of the application
            document_type: Type of document (resume, aadhaar, pan, etc.)
        
        Returns:
            Signed download URL
        
        Raises:
            HTTPException if application or document not found
        """
        try:
            # Get application to retrieve document URL
            application = self.get_application_by_id(application_id)
            
            document_url = application.get(f"{document_type}_url")
            
            if not document_url:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document {document_type} not found"
                )
            
            # Create signed URL (valid for 1 hour)
            signed_url = self.storage.create_signed_url(
                bucket=self.STORAGE_BUCKET,
                path=document_url,
                expires_in=3600
            )
            
            return signed_url
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating download URL: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate download URL"
            )
