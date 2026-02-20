"""
Career Service - Business Logic for Job Applications
Handles career application submissions, status updates, and queries
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
from urllib.parse import urlparse

from fastapi import HTTPException, status, UploadFile
from pydantic import EmailStr, validate_email, ValidationError
from app.core.database import get_db
from app.services.storage_service import StorageService
from app.services.email import EmailService, email_service
from app.services.activity_log_service import ActivityLogger
from app.api.upload import get_storage_client

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
    
    # Document field name mappings (centralized for consistency)
    DOCUMENT_FIELD_MAPPING = {
        # Form field name -> Database column name
        'resume': 'resume_url',
        'aadhaar_card': 'aadhaar_url',
        'pan_card': 'pan_url',
        'photo': 'photo_url',
        'address_proof': 'address_proof_url',
        'experience_letter': 'experience_letter_url',
        'salary_slip': 'salary_slip_url',
        'educational_certificates': 'educational_certificates_url'
    }
    
    STORAGE_BUCKET = 'career-documents'
    
    # Document field name mappings (centralized for consistency)
    DOCUMENT_FIELD_MAPPING = {
        # Form field name -> Database column name
        'resume': 'resume_url',
        'aadhaar_card': 'aadhaar_url',
        'pan_card': 'pan_url',
        'photo': 'photo_url',
        'address_proof': 'address_proof_url',
        'experience_letter': 'experience_letter_url',
        'salary_slip': 'salary_slip_url',
        'educational_certificates': 'educational_certificates_url'
    }
    
    # Required document fields that must be present
    REQUIRED_DOCUMENTS = {'resume', 'aadhaar_card', 'pan_card', 'photo', 'address_proof'}
    
    def __init__(
        self, 
        db_client, 
        storage_service: Optional[StorageService] = None,
        email_service: Optional[EmailService] = None
    ):
        """
        Initialize career service with storage and email services
        
        Args:
            db_client: Database client (Supabase client)
            storage_service: Optional StorageService instance (creates new if None)
            email_service: Optional EmailService instance (uses global singleton if None)
        """
        self.db = db_client
        self.storage = storage_service or StorageService(db_client=db_client)
        self.email = email_service or globals()['email_service']
    
    @staticmethod
    def _get_db_column_name(form_field_name: str) -> str:
        """
        Get database column name for a form field.
        
        Args:
            form_field_name: Form field name (e.g., 'aadhaar_card')
        
        Returns:
            Database column name (e.g., 'aadhaar_url')
        
        Raises:
            ValueError if field name is not recognized
        """
        if form_field_name in CareerService.DOCUMENT_FIELD_MAPPING:
            return CareerService.DOCUMENT_FIELD_MAPPING[form_field_name]
        
        # Fallback: assume field_name + '_url' convention
        logger.warning(f"Unknown document field '{form_field_name}', using default naming convention")
        return f"{form_field_name}_url"
    
    @staticmethod
    def _get_file_extension(filename: str) -> str:
        """
        Safely extract file extension from filename.
        
        Args:
            filename: Original filename
        
        Returns:
            File extension including the dot (e.g., '.pdf', '.jpg')
        
        Raises:
            HTTPException if filename has no extension
        """
        if '.' not in filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{filename}' has no extension. Please upload a file with a valid extension."
            )
        
        # Get extension and ensure it's lowercase
        ext = '.' + filename.rsplit('.', 1)[-1].lower()
        
        # Additional validation: extension shouldn't be empty or just a dot
        if len(ext) <= 1:  # Just a dot
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{filename}' has an invalid extension."
            )
        
        return ext
    
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
            # Validate email at service layer for defense in depth
            email = personal_info.get('email')
            if not email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email is required"
                )
            
            try:
                validate_email(email)
            except ValidationError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid email format"
                )
            
            # Validate experience years at service layer
            experience_years = job_details.get('experience_years', 0)
            if experience_years < 0 or experience_years > 50:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Experience years must be between 0 and 50"
                )
            
            logger.info(f"Processing application from {email}")
            
            # Generate application ID and application number
            application_id = str(uuid.uuid4())
            created_at = datetime.now()
            application_number = f"CA-{created_at.strftime('%Y%m%d')}-{application_id[:8].upper()}"
            folder = f"applications/{application_id}"
            

            
            # Upload required documents
            logger.info(f"Uploading documents for application {application_id}")
            document_urls = {}
            
            # Validate all required documents are present
            missing_docs = self.REQUIRED_DOCUMENTS - set(required_documents.keys())
            if missing_docs:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required documents: {', '.join(missing_docs)}"
                )
            
            for doc_type, doc_file in required_documents.items():
                if doc_file:
                    ext = self._get_file_extension(doc_file.filename)
                    url = await self.storage.upload_file(
                        file=doc_file,
                        bucket=self.STORAGE_BUCKET,
                        folder=folder,
                        custom_filename=f"{doc_type}{ext}"
                    )
                    # Use centralized mapping
                    column_name = self._get_db_column_name(doc_type)
                    document_urls[column_name] = url
            
            # Upload optional documents
            educational_certs_urls = []
            if optional_documents.get('educational_certificates'):
                for idx, cert in enumerate(optional_documents['educational_certificates']):
                    ext = self._get_file_extension(cert.filename)
                    url = await self.storage.upload_file(
                        file=cert,
                        bucket=self.STORAGE_BUCKET,
                        folder=folder,
                        custom_filename=f"educational_cert_{idx}{ext}"
                    )
                    educational_certs_urls.append(url)
            
            if educational_certs_urls:
                document_urls['educational_certificates_url'] = educational_certs_urls
            
            if optional_documents.get('experience_letter'):
                ext = self._get_file_extension(optional_documents['experience_letter'].filename)
                url = await self.storage.upload_file(
                    file=optional_documents['experience_letter'],
                    bucket=self.STORAGE_BUCKET,
                    folder=folder,
                    custom_filename=f"experience_letter{ext}"
                )
                column_name = self._get_db_column_name('experience_letter')
                document_urls[column_name] = url
            
            if optional_documents.get('salary_slip'):
                ext = self._get_file_extension(optional_documents['salary_slip'].filename)
                url = await self.storage.upload_file(
                    file=optional_documents['salary_slip'],
                    bucket=self.STORAGE_BUCKET,
                    folder=folder,
                    custom_filename=f"salary_slip{ext}"
                )
                column_name = self._get_db_column_name('salary_slip')
                document_urls[column_name] = url
            
            # Prepare application data by merging dicts
            application_data = {
                "id": application_id,
                "application_number": application_number,
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
            
            # Track email delivery status
            email_sent = False
            email_error = None
            
            # Send confirmation email to applicant
            try:
                await self.email.send_career_application_confirmation(
                    to_email=personal_info.get('email'),
                    applicant_name=personal_info.get('full_name'),
                    position=job_details.get('position'),
                    application_number=application_number
                )
                email_sent = True
                logger.info(f"Confirmation email sent successfully to {personal_info.get('email')}")
            except Exception as e:
                email_error = str(e)
                logger.error(
                    f"CRITICAL: Failed to send confirmation email to {personal_info.get('email')} "
                    f"for application {application_id}. Error: {email_error}"
                )
                # Update application to flag for manual follow-up
                try:
                    self.db.table("career_applications").update({
                        "admin_notes": f"⚠️ Confirmation email failed: {email_error}. Please contact applicant manually."
                    }).eq("id", application_id).execute()
                except Exception as update_error:
                    logger.error(f"Failed to update admin notes: {str(update_error)}")
            
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
            
            logger.info(f"Application {application_id} submitted successfully")
            
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
                        "application_number": application_number,
                        "email_sent": email_sent
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to log career application activity: {str(e)}")
            
            # Prepare response with email status warning if needed
            response = {
                "id": application_id,
                "application_number": application_number,
                "message": "Application submitted successfully! We'll review and get back to you soon."
            }
            
            if not email_sent:
                response["warning"] = (
                    "Your application was received, but we couldn't send a confirmation email. "
                    "Please note your application number for reference. Our team will contact you directly."
                )
                response["email_sent"] = False
            else:
                response["email_sent"] = True
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error submitting application: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to submit application. Please try again or contact support if the issue persists."
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
            logger.error(f"Error fetching applications: {str(e)}", exc_info=True)
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
            logger.error(f"Error fetching application {application_id}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch application"
            )
    
    def get_application_by_number(self, application_number: str) -> Dict[str, Any]:
        """
        Get a specific career application by application number
        
        Args:
            application_number: Application number (e.g., CA-20260112-A1B2C3D4)
        
        Returns:
            Application data dict
        
        Raises:
            HTTPException if not found
        """
        try:
            result = self.db.table("career_applications").select("*").eq("application_number", application_number).execute()
            
            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Application with number {application_number} not found"
                )
            
            return result.data[0]
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching application by number {application_number}: {str(e)}", exc_info=True)
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
        interview_location: Optional[str] = None,
        admin_user_id: Optional[str] = None
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
            admin_user_id: ID of the admin performing the update (for audit logging)
        
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
            
            logger.info(f"Application {application_id} updated to {new_status}")
            
            # Log activity for status update
            try:
                application_data = result.data[0]
                await ActivityLogger.log(
                    user_id=admin_user_id,  # Track which admin updated the application
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
            logger.error(f"Error updating application {application_id}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update application"
            )
    
    def get_document_download_url(
        self, 
        application_id: str, 
        document_type: str,
        admin_user_id: Optional[str] = None
    ) -> str:
        """
        Generate a signed URL for document download
        
        Args:
            application_id: UUID of the application
            document_type: Type of document (resume, aadhaar, pan, etc.)
            admin_user_id: ID of the admin downloading the document (for audit logging)
        
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
            
            # Debug: Log what we got from the database
            logger.info(f"document_url from DB: {document_url}")
            
            # Extract storage path from URL if it's a full URL
            # Handle both cases: full URL (old data) and path-only (new data)
            if document_url.startswith('http://') or document_url.startswith('https://'):
                parsed = urlparse(document_url)
                # Extract path after '/object/public/bucket-name/' or '/object/bucket-name/'
                path_parts = parsed.path.split(f"/object/public/{self.STORAGE_BUCKET}/")
                if len(path_parts) > 1:
                    storage_path = path_parts[-1]
                else:
                    # Try without 'public' (for private buckets)
                    path_parts = parsed.path.split(f"/object/{self.STORAGE_BUCKET}/")
                    storage_path = path_parts[-1] if len(path_parts) > 1 else document_url
                logger.info(f"Extracted storage path from URL: {storage_path}")
            else:
                # Already a storage path
                storage_path = document_url
            
            # Log document access for audit trail (important for sensitive documents)
            logger.info(
                f"Document download requested - Application: {application_id}, "
                f"Document: {document_type}, Admin: {admin_user_id or 'unknown'}"
            )
            
            # Create signed URL (valid for 1 hour) using refreshable storage client
            storage_client = get_storage_client()
            signed_url_response = storage_client.storage.from_(self.STORAGE_BUCKET).create_signed_url(
                storage_path,
                3600  # 1 hour expiration
            )
            
            # Handle response format (same as agreement API)
            if isinstance(signed_url_response, dict):
                signed_url = signed_url_response.get('signedURL') or signed_url_response.get('signedUrl')
            else:
                signed_url = str(signed_url_response)
            
            if not signed_url:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to generate signed URL"
                )
            
            return signed_url
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating download URL for application {application_id}, document {document_type}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate download URL"
            )
