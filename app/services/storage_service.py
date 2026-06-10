"""
Storage Service - File Upload & Management
Handles Supabase Storage operations for file uploads.

Currently used only for the service-category icon upload; most document/image
uploads now go through CloudinaryService.
"""
import logging
from typing import Optional
from fastapi import UploadFile, HTTPException, status
import uuid


logger = logging.getLogger(__name__)


class StorageService:
    """Service for uploading files to Supabase Storage."""

    def __init__(self, db_client):
        """Initialize storage service"""
        self.client = db_client

    async def upload_file(
        self,
        file: UploadFile,
        bucket: str,
        folder: str,
        custom_filename: Optional[str] = None
    ) -> str:
        """
        Upload file to Supabase Storage.

        Args:
            file: UploadFile object
            bucket: Storage bucket name
            folder: Folder path within bucket
            custom_filename: Optional custom filename (generates UUID if not provided)

        Returns:
            File path in storage (folder/filename)

        Raises:
            HTTPException on upload failure
        """
        # Generate unique filename if not provided
        ext = file.filename.split('.')[-1] if '.' in file.filename else 'bin'
        filename = custom_filename or f"{uuid.uuid4()}.{ext}"
        storage_path = f"{folder}/{filename}"
        
        # Read file content once
        content = await file.read()
        
        # Use existing client
        storage_client = self.client
        
        # Upload to Supabase Storage
        try:
            result = storage_client.storage.from_(bucket).upload(
                path=storage_path,
                file=content,
                file_options={"content-type": file.content_type or "application/octet-stream"}
            )
            
            if hasattr(result, 'error') and result.error:
                logger.error(f"Storage upload error: {result.error}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to upload file"
                )
            
            # Reset file pointer for potential reuse
            await file.seek(0)
            
            logger.info(f"File uploaded successfully: {storage_path}")
            return storage_path
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"File upload failed: {str(e)}"
            )
