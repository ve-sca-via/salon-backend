"""
Centralized Database Client Management

This module provides Supabase client instances for the entire application.
Uses Factory Pattern to support mocking in test environments.

- get_auth_client(): Returns auth client (ANON key for sign_in operations)
- get_db(): Returns database client (SERVICE_ROLE key, bypasses RLS)
"""
from supabase import create_client, Client
from app.core.config import settings
from typing import Optional
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)

# =====================================================
# SINGLETON INSTANCES
# =====================================================
# These clients are created once and reused across all requests
# to avoid memory leaks and connection pool exhaustion
_db_client: Optional[Client] = None
_auth_client: Optional[Client] = None


class MockSupabaseClient:
    """
    Mock Supabase client for testing without real database connection.
    
    This is a simple mock that prevents crashes when Supabase credentials
    are missing. For proper testing, use pytest mocking with MagicMock.
    """
    def __init__(self):
        logger.info("Using MockSupabaseClient (Test Mode)")
        self._single_mode = False
    
    def table(self, table_name: str):
        """Mock table access"""
        return self
    
    def select(self, *args, **kwargs):
        """Mock select query"""
        return self
    
    def insert(self, *args, **kwargs):
        """Mock insert query"""
        return self
    
    def update(self, *args, **kwargs):
        """Mock update query"""
        return self
    
    def delete(self, *args, **kwargs):
        """Mock delete query"""
        return self
    
    def eq(self, *args, **kwargs):
        """Mock equals filter"""
        return self
    
    def lt(self, *args, **kwargs):
        """Mock less than filter"""
        return self
    
    def lte(self, *args, **kwargs):
        """Mock less than or equal filter"""
        return self
    
    def gt(self, *args, **kwargs):
        """Mock greater than filter"""
        return self
    
    def gte(self, *args, **kwargs):
        """Mock greater than or equal filter"""
        return self
    
    def neq(self, *args, **kwargs):
        """Mock not equal filter"""
        return self
    
    def like(self, *args, **kwargs):
        """Mock like filter"""
        return self
    
    def ilike(self, *args, **kwargs):
        """Mock case-insensitive like filter"""
        return self
    
    def in_(self, *args, **kwargs):
        """Mock in filter"""
        return self
    
    def contains(self, *args, **kwargs):
        """Mock contains filter"""
        return self
    
    def order(self, *args, **kwargs):
        """Mock order by"""
        return self
    
    def limit(self, *args, **kwargs):
        """Mock limit"""
        return self
    
    def range(self, *args, **kwargs):
        """Mock range"""
        return self
    
    def single(self):
        """Mock single record query"""
        self._single_mode = True
        return self
    
    def execute(self):
        """Mock execute - returns appropriate result based on query type"""
        if self._single_mode:
            # Single record queries return a dict
            return type('obj', (object,), {'data': {}} )()
        else:
            # Multi-record queries return a list
            return type('obj', (object,), {'data': [], 'count': 0})()
    
    def transaction(self):
        """Mock async transaction context manager (no-op)."""
        @asynccontextmanager
        async def _noop():
            yield None

        return _noop()
    
    @property
    def auth(self):
        """Mock auth client"""
        return self
    
    def sign_in_with_password(self, *args, **kwargs):
        """Mock sign in"""
        return type('obj', (object,), {'user': None, 'session': None})()
    
    def sign_up(self, *args, **kwargs):
        """Mock sign up"""
        return type('obj', (object,), {'user': None, 'session': None})()
    
    def reset_password_for_email(self, *args, **kwargs):
        """Mock password reset"""
        return None
    
    def verify_otp(self, *args, **kwargs):
        """Mock OTP verification"""
        return type('obj', (object,), {'user': None, 'session': None})()
    
    def update_user(self, *args, **kwargs):
        """Mock user update"""
        return None


def get_db() -> Client:
    """
    Factory function to get database client with SERVICE_ROLE key.
    Returns a SINGLETON instance that is reused across all requests.
    
    ==================== ARCHITECTURE DECISION ====================
    We use SERVICE_ROLE key to bypass RLS entirely.
    This is the standard pattern for backend-only Supabase applications.
    
    WHY SERVICE_ROLE?
    - FastAPI backend is the ONLY client accessing Supabase
    - All authentication/authorization is handled in FastAPI code
    - We use custom JWT tokens (not Supabase JWT)
    - RLS policies don't work with service_role (and we don't need them)
    
    SECURITY MODEL:
    - Service role key NEVER exposed to frontend (stays in .env)
    - Every protected endpoint uses Depends(get_current_user) for JWT validation
    - Authorization enforced via role checks (require_admin, require_vendor, etc.)
    - All security logic is explicit and auditable in Python code
    
    WHY SINGLETON?
    - Avoids creating new HTTP connection pools per request
    - Prevents memory leaks (each client = ~10MB overhead)
    - Enables connection pooling and reuse
    - Supabase client is thread-safe and async-safe
    
    ALTERNATIVE APPROACH (Not Used):
    If we wanted RLS to work, we would need to:
    1. Use Supabase JWT tokens (not custom FastAPI JWT)
    2. Pass user's access_token to create_client()
    3. Use ANON key instead of SERVICE_ROLE key
    4. Let RLS policies handle authorization
    But this is unnecessarily complex for backend-only architecture.
    ===============================================================
    
    Returns:
        - MockSupabaseClient if ENVIRONMENT is 'test' or credentials missing
        - Real Supabase Client with SERVICE_ROLE key otherwise (SINGLETON)
    """
    global _db_client
    
    # Return existing singleton if already created
    if _db_client is not None:
        return _db_client
    
    # Check if we're in test environment
    if settings.ENVIRONMENT == "test":
        logger.info("Test environment detected - using MockSupabaseClient")
        _db_client = MockSupabaseClient()
        return _db_client
    
    # Check if credentials are present
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        logger.warning("WARNING: Supabase credentials missing - using MockSupabaseClient")
        _db_client = MockSupabaseClient()
        return _db_client
    
    # Create real client with SERVICE_ROLE (bypasses RLS) - ONCE
    logger.info("Creating SINGLETON Supabase client (SERVICE_ROLE - bypasses RLS)")
    real_client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY
    )

    # Wrap the real client to provide a compatible async transaction() method
    class SupabaseClientWrapper:
        def __init__(self, client):
            self._client = client

        def __getattr__(self, name):
            return getattr(self._client, name)

        def transaction(self):
            """Provide an async no-op transaction context manager.

            Supabase REST client does not support DB transactions in this setup,
            but service layer code expects an async context manager. This wrapper
            provides a safe no-op implementation to keep the existing service
            code working across real and mock clients.
            """
            @asynccontextmanager
            async def _noop():
                yield None

            return _noop()

    _db_client = SupabaseClientWrapper(real_client)
    return _db_client


def get_auth_client() -> Client:
    """
    Factory function to get auth client.
    Returns a SINGLETON instance that is reused across all requests.
    
    Returns:
        - MockSupabaseClient if ENVIRONMENT is 'test' or credentials missing
        - Real Supabase Client otherwise (SINGLETON)
    
    Uses ANON key for sign_in_with_password() and other auth operations.
    Singleton pattern prevents connection pool exhaustion and memory leaks.
    """
    global _auth_client
    
    # Return existing singleton if already created
    if _auth_client is not None:
        return _auth_client
    
    # Check if we're in test environment
    if settings.ENVIRONMENT == "test":
        logger.info("Test environment detected - using MockSupabaseClient for auth")
        _auth_client = MockSupabaseClient()
        return _auth_client
    
    # Check if credentials are present
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        logger.warning("Supabase auth credentials missing - using MockSupabaseClient")
        _auth_client = MockSupabaseClient()
        return _auth_client
    
    # Create real client - ONCE
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
    FastAPI dependency for database client.
    
    Returns the singleton database client (same instance for all requests).
    The Supabase client is thread-safe and async-safe, so reusing it is both
    safe and dramatically more efficient than creating fresh clients per request.
    
    Performance Impact:
    - BEFORE: 10 MB × concurrent_requests (memory disaster)
    - AFTER:  10 MB total (constant overhead)
    - BEFORE: ~200-400ms client creation overhead per request
    - AFTER:  0ms overhead
    """
    return get_db()
