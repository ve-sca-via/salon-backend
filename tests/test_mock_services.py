"""
Test to demonstrate how mock services work in test mode
"""
import pytest
from unittest.mock import patch, MagicMock
from tests.mocks import MockEmailService, MockGeocodingService

# Import services 
from app.services.email import email_service
from app.services.geocoding import geocoding_service


@pytest.mark.asyncio
async def test_mock_email_sending():
    """Test that mock email service stores emails using patch"""
    
    # We patch the GLOBAL 'email_service' in the app.services.email module
    # or we can patch the methods if we want to spy on them.
    # Since we want to use our MockEmailService logic, we can replace the object.
    
    with patch('app.services.email.email_service', new_callable=MockEmailService) as mock_service:
        # Send an email
        result = await mock_service.send_vendor_approval_email(
            to_email="test@example.com",
            owner_name="John Doe",
            salon_name="Test Salon",
            registration_token="fake_token_123",
            registration_fee=5000.0
        )

        # Check email was "sent" (stored in our mock)
        assert result == True
        assert len(mock_service.sent_emails) == 1

        # Check email data
        sent_email = mock_service.sent_emails[0]
        assert sent_email["to_email"] == "test@example.com"
        assert "Test Salon" in sent_email["subject"]
        
        print(f"Mock email stored: {sent_email['subject']}")


@pytest.mark.asyncio
async def test_mock_geocoding():
    """Test that mock geocoding returns fake coordinates using patch"""
    
    with patch('app.services.geocoding.geocoding_service', new_callable=MockGeocodingService) as mock_service:
        # Geocode an address
        coords = await mock_service.geocode_address("123 Test Street, Mumbai")
        
        # Should return fake Mumbai coordinates
        assert coords is not None
        assert coords == (19.0760, 72.8777)
        
        print(f"Mock geocoding returned: {coords}")


@pytest.mark.asyncio
async def test_mock_reverse_geocoding():
    """Test that mock reverse geocoding returns fake address using patch"""
    
    with patch('app.services.geocoding.geocoding_service', new_callable=MockGeocodingService) as mock_service:
        # Reverse geocode coordinates
        address = await mock_service.reverse_geocode(19.0760, 72.8777)
        
        # Should return fake address
        assert address is not None
        assert address["city"] == "Mumbai"
        assert address["state"] == "Maharashtra"
        
        print(f"Mock reverse geocoding returned: {address['formatted_address']}")


if __name__ == "__main__":
    print("=" * 80)
    print("TESTING MOCK SERVICES")
    print("=" * 80)
    
    import asyncio
    asyncio.run(test_mock_email_sending())
    asyncio.run(test_mock_geocoding())
    asyncio.run(test_mock_reverse_geocoding())
    
    print("=" * 80)
    print("ALL TESTS PASSED!")
    print("=" * 80)
