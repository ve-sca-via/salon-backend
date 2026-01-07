"""
Pytest configuration and fixtures
"""
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock
import uuid

# Set test environment before any imports
os.environ["ENVIRONMENT"] = "test"

# Now import settings to ensure test mode
from app.core.config import settings
from main import app
from app.core.database import MockSupabaseClient

# Integration test imports (for Supabase Docker)
try:
    from supabase import create_client, Client
    from postgrest import SyncPostgrestClient
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    SyncPostgrestClient = None


@pytest.fixture(scope="session", autouse=True)
def set_test_environment():
    """Ensure test environment is set for all tests"""
    assert settings.ENVIRONMENT == "test", f"Expected test environment, got {settings.ENVIRONMENT}"


@pytest.fixture(scope="session")
def client():
    """FastAPI test client"""
    from main import app
    from app.core.database import get_db_client, get_auth_client, MockSupabaseClient
    from app.core.auth import get_current_user
    from unittest.mock import Mock

    # Override dependencies to use mock clients
    mock_db = MockSupabaseClient()
    mock_auth = MockSupabaseClient()

    # Mock current user for authenticated endpoints
    mock_user = Mock()
    mock_user.user_id = "test_user_123"
    mock_user.email = "test@example.com"
    mock_user.user_role = "customer"
    mock_user.jti = "test_jti_123"
    mock_user.exp = 1234567890

    app.dependency_overrides[get_db_client] = lambda: mock_db
    app.dependency_overrides[get_auth_client] = lambda: mock_auth
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with TestClient(app) as test_client:
        yield test_client

    # Clean up overrides
    app.dependency_overrides = {}


@pytest.fixture
def mock_db():
    """Mock database client"""
    return MockSupabaseClient()


@pytest.fixture
def mock_auth():
    """Mock auth client"""
    return MockSupabaseClient()


@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client for general use"""
    return MockSupabaseClient()


# =====================================================
# INTEGRATION TEST FIXTURES (for local Supabase Docker)
# =====================================================

@pytest.fixture(scope="session")
def supabase_client():
    """Use real database client for integration tests (from app's database module)"""
    # Import the real database client from the app
    from app.core.database import get_db
    
    # Get the actual Supabase client used by the app
    client = get_db()
    return client


@pytest.fixture(scope="function")
def db_integration(supabase_client):
    """Provide real database client for integration tests"""
    yield supabase_client


@pytest.fixture
def test_user_data():
    """Generate unique test user data for integration tests"""
    unique_id = str(uuid.uuid4())[:8]
    return {
        "email": f"test_{unique_id}@example.com",
        "password": "TestPassword123!",
        "full_name": f"Test User {unique_id}",
        "phone": f"+91{unique_id[:10].zfill(10)}",
        "role": "customer"
    }


@pytest.fixture
def test_salon_data():
    """Generate unique test salon data for integration tests"""
    unique_id = str(uuid.uuid4())[:8]
    return {
        "business_name": f"Test Salon {unique_id}",
        "owner_name": f"Owner {unique_id}",
        "owner_email": f"owner_{unique_id}@example.com",
        "owner_phone": f"+91{unique_id[:10].zfill(10)}",
        "address": "123 Test Street",
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400001",
        "latitude": 19.0760,
        "longitude": 72.8777,
        "is_active": True
    }


@pytest.fixture
def test_service_data():
    """Generate test service data for integration tests"""
    return {
        "name": "Haircut",
        "description": "Professional haircut service",
        "price": 500.0,
        "duration_minutes": 30,
        "is_active": True
    }


@pytest.fixture
def cleanup_records():
    """Track and cleanup test records after integration tests"""
    created_records = {
        "users": [],
        "salons": [],
        "services": [],
        "bookings": [],
        "user_carts": [],
        "reviews": [],
        "system_config": []
    }
    
    yield created_records
    
    # Cleanup happens in individual test teardown to avoid issues