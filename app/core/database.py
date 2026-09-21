"""
Centralized Database Client Management

This module provides Supabase client instances for the entire application.

- get_auth_client(): Returns auth client (ANON key for sign_in operations)
- get_db(): Returns database client (SERVICE_ROLE key, bypasses RLS)
"""
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
from app.core.config import settings
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _isolated_options() -> ClientOptions:
    """
    Build a fresh ClientOptions for every create_client() call.

    supabase-py 2.0.3 declares `def __init__(self, url, key, options=ClientOptions())`
    - a mutable default argument, evaluated once at import. Client.__init__ then does
    `options.headers.update(self._get_auth_headers())`, so every client built without
    an explicit `options` mutates that ONE shared headers dict. The GoTrue client keeps
    a reference to it (and passes the same dict to self.admin), so creating the anon
    client overwrites the service-role client's Authorization header with the anon key,
    and every db.auth.admin.* call then fails with GoTrue's "User not allowed".

    Because RLS is disabled here (migrations/20251123000000_...), PostgREST table calls
    keep working with either key, so the only visible symptom is admin auth operations
    breaking - e.g. creating a relationship manager from the admin panel.

    Passing a fresh ClientOptions() gives each client its own headers dict
    (ClientOptions.headers uses field(default_factory=DEFAULT_HEADERS.copy)).
    """
    return ClientOptions()

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
        settings.SUPABASE_SERVICE_ROLE_KEY,
        options=_isolated_options(),
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
        settings.SUPABASE_ANON_KEY,
        options=_isolated_options(),
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
        _storage_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
            options=_isolated_options(),
        )
        _storage_client_created_at = current_time
        logger.info("Storage client refreshed")
    
    return _storage_client
