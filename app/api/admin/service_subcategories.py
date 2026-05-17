"""
Admin Service Subcategories Management API Endpoints
Handles subcategory CRUD operations nested under parent categories (Category 2)
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import Optional
from app.core.auth import require_admin, TokenData
from app.core.database import get_db_client
from app.schemas.admin import ServiceSubcategoryCreate, ServiceSubcategoryUpdate, StatusToggle
from app.services.activity_log_service import ActivityLogger
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# =====================================================
# SUBCATEGORIES UNDER A PARENT CATEGORY
# =====================================================

@router.get("/{category_id}/subcategories", operation_id="admin_get_subcategories")
async def get_subcategories_by_category(
    category_id: str,
    is_active: Optional[bool] = Query(None),
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Get all subcategories for a given parent category"""
    try:
        query = db.table("service_subcategories").select("*").eq("parent_category_id", category_id)
        
        if is_active is not None:
            query = query.eq("is_active", is_active)
        
        query = query.order("display_order", desc=False).order("name", desc=False)
        response = query.execute()
        
        return {"data": response.data or [], "total": len(response.data or [])}
    except Exception as e:
        logger.error(f"Error fetching subcategories for category {category_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch subcategories: {str(e)}"
        )


@router.post("/{category_id}/subcategories", operation_id="admin_create_subcategory")
async def create_subcategory(
    category_id: str,
    subcategory_data: ServiceSubcategoryCreate,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Create a new subcategory under a parent category"""
    try:
        # Verify parent category exists
        parent = db.table("service_categories").select("id, name").eq("id", category_id).execute()
        if not parent.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent category not found"
            )
        
        # Auto-assign display_order if not specified
        if subcategory_data.display_order == 0:
            max_order = db.table("service_subcategories").select("display_order").eq(
                "parent_category_id", category_id
            ).order("display_order", desc=True).limit(1).execute()
            if max_order.data:
                subcategory_data.display_order = max_order.data[0]['display_order'] + 1
            else:
                subcategory_data.display_order = 1
        
        insert_data = subcategory_data.model_dump()
        insert_data["parent_category_id"] = category_id
        
        response = db.table("service_subcategories").insert(insert_data).execute()
        created = response.data[0]
        
        # Log activity
        try:
            await ActivityLogger.log(
                user_id=current_user.user_id,
                action="service_subcategory_created",
                entity_type="service_subcategory",
                entity_id=created['id'],
                details={
                    "name": created['name'],
                    "parent_category_id": category_id,
                    "parent_category_name": parent.data[0]['name']
                }
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
        
        return {"success": True, "data": created}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating subcategory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create subcategory: {str(e)}"
        )


# =====================================================
# SUBCATEGORY-LEVEL OPERATIONS (by subcategory ID)
# =====================================================

@router.get("/subcategories/{subcategory_id}", operation_id="admin_get_subcategory")
async def get_subcategory(
    subcategory_id: str,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Get a specific subcategory by ID"""
    try:
        response = db.table("service_subcategories").select(
            "*, service_categories(id, name)"
        ).eq("id", subcategory_id).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subcategory not found"
            )
        
        return response.data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching subcategory {subcategory_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch subcategory: {str(e)}"
        )


@router.put("/subcategories/{subcategory_id}", operation_id="admin_update_subcategory")
async def update_subcategory(
    subcategory_id: str,
    subcategory_data: ServiceSubcategoryUpdate,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Update a subcategory"""
    try:
        update_data = subcategory_data.model_dump(exclude_unset=True)
        response = db.table("service_subcategories").update(update_data).eq("id", subcategory_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subcategory not found"
            )
        
        updated = response.data[0]
        
        # Log activity
        try:
            await ActivityLogger.log(
                user_id=current_user.user_id,
                action="service_subcategory_updated",
                entity_type="service_subcategory",
                entity_id=subcategory_id,
                details={"name": updated['name'], "updated_fields": list(update_data.keys())}
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
        
        return {"success": True, "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating subcategory {subcategory_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update subcategory: {str(e)}"
        )


@router.patch("/subcategories/{subcategory_id}/toggle-status", operation_id="admin_toggle_subcategory_status")
async def toggle_subcategory_status(
    subcategory_id: str,
    status_data: StatusToggle,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Toggle subcategory active status"""
    try:
        response = db.table("service_subcategories").update({
            "is_active": status_data.is_active
        }).eq("id", subcategory_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subcategory not found"
            )
        
        updated = response.data[0]
        
        # Log activity
        try:
            await ActivityLogger.log(
                user_id=current_user.user_id,
                action="service_subcategory_status_toggled",
                entity_type="service_subcategory",
                entity_id=subcategory_id,
                details={"name": updated['name'], "is_active": status_data.is_active}
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
        
        return {"success": True, "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling subcategory status {subcategory_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle subcategory status: {str(e)}"
        )


@router.delete("/subcategories/{subcategory_id}", operation_id="admin_delete_subcategory")
async def delete_subcategory(
    subcategory_id: str,
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Delete a subcategory — prevents deletion if services are using it"""
    try:
        # Check if any services reference this subcategory
        services_response = db.table("services").select("id, name").eq("subcategory_id", subcategory_id).execute()
        
        if services_response.data:
            service_count = len(services_response.data)
            service_names = [s['name'] for s in services_response.data[:3]]
            names_str = ', '.join(service_names)
            more_text = f' and {service_count - 3} more' if service_count > 3 else ''
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete subcategory. {service_count} service(s) are using it: {names_str}{more_text}. Please reassign or delete these services first."
            )
        
        # Get subcategory info before deleting
        subcategory_response = db.table("service_subcategories").select("*").eq("id", subcategory_id).single().execute()
        
        if not subcategory_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subcategory not found"
            )
        
        deleted_subcategory = subcategory_response.data
        
        # Delete the subcategory
        db.table("service_subcategories").delete().eq("id", subcategory_id).execute()
        
        # Log activity
        try:
            await ActivityLogger.log(
                user_id=current_user.user_id,
                action="service_subcategory_deleted",
                entity_type="service_subcategory",
                entity_id=subcategory_id,
                details={"name": deleted_subcategory.get('name', 'Unknown')}
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
        
        return {"success": True, "message": "Subcategory deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting subcategory {subcategory_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete subcategory: {str(e)}"
        )


@router.get("/all-subcategories", operation_id="admin_get_all_subcategories")
async def get_all_subcategories(
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Get all subcategories with their parent category info (useful for admin overview)"""
    try:
        response = db.table("service_subcategories").select(
            "*, service_categories(id, name)"
        ).order("parent_category_id").order("display_order").execute()
        
        return {"data": response.data or [], "total": len(response.data or [])}
    except Exception as e:
        logger.error(f"Error fetching all subcategories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch subcategories: {str(e)}"
        )
