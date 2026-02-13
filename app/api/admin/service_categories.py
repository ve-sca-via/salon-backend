"""
Admin Service Categories Management API Endpoints
Handles service categories CRUD operations for admins
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query, UploadFile, File
from typing import Optional
from app.core.auth import require_admin, TokenData
from app.core.database import get_db_client
from app.schemas.admin import ServiceCategoryCreate, ServiceCategoryUpdate, StatusToggle
from app.services.storage_service import StorageService
from app.services.activity_log_service import ActivityLogger
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# =====================================================
# SERVICE CATEGORIES MANAGEMENT
# =====================================================

@router.get("", operation_id="admin_get_all_service_categories")
async def get_all_service_categories(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    is_active: Optional[bool] = Query(None),
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Get all service categories with optional filtering"""
    try:
        query = db.table("service_categories").select("*")
        
        # Filter by active status if provided
        if is_active is not None:
            query = query.eq("is_active", is_active)
        
        # Order by display_order and then by name
        query = query.order("display_order", desc=False).order("name", desc=False)
        
        response = query.range(offset, offset + limit - 1).execute()
        
        return {"data": response.data, "total": len(response.data)}
    except Exception as e:
        logger.error(f"Error fetching service categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch service categories: {str(e)}"
        )


@router.get("/{category_id}", operation_id="admin_get_service_category")
async def get_service_category(
    category_id: str,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Get a specific service category by ID"""
    try:
        response = db.table("service_categories").select("*").eq("id", category_id).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service category not found"
            )
        
        return response.data
    except Exception as e:
        logger.error(f"Error fetching service category {category_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch service category: {str(e)}"
        )


@router.post("", operation_id="admin_create_service_category")
async def create_service_category(
    category_data: ServiceCategoryCreate,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Create a new service category"""
    try:
        # If display_order is 0 or not specified, set it to the end
        if category_data.display_order == 0:
            max_order_response = db.table("service_categories").select("display_order").order("display_order", desc=True).limit(1).execute()
            if max_order_response.data:
                category_data.display_order = max_order_response.data[0]['display_order'] + 1
            else:
                category_data.display_order = 1
        
        response = db.table("service_categories").insert(category_data.model_dump()).execute()
        
        created_category = response.data[0]
        
        # Log activity
        try:
            await ActivityLogger.log(
                user_id=current_user.user_id,
                action="service_category_created",
                entity_type="service_category",
                entity_id=created_category['id'],
                details={"name": created_category['name'], "display_order": created_category.get('display_order')}
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
        
        return {"success": True, "data": created_category}
    except Exception as e:
        logger.error(f"Error creating service category: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create service category: {str(e)}"
        )


@router.put("/{category_id}", operation_id="admin_update_service_category")
async def update_service_category(
    category_id: str,
    category_data: ServiceCategoryUpdate,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Update a service category"""
    try:
        update_data = category_data.model_dump(exclude_unset=True)
        response = db.table("service_categories").update(update_data).eq("id", category_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service category not found"
            )
        
        updated_category = response.data[0]
        
        # Log activity
        try:
            await ActivityLogger.log(
                user_id=current_user.user_id,
                action="service_category_updated",
                entity_type="service_category",
                entity_id=category_id,
                details={"name": updated_category['name'], "updated_fields": list(update_data.keys())}
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
        
        return {"success": True, "data": updated_category}
    except Exception as e:
        logger.error(f"Error updating service category {category_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update service category: {str(e)}"
        )


@router.patch("/{category_id}/toggle-status", operation_id="admin_toggle_service_category_status")
async def toggle_service_category_status(
    category_id: str,
    status_data: StatusToggle,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Toggle service category active status"""
    try:
        response = db.table("service_categories").update({
            "is_active": status_data.is_active
        }).eq("id", category_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service category not found"
            )
        
        updated_category = response.data[0]
        
        # Log activity
        try:
            await ActivityLogger.log(
                user_id=current_user.user_id,
                action="service_category_status_toggled",
                entity_type="service_category",
                entity_id=category_id,
                details={"name": updated_category['name'], "is_active": status_data.is_active}
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
        
        return {"success": True, "data": updated_category}
    except Exception as e:
        logger.error(f"Error toggling service category status {category_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle service category status: {str(e)}"
        )


@router.delete("/{category_id}", operation_id="admin_delete_service_category")
async def delete_service_category(
    category_id: str,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Delete a service category"""
    try:
        # Check if there are services using this category
        services_response = db.table("services").select("id, name").eq("category_id", category_id).execute()
        
        if services_response.data:
            service_count = len(services_response.data)
            service_names = [s['name'] for s in services_response.data[:3]]  # Show first 3
            names_str = ', '.join(service_names)
            more_text = f' and {service_count - 3} more' if service_count > 3 else ''
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete category. {service_count} service(s) are using it: {names_str}{more_text}. Please reassign or delete these services first."
            )
        
        # Get the category's display_order before deleting
        category_response = db.table("service_categories").select("display_order").eq("id", category_id).single().execute()
        
        if not category_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service category not found"
            )
        
        deleted_order = category_response.data['display_order']
        deleted_category = category_response.data
        
        # Delete the category
        response = db.table("service_categories").delete().eq("id", category_id).execute()
        
        # Auto-reorder: decrement display_order for all categories that came after the deleted one
        # This removes gaps in the ordering
        db.table("service_categories").update({
            "display_order": db.func("display_order - 1")
        }).gt("display_order", deleted_order).execute()
        
        # Log activity
        try:
            await ActivityLogger.log(
                user_id=current_user.user_id,
                action="service_category_deleted",
                entity_type="service_category",
                entity_id=category_id,
                details={"name": deleted_category.get('name', 'Unknown')}
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
        
        return {"success": True, "message": "Service category deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting service category {category_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete service category: {str(e)}"
        )


@router.post("/reorder", operation_id="admin_reorder_service_categories")
async def reorder_service_categories(
    order_data: list[dict],
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """
    Bulk reorder service categories
    
    Expects: [{"id": "uuid", "display_order": 1}, {"id": "uuid", "display_order": 2}, ...]
    """
    try:
        # Update each category's display_order
        for item in order_data:
            db.table("service_categories").update({
                "display_order": item["display_order"]
            }).eq("id", item["id"]).execute()
        
        return {"success": True, "message": f"Reordered {len(order_data)} categories"}
    except Exception as e:
        logger.error(f"Error reordering service categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reorder categories: {str(e)}"
        )


@router.post("/upload-icon", operation_id="admin_upload_service_category_icon")
async def upload_service_category_icon(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Upload an icon image for a service category"""
    try:
        # Validate file type
        allowed_types = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/svg+xml"}
        
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Allowed types: JPEG, PNG, WebP, SVG"
            )
        
        # Check file size (max 5MB)
        content = await file.read()
        file_size = len(content)
        if file_size > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size exceeds 5MB limit"
            )
        
        # Reset file pointer
        await file.seek(0)
        
        # Upload to storage using StorageService
        storage_service = StorageService(db)
        storage_path = await storage_service.upload_file(
            file=file,
            bucket="service-category-icons",
            folder="icons",
            custom_filename=None  # Let it generate UUID filename
        )
        
        # Get public URL
        public_url = db.storage.from_("service-category-icons").get_public_url(storage_path)
        
        return {"success": True, "url": public_url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading service category icon: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload icon: {str(e)}"
        )
