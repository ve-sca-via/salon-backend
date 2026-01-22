from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import Optional
from app.core.auth import require_admin, TokenData
from app.services.user_service import UserService, CreateUserRequest
from app.schemas.user import UserCreate, UserUpdate
from app.services.activity_log_service import ActivityLogger
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_user_service() -> UserService:
    """Dependency injection for UserService"""
    return UserService()


# =====================================================
# USER MANAGEMENT
# =====================================================

@router.get("/", operation_id="admin_get_all_users")
async def get_all_users(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Results per page (max 100)"),
    search: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: TokenData = Depends(require_admin),
    user_service: UserService = Depends(get_user_service)
):
    """Get all users with pagination and filters"""
    result = await user_service.list_users(
        page=page,
        limit=limit,
        search=search,
        role=role,  # Service layer expects 'role' parameter but uses 'user_role' column
        is_active=is_active
    )

    return result


@router.post("/", operation_id="admin_create_user")
async def create_user(
    user_data: UserCreate,
    current_user: TokenData = Depends(require_admin),
    user_service: UserService = Depends(get_user_service)
):
    """Create a new user (Relationship Manager or Customer only)"""
    # Validate required fields
    # Use Pydantic validated user_data, map to service dataclass
    role = user_data.role

    if role not in ["relationship_manager", "customer"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only create Relationship Manager or Customer accounts"
        )

    request = CreateUserRequest(
        email=user_data.email,
        full_name=user_data.full_name,
        user_role=role,
        password=user_data.password,
        phone=user_data.phone or None,
        age=user_data.age,
        gender=user_data.gender
    )

    result = await user_service.create_user(request)

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error
        )

    logger.info(f"User created by admin {current_user.user_id}: {user_data.email} ({role})")

    # Log activity
    try:
        await ActivityLogger.user_created(
            admin_id=current_user.user_id,
            new_user_id=result.user_id,
            role=role,
            email=user_data.email
        )
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")

    return {
        "success": True,
        "message": f"{role.replace('_', ' ').title()} created successfully!",
        "data": {
            "user_id": result.user_id,
            "email": user_data.email,
            "role": role
        }
    }


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    updates: UserUpdate,
    current_user: TokenData = Depends(require_admin),
    user_service: UserService = Depends(get_user_service)
):
    """Update user profile"""
    result = await user_service.update_user(user_id, updates)

    return result


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: TokenData = Depends(require_admin),
    user_service: UserService = Depends(get_user_service)
):
    """Delete user (soft delete by setting is_active=false)"""
    # Use service layer for user deletion

    result = await user_service.delete_user(user_id)

    return {
        "success": True,
        "message": "User deleted successfully",
        "data": result
    }