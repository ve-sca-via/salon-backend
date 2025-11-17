"""
Unit tests for SalonService
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.services.salon_service import SalonService, SalonSearchParams, NearbySearchParams
from app.core.database import MockSupabaseClient


class MockResponse:
    """Mock response object with data attribute"""
    def __init__(self, data):
        self.data = data


class TestSalonService:
    """Test SalonService methods"""

    @pytest.fixture
    def mock_db(self):
        """Mock database client"""
        return MockSupabaseClient()

    @pytest.fixture
    def salon_service(self, mock_db):
        """SalonService instance with mocked database"""
        return SalonService(db_client=mock_db)

    def test_init(self, mock_db):
        """Test service initialization"""
        service = SalonService(db_client=mock_db)
        assert service.db == mock_db

    @pytest.mark.asyncio
    async def test_get_salon_success(self, salon_service, mock_db):
        """Test getting salon by ID successfully"""
        mock_response = Mock()
        mock_response.data = {
            "id": "salon123",
            "name": "Test Salon",
            "is_active": True
        }

        with patch.object(salon_service.db, 'table') as mock_table:
            mock_table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_response

            result = await salon_service.get_salon("salon123")

            assert result["id"] == "salon123"
            assert result["name"] == "Test Salon"

    @pytest.mark.asyncio
    async def test_get_salon_not_found(self, salon_service, mock_db):
        """Test getting non-existent salon"""
        mock_response = Mock()
        mock_response.data = None

        with patch.object(salon_service.db, 'table') as mock_table:
            mock_table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_response

            with pytest.raises(ValueError, match="Salon salon123 not found"):
                await salon_service.get_salon("salon123")

    @pytest.mark.asyncio
    async def test_get_salon_with_services(self, salon_service, mock_db):
        """Test getting salon with services included"""
        mock_response = Mock()
        mock_response.data = {
            "id": "salon123",
            "name": "Test Salon",
            "services": [
                {"id": "service1", "name": "Hair Cut"}
            ]
        }

        with patch.object(salon_service.db, 'table') as mock_table:
            mock_table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_response

            result = await salon_service.get_salon("salon123", include_services=True)

            assert result["services"] is not None
            assert len(result["services"]) == 1

    @pytest.mark.asyncio
    async def test_list_salons_basic(self, salon_service, mock_db):
        """Test listing salons with basic parameters"""
        mock_response = Mock()
        mock_response.data = [
            {"id": "salon1", "name": "Salon 1"},
            {"id": "salon2", "name": "Salon 2"}
        ]

        with patch.object(salon_service.db, 'table') as mock_table:
            mock_table.return_value.select.return_value.range.return_value.order.return_value.execute.return_value = mock_response

            params = SalonSearchParams(limit=10, offset=0)
            result = await salon_service.list_salons(params)

            assert len(result) == 2
            assert result[0]["name"] == "Salon 1"

    @pytest.mark.asyncio
    async def test_list_salons_with_filters(self, salon_service, mock_db):
        """Test listing salons with filters"""
        mock_response = Mock()
        mock_response.data = [
            {"id": "salon1", "name": "Mumbai Salon", "city": "Mumbai"}
        ]

        with patch.object(salon_service.db, 'table') as mock_table:
            mock_table.return_value.select.return_value.eq.return_value.range.return_value.order.return_value.execute.return_value = mock_response

            params = SalonSearchParams(city="Mumbai", limit=10, offset=0)
            result = await salon_service.list_salons(params)

            assert len(result) == 1
            assert result[0]["city"] == "Mumbai"

    @pytest.mark.asyncio
    async def test_get_public_salons(self, salon_service, mock_db):
        """Test getting public salons"""
        mock_response = Mock()
        mock_response.data = [
            {
                "id": "salon1",
                "name": "Public Salon",
                "is_active": True,
                "is_verified": True,
                "registration_fee_paid": True
            }
        ]

        with patch.object(salon_service.db, 'table') as mock_table:
            mock_table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = mock_response

            result = await salon_service.get_public_salons(limit=10, offset=0)

            assert len(result) == 1
            assert result[0]["is_active"] is True
            assert result[0]["is_verified"] is True

    @pytest.mark.asyncio
    async def test_get_salon_services(self, salon_service, mock_db):
        """Test getting salon services"""
        services_data = [
            {"id": "service1", "name": "Hair Cut", "price": 500}
        ]

        with patch.object(salon_service, 'get_salon', new_callable=AsyncMock) as mock_get_salon, \
             patch.object(salon_service.db.table("services").select().eq().eq().order(), 'execute') as mock_execute:
            
            mock_get_salon.return_value = {
                "id": "salon123", 
                "is_active": True, 
                "is_verified": True, 
                "registration_fee_paid": True
            }
            
            mock_response = Mock()
            mock_response.data = services_data
            mock_execute.return_value = mock_response

            result = await salon_service.get_salon_services("salon123")

            assert len(result) == 1
            assert result[0]["name"] == "Hair Cut"
    @pytest.mark.asyncio
    async def test_get_salon_services(self, salon_service, mock_db):
        """Test getting salon services"""
        services_data = [
            {"id": "service1", "name": "Hair Cut", "price": 500}
        ]

        with patch.object(salon_service, 'get_salon', new_callable=AsyncMock) as mock_get_salon, \
             patch.object(salon_service.db, 'table') as mock_table:
            
            mock_get_salon.return_value = {
                "id": "salon123", 
                "is_active": True, 
                "is_verified": True, 
                "registration_fee_paid": True
            }
            
            mock_table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MockResponse(services_data)

            result = await salon_service.get_salon_services("salon123")

            assert len(result) == 1
            assert result[0]["name"] == "Hair Cut"