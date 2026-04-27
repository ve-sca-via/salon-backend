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


