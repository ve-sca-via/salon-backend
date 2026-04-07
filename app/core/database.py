"""
Centralized Database Client Management

This module provides Supabase client instances for the entire application.

- get_auth_client(): Returns auth client (ANON key for sign_in operations)
- get_db(): Returns database client (SERVICE_ROLE key, bypasses RLS)
"""
from supabase import create_client, Client
from app.core.config import settings
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# =====================================================
# SINGLETON INSTANCES
# =====================================================
# These clients are created once and reused across all requests
# to avoid memory leaks and connection pool exhaustion
_db_client: Optional[Client] = None
_auth_client: Optional[Client] = None


def get_db() -> Client:
    """
    Return the shared database client.

    Raises:
        RuntimeError: If Supabase database credentials are missing.
    """
    global _db_client
    
    # Return existing singleton if already created
    if _db_client is not None:
        return _db_client
    
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase database credentials are missing")
    
    # Create the shared database client
    logger.info("Creating SINGLETON Supabase client (SERVICE_ROLE - bypasses RLS)")
    _db_client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY
    )
    return _db_client


def get_auth_client() -> Client:
    """
    Return the shared auth client.

    Raises:
        RuntimeError: If Supabase auth credentials are missing.
    """
    global _auth_client
    
    # Return existing singleton if already created
    if _auth_client is not None:
        return _auth_client
    
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        raise RuntimeError("Supabase auth credentials are missing")
    
    # Create the shared auth client
    logger.info("Creating SINGLETON Supabase auth client (ANON)")
    _auth_client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY
    )
    return _auth_client


# =====================================================
# FASTAPI DEPENDENCIES
# =====================================================

def get_db_client() -> Client:
    """
    FastAPI dependency that returns the database client.
    """
    return get_db()


# =====================================================
# STORAGE CLIENT (with token refresh)
# =====================================================
_storage_client: Client = None
_storage_client_created_at: float = 0
STORAGE_CLIENT_TTL = 3000  # 50 minutes (before 1-hour token expiry)


def get_storage_client() -> Client:
    """
    Return the shared storage client and refresh it when needed.
    """
    global _storage_client, _storage_client_created_at
    
    import time
    from fastapi import HTTPException, status
    
    current_time = time.time()
    
    # Refresh the client when it is missing or expired
    if _storage_client is None or (current_time - _storage_client_created_at) > STORAGE_CLIENT_TTL:
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Storage configuration missing"
            )
        _storage_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        _storage_client_created_at = current_time
        logger.info("Storage client refreshed")
    
    return _storage_client
