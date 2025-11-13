"""
Fix Salon Coordinates - Retry Geocoding for Failed Salons
Run this script to geocode salons with 0.0, 0.0 coordinates
"""
import asyncio
from supabase import create_client
from app.core.config import settings
from app.services.geocoding import geocoding_service
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_salon_coordinates():
    """Retry geocoding for salons with invalid coordinates"""
    
    # Initialize Supabase client
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    
    # Find salons with 0.0 coordinates
    response = supabase.table("salons").select("*").or_(
        "latitude.eq.0,longitude.eq.0,latitude.is.null,longitude.is.null"
    ).execute()
    
    salons = response.data
    logger.info(f"🔍 Found {len(salons)} salons with missing/invalid coordinates")
    
    fixed_count = 0
    failed_count = 0
    
    for salon in salons:
        salon_id = salon['id']
        business_name = salon['business_name']
        
        logger.info(f"\n📍 Processing: {business_name} (ID: {salon_id})")
        
        # Build full address
        full_address = f"{salon['address']}, {salon['city']}, {salon['state']}, {salon['pincode']}"
        logger.info(f"   Address: {full_address}")
        
        try:
            # Try full address first
            coords = await geocoding_service.geocode_address(full_address)
            
            if coords:
                # geocode_address returns tuple (latitude, longitude)
                latitude, longitude = coords
                logger.info(f"   ✅ Geocoded to: {latitude}, {longitude}")
            else:
                # Fallback to city + state
                logger.warning(f"   ⚠️ Full address failed, trying city fallback...")
                city_coords = await geocoding_service.geocode_address(
                    f"{salon['city']}, {salon['state']}"
                )
                
                if city_coords:
                    # geocode_address returns tuple (latitude, longitude)
                    latitude, longitude = city_coords
                    logger.info(f"   ✅ City geocoded to: {latitude}, {longitude}")
                else:
                    logger.error(f"   ❌ All geocoding failed for {business_name}")
                    failed_count += 1
                    continue
            
            # Update salon coordinates
            supabase.table("salons").update({
                "latitude": latitude,
                "longitude": longitude,
                "updated_at": "now()"
            }).eq("id", salon_id).execute()
            
            logger.info(f"   💾 Updated coordinates in database")
            fixed_count += 1
            
            # Rate limiting - wait 1 second between requests (Nominatim requirement)
            await asyncio.sleep(1.1)
            
        except Exception as e:
            logger.error(f"   ❌ Error geocoding {business_name}: {str(e)}")
            failed_count += 1
    
    logger.info(f"\n✅ Summary:")
    logger.info(f"   Fixed: {fixed_count} salons")
    logger.info(f"   Failed: {failed_count} salons")
    logger.info(f"   Total: {len(salons)} salons")

if __name__ == "__main__":
    asyncio.run(fix_salon_coordinates())
