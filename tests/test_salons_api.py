"""
Integration tests for salons API endpoints
"""
import pytest
import logging
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.core.database import MockSupabaseClient

logger = logging.getLogger(__name__)


class TestSalonsAPI:
    """Test salons API endpoints"""

    def test_get_public_salons_success(self, client, mock_db):
        """Test getting public salons"""
        with patch('app.services.salon_service.SalonService.get_public_salons', new_callable=AsyncMock) as mock_get_public:
            mock_get_public.return_value = [
                {
                    "id": "salon1",
                    "business_name": "Test Salon",
                    "business_type": "salon",
                    "city": "Mumbai",
                    "state": "Maharashtra",
                    "latitude": 19.0760,
                    "longitude": 72.8777,
                    "logo_url": None,
                    "average_rating": 4.5,
                    "total_reviews": 25,
                    "is_active": True,
                    "distance_km": None
                }
            ]

            with patch('app.core.database.get_db_client', return_value=mock_db):

                response = client.get("/api/v1/salons/public")

                assert response.status_code == 200
                data = response.json()
                assert "salons" in data
                assert len(data["salons"]) == 1
                assert data["salons"][0]["business_name"] == "Test Salon"

    def test_get_public_salons_with_filters(self, client, mock_db):
        """Test getting public salons with city filter"""
        with patch('app.services.salon_service.SalonService.get_public_salons', new_callable=AsyncMock) as mock_get_public:
            mock_get_public.return_value = [
                {
                    "id": "salon1",
                    "business_name": "Mumbai Salon",
                    "business_type": "salon",
                    "city": "Mumbai",
                    "state": "Maharashtra",
                    "latitude": 19.0760,
                    "longitude": 72.8777,
                    "logo_url": None,
                    "average_rating": 4.5,
                    "total_reviews": 25,
                    "is_active": True,
                    "distance_km": None
                }
            ]

            with patch('app.core.database.get_db_client', return_value=mock_db):

                response = client.get("/api/v1/salons/public?city=Mumbai&limit=10&offset=0")

                assert response.status_code == 200
                data = response.json()
                assert data["count"] == 1
                assert data["limit"] == 10
                assert data["offset"] == 0

    def test_get_salon_detail_success(self, client, mock_db):
        """Test getting salon detail"""
        with patch('app.services.salon_service.SalonService.get_salon', new_callable=AsyncMock) as mock_get_detail:
            mock_get_detail.return_value = {
                "id": "salon1",
                "business_name": "Test Salon",
                "business_type": "salon",
                "description": "A test salon",
                "address": "123 Test St",
                "city": "Mumbai",
                "state": "Maharashtra",
                "latitude": 19.0760,
                "longitude": 72.8777,
                "is_active": True,
                "is_verified": True,
                "registration_fee_paid": True,
                "services": [
                    {"id": "service1", "name": "Hair Cut", "price": 500}
                ],
                "salon_staff": [
                    {"id": "staff1", "name": "John Doe", "role": "stylist"}
                ]
            }

            with patch('app.core.database.get_db_client', return_value=mock_db):

                response = client.get("/api/v1/salons/salon1")

                assert response.status_code == 200
                data = response.json()
                assert data["name"] == "Test Salon"
                assert data["id"] == "salon1"

    def test_get_salon_detail_not_found(self, client, mock_db):
        """Test getting salon detail for non-existent salon"""
        with patch('app.services.salon_service.SalonService.get_salon', new_callable=AsyncMock) as mock_get_detail:
            mock_get_detail.side_effect = ValueError("Salon not found")

            with patch('app.core.database.get_db_client', return_value=mock_db):

                response = client.get("/api/v1/salons/nonexistent")

                assert response.status_code == 500  # Or appropriate error code

    def test_get_salon_services_success(self, client, mock_db):
        """Test getting salon services"""
        with patch('app.services.salon_service.SalonService.get_salon_services', new_callable=AsyncMock) as mock_get_services:
            mock_get_services.return_value = [
                {
                    "id": "service1",
                    "name": "Hair Cut",
                    "price": 500,
                    "duration": 30
                }
            ]

            with patch('app.core.database.get_db_client', return_value=mock_db):

                response = client.get("/api/v1/salons/salon1/services")

                assert response.status_code == 200
                data = response.json()
                assert "services" in data
                assert len(data["services"]) == 1

    def test_get_salon_staff_success(self, client, mock_db):
        """Test getting salon staff"""
        with patch('app.services.salon_service.SalonService.get_salon_staff', new_callable=AsyncMock) as mock_get_staff:
            mock_get_staff.return_value = [
                {
                    "id": "staff1",
                    "name": "John Doe",
                    "role": "stylist"
                }
            ]

            with patch('app.core.database.get_db_client', return_value=mock_db):

                response = client.get("/api/v1/salons/salon1/staff")

                assert response.status_code == 200
                data = response.json()
                assert "staff" in data
                assert len(data["staff"]) == 1

    def test_get_available_slots_success(self, client, mock_db):
        """Test getting available booking slots"""
        # Mock the get_salon call
        with patch('app.services.salon_service.SalonService.get_salon', new_callable=AsyncMock) as mock_get_salon:
            mock_get_salon.return_value = {
                "id": "salon1",
                "business_name": "Test Salon",
                "is_active": True,
                "is_verified": True,
                "registration_fee_paid": True,
                "opening_time": "09:00:00",
                "closing_time": "18:00:00"
            }
            
            # Mock the bookings query
            mock_bookings_result = MagicMock()
            mock_bookings_result.data = []
            
            with patch.object(mock_db, 'table') as mock_table:
                mock_table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value = mock_bookings_result

                response = client.get("/api/v1/salons/salon1/available-slots?date=2024-01-15&service_id=service1")

                assert response.status_code == 200
                data = response.json()
                assert "slots" in data
                assert len(data["available_slots"]) >= 1

    def test_search_salons_success(self, client, mock_db):
        """Test searching salons"""
        with patch('app.services.salon_service.SalonService.search_salons_by_query', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [
                {
                    "id": "salon1",
                    "business_name": "Test Salon",
                    "business_type": "salon",
                    "city": "Mumbai",
                    "state": "Maharashtra",
                    "latitude": 19.0760,
                    "longitude": 72.8777,
                    "is_active": True,
                    "is_verified": True,
                    "average_rating": 4.5,
                    "total_reviews": 25
                }
            ]

            with patch('app.core.database.get_db_client', return_value=mock_db):

                response = client.get("/api/v1/salons/search/query?q=test&limit=10")

                assert response.status_code == 200
                data = response.json()
                assert "salons" in data
                assert len(data["salons"]) == 1

    def test_get_nearby_salons_success(self, client, mock_db):
        """Test getting nearby salons"""
        with patch('app.services.salon_service.SalonService.get_nearby_salons', new_callable=AsyncMock) as mock_nearby:
            mock_nearby.return_value = [
                {
                    "id": "salon1",
                    "name": "Nearby Salon",
                    "distance_km": 2.5
                }
            ]

            with patch('app.core.database.get_db_client', return_value=mock_db):

                response = client.get("/api/v1/salons/search/nearby?lat=19.0760&lon=72.8777&radius=5")

                assert response.status_code == 200
                data = response.json()
                assert "salons" in data
                assert len(data["salons"]) == 1
                assert data["count"] == 1
                assert "query" in data
                assert data["query"]["lat"] == 19.0760
                assert data["query"]["lon"] == 72.8777
                assert data["query"]["radius"] == 5