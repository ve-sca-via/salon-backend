"""
Tests for Email Service
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.email import EmailService, MockEmailService


class TestMockEmailService:
    """Test MockEmailService functionality"""

    def test_mock_email_service_init(self):
        """Test MockEmailService initialization"""
        service = MockEmailService()
        assert service.sent_emails == []
        assert len(service.sent_emails) == 0

    @pytest.mark.asyncio
    async def test_send_vendor_approval_email(self):
        """Test sending vendor approval email"""
        service = MockEmailService()

        result = await service.send_vendor_approval_email(
            to_email="vendor@test.com",
            owner_name="John Doe",
            salon_name="Test Salon",
            registration_token="token123",
            registration_fee=5000.0
        )

        assert result == True
        assert len(service.sent_emails) == 1
        email = service.sent_emails[0]
        assert email["to_email"] == "vendor@test.com"
        assert "Test Salon" in email["subject"]
        assert "Mock approval email" in email["html_body"]

    @pytest.mark.asyncio
    async def test_send_vendor_rejection_email(self):
        """Test sending vendor rejection email"""
        service = MockEmailService()

        result = await service.send_vendor_rejection_email(
            to_email="vendor@test.com",
            owner_name="John Doe",
            salon_name="Test Salon",
            rejection_reason="Invalid documents",
            rm_name="Jane Smith"
        )

        assert result == True
        assert len(service.sent_emails) == 1
        email = service.sent_emails[0]
        assert email["to_email"] == "vendor@test.com"
        assert "Test Salon" in email["subject"]

    @pytest.mark.asyncio
    async def test_send_booking_confirmation_email(self):
        """Test sending booking confirmation email"""
        service = MockEmailService()

        result = await service.send_booking_confirmation_email(
            to_email="customer@test.com",
            customer_name="Alice Johnson",
            salon_name="Beauty Spa",
            service_name="Hair Cut",
            booking_date="2024-01-15",
            booking_time="14:00",
            staff_name="Mike",
            total_amount=1500.0,
            booking_id="BK123"
        )

        assert result == True
        assert len(service.sent_emails) == 1

    @pytest.mark.asyncio
    async def test_send_booking_cancellation_email(self):
        """Test sending booking cancellation email"""
        service = MockEmailService()

        result = await service.send_booking_cancellation_email(
            to_email="customer@test.com",
            customer_name="Alice Johnson",
            salon_name="Beauty Spa",
            service_name="Hair Cut",
            booking_date="2024-01-15",
            booking_time="14:00",
            refund_amount=1500.0,
            cancellation_reason="Customer request"
        )

        assert result == True
        assert len(service.sent_emails) == 1


class TestEmailServiceIntegration:
    """Integration tests for EmailService (using mocks)"""

    @pytest.mark.asyncio
    @patch('app.services.email.settings')
    @patch('app.services.email.EmailService._send_email_sync')
    async def test_send_vendor_approval_email_integration(self, mock_send, mock_settings):
        """Test vendor approval email sending with mocked SMTP"""
        mock_send.return_value = True
        mock_settings.EMAIL_ENABLED = True

        service = EmailService()
        result = await service.send_vendor_approval_email(
            to_email="vendor@test.com",
            owner_name="John Doe",
            salon_name="Test Salon",
            registration_token="token123",
            registration_fee=5000.0
        )

        assert result == True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.services.email.settings')
    @patch('app.services.email.EmailService._send_email_sync')
    async def test_send_booking_confirmation_email_integration(self, mock_send, mock_settings):
        """Test booking confirmation email with mocked SMTP"""
        mock_send.return_value = True
        mock_settings.EMAIL_ENABLED = True

        service = EmailService()
        result = await service.send_booking_confirmation_email(
            to_email="customer@test.com",
            customer_name="Alice",
            salon_name="Salon",
            services=[{"name": "Hair Cut", "price": 1000}],
            booking_date="2024-01-01",
            booking_time="10:00",
            staff_name="Staff",
            total_amount=1000.0,
            booking_id="BK001"
        )

        assert result == True
        mock_send.assert_called_once()