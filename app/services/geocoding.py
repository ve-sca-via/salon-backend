from geopy.geocoders import GoogleV3, Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from app.core.config import settings
from typing import Optional, Tuple
import asyncio


class GeocodingService:
    def __init__(self):
        if settings.GOOGLE_MAPS_API_KEY:
            self.geocoder = GoogleV3(api_key=settings.GOOGLE_MAPS_API_KEY)
            self.provider = "google"
        else:
            # Fallback to free OpenStreetMap
            self.geocoder = Nominatim(user_agent="salon-management-app")
            self.provider = "osm"

    async def _geocode_sync(self, address: str):
        # run the blocking geopy call in a thread
        return await asyncio.to_thread(self.geocoder.geocode, address, timeout=10)

    async def _reverse_sync(self, lat: float, lon: float):
        return await asyncio.to_thread(self.geocoder.reverse, (lat, lon), timeout=10)

    async def geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Convert address to (latitude, longitude)
        Returns None if geocoding fails
        """
        try:
            location = await self._geocode_sync(address)
            if location:
                return (location.latitude, location.longitude)
            return None
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            print(f"Geocoding error: {e}")
            return None

    async def reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        """
        Convert (latitude, longitude) to address
        """
        try:
            location = await self._reverse_sync(lat, lon)
            if location:
                return location.address
            return None
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            print(f"Reverse geocoding error: {e}")
            return None


# Singleton instance
geocoding_service = GeocodingService()
