"""
Upload API - Handle file uploads to Supabase Storage
Provides secure, authenticated file upload endpoints
"""
import os
import uuid
import logging
from typing import List
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, status, Query
from fastapi.responses import JSONResponse
from supabase import Client, create_client

from app.core.auth import get_current_user
from app.core.auth import TokenData
from app.core.config import settings
from app.core.database import get_db_client, get_storage_client
from app.schemas import ImageUploadResponse, MultipleImageUploadResponse, ImageDeleteResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["Upload"])

# Allowed file extensions and MIME types
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_MIME_TYPES = {'image/jpeg', 'image/jpg', 'image/png', 'image/webp'}
ALLOWED_DOCUMENT_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_DOCUMENT_MIME_TYPES = {'application/pdf', 'image/jpeg', 'image/jpg', 'image/png', 'image/webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10MB for documents


def validate_image(file: UploadFile) -> None:
    """
    Validate uploaded image file.
    
    Args:
        file: Uploaded file object
        
    Raises:
        HTTPException: If validation fails
    """
    # Check MIME type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
        )
    
    # Check file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file extension. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )


@router.post("/salon-image", response_model=ImageUploadResponse, operation_id="upload_salon_image_upload")
async def upload_salon_image(
    file: UploadFile = File(...),
    folder: str = "covers",  # covers, logos, gallery
    current_user: TokenData = Depends(get_current_user)
):
    """
    Upload a salon image to Supabase Storage.
    Requires authentication.
    
    Args:
        file: Image file to upload
        folder: Destination folder (covers/logos/gallery)
        current_user: Authenticated user from JWT
        
    Returns:
        JSON with public URL of uploaded image
    """
    storage_client = get_storage_client()
    
    # Validate folder name
    if folder not in ['covers', 'logos', 'gallery']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid folder. Must be: covers, logos, or gallery"
        )
    
    # Validate image
    validate_image(file)
    
    # Read file content
    file_content = await file.read()
    
    # Check file size
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )
    
    # Generate unique filename
    file_ext = os.path.splitext(file.filename)[1].lower()
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    storage_path = f"{folder}/{unique_filename}"
    
    try:
        # Upload to Supabase Storage
        storage_client.storage.from_('salon-images').upload(
            path=storage_path,
            file=file_content,
            file_options={
                "content-type": file.content_type,
                "cache-control": "3600",
                "upsert": "false"
            }
        )
        
        # Get public URL
        public_url = storage_client.storage.from_('salon-images').get_public_url(storage_path)
        
        logger.info(f"Image uploaded by user {current_user.user_id}: {storage_path}")
        
        return {
            "success": True,
            "url": public_url,
            "path": storage_path,
            "filename": unique_filename
        }
    except Exception as upload_error:
        logger.error(f"Storage upload failed: {str(upload_error)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload image"
        )


@router.post("/salon-images/multiple", response_model=MultipleImageUploadResponse, operation_id="upload_multiple_salon_images")
async def upload_multiple_salon_images(
    files: List[UploadFile] = File(...),
    folder: str = "gallery",
    current_user: TokenData = Depends(get_current_user)
):
    """
    Upload multiple salon images at once.
    Useful for gallery uploads.
    
    Args:
        files: List of image files
        folder: Destination folder
        current_user: Authenticated user
        
    Returns:
        JSON with list of uploaded image URLs
    """
    storage_client = get_storage_client()
    
    if len(files) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 files per upload"
        )
    
    uploaded_images = []
    failed_uploads = []
    
    for file in files:
        # Validate and upload each file
        validate_image(file)
        
        file_content = await file.read()
        
        if len(file_content) > MAX_FILE_SIZE:
            failed_uploads.append({
                "filename": file.filename,
                "error": "File too large"
            })
            continue
        
        # Generate unique filename
        file_ext = os.path.splitext(file.filename)[1].lower()
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        storage_path = f"{folder}/{unique_filename}"
        
        # Upload
        storage_client.storage.from_('salon-images').upload(
            path=storage_path,
            file=file_content,
            file_options={
                "content-type": file.content_type,
                "cache-control": "3600",
                "upsert": "false"
            }
        )
        
        public_url = storage_client.storage.from_('salon-images').get_public_url(storage_path)
        
        uploaded_images.append({
            "url": public_url,
            "path": storage_path,
            "filename": unique_filename,
            "original_name": file.filename
        })
    
    logger.info(
        f"Batch upload by user {current_user.user_id}: "
        f"{len(uploaded_images)} succeeded, {len(failed_uploads)} failed"
    )
    
    return {
        "success": True,
        "uploaded": uploaded_images,
        "failed": failed_uploads,
        "total": len(files),
        "successful_count": len(uploaded_images),
        "failed_count": len(failed_uploads)
    }


@router.post("/agreement-document", response_model=ImageUploadResponse)
async def upload_agreement_document(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Upload salon agreement document (PDF or image) to Supabase Storage.
    Requires authentication. For use by Relationship Managers during salon registration.
    
    Args:
        file: Document file to upload (PDF or image)
        current_user: Authenticated user from JWT (already verified by dependency)
        
    Returns:
        JSON with storage path (use signed URL endpoint to view)
    """
    # Use service role client which bypasses RLS (authentication already done at API level)
    storage_client = get_storage_client()
    
    # Validate document file type
    if file.content_type not in ALLOWED_DOCUMENT_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types: PDF, JPEG, PNG, WebP"
        )
    
    # Check file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file extension. Allowed: {', '.join(ALLOWED_DOCUMENT_EXTENSIONS)}"
        )
    
    # Read file content
    file_content = await file.read()
    
    # Check file size (10MB for documents)
    if len(file_content) > MAX_DOCUMENT_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {MAX_DOCUMENT_SIZE / 1024 / 1024}MB"
        )
    
    # Generate unique filename
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    storage_path = f"agreements/{unique_filename}"
    
    try:
        # Upload to salon-agreement bucket
        storage_client.storage.from_('salon-agreement').upload(
            path=storage_path,
            file=file_content,
            file_options={
                "content-type": file.content_type,
                "cache-control": "3600",
                "upsert": "false"
            }
        )
        
        logger.info(f"Agreement document uploaded by user {current_user.user_id}: {storage_path}")
        
        # Return path as both 'url' and 'path' for backward compatibility with ImageUploadResponse schema
        # Frontend will use 'path' to generate signed URLs
        return {
            "success": True,
            "url": storage_path,  # Return path here (not actual URL) for schema compatibility
            "path": storage_path,
            "filename": unique_filename
        }
    except Exception as upload_error:
        error_str = str(upload_error)
        logger.error(f"Agreement document upload failed: {error_str}")
        
        # Check if error is authentication-related (expired token, unauthorized)
        if any(phrase in error_str.lower() for phrase in ['unauthorized', 'exp', 'token', 'jwt', 'auth']):
            # Return 401 so frontend interceptor can refresh token and retry
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication expired. Please try again.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Other errors return 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload document: {error_str}"
        )


@router.delete("/salon-image", response_model=ImageDeleteResponse)
async def delete_salon_image(
    path: str,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Delete an image from Supabase Storage.
    
    Args:
        path: Storage path of the image (e.g., "covers/abc123.jpg")
        current_user: Authenticated user
        
    Returns:
        Success confirmation
    """
    storage_client = get_storage_client()
    
    # Delete from storage
    storage_client.storage.from_('salon-images').remove([path])
    
    logger.info(f"Image deleted by user {current_user.user_id}: {path}")
    
    return {
        "success": True,
        "message": "Image deleted successfully",
        "path": path
    }


@router.get("/agreement-document/signed-url")
async def get_agreement_document_signed_url(
    path: str = Query(..., description="Storage path of the agreement document (e.g., 'agreements/abc123.pdf')"),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Generate a signed URL for viewing a private agreement document.
    Documents in salon-agreement bucket are private and require signed URLs.
    URL expires in 1 hour for security.
    
    Args:
        path: Storage path of the document
        current_user: Authenticated user (RMs and admins can access, verified at API level)
        
    Returns:
        JSON with signed URL valid for 1 hour
    """
    # Use service role client to generate signed URLs (authentication already done at API level)
    storage_client = get_storage_client()
    
    try:
        # Generate signed URL (valid for 1 hour)
        signed_url_response = storage_client.storage.from_('salon-agreement').create_signed_url(
            path,
            3600  # 1 hour expiration
        )
        
        # Handle response format
        if isinstance(signed_url_response, dict):
            signed_url = signed_url_response.get('signedURL') or signed_url_response.get('signedUrl')
        else:
            signed_url = str(signed_url_response)
        
        if not signed_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate signed URL"
            )
        
        logger.info(f"Signed URL generated for document {path} by user {current_user.user_id}")
        
        return {
            "success": True,
            "signedUrl": signed_url,
            "expiresIn": 3600
        }
    except Exception as e:
        error_str = str(e)
        logger.error(f"Failed to generate signed URL for {path}: {error_str}")
        
        # Check if error is authentication-related (expired token, unauthorized)
        if any(phrase in error_str.lower() for phrase in ['unauthorized', 'exp', 'token', 'jwt', 'auth']):
            # Return 401 so frontend interceptor can refresh token and retry
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication expired. Please try again.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Other errors return 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate signed URL: {error_str}"
        )
