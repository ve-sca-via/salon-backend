"""
Unit tests for AuthService
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import HTTPException
from app.services.auth_service import AuthService
from app.core.database import MockSupabaseClient


class TestAuthService:
    """Test AuthService methods"""

    @pytest.fixture
    def mock_db(self):
        """Mock database client"""
        return MockSupabaseClient()

    @pytest.fixture
    def mock_auth(self):
        """Mock auth client"""
        return MockSupabaseClient()

    @pytest.fixture
    def auth_service(self, mock_db, mock_auth):
        """AuthService instance with mocked clients"""
        return AuthService(db_client=mock_db, auth_client=mock_auth)

    def test_init(self, mock_db, mock_auth):
        """Test service initialization"""
        service = AuthService(db_client=mock_db, auth_client=mock_auth)
        assert service.db == mock_db
        assert service.auth_client == mock_auth

    @pytest.mark.asyncio
    async def test_authenticate_user_success(self, auth_service, mock_db, mock_auth):
        """Test successful user authentication"""
        # Mock Supabase auth response
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.email = "test@example.com"

        mock_session = Mock()
        mock_session.access_token = "access_token"
        mock_session.refresh_token = "refresh_token"

        mock_auth_response = Mock()
        mock_auth_response.user = mock_user
        mock_auth_response.session = mock_session

        # Mock auth client
        mock_auth.auth.sign_in_with_password = Mock(return_value=mock_auth_response)

        # Mock database user profile
        mock_profile_response = Mock()
        mock_profile_response.data = {
            "id": "user123",
            "user_role": "customer",
            "full_name": "Test User",
            "is_active": True
        }

        mock_db.table = Mock(return_value=Mock())
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_profile_response

        result = await auth_service.authenticate_user("test@example.com", "password123")

        assert "access_token" in result
        assert "refresh_token" in result
        assert "user" in result
        assert result["user"]["id"] == "user123"
        assert result["user"]["user_role"] == "customer"
        assert result["user"]["full_name"] == "Test User"

    @pytest.mark.asyncio
    async def test_authenticate_user_invalid_credentials(self, auth_service, mock_auth):
        """Test authentication with invalid credentials"""
        # Mock auth client to raise exception
        mock_auth.auth.sign_in_with_password = Mock(side_effect=Exception("Invalid credentials"))

        with pytest.raises(HTTPException, match="Invalid credentials"):
            await auth_service.authenticate_user("wrong@example.com", "wrongpassword")

    @pytest.mark.asyncio
    async def test_register_user_success(self, auth_service, mock_db, mock_auth):
        """Test successful user registration"""
        # Mock Supabase auth response
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.email = "newuser@example.com"

        mock_session = Mock()
        mock_session.access_token = "access_token"
        mock_session.refresh_token = "refresh_token"

        mock_auth_response = Mock()
        mock_auth_response.user = mock_user
        mock_auth_response.session = mock_session

        # Mock auth client
        mock_auth.auth.sign_up = Mock(return_value=mock_auth_response)

        # Mock database operations - email check should return empty
        mock_email_check = Mock()
        mock_email_check.data = []  # No existing user
        mock_email_check.execute = Mock(return_value=mock_email_check)
        mock_email_check.eq = Mock(return_value=mock_email_check)
        mock_email_check.select = Mock(return_value=mock_email_check)
        
        # Mock profile insert
        mock_insert_result = Mock()
        mock_insert_result.data = [{"id": "profile123"}]
        mock_insert = Mock(return_value=mock_insert_result)
        mock_insert.execute = Mock(return_value=mock_insert_result)
        
        # Mock table method
        def mock_table_side_effect(table_name):
            if table_name == "profiles":
                mock_table_mock = Mock()
                mock_table_mock.select = Mock(return_value=mock_email_check)
                mock_table_mock.insert = mock_insert
                return mock_table_mock
            return Mock()
        
        mock_db.table = Mock(side_effect=mock_table_side_effect)

        result = await auth_service.register_user(
            email="newuser@example.com",
            password="password123",
            full_name="New User",
            phone="+1234567890",
            user_role="customer"
        )

        assert result["success"] is True
        assert result["access_token"] == "access_token"
        assert result["user"]["email"] == "newuser@example.com"
        assert "message" in result

    @pytest.mark.asyncio
    async def test_refresh_user_session_success(self, auth_service, mock_db, mock_auth):
        """Test successful token refresh"""
        # Mock token verification
        with patch('app.services.auth_service.verify_refresh_token', return_value={"sub": "user123", "user_role": "customer", "email": "test@example.com"}) as mock_verify, \
             patch('app.services.auth_service.create_access_token', return_value="new_access_token") as mock_create_access, \
             patch('app.services.auth_service.create_refresh_token', return_value="new_refresh_token") as mock_create_refresh:

            result = await auth_service.refresh_user_session("valid_refresh_token")

            assert result["access_token"] == "new_access_token"
            assert result["refresh_token"] == "new_refresh_token"
            mock_verify.assert_called_once_with("valid_refresh_token")

    @pytest.mark.asyncio
    async def test_refresh_user_session_invalid_token(self, auth_service):
        """Test token refresh with invalid token"""
        with patch('app.services.auth_service.verify_refresh_token', side_effect=HTTPException(status_code=401, detail="Invalid token")):
            with pytest.raises(HTTPException) as exc_info:
                await auth_service.refresh_user_session("invalid_token")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_user_profile_success(self, auth_service, mock_db):
        """Test getting user profile successfully"""
        mock_response = Mock()
        mock_response.data = {
            "id": "user123",
            "email": "test@example.com",
            "user_role": "customer",
            "full_name": "Test User",
            "phone": "+1234567890"
        }

        # Mock database query
        mock_db.table = Mock(return_value=Mock())
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_response

        result = await auth_service.get_user_profile("user123")

        assert result["id"] == "user123"
        assert result["email"] == "test@example.com"
        assert result["user_role"] == "customer"

    @pytest.mark.asyncio
    async def test_get_user_profile_not_found(self, auth_service, mock_db):
        """Test getting profile for non-existent user"""
        mock_response = Mock()
        mock_response.data = None

        # Mock database query
        mock_db.table = Mock(return_value=Mock())
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_response

        with pytest.raises(HTTPException, match="User not found"):
            await auth_service.get_user_profile("nonexistent")

    @pytest.mark.asyncio
    async def test_logout_user_success(self, auth_service, mock_db):
        """Test successful user logout"""
        with patch('app.core.auth.revoke_token', return_value=True) as mock_revoke:
            result = await auth_service.logout_user(
                user_id="user123",
                token_jti="token_jti",
                expires_at=1234567890
            )

            assert result["message"] == "Logged out successfully"
            mock_revoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_logout_all_devices_success(self, auth_service, mock_db, mock_auth):
        """Test logout from all devices"""
        # Mock token revocation
        with patch('app.core.auth.revoke_all_user_tokens', return_value=True) as mock_revoke_all:
            result = await auth_service.logout_all_devices(
                user_id="user123",
                email="test@example.com",
                password="password123",
                current_token_jti="current_jti",
                current_token_exp=1234567890
            )

            assert result["message"] == "Logged out from all devices successfully"
            mock_revoke_all.assert_called_once_with("user123")

    @pytest.mark.asyncio
    async def test_initiate_password_reset_success(self, auth_service, mock_auth):
        """Test initiating password reset"""
        mock_auth.auth.reset_password_for_email = Mock(return_value=None)

        result = await auth_service.initiate_password_reset("test@example.com")

        assert result["message"] == "Password reset email sent successfully"
        mock_auth.auth.reset_password_for_email.assert_called_once_with("test@example.com")

    @pytest.mark.asyncio
    async def test_confirm_password_reset_success(self, auth_service, mock_auth):
        """Test confirming password reset"""
        # Mock Supabase auth response
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.email = "test@example.com"

        mock_session = Mock()
        mock_session.access_token = "new_access_token"
        mock_session.refresh_token = "new_refresh_token"

        mock_auth_response = Mock()
        mock_auth_response.user = mock_user
        mock_auth_response.session = mock_session

        mock_auth.auth.update_user = Mock(return_value=mock_auth_response)

        with patch('app.core.auth.create_access_token', return_value="final_access_token"), \
             patch('app.core.auth.create_refresh_token', return_value="final_refresh_token"):

            result = await auth_service.confirm_password_reset("reset_token", "newpassword123")

            assert result["access_token"] == "final_access_token"
            assert result["refresh_token"] == "final_refresh_token"
            assert result["user"]["id"] == "user123"