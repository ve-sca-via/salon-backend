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
from app.services.config_service import ConfigService
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


@router.put("/{config_key}")
async def update_config(
    config_key: str,
    update: SystemConfigUpdate,
    current_user: TokenData = Depends(require_admin),
    config_service: ConfigService = Depends(get_config_service)
):
    """Update system configuration"""
    # Prepare update data
    update_data = update.model_dump(exclude_unset=True)

    # Update config
    updated_config = await config_service.update_config(config_key, update_data)

    logger.info(f"System config updated: {config_key} = {update.config_value}")

    return {
        "success": True,
        "message": "Configuration updated successfully",
        "data": updated_config
    }


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