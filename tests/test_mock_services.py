"""
Test to demonstrate how mock services work in test mode
"""
import pytest
from unittest.mock import patch, MagicMock

# Import services after patching settings
from app.services.email import email_service, MockEmailService, get_email_service
from app.services.geocoding import geocoding_service, MockGeocodingService, get_geocoding_service


def test_email_service_is_mocked():
    """Verify email service is mocked in test mode"""
    # In test mode, email_service should be MockEmailService
    assert isinstance(email_service, MockEmailService)
    print("✅ Email service is MockEmailService!")


def test_geocoding_service_is_mocked():
    """Verify geocoding service is mocked in test mode"""
    # In test mode, geocoding_service should be MockGeocodingService
    assert isinstance(geocoding_service, MockGeocodingService)
    print("✅ Geocoding service is MockGeocodingService!")


@pytest.mark.asyncio
async def test_mock_email_sending():
    """Test that mock email service stores emails without sending"""
    # Clear any previous emails
    email_service.sent_emails = []

    # Send an email
    result = await email_service.send_vendor_approval_email(
        to_email="test@example.com",
        owner_name="John Doe",
        salon_name="Test Salon",
        registration_token="fake_token_123",
        registration_fee=5000.0
    )

    # Check email was "sent" (stored)
    assert result == True
    assert len(email_service.sent_emails) == 1

    # Check email data
    sent_email = email_service.sent_emails[0]
    assert sent_email["to_email"] == "test@example.com"
    assert "Test Salon" in sent_email["subject"]
    
    print(f"✅ Mock email stored: {sent_email['subject']}")
    print(f"   To: {sent_email['to_email']}")


async def test_mock_geocoding():
    """Test that mock geocoding returns fake coordinates"""
    # Geocode an address
    coords = await geocoding_service.geocode_address("123 Test Street, Mumbai")
    
    # Should return fake Mumbai coordinates
    assert coords is not None
    assert coords == (19.0760, 72.8777)
    
    print(f"✅ Mock geocoding returned: {coords}")


async def test_mock_reverse_geocoding():
    """Test that mock reverse geocoding returns fake address"""
    # Reverse geocode coordinates
    address = await geocoding_service.reverse_geocode(19.0760, 72.8777)
    
    # Should return fake address
    assert address is not None
    assert address["city"] == "Mumbai"
    assert address["state"] == "Maharashtra"
    
    print(f"✅ Mock reverse geocoding returned: {address['formatted_address']}")


if __name__ == "__main__":
    print("=" * 80)
    print("TESTING MOCK SERVICES")
    print("=" * 80)
    
    # Run tests
    test_email_service_is_mocked()
    test_geocoding_service_is_mocked()
    
    import asyncio
    asyncio.run(test_mock_email_sending())
    asyncio.run(test_mock_geocoding())
    asyncio.run(test_mock_reverse_geocoding())
    
    print("=" * 80)
    print("ALL TESTS PASSED! ✅")
    print("=" * 80)
