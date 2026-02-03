"""
Storage Service - File Upload & Management
Handles Supabase Storage operations for file uploads
"""
import logging
from typing import Optional
from fastapi import UploadFile, HTTPException, status
import uuid
import mimetypes
import magic  # python-magic-bin for Windows
from app.core.database import get_db

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
    
    def validate_file(self, file: UploadFile, allowed_types: Optional[set] = None) -> bool:
        """
        Validate file type and size using actual file content
        
        Reads file content once to avoid race conditions and validates everything
        from the buffer.
        
        Args:
            file: UploadFile object from FastAPI
            allowed_types: Optional set of allowed MIME types (defaults to class ALLOWED_MIME_TYPES)
        
        Returns:
            True if valid
            
        Raises:
            HTTPException if validation fails
        """
        allowed_types = allowed_types or self.ALLOWED_MIME_TYPES
        
        # Check file extension (first line of defense)
        ext = '.' + file.filename.split('.')[-1].lower() if '.' in file.filename else ''
        if ext not in self.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type {ext} not allowed"
            )
        
        # Read entire file content once to avoid race conditions
        # This ensures size and content validation happen on the same data
        try:
            file.file.seek(0)
            file_content = file.file.read()  # Read entire file into memory
            file.file.seek(0)  # Reset for subsequent upload
            
            # Check file size from actual content
            file_size = len(file_content)
            if file_size == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File {file.filename} is empty"
                )
            
            if file_size > self.MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File {file.filename} exceeds 5MB limit ({file_size / 1024 / 1024:.2f}MB)"
                )
            
            # Detect MIME type from actual file content (using first 2KB for efficiency)
            mime = magic.Magic(mime=True)
            detected_mime = mime.from_buffer(file_content[:2048])
            
            logger.debug(f"File {file.filename}: Size={file_size} bytes, Extension={ext}, Detected MIME={detected_mime}")
            
            # Verify detected MIME type is in allowed types
            if detected_mime not in allowed_types:
                # Check for common variations
                allowed_variations = {
                    'image/jpg': 'image/jpeg',
                    'image/jpeg': 'image/jpg',
                }
                
                normalized_mime = allowed_variations.get(detected_mime, detected_mime)
                if normalized_mime not in allowed_types:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"File content type mismatch. Detected: {detected_mime}, Allowed: {', '.join(allowed_types)}"
                    )
            
            # Additional check: filename MIME should roughly match content MIME
            filename_mime, _ = mimetypes.guess_type(file.filename)
            if filename_mime:
                # Extract main type (e.g., 'image' from 'image/jpeg')
                filename_type = filename_mime.split('/')[0]
                detected_type = detected_mime.split('/')[0]
                
                if filename_type != detected_type:
                    logger.warning(
                        f"Suspicious file detected: {file.filename} "
                        f"(extension suggests {filename_mime} but content is {detected_mime})"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"File extension does not match file content"
                    )
        
        except HTTPException:
            raise
        except MemoryError:
            logger.error(f"File {file.filename} too large to load into memory")
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File too large to process"
            )
        except Exception as e:
            logger.error(f"File content validation failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File validation failed. Please ensure the file is not corrupted."
            )
        
        return True
    
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
        
        # Retry logic for token expiration
        for attempt in range(max_retries + 1):
            try:
                # Get fresh client on retry attempts
                if attempt > 0:
                    logger.warning(f"Retrying upload (attempt {attempt + 1}/{max_retries + 1}) for {storage_path}")
                    self.client = get_db()  # Get fresh client with new token
                
                # Upload to Supabase Storage
                result = self.client.storage.from_(bucket).upload(
                    path=storage_path,
                    file=content,
                    file_options={"content-type": file.content_type or "application/octet-stream"}
                )
                
                if hasattr(result, 'error') and result.error:
                    error_dict = result.error if isinstance(result.error, dict) else {}
                    error_msg = error_dict.get('message', str(result.error))
                    
                    # Check for token expiration error
                    if 'exp' in error_msg or 'Unauthorized' in error_msg:
                        if attempt < max_retries:
                            logger.warning(f"Token expired during upload, retrying... ({error_msg})")
                            continue  # Retry with fresh client
                    
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
                error_str = str(e)
                
                # Check for token expiration in exception message
                if ('exp' in error_str or 'Unauthorized' in error_str) and attempt < max_retries:
                    logger.warning(f"Token expiration error, retrying... ({error_str})")
                    continue
                
                logger.error(f"Error uploading file: {error_str}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"File upload failed: {error_str}"
                )
        
        # If all retries failed
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File upload failed after multiple attempts due to authentication issues"
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
            signed_url = self.client.storage.from_(bucket).create_signed_url(
                path=path,
                expires_in=expires_in
            )
            
            if hasattr(signed_url, 'error') and signed_url.error:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to generate signed URL"
                )
            
            return signed_url.get('signedURL') or signed_url['signedURL']
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating signed URL: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate download URL"
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
