"""
Admin System Configuration API Endpoints
Handles system-wide configuration management
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List
from app.core.auth import require_admin, TokenData, cleanup_expired_tokens
from app.core.database import get_db, get_db_client
from app.schemas import (
    SystemConfigResponse,
    SystemConfigUpdate
)
from app.schemas.request.admin import SystemConfigCreate
from app.services.config_service import ConfigService
from app.services.activity_log_service import ActivityLogger
from app.core.cache import clear_razorpay_credentials_cache
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_config_service(db = Depends(get_db_client)) -> ConfigService:
    """Dependency injection for ConfigService"""
    return ConfigService(db_client=db)


# =====================================================
# SYSTEM CONFIGURATION MANAGEMENT
# =====================================================

@router.get("", response_model=List[SystemConfigResponse])
async def get_all_configs(
    current_user: TokenData = Depends(require_admin),
    config_service: ConfigService = Depends(get_config_service)
):
    """Get all system configurations"""
    configs = await config_service.get_all_configs()

    return configs


@router.get("/{config_key}", response_model=SystemConfigResponse)
async def get_config(
    config_key: str,
    current_user: TokenData = Depends(require_admin),
    config_service: ConfigService = Depends(get_config_service)
):
    """Get specific configuration"""
    config = await config_service.get_config(config_key)

    return config


@router.post("", response_model=SystemConfigResponse)
async def create_config(
    create_data: SystemConfigCreate,
    current_user: TokenData = Depends(require_admin),
    config_service: ConfigService = Depends(get_config_service)
):
    """Create a new system configuration"""
    try:
        new_config = await config_service.create_config(
            config_key=create_data.config_key,
            config_value=create_data.config_value,
            description=create_data.description,
            config_type=create_data.config_type
        )
        
        logger.info(f"System config created: {create_data.config_key} by admin {current_user.user_id}")
        
        return new_config
    
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create config: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{config_key}")
async def update_config(
    config_key: str,
    update: SystemConfigUpdate,
    current_user: TokenData = Depends(require_admin),
    config_service: ConfigService = Depends(get_config_service)
):
    """Update system configuration"""
    try:
        # Get old value first for logging
        old_config = await config_service.get_config(config_key)
        old_value = old_config.get('config_value') if old_config else None
        
        # Update config (config_service.update_config expects the update object directly)
        updated_config = await config_service.update_config(config_key, update)

        # Get the new value from the updated config
        new_value = updated_config.get('config_value') if updated_config else None
        logger.info(f"System config updated: {config_key} = {new_value}")

        # Clear Razorpay cache if credentials were updated
        if config_key in ["razorpay_key_id", "razorpay_key_secret"]:
            clear_razorpay_credentials_cache()
            logger.info(f"Razorpay credentials cache cleared after {config_key} update")

        # Log activity
        try:
            await ActivityLogger.config_updated(
                user_id=current_user.user_id,
                config_key=config_key,
                old_value=old_value,
                new_value=new_value
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")

        return {
            "success": True,
            "message": "Configuration updated successfully",
            "data": updated_config
        }
    
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update config: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{config_key}")
async def delete_config(
    config_key: str,
    current_user: TokenData = Depends(require_admin),
    config_service: ConfigService = Depends(get_config_service)
):
    """Delete a system configuration"""
    try:
        await config_service.delete_config(config_key)
        
        logger.info(f"System config deleted: {config_key} by admin {current_user.user_id}")
        
        return {
            "success": True,
            "message": f"Configuration '{config_key}' deleted successfully"
        }
    
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete config: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/cleanup/expired-tokens")
async def cleanup_expired_tokens_endpoint(
    current_user: TokenData = Depends(require_admin),
    db = Depends(get_db_client)
):
    """Clean up expired tokens from blacklist (admin only)"""
    cleaned_count = cleanup_expired_tokens(db)
    
    logger.info(f"Admin {current_user.user_id} cleaned up {cleaned_count} expired tokens")
    
    return {
        "success": True,
        "message": f"Cleaned up {cleaned_count} expired tokens from blacklist",
        "tokens_removed": cleaned_count
    }


@router.post("/cache/clear-razorpay")
async def clear_razorpay_cache(
    current_user: TokenData = Depends(require_admin)
):
    """
    Manually clear Razorpay credentials cache (admin only)
    
    Use this endpoint after updating Razorpay credentials to force
    immediate cache refresh without waiting for 6-hour TTL expiry.
    """
    clear_razorpay_credentials_cache()
    
    logger.info(f"Admin {current_user.user_id} manually cleared Razorpay credentials cache")
    
    return {
        "success": True,
        "message": "Razorpay credentials cache cleared. Next request will fetch fresh credentials from database."
    }