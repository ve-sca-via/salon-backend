"""
Config Service
Handles system configuration CRUD operations
"""
from typing import List, Dict, Any, Optional
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

# Get database client using factory function
db = get_db()


class ConfigService:
    """Service for system configuration management"""
    
    def __init__(self):
        self.db = db
    
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
            
            logger.info(f"Retrieved {len(response.data) if response.data else 0} system configurations")
            
            return response.data if response.data else []
            
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
            ).eq("config_key", config_key).single().execute()
            
            if not response.data:
                raise ValueError(f"Configuration not found: {config_key}")
            
            logger.info(f"Retrieved configuration: {config_key}")
            
            return response.data
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch configuration {config_key}: {str(e)}")
            raise Exception(f"Failed to fetch configuration: {str(e)}")
    
    async def update_config(
        self,
        config_key: str,
        updates: Dict[str, Any]
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
            
            # Perform update
            response = self.db.table("system_config").update(
                updates
            ).eq("config_key", config_key).execute()
            
            if not response.data:
                raise Exception("Update operation returned no data")
            
            updated_config = response.data[0]
            
            logger.info(f"Updated configuration: {config_key} = {updates.get('config_value', 'N/A')}")
            
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
            
            # Create new config
            new_config = {
                "config_key": config_key,
                "config_value": config_value,
                "config_type": config_type
            }
            
            if description:
                new_config["description"] = description
            
            response = self.db.table("system_config").insert(new_config).execute()
            
            if not response.data:
                raise Exception("Insert operation returned no data")
            
            created_config = response.data[0]
            
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
