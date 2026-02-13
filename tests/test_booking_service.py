"""
Unit tests for BookingService
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from app.services.booking_service import BookingService
from app.core.database import MockSupabaseClient


class TestBookingService:
    """Test BookingService methods"""

    @pytest.fixture
    def mock_db(self):
        """Mock database client"""
        return MockSupabaseClient()

    @pytest.fixture
    def booking_service(self, mock_db):
        """BookingService instance with mocked database"""
        return BookingService(db_client=mock_db)

    def test_init(self, mock_db):
        """Test service initialization"""
        service = BookingService(db_client=mock_db)
        assert service.db == mock_db

    @pytest.mark.asyncio
    async def test_get_bookings_customer(self, booking_service, mock_db):
        """Test getting bookings for a customer"""
        mock_response = Mock()
        mock_response.data = [
            {
                "id": "booking1",
                "customer_id": "user123",
                "status": "confirmed",
                "booking_date": "2024-01-15"
            }
        ]

        with patch.object(booking_service.db, 'table') as mock_table:
            mock_table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_response

            result = await booking_service.get_bookings(
                user_id="user123",
                current_user_id="user123",
                current_user_role="customer"
            )

            assert "bookings" in result
            assert len(result["bookings"]) == 1
            assert result["bookings"][0]["customer_id"] == "user123"

    @pytest.mark.asyncio
    async def test_get_bookings_vendor(self, booking_service, mock_db):
        """Test getting bookings for a vendor/salon"""
        mock_response = Mock()
        mock_response.data = [
            {
                "id": "booking1",
                "salon_id": "salon123",
                "status": "confirmed"
            }
        ]

        with patch.object(booking_service.db, 'table') as mock_table:
            mock_table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_response

            # Mock salon ownership verification
            with patch.object(booking_service, '_verify_salon_ownership', new_callable=AsyncMock):
                result = await booking_service.get_bookings(
                    salon_id="salon123",
                    current_user_id="vendor123",
                    current_user_role="vendor"
                )

                assert "bookings" in result
                assert len(result["bookings"]) == 1

    @pytest.mark.asyncio
    async def test_get_booking_detail(self, booking_service, mock_db):
        """Test getting booking detail"""
        mock_response = Mock()
        mock_response.data = {
            "id": "booking1",
            "customer_id": "user123",
            "salon_id": "salon123",
            "status": "confirmed",
            "services": [{"id": "service1", "name": "Hair Cut"}]
        }

        with patch.object(booking_service.db, 'table') as mock_table:
            mock_query = Mock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.single.return_value = mock_query
            mock_query.execute.return_value = mock_response
            mock_table.return_value = mock_query

            # Mock booking access verification
            with patch.object(booking_service, '_verify_booking_access', new_callable=AsyncMock):
                result = await booking_service.get_booking("booking1", "user123", "customer")

                assert result["id"] == "booking1"
                assert result["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_create_booking_success(self, booking_service, mock_db):
        """Test creating a booking successfully"""
        from app.schemas.request.booking import BookingCreate, ServiceItem
        
        booking_data = BookingCreate(
            salon_id="salon123",
            booking_date="2024-01-15",
            booking_time="10:00",
            time_slots=["10:00"],
            services=[ServiceItem(service_id="service1", quantity=1)],
            total_amount=500.0,
            notes="Test booking",
            booking_fee=50.0,
            payment_status="pending"
        )

        # Mock all the internal methods that create_booking calls
        with patch.object(booking_service, '_get_customer_profile', new_callable=AsyncMock) as mock_get_customer, \
             patch.object(booking_service, '_get_salon_details', new_callable=AsyncMock) as mock_get_salon, \
             patch.object(booking_service, '_get_services_batch', new_callable=AsyncMock) as mock_get_services, \
             patch.object(booking_service, '_send_booking_confirmation', new_callable=AsyncMock) as mock_send_email:

            mock_get_customer.return_value = {"email": "test@example.com", "full_name": "Test User"}
            mock_get_salon.return_value = {"business_name": "Test Salon"}
            mock_get_services.return_value = {
                "service1": {
                    "name": "Hair Cut",
                    "price": 500.0,
                    "duration_minutes": 60,
                    "is_active": True
                }
            }
            mock_send_email.return_value = None

            # Mock the database insert
            mock_insert_response = Mock()
            mock_insert_response.data = [{"id": "booking123", "booking_number": "BK2024001"}]

            with patch.object(booking_service.db, 'table') as mock_table:
                mock_query = Mock()
                mock_query.insert.return_value = mock_query
                mock_query.execute.return_value = mock_insert_response
                mock_table.return_value = mock_query

                result = await booking_service.create_booking(booking_data, "user123")

                assert result["id"] == "booking123"
                assert result["booking_number"] == "BK2024001"

    @pytest.mark.asyncio
    async def test_update_booking_status(self, booking_service, mock_db):
        """Test updating booking status"""
        from app.schemas.request.booking import BookingUpdate
        
        # Mock database operations
        mock_update_response = Mock()
        mock_update_response.data = [{"status": "cancelled"}]

        with patch.object(booking_service.db, 'table') as mock_table:
            mock_query = Mock()
            mock_query.update.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.execute.return_value = mock_update_response
            mock_table.return_value = mock_query

            # Mock the _get_booking_for_update and _verify_booking_access methods
            with patch.object(booking_service, '_get_booking_for_update', new_callable=AsyncMock) as mock_get_booking, \
                 patch.object(booking_service, '_verify_booking_access', new_callable=AsyncMock) as mock_verify_access:

                mock_get_booking.return_value = {"id": "booking123", "customer_id": "user123"}
                mock_verify_access.return_value = None

                update_data = BookingUpdate(status="cancelled")
                result = await booking_service.update_booking("booking123", update_data, "user123", "customer")

                assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_booking(self, booking_service, mock_db):
        """Test cancelling a booking"""
        # Mock database operations for the complex cancel_booking method
        mock_booking_response = Mock()
        mock_booking_response.data = {
            "id": "booking123",
            "customer_id": "user123",
            "salon_id": "salon123",
            "convenience_fee": 50.0
        }

        mock_update_response = Mock()
        mock_update_response.data = [{"status": "cancelled"}]

        with patch.object(booking_service.db, 'table') as mock_table:
            mock_query = Mock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.single.return_value = mock_query
            mock_query.execute.return_value = mock_booking_response
            mock_query.update.return_value = mock_query
            mock_table.return_value = mock_query

            # Set up the update query separately
            mock_update_query = Mock()
            mock_update_query.eq.return_value = mock_update_query
            mock_update_query.execute.return_value = mock_update_response

            # Mock the email sending
            with patch.object(booking_service, '_send_cancellation_email', new_callable=AsyncMock) as mock_send_email:
                mock_send_email.return_value = None

                result = await booking_service.cancel_booking("booking123", "Changed plans", "user123", "customer")

                assert result["success"] is True
                assert result["message"] == "Booking cancelled"
                mock_send_email.assert_called_once()