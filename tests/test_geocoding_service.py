"""
Tests for Geocoding Service
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.geocoding import GeocodingService, MockGeocodingService


class TestMockGeocodingService:
    """Test MockGeocodingService functionality"""

    def test_mock_geocoding_service_init(self):
        """Test MockGeocodingService initialization"""
        service = MockGeocodingService()
        assert service.provider == "mock"

    @pytest.mark.asyncio
    async def test_geocode_address(self):
        """Test mock geocoding returns fake coordinates"""
        service = MockGeocodingService()

        coords = await service.geocode_address("Mumbai, India")

        assert coords is not None
        assert len(coords) == 2
        assert coords[0] == 19.0760  # Mumbai latitude
        assert coords[1] == 72.8777  # Mumbai longitude

    @pytest.mark.asyncio
    async def test_reverse_geocode(self):
        """Test mock reverse geocoding returns fake address"""
        service = MockGeocodingService()

        result = await service.reverse_geocode(19.0760, 72.8777)

        assert result is not None
        assert "city" in result
        assert "state" in result
        assert "country" in result
        assert "formatted_address" in result
        assert result["city"] == "Mumbai"
        assert result["state"] == "Maharashtra"


class TestGeocodingServiceIntegration:
    """Integration tests for GeocodingService (using mocks)"""

    @pytest.mark.asyncio
    @patch('app.services.geocoding.GeocodingService._geocode_sync')
    async def test_geocode_address_success(self, mock_geocode):
        """Test successful geocoding with mocked geopy"""
        # Mock geopy Location object
        mock_location = MagicMock()
        mock_location.latitude = 28.6139
        mock_location.longitude = 77.2090
        mock_geocode.return_value = mock_location

        service = GeocodingService()
        coords = await service.geocode_address("New Delhi, India")

        assert coords == (28.6139, 77.2090)
        mock_geocode.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.services.geocoding.GeocodingService._geocode_sync')
    async def test_geocode_address_failure(self, mock_geocode):
        """Test geocoding failure"""
        mock_geocode.return_value = None

        service = GeocodingService()
        coords = await service.geocode_address("Invalid Address")

        assert coords is None

    @pytest.mark.asyncio
    @patch('app.services.geocoding.GeocodingService._reverse_sync')
    async def test_reverse_geocode_success(self, mock_reverse):
        """Test successful reverse geocoding"""
        # Mock geopy Location object
        mock_location = MagicMock()
        mock_location.address = "Connaught Place, New Delhi, India"
        mock_location.raw = {
            "address": {
                "road": "Connaught Place",
                "city": "New Delhi",
                "country": "India"
            }
        }
        mock_reverse.return_value = mock_location

        service = GeocodingService()
        result = await service.reverse_geocode(28.6139, 77.2090)

        assert result is not None
        assert result["address"] == "Connaught Place, New Delhi, India"
        assert "components" in result
        assert result["latitude"] == 28.6139
        assert result["longitude"] == 77.2090

    @pytest.mark.asyncio
    @patch('app.services.geocoding.GeocodingService._reverse_sync')
    async def test_reverse_geocode_failure(self, mock_reverse):
        """Test reverse geocoding failure"""
        mock_reverse.return_value = None

        service = GeocodingService()
        result = await service.reverse_geocode(0.0, 0.0)

        assert result is None


class TestGeocodingServiceProviders:
    """Test different geocoding providers"""

    @patch('app.services.geocoding.settings')
    def test_google_provider_initialization(self, mock_settings):
        """Test Google provider initialization"""
        mock_settings.GOOGLE_MAPS_API_KEY = "test_key_that_is_long_enough_for_validation"

        service = GeocodingService()
        assert service.provider == "google"

    @patch('app.services.geocoding.settings')
    def test_nominatim_provider_initialization(self, mock_settings):
        """Test Nominatim provider initialization"""
        mock_settings.GOOGLE_MAPS_API_KEY = None

        service = GeocodingService()
        assert service.provider == "nominatim"