"""
Config Service
Handles system configuration CRUD operations
"""
from typing import List, Dict, Any, Optional
from app.schemas.request.admin import SystemConfigUpdate
from app.core.database import get_db
from app.core.encryption import get_encryption_service
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Sensitive configuration keys that should be encrypted
SENSITIVE_CONFIG_KEYS = {
    'razorpay_key_secret',
    'razorpay_key_id',
    'razorpay_webhook_secret',
    'stripe_secret_key',
    'stripe_webhook_secret',
    'smtp_password',
    'resend_api_key',
    'google_maps_api_key'
}


class ConfigService:
    """Service for system configuration management"""
    
    def __init__(self, db_client):
        self.db = db_client
    
    # =====================================================
    # CONFIGURATION CRUD OPERATIONS
    # =====================================================
    
    async def get_all_configs(self, order_by: str = "config_key") -> List[Dict[str, Any]]:
        """
        Get all system configurations
        
        Args:
            order_by: Field to order results by (default: config_key)
            
        Returns:
            List of configuration dictionaries
            
        Raises:
            Exception: If database query fails
        """
        try:
            response = self.db.table("system_config").select("*").order(order_by).execute()
            data = response.data if response.data else []

            # Auto-decrypt any sensitive config values
            if data:
                try:
                    encryption_service = get_encryption_service()
                    for cfg in data:
                        key = cfg.get("config_key")
                        if key in SENSITIVE_CONFIG_KEYS and cfg.get("config_value"):
                            try:
                                cfg["config_value"] = encryption_service.decrypt_value(cfg["config_value"])
                            except Exception:
                                # If decryption fails, leave value as-is and log
                                logger.debug(f"Failed to decrypt config: {key}")
                except Exception:
                    logger.debug("Encryption service unavailable when decrypting all configs")

            logger.info(f"Retrieved {len(data)} system configurations")

            return data
            
        except Exception as e:
            logger.error(f"Failed to fetch system configurations: {str(e)}")
            raise Exception(f"Failed to fetch configurations: {str(e)}")
    
    async def get_config(self, config_key: str) -> Dict[str, Any]:
        """
        Get a specific configuration by key
        
        Args:
            config_key: The configuration key to retrieve
            
        Returns:
            Configuration dictionary
            
        Raises:
            ValueError: If configuration not found
            Exception: If database query fails
        """
        try:
            response = self.db.table("system_config").select(
                "*"
            ).eq("config_key", config_key).execute()
            
            if not response.data or len(response.data) == 0:
                logger.error(f"Configuration not found in database: {config_key}")
                raise ValueError(f"Configuration '{config_key}' not found. Please contact system administrator.")
            
            config = response.data[0]
            
            # Auto-decrypt sensitive values
            if config_key in SENSITIVE_CONFIG_KEYS and config.get('config_value'):
                try:
                    encryption_service = get_encryption_service()
                    original_value = config['config_value']
                    
                    # Try to decrypt
                    decrypted = encryption_service.decrypt_value(original_value)
                    config['config_value'] = decrypted
                    logger.info(f"Decrypted sensitive config: {config_key}")
                except Exception as e:
                    # Decryption failed - value might be plain text or corrupted
                    logger.warning(f"Failed to decrypt config {config_key}: {e}")
                    
                    # Check if it looks like a Fernet token (starts with 'gAAAAA')
                    if isinstance(config['config_value'], str) and config['config_value'].startswith('gAAAAA'):
                        # It looks encrypted but decryption failed - serious error
                        logger.error(f"Config {config_key} appears encrypted but decryption failed")
                        if settings.is_production:
                            raise Exception(f"Failed to decrypt sensitive configuration in production: {config_key}")
                        config['config_value'] = None
                    else:
                        # Doesn't look encrypted - might be plain text from old data
                        logger.warning(f"Config {config_key} appears to be plain text, not encrypted. Consider re-encrypting.")
                        # Return the plain text value as-is (backward compatibility)
                        pass
            
            logger.info(f"Retrieved configuration: {config_key}")
            
            return config
            
        except ValueError:
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to fetch configuration {config_key}: {error_msg}")
            # Don't expose internal database errors to users
            raise Exception(f"Failed to retrieve system configuration '{config_key}'. Please contact support.")
    
    async def update_config(
        self,
        config_key: str,
        updates: SystemConfigUpdate
    ) -> Dict[str, Any]:
        """
        Update a system configuration
        
        Args:
            config_key: The configuration key to update
            updates: Dictionary of fields to update
            
        Returns:
            Updated configuration dictionary
            
        Raises:
            ValueError: If configuration not found
            Exception: If database update fails
        """
        try:
            # Verify config exists first
            check_response = self.db.table("system_config").select(
                "id"
            ).eq("config_key", config_key).single().execute()
            
            if not check_response.data:
                raise ValueError(f"Configuration not found: {config_key}")
            
            # Convert Pydantic model to dict and encrypt sensitive values before saving
            processed_updates = updates.model_dump(exclude_none=True)
            if config_key in SENSITIVE_CONFIG_KEYS and 'config_value' in processed_updates:
                original_value = processed_updates['config_value']
                try:
                    encryption_service = get_encryption_service()
                    encrypted_value = encryption_service.encrypt_value(original_value)
                    
                    # Verify encryption actually happened
                    if encrypted_value == original_value:
                        logger.warning(f"Encryption service returned same value (NoopEncryptionService in use). Value will be stored unencrypted.")
                    else:
                        logger.info(f"Encrypted sensitive config before saving: {config_key}")
                    
                    processed_updates['config_value'] = encrypted_value
                except Exception as e:
                    logger.error(f"Failed to encrypt config {config_key}: {e}")
                    raise Exception(f"Failed to encrypt sensitive configuration: {e}")
            
            # Perform update
            response = self.db.table("system_config").update(
                processed_updates
            ).eq("config_key", config_key).execute()
            
            if not response.data:
                raise Exception("Update operation returned no data")
            
            updated_config = response.data[0]
            
            # Decrypt the value in the response for consistency
            if config_key in SENSITIVE_CONFIG_KEYS and updated_config.get('config_value'):
                try:
                    encryption_service = get_encryption_service()
                    updated_config['config_value'] = encryption_service.decrypt_value(updated_config['config_value'])
                except Exception as e:
                    logger.error(f"Failed to decrypt response for {config_key}: {e}")
            
            logger.info(f"Updated configuration: {config_key}")
            
            return updated_config
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to update configuration {config_key}: {str(e)}")
            raise Exception(f"Failed to update configuration: {str(e)}")
    
    async def create_config(
        self,
        config_key: str,
        config_value: Any,
        description: Optional[str] = None,
        config_type: str = "string"
    ) -> Dict[str, Any]:
        """
        Create a new system configuration
        
        Args:
            config_key: Unique configuration key
            config_value: Configuration value
            description: Optional description
            config_type: Type of configuration (string, number, boolean, json)
            
        Returns:
            Created configuration dictionary
            
        Raises:
            ValueError: If configuration key already exists
            Exception: If database insert fails
        """
        try:
            # Check if config already exists
            existing = self.db.table("system_config").select(
                "id"
            ).eq("config_key", config_key).execute()
            
            if existing.data and len(existing.data) > 0:
                raise ValueError(f"Configuration already exists: {config_key}")
            
            # Create new config (encrypt sensitive values)
            to_store_value = config_value
            if config_key in SENSITIVE_CONFIG_KEYS and config_value is not None:
                try:
                    encryption_service = get_encryption_service()
                    encrypted = encryption_service.encrypt_value(config_value)
                    
                    # Verify encryption actually happened
                    if encrypted == config_value:
                        logger.warning(f"Encryption service returned same value (NoopEncryptionService in use). Value will be stored unencrypted for {config_key}.")
                    else:
                        logger.info(f"Encrypted sensitive config during create: {config_key}")
                    
                    to_store_value = encrypted
                except Exception as e:
                    logger.error(f"Failed to encrypt config during create {config_key}: {e}")
                    raise Exception(f"Failed to encrypt sensitive configuration: {e}")

            new_config = {
                "config_key": config_key,
                "config_value": to_store_value,
                "config_type": config_type
            }
            
            if description:
                new_config["description"] = description
            
            response = self.db.table("system_config").insert(new_config).execute()
            
            if not response.data:
                raise Exception("Insert operation returned no data")
            
            created_config = response.data[0]
            # Decrypt returned sensitive value for API consistency
            if config_key in SENSITIVE_CONFIG_KEYS and created_config.get('config_value'):
                try:
                    encryption_service = get_encryption_service()
                    created_config['config_value'] = encryption_service.decrypt_value(created_config['config_value'])
                except Exception:
                    logger.debug(f"Failed to decrypt created config {config_key}")

            logger.info(f"Created new configuration: {config_key}")

            return created_config
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to create configuration {config_key}: {str(e)}")
            raise Exception(f"Failed to create configuration: {str(e)}")
    
    async def delete_config(self, config_key: str) -> bool:
        """
        Delete a system configuration
        
        Args:
            config_key: The configuration key to delete
            
        Returns:
            True if deleted successfully
            
        Raises:
            ValueError: If configuration not found
            Exception: If database delete fails
        """
        try:
            # Verify config exists
            check_response = self.db.table("system_config").select(
                "id"
            ).eq("config_key", config_key).single().execute()
            
            if not check_response.data:
                raise ValueError(f"Configuration not found: {config_key}")
            
            # Delete config
            self.db.table("system_config").delete().eq("config_key", config_key).execute()
            
            logger.info(f"Deleted configuration: {config_key}")
            
            return True
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to delete configuration {config_key}: {str(e)}")
            raise Exception(f"Failed to delete configuration: {str(e)}")
    
    # =====================================================
    # CONFIGURATION HELPERS
    # =====================================================
    
    async def get_config_value(self, config_key: str, default: Any = None) -> Any:
        """
        Get just the value of a configuration (convenience method)
        
        Args:
            config_key: The configuration key
            default: Default value if config not found
            
        Returns:
            Configuration value or default
        """
        try:
            config = await self.get_config(config_key)
            return config.get("config_value", default)
        except ValueError:
            logger.warning(f"Configuration {config_key} not found, returning default: {default}")
            return default
        except Exception as e:
            logger.error(f"Error getting config value for {config_key}: {str(e)}")
            return default
    
    async def get_configs_by_type(self, config_type: str) -> List[Dict[str, Any]]:
        """
        Get all configurations of a specific type
        
        Args:
            config_type: Type to filter by (string, number, boolean, json)
            
        Returns:
            List of configurations matching the type
            
        Raises:
            Exception: If database query fails
        """
        try:
            response = self.db.table("system_config").select(
                "*"
            ).eq("config_type", config_type).order("config_key").execute()
            
            logger.info(f"Retrieved {len(response.data) if response.data else 0} configs of type {config_type}")
            
            return response.data if response.data else []
            
        except Exception as e:
            logger.error(f"Failed to fetch configs by type {config_type}: {str(e)}")
            raise Exception(f"Failed to fetch configurations by type: {str(e)}")
    
    async def search_configs(self, search_term: str) -> List[Dict[str, Any]]:
        """
        Search configurations by key or description
        
        Args:
            search_term: Term to search for
            
        Returns:
            List of matching configurations
            
        Raises:
            Exception: If database query fails
        """
        try:
            # Search in config_key and description fields
            response = self.db.table("system_config").select(
                "*"
            ).or_(
                f"config_key.ilike.%{search_term}%,description.ilike.%{search_term}%"
            ).order("config_key").execute()
            
            logger.info(f"Found {len(response.data) if response.data else 0} configs matching '{search_term}'")
            
            return response.data if response.data else []
            
        except Exception as e:
            logger.error(f"Failed to search configurations for '{search_term}': {str(e)}")
            raise Exception(f"Failed to search configurations: {str(e)}")
