"""
Config Service
Handles system configuration CRUD operations
"""
from time import monotonic
from typing import List, Dict, Any, Optional, Tuple
from app.schemas.request.admin import SystemConfigUpdate
from app.core.encryption import get_encryption_service
from app.core.config import settings
from app.core.database import db_exec
import logging

logger = logging.getLogger(__name__)

# Sensitive configuration keys that should be encrypted
SENSITIVE_CONFIG_KEYS = {
    'razorpay_key_secret',
    'razorpay_key_id',
    'razorpay_webhook_secret',
    'resend_api_key',
}

# =====================================================
# SHORT-LIVED VALUE CACHE
# =====================================================
# The payment paths read the same handful of config keys several times per
# request — Razorpay's key_id/key_secret are read (and Fernet-decrypted) once
# per PaymentService and convenience_fee_percentage once per pricing pass, which
# cost four decrypted round trips and two config reads inside a single cart
# checkout (payment audit 10.3 / H-3 / M-2).
#
# Only the keys below are cached, and only for CONFIG_CACHE_TTL_SECONDS. Every
# write through this service drops the key, so a change made in the admin panel
# still takes effect immediately — the TTL only bounds staleness from a change
# made directly in the database. Values live in a process-local dict; the
# decrypted secrets they hold are no more exposed than the RazorpayService
# instance that already holds them for the life of a request.
CONFIG_CACHE_TTL_SECONDS = 60

CACHEABLE_CONFIG_KEYS = {
    'razorpay_key_id',
    'razorpay_key_secret',
    'razorpay_webhook_secret',
    'convenience_fee_percentage',
}

CONVENIENCE_FEE_CONFIG_KEY = 'convenience_fee_percentage'

# config_key -> (expires_at_monotonic, value)
_config_cache: Dict[str, Tuple[float, Any]] = {}


def clear_config_cache(config_key: Optional[str] = None) -> None:
    """
    Drop cached config values.

    Called on every write through ConfigService so an admin edit is visible at
    once. Tests use the no-argument form to keep a process-level cache from
    leaking one test's seeded config into the next.
    """
    if config_key is None:
        _config_cache.clear()
    else:
        _config_cache.pop(config_key, None)


def _cache_read(config_key: str) -> Any:
    """Return the cached value for a key, or None if absent/expired."""
    entry = _config_cache.get(config_key)
    if entry is None:
        return None
    expires_at, value = entry
    if expires_at <= monotonic():
        _config_cache.pop(config_key, None)
        return None
    return value


def _cache_write(config_key: str, value: Any) -> None:
    """
    Cache a config value, if the key is cacheable and the value is real.

    A None is never cached: ConfigService swallows read failures and returns the
    caller's default, so caching one would turn a single transient DB blip into
    a full minute of "payment service not configured".
    """
    if value is None or config_key not in CACHEABLE_CONFIG_KEYS:
        return
    _config_cache[config_key] = (monotonic() + CONFIG_CACHE_TTL_SECONDS, value)


# Predefined platform-native configuration schema available for admins to set
AVAILABLE_SYSTEM_CONFIGS = [
    {
        "config_key": "registration_fee_amount",
        "label": "Vendor Registration Fee",
        "config_type": "number",
        "description": "The one-time registration fee charged to vendors when joining the platform. Used during checkout."
    },
    {
        "config_key": "convenience_fee_percentage",
        "label": "Convenience Fee Percentage",
        "config_type": "number",
        "description": "The additional platform fee percentage charged to the customer at booking checkout."
    },
    {
        "config_key": "rm_score_per_approval",
        "label": "RM Score Per Approval",
        "config_type": "number",
        "description": "Score increment applied when a Relationship Manager approves a vendor."
    },
    {
        "config_key": "rm_rejection_penalty",
        "label": "RM Rejection Penalty",
        "config_type": "number",
        "description": "Score decrement applied when a Relationship Manager rejects a vendor."
    },
    {
        "config_key": "max_booking_advance_days",
        "label": "Max Booking Advance Days",
        "config_type": "number",
        "description": "Maximum days in advance a customer can book exactly."
    },
    {
        "config_key": "cancellation_window_hours",
        "label": "Cancellation Window Hours",
        "config_type": "number",
        "description": "Hours before appointment time that cancellation is allowed without penalty."
    },
    {
        "config_key": "razorpay_key_id",
        "label": "Razorpay Key ID",
        "config_type": "string",
        "description": "Public Key ID for Razorpay payments. Sent to frontend."
    },
    {
        "config_key": "razorpay_key_secret",
        "label": "Razorpay Key Secret",
        "config_type": "string",
        "description": "Private Key Secret for Razorpay signature verification. Protected and encrypted."
    },
    {
        "config_key": "razorpay_webhook_secret",
        "label": "Razorpay Webhook Secret",
        "config_type": "string",
        "description": "Secret from the Razorpay webhook settings, used to authenticate payment.captured deliveries. Without it, a payment whose browser callback is lost never becomes a booking. Protected and encrypted."
    }
]


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
            response = await db_exec(self.db.table("system_config").select("*").order(order_by))
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
            response = await db_exec(self.db.table("system_config").select(
                "*"
            ).eq("config_key", config_key))
            
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
            check_response = await db_exec(self.db.table("system_config").select(
                "id"
            ).eq("config_key", config_key).single())
            
            if not check_response.data:
                raise ValueError(f"Configuration not found: {config_key}")
            
            # Convert Pydantic model to dict and encrypt sensitive values before saving
            processed_updates = updates.model_dump(exclude_unset=True)
            if config_key in SENSITIVE_CONFIG_KEYS and 'config_value' in processed_updates:
                original_value = processed_updates['config_value']
                try:
                    encryption_service = get_encryption_service()
                    encrypted_value = encryption_service.encrypt_value(original_value)
                    
                    # Verify encryption actually happened
                    if encrypted_value == original_value:
                        logger.warning("Encryption service returned same value (NoopEncryptionService in use). Value will be stored unencrypted.")
                    else:
                        logger.info(f"Encrypted sensitive config before saving: {config_key}")
                    
                    processed_updates['config_value'] = encrypted_value
                except Exception as e:
                    logger.error(f"Failed to encrypt config {config_key}: {e}")
                    raise Exception(f"Failed to encrypt sensitive configuration: {e}")
            
            # Perform update
            response = await db_exec(self.db.table("system_config").update(
                processed_updates
            ).eq("config_key", config_key))
            
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
            
            # An admin edit must be visible on the next request, not after the TTL.
            clear_config_cache(config_key)

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
            existing = await db_exec(self.db.table("system_config").select(
                "id"
            ).eq("config_key", config_key))
            
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
            
            response = await db_exec(self.db.table("system_config").insert(new_config))
            
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

            clear_config_cache(config_key)

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
            check_response = await db_exec(self.db.table("system_config").select(
                "id"
            ).eq("config_key", config_key).single())
            
            if not check_response.data:
                raise ValueError(f"Configuration not found: {config_key}")
            
            # Delete config
            await db_exec(self.db.table("system_config").delete().eq("config_key", config_key))

            clear_config_cache(config_key)

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
    
    async def get_cached_config_value(self, config_key: str, default: Any = None) -> Any:
        """
        Get a configuration value, served from the short-lived cache when the key
        is one of CACHEABLE_CONFIG_KEYS.

        Same contract as get_config_value (missing/unreadable -> default), so it
        is a drop-in for the hot payment reads. Uncacheable keys pass straight
        through, which keeps the call sites free of per-key special cases.
        """
        cached = _cache_read(config_key)
        if cached is not None:
            return cached

        value = await self.get_config_value(config_key, default)
        _cache_write(config_key, value)
        return value

    async def get_convenience_fee_percentage(self) -> float:
        """
        The admin-managed convenience fee percentage, cached for
        CONFIG_CACHE_TTL_SECONDS.

        Single accessor for a value that was read twice per cart checkout —
        once in CustomerService.checkout_cart and again in
        BookingService.create_booking — with *different* filters: only the
        booking-side read honoured `is_active`. This honours it, which is the
        stricter of the two and the only reading that respects the admin's
        toggle. (A row with is_active false would already have failed the
        booking-side read, so no working configuration changes meaning.)

        Raises:
            ValueError: config row missing, inactive, or not a number. Every
                caller already refuses to guess a default here — a wrong
                platform fee is worse than a failed request — so each maps this
                to its own 500 message.
        """
        cached = _cache_read(CONVENIENCE_FEE_CONFIG_KEY)
        if cached is not None:
            return cached

        # maybe_single(): a missing row comes back empty instead of raising
        # PGRST116, so "not configured" stays a value check, not an exception.
        response = await db_exec(self.db.table("system_config")\
            .select("config_value")\
            .eq("config_key", CONVENIENCE_FEE_CONFIG_KEY)\
            .eq("is_active", True)\
            .maybe_single())

        row = getattr(response, "data", None)
        raw_value = row.get("config_value") if row else None
        if raw_value is None or raw_value == "":
            raise ValueError(
                f"Configuration '{CONVENIENCE_FEE_CONFIG_KEY}' is missing or inactive"
            )

        try:
            percentage = float(raw_value)
        except (TypeError, ValueError):
            raise ValueError(
                f"Configuration '{CONVENIENCE_FEE_CONFIG_KEY}' is not a number: {raw_value!r}"
            )

        _cache_write(CONVENIENCE_FEE_CONFIG_KEY, percentage)
        logger.info(f"Using convenience_fee_percentage from config: {percentage}%")
        return percentage

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
            response = await db_exec(self.db.table("system_config").select(
                "*"
            ).eq("config_type", config_type).order("config_key"))
            
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
            response = await db_exec(self.db.table("system_config").select(
                "*"
            ).or_(
                f"config_key.ilike.%{search_term}%,description.ilike.%{search_term}%"
            ).order("config_key"))
            
            logger.info(f"Found {len(response.data) if response.data else 0} configs matching '{search_term}'")
            
            return response.data if response.data else []
            
        except Exception as e:
            logger.error(f"Failed to search configurations for '{search_term}': {str(e)}")
            raise Exception(f"Failed to search configurations: {str(e)}")
