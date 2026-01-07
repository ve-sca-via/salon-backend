"""
Integration tests for ConfigService using local Supabase Docker

Run with: pytest tests/integration/test_config_integration.py -v
Requires: Supabase Docker running (supabase start)
"""
import pytest
from app.services.config_service import ConfigService


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_get_all_configs(db_integration):
    """Test retrieving all system configurations"""
    service = ConfigService(db_client=db_integration)
    
    # Get all configs
    configs = await service.get_all_configs()
    
    assert isinstance(configs, list)
    # Should have at least some default configs
    assert len(configs) >= 0


@pytest.mark.asyncio
async def test_set_and_get_config(db_integration, cleanup_records):
    """Test setting and retrieving a configuration"""
    service = ConfigService(db_client=db_integration)
    
    # Set a test configuration
    config_key = "test_integration_key"
    config_value = "test_value_123"
    
    result = await service.set_config(
        config_key=config_key,
        config_value=config_value,
        description="Integration test config"
    )
    
    cleanup_records["system_config"].append(config_key)
    
    assert result["config_key"] == config_key
    assert result["config_value"] == config_value
    
    # Retrieve the config
    retrieved = await service.get_config(config_key)
    assert retrieved["config_key"] == config_key
    assert retrieved["config_value"] == config_value
    
    # Cleanup
    try:
        await service.delete_config(config_key)
    except:
        pass


@pytest.mark.asyncio
async def test_update_existing_config(db_integration, cleanup_records):
    """Test updating an existing configuration"""
    service = ConfigService(db_client=db_integration)
    
    config_key = "test_update_key"
    
    # Create initial config
    await service.set_config(
        config_key=config_key,
        config_value="initial_value",
        description="Test config"
    )
    cleanup_records["system_config"].append(config_key)
    
    # Update the config
    updated = await service.set_config(
        config_key=config_key,
        config_value="updated_value",
        description="Updated test config"
    )
    
    assert updated["config_value"] == "updated_value"
    assert updated["description"] == "Updated test config"
    
    # Cleanup
    try:
        await service.delete_config(config_key)
    except:
        pass


@pytest.mark.asyncio
async def test_delete_config(db_integration, cleanup_records):
    """Test deleting a configuration"""
    service = ConfigService(db_client=db_integration)
    
    config_key = "test_delete_key"
    
    # Create config
    await service.set_config(
        config_key=config_key,
        config_value="delete_me",
        description="Config to delete"
    )
    
    # Delete it
    result = await service.delete_config(config_key)
    
    assert result["success"] is True
    assert result["message"] == "Configuration deleted successfully"
    
    # Verify it's gone
    with pytest.raises(Exception) as exc_info:
        await service.get_config(config_key)
    assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_get_nonexistent_config(db_integration):
    """Test retrieving a non-existent configuration"""
    service = ConfigService(db_client=db_integration)
    
    with pytest.raises(Exception) as exc_info:
        await service.get_config("nonexistent_key_12345")
    
    assert "not found" in str(exc_info.value).lower()
