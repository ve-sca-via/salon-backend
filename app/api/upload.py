"""
Upload API - Handle file uploads to Supabase Storage
Provides secure, authenticated file upload endpoints
"""
import os
import uuid
import logging
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, status, Query

from app.core.auth import get_current_user, TokenData
from app.core.config import settings
from app.core.database import get_storage_client
from app.services.cloudinary_service import CloudinaryService
from app.schemas import ImageUploadResponse

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


@router.post("/cloudinary-product-image", response_model=ImageUploadResponse)
async def upload_cloudinary_product_image(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Upload a product image to Cloudinary.
    Requires authentication.
    
    Args:
        file: Image file to upload
        current_user: Authenticated user from JWT
        
    Returns:
        JSON with public URL of uploaded image
    """
    # Validate image
    validate_image(file)
    
    # Read file content to check size
    file_content = await file.read()
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )
    
    # Reset file pointer since CloudinaryService calls read() again
    await file.seek(0)
    
    try:
        cloudinary_service = CloudinaryService()
        secure_url = await cloudinary_service.upload_file(file, folder="products")
        
        logger.info(f"Product image uploaded to Cloudinary by user {current_user.user_id}: {secure_url}")
        
        return {
            "success": True,
            "url": secure_url,
            "path": secure_url,  # Cloudinary URL acts as path for frontend referencing
            "filename": file.filename
        }
    except HTTPException:
        raise
    except Exception as upload_error:
        logger.error(f"Cloudinary upload failed: {str(upload_error)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload image to Cloudinary"
        )


@router.post("/agreement-document", response_model=ImageUploadResponse)
async def upload_agreement_document(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Upload salon agreement document (PDF or image) to Cloudinary (private).
    Requires authentication. For use by Relationship Managers during salon registration.

    Stored on Cloudinary rather than Supabase Storage to avoid the recurring
    storage RLS / service-role failures the salon-agreement bucket suffered in
    production. View documents via the signed-url endpoint below.

    Args:
        file: Document file to upload (PDF or image)
        current_user: Authenticated user from JWT (already verified by dependency)

    Returns:
        JSON with the Cloudinary URL (persist it and pass to the signed-url endpoint to view)
    """
    # Validate document file type
    if file.content_type not in ALLOWED_DOCUMENT_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Allowed types: PDF, JPEG, PNG, WebP"
        )

    # Check file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file extension. Allowed: {', '.join(ALLOWED_DOCUMENT_EXTENSIONS)}"
        )

    # Check file size (10MB for documents)
    file_content = await file.read()
    if len(file_content) > MAX_DOCUMENT_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {MAX_DOCUMENT_SIZE / 1024 / 1024}MB"
        )
    # Reset pointer so CloudinaryService can read the file again
    await file.seek(0)

    try:
        cloudinary_service = CloudinaryService()
        secure_url = await cloudinary_service.upload_file(file, folder="agreements")

        logger.info(f"Agreement document uploaded by user {current_user.user_id}: {secure_url}")

        # Persist the Cloudinary URL as both 'url' and 'path'; the frontend stores
        # 'path' and passes it to the signed-url endpoint for private viewing.
        return {
            "success": True,
            "url": secure_url,
            "path": secure_url,
            "filename": file.filename
        }
    except HTTPException:
        raise
    except Exception as upload_error:
        logger.error(f"Agreement document upload failed: {str(upload_error)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload agreement document"
        )


@router.get("/agreement-document/signed-url")
async def get_agreement_document_signed_url(
    path: str = Query(..., description="Cloudinary URL (new) or legacy Supabase storage path (e.g., 'agreements/abc123.pdf')"),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Generate a signed URL for viewing a private agreement document.

    Dual-read: new documents live on Cloudinary (private) and are served via a
    Cloudinary signed download URL; legacy documents still in the Supabase
    salon-agreement bucket are served via a Supabase signed URL.

    Args:
        path: Cloudinary URL or legacy Supabase storage path
        current_user: Authenticated user (RMs and admins can access, verified at API level)

    Returns:
        JSON with a time-limited signed URL
    """
    # New documents: Cloudinary-hosted (private) -> Cloudinary signed download URL.
    if "res.cloudinary.com" in path or path.startswith("cloudinary://"):
        try:
            signed_url = CloudinaryService().generate_download_url(path)
            logger.info(f"Cloudinary signed URL generated for {path} by user {current_user.user_id}")
            return {
                "success": True,
                "signedUrl": signed_url,
                "expiresIn": settings.CAREER_CLOUDINARY_SIGNED_URL_TTL
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to generate Cloudinary signed URL for {path}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate signed URL"
            )

    # Legacy documents: still in the Supabase salon-agreement bucket.
    storage_client = get_storage_client()
    try:
        signed_url_response = storage_client.storage.from_('salon-agreement').create_signed_url(
            path,
            3600  # 1 hour expiration
        )

        if isinstance(signed_url_response, dict):
            signed_url = signed_url_response.get('signedURL') or signed_url_response.get('signedUrl')
        else:
            signed_url = str(signed_url_response)

        if not signed_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate signed URL"
            )

        logger.info(f"Legacy Supabase signed URL generated for {path} by user {current_user.user_id}")
        return {
            "success": True,
            "signedUrl": signed_url,
            "expiresIn": 3600
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate signed URL for {path}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate signed URL"
        )
