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
import logging

logger = logging.getLogger(__name__)


class MockSupabaseClient:
    """
    Mock Supabase client for testing without real database connection.
    
    This is a simple mock that prevents crashes when Supabase credentials
    are missing. For proper testing, use pytest mocking with MagicMock.
    """
    def __init__(self):
        logger.info("🧪 Using MockSupabaseClient (Test Mode)")
    
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
    
    def execute(self):
        """Mock execute - returns empty result"""
        return type('obj', (object,), {'data': [], 'count': 0})()
    
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


def get_db() -> Client:
    """
    Factory function to get database client.
    
    Returns:
        - MockSupabaseClient if ENVIRONMENT is 'test' or credentials missing
        - Real Supabase Client otherwise
    
    This allows testing without real Supabase connection.
    """
    # Check if we're in test environment
    if settings.ENVIRONMENT == "test":
        logger.info("🧪 Test environment detected - using MockSupabaseClient")
        return MockSupabaseClient()
    
    # Check if credentials are present
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        logger.warning("⚠️  Supabase credentials missing - using MockSupabaseClient")
        return MockSupabaseClient()
    
    # Create real client
    logger.info("✅ Creating real Supabase client (SERVICE_ROLE)")
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY
    )


def get_auth_client() -> Client:
    """
    Factory function to get auth client.
    
    Returns:
        - MockSupabaseClient if ENVIRONMENT is 'test' or credentials missing
        - Real Supabase Client otherwise
    
    Uses ANON key for sign_in_with_password() and other auth operations.
    """
    # Check if we're in test environment
    if settings.ENVIRONMENT == "test":
        logger.info("🧪 Test environment detected - using MockSupabaseClient for auth")
        return MockSupabaseClient()
    
    # Check if credentials are present
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        logger.warning("⚠️  Supabase auth credentials missing - using MockSupabaseClient")
        return MockSupabaseClient()
    
    # Create real client
    logger.info("✅ Creating real Supabase auth client (ANON)")
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY
    )
