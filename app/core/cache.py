"""
Simple TTL Cache Implementation

Provides time-based caching for expensive operations like database config fetches.
Thread-safe implementation with automatic expiration.
"""

import time
from typing import Any, Optional, Callable, Tuple
from threading import Lock
import logging

logger = logging.getLogger(__name__)


class TTLCache:
    """
    Simple TTL (Time To Live) cache implementation.
    
    Caches a value for a specified duration. When the cache expires,
    the value is refetched using the provided loader function.
    
    Thread-safe for concurrent access.
    """
    
    def __init__(self, ttl_seconds: int = 21600):  # Default: 6 hours
        """
        Initialize TTL cache.
        
        Args:
            ttl_seconds: Time to live in seconds (default: 21600 = 6 hours)
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Optional[Any] = None
        self._expiry_time: float = 0
        self._lock = Lock()
        
    def get(self, loader: Callable[[], Any]) -> Any:
        """
        Get cached value or fetch new value if expired.
        
        Args:
            loader: Function to call if cache is expired or empty
            
        Returns:
            Cached or freshly loaded value
        """
        current_time = time.time()
        
        # Quick check without lock (optimization for hot path)
        if self._cache is not None and current_time < self._expiry_time:
            return self._cache
        
        # Acquire lock for cache update
        with self._lock:
            # Double-check after acquiring lock (another thread might have updated)
            if self._cache is not None and current_time < self._expiry_time:
                return self._cache
            
            # Cache expired or empty - fetch new value
            logger.info(f"Cache expired or empty, fetching new value (TTL: {self.ttl_seconds}s)")
            self._cache = loader()
            self._expiry_time = current_time + self.ttl_seconds
            
            return self._cache
    
    def clear(self):
        """Clear the cache manually."""
        with self._lock:
            self._cache = None
            self._expiry_time = 0
            logger.info("Cache cleared manually")
    
    def is_expired(self) -> bool:
        """Check if cache is expired without fetching."""
        return self._cache is None or time.time() >= self._expiry_time


# Global cache instance for Razorpay credentials
# 6 hours TTL - balances freshness with performance
_razorpay_credentials_cache = TTLCache(ttl_seconds=21600)


async def get_cached_razorpay_credentials(
    config_service
) -> Tuple[str, str]:
    """
    Get Razorpay credentials with caching.
    
    Fetches from database on first call, then caches for 6 hours.
    Dramatically reduces database load for payment operations.
    
    Args:
        config_service: ConfigService instance for fetching from database
        
    Returns:
        Tuple of (razorpay_key_id, razorpay_key_secret)
    """
    
    async def _fetch_credentials() -> Tuple[str, str]:
        """Internal loader function for cache."""
        logger.info("Fetching Razorpay credentials from database")
        
        key_id_config = await config_service.get_config("razorpay_key_id")
        key_secret_config = await config_service.get_config("razorpay_key_secret")
        
        razorpay_key_id = key_id_config.get("config_value")
        razorpay_key_secret = key_secret_config.get("config_value")
        
        if not razorpay_key_id or not razorpay_key_secret:
            raise ValueError("Razorpay credentials not found in database")
        
        logger.info("Razorpay credentials fetched and cached successfully")
        return (razorpay_key_id, razorpay_key_secret)
    
    # Use sync cache with async loader
    # Cache checks are synchronous, only loader is async
    if _razorpay_credentials_cache.is_expired():
        credentials = await _fetch_credentials()
        with _razorpay_credentials_cache._lock:
            _razorpay_credentials_cache._cache = credentials
            _razorpay_credentials_cache._expiry_time = time.time() + _razorpay_credentials_cache.ttl_seconds
        return credentials
    else:
        return _razorpay_credentials_cache._cache


def clear_razorpay_credentials_cache():
    """
    Manually clear Razorpay credentials cache.
    
    Useful when credentials are updated in the database and
    you need to force a refresh without waiting for TTL expiry.
    """
    _razorpay_credentials_cache.clear()
