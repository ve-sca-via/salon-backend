"""
Storage Service - File Upload & Management
Handles Supabase Storage operations for file uploads
"""
import logging
from typing import Optional
from fastapi import UploadFile, HTTPException, status
import uuid
import mimetypes

from supabase import Client, create_client
from app.core.database import get_db
from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """
    Service for managing file uploads to Supabase Storage.
    Provides validation, upload, and signed URL generation.
    """
    
    ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.webp', '.svg', '.doc', '.docx'}
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    ALLOWED_MIME_TYPES = {
        'application/pdf',
        'image/jpeg',
        'image/jpg', 
        'image/png',
        'image/webp',
        'image/svg+xml',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    }
    
    def __init__(self, db_client):
        """Initialize storage service"""
        self.client = db_client
    
    async def upload_file(
        self, 
        file: UploadFile, 
        bucket: str,
        folder: str,
        custom_filename: Optional[str] = None,
        max_retries: int = 2
    ) -> str:
        """
        Upload file to Supabase Storage
        
        Args:
            file: UploadFile object
            bucket: Storage bucket name
            folder: Folder path within bucket
            custom_filename: Optional custom filename (generates UUID if not provided)
            max_retries: Maximum number of retry attempts for token expiration errors
        
        Returns:
            File path in storage (bucket/folder/filename)
            
        Raises:
            HTTPException on upload failure
        """
        # Generate unique filename if not provided
        ext = file.filename.split('.')[-1] if '.' in file.filename else 'bin'
        filename = custom_filename or f"{uuid.uuid4()}.{ext}"
        storage_path = f"{folder}/{filename}"
        
        # Read file content once
        content = await file.read()
        
        # Upload to Supabase Storage
        try:
            if not self.client:
                 raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Database client not initialized"
                )

            result = self.client.storage.from_(bucket).upload(
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
    
    def create_signed_url(self, bucket: str, path: str, expires_in: int = 3600) -> str:
        """
        Create a signed URL for private file access
        
        Args:
            bucket: Storage bucket name
            path: File path within bucket
            expires_in: URL expiration time in seconds (default 1 hour)
        
        Returns:
            Signed URL string
            
        Raises:
            HTTPException on failure
        """
        try:
            if not self.client:
                 raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Database client not initialized"
                )
                
            signed_url_response = self.client.storage.from_(bucket).create_signed_url(
                path=path,
                expires_in=expires_in
            )
            
            # Handle error responses
            if hasattr(signed_url_response, 'error') and signed_url_response.error:
                logger.error(f"Signed URL error: {signed_url_response.error}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to generate signed URL"
                )
            
            # Extract signed URL from response
            # The response can be a dict with 'signedURL' key or have different structures
            if isinstance(signed_url_response, dict):
                # Try different possible key names
                signed_url = (
                    signed_url_response.get('signedURL') or 
                    signed_url_response.get('signed_url') or
                    signed_url_response.get('url') or
                    signed_url_response.get('data', {}).get('signedURL') or
                    signed_url_response.get('data', {}).get('signed_url')
                )
                
                if signed_url:
                    logger.info(f"Successfully generated signed URL for {path}")
                    return signed_url
                else:
                    logger.error(f"Could not find signed URL in response: {signed_url_response}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Signed URL not found in response"
                    )
            else:
                # If response is not a dict, try to return it directly
                logger.warning(f"Unexpected response type: {type(signed_url_response)}")
                return str(signed_url_response)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating signed URL: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate download URL: {str(e)}"
            )
    
    async def upload_file(
        self, 
        file: UploadFile, 
        bucket: str,
        folder: str,
        custom_filename: Optional[str] = None,
        max_retries: int = 2
    ) -> str:
        """
        Upload file to Supabase Storage with retry logic for token expiration
        
        Args:
            file: UploadFile object
            bucket: Storage bucket name
            folder: Folder path within bucket
            custom_filename: Optional custom filename (generates UUID if not provided)
            max_retries: Maximum number of retry attempts for token expiration errors
        
        Returns:
            File path in storage (bucket/folder/filename)
            
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
    
    def create_signed_url(self, bucket: str, path: str, expires_in: int = 3600) -> str:
        """
        Create a signed URL for private file access
        
        Args:
            bucket: Storage bucket name
            path: File path within bucket
            expires_in: URL expiration time in seconds (default 1 hour)
        
        Returns:
            Signed URL string
            
        Raises:
            HTTPException on failure
        """
        try:
            # Use existing client
            if not self.client:
                 raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Database client not initialized"
                )
            
            signed_url_response = self.client.storage.from_(bucket).create_signed_url(
                path=path,
                expires_in=expires_in
            )
            
            # Handle error responses
            if hasattr(signed_url_response, 'error') and signed_url_response.error:
                logger.error(f"Signed URL error: {signed_url_response.error}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to generate signed URL"
                )
            
            # Extract signed URL from response
            # The response can be a dict with 'signedURL' key or have different structures
            if isinstance(signed_url_response, dict):
                # Try different possible key names
                signed_url = (
                    signed_url_response.get('signedURL') or 
                    signed_url_response.get('signed_url') or
                    signed_url_response.get('url') or
                    signed_url_response.get('data', {}).get('signedURL') or
                    signed_url_response.get('data', {}).get('signed_url')
                )
                
                if signed_url:
                    logger.info(f"Successfully generated signed URL for {path}")
                    return signed_url
                else:
                    logger.error(f"Could not find signed URL in response: {signed_url_response}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Signed URL not found in response"
                    )
            else:
                # If response is not a dict, try to return it directly
                logger.warning(f"Unexpected response type: {type(signed_url_response)}")
                return str(signed_url_response)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating signed URL for bucket={bucket}, path={path}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate download URL: {str(e)}"
            )
    
    def delete_file(self, bucket: str, path: str) -> bool:
        """
        Delete a file from storage
        
        Args:
            bucket: Storage bucket name
            path: File path within bucket
        
        Returns:
            True if deleted successfully
            
        Raises:
            HTTPException on failure
        """
        try:
            result = self.client.storage.from_(bucket).remove([path])
            
            if hasattr(result, 'error') and result.error:
                logger.error(f"Storage delete error: {result.error}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to delete file"
                )
            
            logger.info(f"File deleted: {path}")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting file: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete file"
            )
