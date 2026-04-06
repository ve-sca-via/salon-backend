import logging
import os
import time
import uuid
from typing import Optional, Tuple
from urllib.parse import urlparse

from fastapi import HTTPException, UploadFile, status

import cloudinary
import cloudinary.api
import cloudinary.uploader
import cloudinary.utils

from app.core.config import settings

logger = logging.getLogger(__name__)

class CloudinaryService:
    """
    Service for managing file uploads to Cloudinary.
    Provides validation, upload, and signed URL generation for private files.
    """
    
    RAW_EXTENSIONS = {".doc", ".docx"}

    def __init__(self):
        """Initialize Cloudinary service."""
        self._upload_type = settings.CAREER_CLOUDINARY_UPLOAD_TYPE
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True
        )

    @staticmethod
    def _extension(filename: str) -> str:
        if not filename or "." not in filename:
            return ""
        return f".{filename.rsplit('.', 1)[-1].lower()}"

    @staticmethod
    def _split_public_id_and_format(resource_type: str, path_value: str) -> Tuple[str, Optional[str]]:
        if resource_type == "raw":
            # Raw assets can have extension as part of public_id (e.g., resume.docx).
            # Keep it intact for delivery APIs to avoid "Resource not found".
            return path_value, None

        root, ext = os.path.splitext(path_value)
        if ext:
            return root, ext.lstrip(".")

        return path_value, None

    @staticmethod
    def _extract_from_cloudinary_url(url: str) -> Tuple[str, str, Optional[str]]:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = path.split("/")

        if len(parts) < 4:
            raise ValueError("Invalid Cloudinary URL path")

        # Standard format includes cloud name as the first path segment:
        # /<cloud_name>/<resource_type>/<asset_type>/.../public_id
        if parts[0] in {"image", "video", "raw"}:
            resource_type = parts[0]
            asset_type = parts[1]
            remainder = parts[2:]
        else:
            if len(parts) < 5:
                raise ValueError("Invalid Cloudinary URL path")
            resource_type = parts[1]
            asset_type = parts[2]
            remainder = parts[3:]

        if resource_type not in {"image", "video", "raw"}:
            raise ValueError("Invalid Cloudinary resource type in URL")
        if asset_type not in {"upload", "private"}:
            raise ValueError("Invalid Cloudinary asset type in URL")

        if remainder and remainder[0].startswith("s--"):
            remainder = remainder[1:]
        if remainder and remainder[0].startswith("v") and remainder[0][1:].isdigit():
            remainder = remainder[1:]

        if not remainder:
            raise ValueError("Could not determine Cloudinary public ID")

        path_value = "/".join(remainder)
        public_id, file_format = CloudinaryService._split_public_id_and_format(resource_type, path_value)
        return resource_type, public_id, file_format

    @staticmethod
    def _extract_from_internal_uri(uri: str) -> Tuple[str, str, Optional[str]]:
        # Legacy format: cloudinary://private/<resource_type>/<public_id_or_public_id.ext>
        raw = uri.replace("cloudinary://private/", "", 1)
        resource_type, _, rest = raw.partition("/")
        if not resource_type or not rest:
            raise ValueError("Invalid internal Cloudinary URI")
        public_id, file_format = CloudinaryService._split_public_id_and_format(resource_type, rest)
        return resource_type, public_id, file_format

    def _ensure_configured(self) -> None:
        if settings.cloudinary_is_configured:
            return

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Cloudinary is not configured. Set CLOUDINARY_CLOUD_NAME, "
                "CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET."
            )
        )

    @staticmethod
    def _download_filename(public_id: str, file_format: Optional[str]) -> Optional[str]:
        base_name = os.path.basename(public_id)
        if not base_name:
            return None
        # If public_id already includes extension (common for raw assets), use it directly.
        _, existing_ext = os.path.splitext(base_name)
        if existing_ext:
            return base_name
        if file_format and not base_name.lower().endswith(f".{file_format.lower()}"):
            return f"{base_name}.{file_format}"
        return base_name

    @staticmethod
    def _fetch_missing_format(resource_type: str, public_id: str) -> Optional[str]:
        try:
            asset = cloudinary.api.resource(
                public_id,
                resource_type=resource_type,
                type="private",
            )
            fetched_format = asset.get("format")
            return fetched_format if isinstance(fetched_format, str) and fetched_format else None
        except Exception:
            return None
    
    async def upload_file(
        self, 
        file: UploadFile, 
        folder: str,
        custom_filename: Optional[str] = None
    ) -> str:
        """
        Upload a file to Cloudinary and return the persisted Cloudinary URL.
        """
        self._ensure_configured()

        content = await file.read()
        
        file_extension = self._extension(file.filename or custom_filename or "")
        resource_type = "raw" if file_extension in self.RAW_EXTENSIONS else "auto"

        if custom_filename:
            filename_for_public_id = custom_filename if resource_type == "raw" else custom_filename.rsplit('.', 1)[0]
        else:
            filename_for_public_id = str(uuid.uuid4())
            if resource_type == "raw" and file_extension:
                filename_for_public_id = f"{filename_for_public_id}{file_extension}"

        public_id = f"{folder}/{filename_for_public_id}"
        
        try:
            result = cloudinary.uploader.upload(
                content,
                public_id=public_id,
                resource_type=resource_type,
                type=self._upload_type,
                overwrite=True
            )
            
            await file.seek(0)

            secure_url = result.get("secure_url")
            if not secure_url:
                raise ValueError("Cloudinary did not return a secure_url")

            return secure_url
            
        except Exception as e:
            logger.error(f"Error uploading file to Cloudinary: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"File upload failed: {str(e)}"
            )

    def generate_download_url(self, db_url: str, expires_in: Optional[int] = None) -> str:
        """
        Generate a download URL. Returns a signed URL for private assets
        and returns the original URL for public assets.
        """
        try:
            if not db_url or db_url in ["", "N/A"]:
                return ""

            if not db_url.startswith("cloudinary://") and "res.cloudinary.com" not in db_url:
                return db_url

            if settings.CAREER_CLOUDINARY_UPLOAD_TYPE != "private":
                return db_url

            self._ensure_configured()

            if db_url.startswith("cloudinary://"):
                resource_type, public_id, fmt = self._extract_from_internal_uri(db_url)
            else:
                resource_type, public_id, fmt = self._extract_from_cloudinary_url(db_url)

            # Raw assets frequently store extension in public_id; only fetch format when missing
            # and public_id does not already provide one.
            if not fmt and not os.path.splitext(public_id)[1]:
                fmt = self._fetch_missing_format(resource_type, public_id)

            expiry = int(time.time()) + (expires_in or settings.CAREER_CLOUDINARY_SIGNED_URL_TTL)
            # Cloudinary private assets are best delivered through the signed
            # private download endpoint, which reliably supports PDFs/images/raw files.
            attachment_name = self._download_filename(public_id, fmt)
            download_url = cloudinary.utils.private_download_url(
                public_id,
                fmt,
                resource_type=resource_type,
                type="private",
                expires_at=expiry,
                attachment=attachment_name,
            )
            return download_url
            
        except Exception as e:
            logger.error(f"Error creating Cloudinary signed URL: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate Cloudinary URL"
            )
