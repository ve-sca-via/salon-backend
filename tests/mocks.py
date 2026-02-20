from typing import Optional, List, Dict, Any, Tuple

class MockEmailService:
    """Mock Email Service for testing"""
    def __init__(self):
        self.sent_emails = []

    async def send_vendor_approval_email(self, to_email: str, owner_name: str, salon_name: str, registration_token: str, registration_fee: float, salon_id: Optional[str] = None):
        self.sent_emails.append({
            "to_email": to_email,
            "subject": f"Welcome to SalonHub - {salon_name} Approved!",
            "html_body": "Mock approval email"
        })
        return True

    async def send_vendor_rejection_email(self, to_email: str, owner_name: str, salon_name: str, rejection_reason: str, rm_name: str, request_id: Optional[str] = None):
        self.sent_emails.append({
            "to_email": to_email,
            "subject": f"Update regarding {salon_name} registration",
            "html_body": "Mock rejection email"
        })
        return True

    async def send_booking_confirmation_email(self, to_email: str, customer_name: str, salon_name: str, **kwargs):
        self.sent_emails.append({
            "to_email": to_email,
            "subject": f"Booking Confirmation - {salon_name}",
            "html_body": "Mock booking confirmation"
        })
        return True

    async def send_booking_cancellation_email(self, to_email: str, customer_name: str, salon_name: str, service_name: str, **kwargs):
        self.sent_emails.append({
            "to_email": to_email,
            "subject": f"Booking Cancelled - {salon_name}",
            "html_body": "Mock cancellation email"
        })
        return True

class MockGeocodingService:
    """Mock Geocoding Service for testing"""
    def __init__(self):
        self.provider = "mock"

    async def geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        return (19.0760, 72.8777)

    async def reverse_geocode(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        return {
            "address": "123 Test Street, Mumbai, Maharashtra, India",
            "formatted_address": "123 Test Street, Mumbai, Maharashtra, India",
            "city": "Mumbai",
            "state": "Maharashtra",
            "country": "India",
            "latitude": lat,
            "longitude": lon,
            "components": {
                "city": "Mumbai",
                "state": "Maharashtra",
                "country": "India"
            }
        }
