"""
Unit tests for AdminService
"""
import pytest
from unittest.mock import Mock, AsyncMock
from app.services.admin_service import AdminService
from app.core.database import MockSupabaseClient


class TestAdminService:
    """Test AdminService methods"""

    @pytest.fixture
    def mock_db(self):
        """Mock database client"""
        return MockSupabaseClient()

    @pytest.fixture
    def admin_service(self, mock_db):
        """AdminService instance with mocked client"""
        return AdminService(db_client=mock_db)

    @pytest.mark.asyncio
    async def test_get_dashboard_stats_success(self, admin_service, mock_db):
        """Test getting dashboard stats successfully"""
        # Simple mock
        mock_db.table = Mock(return_value=Mock())
        mock_db.table.return_value.select = Mock(return_value=Mock())
        mock_db.table.return_value.select.return_value.eq = Mock(return_value=Mock())
        mock_db.table.return_value.select.return_value.eq.return_value.execute = Mock(return_value=Mock(count=5))   

        # Mock revenue calculation
        admin_service._calculate_revenue = AsyncMock(return_value={"total": 50000.0, "this_month": 8500.0})

        result = await admin_service.get_dashboard_stats()

        assert result.pending_requests == 5
