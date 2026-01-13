"""
Geocoding Service Module

Provides address-to-coordinates (geocoding) and coordinates-to-address (reverse geocoding)
functionality using either Google Maps API or Nominatim (OpenStreetMap).

Best Practices (Nominatim):
- Include User-Agent header (required)
- Include email for high-volume usage
- Rate limiting: 1 request/second for free tier
- Use format=jsonv2 for consistent JSON responses
- Enable addressdetails for structured address data
"""

from geopy.geocoders import GoogleV3, Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from app.core.config import settings
from typing import Optional, Tuple, Dict
import asyncio
import time
import logging

logger = logging.getLogger(__name__)



class GeocodingService:
    def __init__(self):
        # Initialize rate limiting attributes (needed for both providers)
        self._last_request_time = 0
        self._rate_limit_delay = 1.0
        
        # Log the API key status
        api_key = settings.GOOGLE_MAPS_API_KEY
        logger.info(f"Geocoding initialization:")
        logger.info(f"   Google Maps API key present: {bool(api_key)}")
        logger.info(f"   Google Maps API key length: {len(api_key) if api_key else 0}")
        
        # Reject placeholder values
        placeholder_values = ["your-google-maps-api-key", "YOUR_API_KEY", "xxx", ""]
        is_placeholder = any(api_key == placeholder for placeholder in placeholder_values) if api_key else True
        
        # Try Google Maps first if API key is provided AND not a placeholder
        if api_key and api_key.strip() and len(api_key) > 30 and not is_placeholder:
            try:
                self.geocoder = GoogleV3(api_key=api_key)
                self.provider = "google"
                logger.info("Geocoding: Using Google Maps API")
            except Exception as e:
                logger.warning(f"Google Maps API initialization failed: {e}")
                logger.info("Falling back to Nominatim (OpenStreetMap)")
                self._init_nominatim()
        else:
            if api_key and not is_placeholder:
                logger.warning(f"Google Maps API key is invalid (too short): '{api_key[:20]}...'")
            logger.info("Using Nominatim (OpenStreetMap) - FREE geocoding, no API key needed")
            self._init_nominatim()
    
    def _init_nominatim(self):
        """Initialize Nominatim (free OpenStreetMap geocoder)"""
        logger.info("Initializing Nominatim geocoder...")
        # User agent is required by Nominatim usage policy
        # Format: <application name> <contact email>
        user_agent = "salon-management-app/1.0 (contact: support@salonplatform.com)"
        self.geocoder = Nominatim(
            user_agent=user_agent,
            timeout=10,
            # Nominatim recommends specifying the domain for tracking
            domain='nominatim.openstreetmap.org'
        )
        self.provider = "nominatim"
        logger.info("Nominatim initialized successfully (FREE, no API key needed)")

    async def _rate_limit(self):
        """
        Enforce rate limiting for Nominatim (1 req/sec)
        Not needed for Google Maps API (has much higher limits)
        """
        if self.provider == "nominatim":
            current_time = time.time()
            time_since_last = current_time - self._last_request_time
            if time_since_last < self._rate_limit_delay:
                await asyncio.sleep(self._rate_limit_delay - time_since_last)
            self._last_request_time = time.time()

    async def _geocode_sync(self, address: str):
        """Run the blocking geopy geocode call in a thread"""
        await self._rate_limit()
        
        # Build kwargs conditionally based on provider
        kwargs = {"timeout": 10}
        if self.provider == "nominatim":
            kwargs["addressdetails"] = True
        
        return await asyncio.to_thread(
            self.geocoder.geocode, 
            address,
            **kwargs
        )

    async def _reverse_sync(self, lat: float, lon: float):
        """Run the blocking geopy reverse geocode call in a thread"""
        await self._rate_limit()
        
        # Build kwargs conditionally based on provider
        kwargs = {"timeout": 10}
        if self.provider == "nominatim":
            kwargs["zoom"] = 18  # Building level detail
            kwargs["addressdetails"] = True
        
        return await asyncio.to_thread(
            self.geocoder.reverse, 
            (lat, lon),
            **kwargs
        )

    async def geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Convert address to (latitude, longitude)
        
        Args:
            address: Full address string (e.g., "123 Main St, Mumbai, India")
            
        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
            
        Example:
            coords = await geocoding_service.geocode_address("Connaught Place, New Delhi")
            # Returns: (28.6315, 77.2167)
        """
        try:
            location = await self._geocode_sync(address)
            if location:
                return (location.latitude, location.longitude)
            return None
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            logger.error(f"[Geocoding Error - {self.provider}] {e}")
            return None
        except Exception as e:
            logger.error(f"[Unexpected Geocoding Error] {e}")
            return None

    async def reverse_geocode(self, lat: float, lon: float) -> Optional[Dict[str, any]]:
        """
        Convert (latitude, longitude) to address with detailed components
        
        Args:
            lat: Latitude coordinate
            lon: Longitude coordinate
            
        Returns:
            Dictionary with 'address' (full string) and 'components' (structured data)
            or None if reverse geocoding fails
            
        Example:
            result = await geocoding_service.reverse_geocode(28.6315, 77.2167)
            # Returns: {
            #     'address': 'Connaught Place, New Delhi, 110001, India',
            #     'components': {
            #         'road': 'Connaught Place',
            #         'city': 'New Delhi',
            #         'postcode': '110001',
            #         'country': 'India',
            #         'country_code': 'in'
            #     }
            # }
        """
        try:
            location = await self._reverse_sync(lat, lon)
            if location:
                # Build response with address string and components
                response = {
                    'address': location.address,
                    'latitude': lat,
                    'longitude': lon
                }
                
                # Add structured address components if available
                if hasattr(location, 'raw') and 'address' in location.raw:
                    response['components'] = location.raw['address']
                
                return response
            return None
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            logger.error(f"[Reverse Geocoding Error - {self.provider}] {e}")
            return None
        except Exception as e:
            logger.error(f"[Unexpected Reverse Geocoding Error] {e}")
            return None


# =====================================================
# GLOBAL INSTANCE (Singleton created at module import)
# =====================================================

geocoding_service = GeocodingService()

