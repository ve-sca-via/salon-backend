"""
Tests for authentication and authorization module
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from fastapi import HTTPException
from jose import JWTError

from app.core.auth import (
    create_access_token,
    create_refresh_token,
    verify_token,
    verify_refresh_token,
    revoke_token,
    cleanup_expired_tokens,
    get_current_user,
    get_current_user_id,
    require_admin,
    require_rm,
    require_vendor,
    require_customer,
    create_registration_token,
    verify_registration_token,
    get_user_salon_id,
    verify_salon_access,
    TokenData,
    TokenPayload
)
from app.core.config import settings


class TestTokenCreation:
    """Test token creation functions"""

    def test_create_access_token(self):
        """Test access token creation"""
        data = {"sub": "test-user-id", "email": "test@example.com", "user_role": "customer"}

        token = create_access_token(data)

        assert isinstance(token, str)
        assert len(token) > 0

        # Note: Token verification is tested separately

    def test_create_refresh_token(self, mocker):
        """Test refresh token creation"""
        mock_db = mocker.Mock()
        # Mock blacklist check
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

        data = {"sub": "test-user-id", "email": "test@example.com", "user_role": "customer"}

        token = create_refresh_token(data)

        assert isinstance(token, str)
        assert len(token) > 0

        # Verify token can be decoded
        payload = verify_refresh_token(token, mock_db)
        assert payload["sub"] == "test-user-id"
        assert payload["email"] == "test@example.com"
        assert payload["user_role"] == "customer"
        assert payload["jti"] is not None

    def test_create_registration_token(self):
        """Test registration token creation"""
        request_id = "test-request-id"
        salon_id = "test-salon-id"
        owner_email = "owner@example.com"

        token = create_registration_token(request_id, salon_id, owner_email)

        assert isinstance(token, str)
        assert len(token) > 0

        # Verify token can be decoded
        payload = verify_registration_token(token)
        assert payload["email"] == owner_email
        assert payload["request_id"] == request_id
        assert payload["salon_id"] == salon_id


class TestTokenVerification:
    """Test token verification functions"""

    def test_verify_token_valid(self, mocker):
        """Test verifying a valid token"""
        mock_db = mocker.Mock()
        
        # Mock profiles table query (for token_valid_after check) - return None to skip check
        mock_profiles_response = mocker.Mock()
        mock_profiles_response.data = {"token_valid_after": None}
        
        # Mock blacklist query - return empty list (not blacklisted)
        mock_blacklist_response = mocker.Mock()
        mock_blacklist_response.data = []
        
        # Set up the mock to return different responses for different table calls
        def mock_table_call(table_name):
            if table_name == "profiles":
                return mocker.Mock(
                    select=lambda *args: mocker.Mock(
                        eq=lambda *args: mocker.Mock(
                            single=lambda: mocker.Mock(
                                execute=lambda: mock_profiles_response
                            )
                        )
                    )
                )
            elif table_name == "token_blacklist":
                return mocker.Mock(
                    select=lambda *args: mocker.Mock(
                        eq=lambda *args: mocker.Mock(
                            execute=lambda: mock_blacklist_response
                        )
                    )
                )
        
        mock_db.table = mock_table_call

        data = {"sub": "test-user-id", "email": "test@example.com", "user_role": "customer"}

        token = create_access_token(data)
        payload = verify_token(token, mock_db)

        assert payload.sub == "test-user-id"
        assert payload.email == "test@example.com"
        assert payload.user_role == "customer"

    def test_verify_token_expired(self, mocker):
        """Test verifying an expired token"""
        mock_db = mocker.Mock()
        data = {"sub": "test-user-id", "email": "test@example.com", "user_role": "customer"}

        # Create token that expires immediately
        with patch.object(settings, 'ACCESS_TOKEN_EXPIRE_MINUTES', -1):
            token = create_access_token(data)

        with pytest.raises(HTTPException) as exc_info:
            verify_token(token, mock_db)

        assert exc_info.value.status_code == 401

    def test_verify_token_invalid(self, mocker):
        """Test verifying an invalid token"""
        mock_db = mocker.Mock()
        with pytest.raises(HTTPException) as exc_info:
            verify_token("invalid-token", mock_db)

        assert exc_info.value.status_code == 401

    def test_verify_refresh_token_valid(self, mocker):
        """Test verifying a valid refresh token"""
        mock_db = mocker.Mock()
        # Mock blacklist check
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

        data = {"sub": "test-user-id", "email": "test@example.com", "user_role": "customer"}

        token = create_refresh_token(data)
        payload = verify_refresh_token(token, mock_db)

        assert payload["sub"] == "test-user-id"
        assert payload["email"] == "test@example.com"
        assert payload["user_role"] == "customer"

    def test_verify_registration_token_valid(self):
        """Test verifying a valid registration token"""
        request_id = "test-request-id"
        salon_id = "test-salon-id"
        owner_email = "owner@example.com"

        token = create_registration_token(request_id, salon_id, owner_email)
        payload = verify_registration_token(token)

        assert payload["email"] == owner_email
        assert payload["request_id"] == request_id
        assert payload["salon_id"] == salon_id


class TestTokenRevocation:
    """Test token revocation functions"""

    def test_revoke_token(self, mocker):
        """Test revoking a specific token"""
        mock_db = mocker.Mock()
        mock_db.table.return_value.insert.return_value.execute.return_value.data = [{}]

        jti = "test-jti"
        user_id = "test-user-id"
        token_type = "access"
        expires_at = datetime.utcnow() + timedelta(hours=1)
        
        result = revoke_token(mock_db, jti, user_id, token_type, expires_at)

        assert result is True
        mock_db.table.assert_called_with('token_blacklist')
        mock_db.table.return_value.insert.assert_called_once()

    def test_verify_token_with_token_valid_after(self, mocker):
        """Test that tokens issued before token_valid_after are rejected"""
        mock_db = mocker.Mock()
        
        # Create a token (will have current timestamp as iat)
        data = {"sub": "test-user-id", "email": "test@example.com", "user_role": "customer"}
        token = create_access_token(data)
        
        # Sleep briefly to ensure timestamp difference
        import time
        time.sleep(0.1)
        
        # Mock token_valid_after to be AFTER the token was issued
        future_time = datetime.utcnow() + timedelta(seconds=1)
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "token_valid_after": future_time.isoformat()
        }
        
        # Token should be rejected because it was issued before token_valid_after
        with pytest.raises(HTTPException) as exc_info:
            verify_token(token, mock_db)
        
        assert exc_info.value.status_code == 401
        assert "revoked" in exc_info.value.detail.lower()
        assert "logged out from all devices" in exc_info.value.detail.lower()

    def test_verify_token_without_token_valid_after(self, mocker):
        """Test that tokens work normally when token_valid_after is NULL"""
        mock_db = mocker.Mock()
        
        # Create a token
        data = {"sub": "test-user-id", "email": "test@example.com", "user_role": "customer"}
        token = create_access_token(data)
        
        # Mock token_valid_after as NULL (no logout_all performed)
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "token_valid_after": None
        }
        
        # Mock blacklist check to return no results
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        
        # Token should be accepted
        payload = verify_token(token, mock_db)
        
        assert payload.sub == "test-user-id"
        assert payload.email == "test@example.com"
        assert payload.user_role == "customer"

    def test_verify_token_issued_after_token_valid_after(self, mocker):
        """Test that tokens issued AFTER token_valid_after are accepted"""
        mock_db = mocker.Mock()
        
        # Set token_valid_after to a past timestamp
        past_time = datetime.utcnow() - timedelta(hours=1)
        
        # Create a token NOW (will be after past_time)
        data = {"sub": "test-user-id", "email": "test@example.com", "user_role": "customer"}
        token = create_access_token(data)
        
        # Mock token_valid_after to be BEFORE the token was issued
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "token_valid_after": past_time.isoformat()
        }
        
        # Mock blacklist check
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        
        # Token should be accepted because it was issued after token_valid_after
        payload = verify_token(token, mock_db)
        
        assert payload.sub == "test-user-id"
        assert payload.email == "test@example.com"

    def test_verify_refresh_token_with_token_valid_after(self, mocker):
        """Test that refresh tokens respect token_valid_after"""
        mock_db = mocker.Mock()
        
        # Create a refresh token
        data = {"sub": "test-user-id", "email": "test@example.com", "user_role": "customer"}
        token = create_refresh_token(data)
        
        import time
        time.sleep(0.1)
        
        # Mock token_valid_after to be AFTER the token was issued
        future_time = datetime.utcnow() + timedelta(seconds=1)
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "token_valid_after": future_time.isoformat()
        }
        
        # Refresh token should be rejected
        with pytest.raises(HTTPException) as exc_info:
            verify_refresh_token(token, mock_db)
        
        assert exc_info.value.status_code == 401
        assert "revoked" in exc_info.value.detail.lower()

    def test_cleanup_expired_tokens(self, mocker):
        """Test cleaning up expired revoked tokens"""
        mock_db = mocker.Mock()
        mock_db.table.return_value.delete.return_value.lt.return_value.execute.return_value.data = None

        result = cleanup_expired_tokens(mock_db)

        assert isinstance(result, int)
        mock_db.table.assert_called_with('token_blacklist')
        mock_db.table.return_value.delete.assert_called_once()


class TestRoleRequirements:
    """Test role-based access control decorators"""

    @pytest.mark.asyncio
    async def test_require_admin_with_admin_role(self):
        """Test admin requirement with admin role"""
        token_data = TokenData(
            user_id="test-id",
            email="admin@test.com",
            user_role="admin"
        )

        # Should not raise exception
        result = await require_admin(token_data)
        assert result == token_data

    @pytest.mark.asyncio
    async def test_require_admin_with_non_admin_role(self):
        """Test admin requirement with non-admin role"""
        token_data = TokenData(
            user_id="test-id",
            email="user@test.com",
            user_role="customer"
        )

        with pytest.raises(HTTPException) as exc_info:
            await require_admin(token_data)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_rm_with_rm_role(self):
        """Test RM requirement with RM role"""
        token_data = TokenData(
            user_id="test-id",
            email="rm@test.com",
            user_role="relationship_manager"
        )

        result = await require_rm(token_data)
        assert result == token_data

    @pytest.mark.asyncio
    async def test_require_rm_with_admin_role(self):
        """Test RM requirement with admin role (should allow)"""
        token_data = TokenData(
            user_id="test-id",
            email="admin@test.com",
            user_role="admin"
        )

        result = await require_rm(token_data)
        assert result == token_data

    @pytest.mark.asyncio
    async def test_require_vendor_with_vendor_role(self):
        """Test vendor requirement with vendor role"""
        token_data = TokenData(
            user_id="test-id",
            email="vendor@test.com",
            user_role="vendor"
        )

        result = await require_vendor(token_data)
        assert result == token_data

    @pytest.mark.asyncio
    async def test_require_customer_with_customer_role(self):
        """Test customer requirement with customer role"""
        token_data = TokenData(
            user_id="test-id",
            email="customer@test.com",
            user_role="customer"
        )

        result = await require_customer(token_data)
        assert result == token_data


class TestUserFunctions:
    """Test user-related functions"""

    @pytest.mark.asyncio
    async def test_get_user_salon_id_success(self, mocker):
        """Test getting salon ID for a vendor user"""
        mock_db = mocker.Mock()
        user_id = "test-user-id"
        salon_id = "test-salon-id"

        mock_response = Mock()
        mock_response.data = {"id": salon_id}
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_response

        result = await get_user_salon_id(user_id, mock_db)
        assert result == salon_id

    @pytest.mark.asyncio
    async def test_get_user_salon_id_not_found(self, mocker):
        """Test getting salon ID when user has no salon"""
        mock_db = mocker.Mock()
        user_id = "test-user-id"

        mock_response = Mock()
        mock_response.data = None
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_response

        result = await get_user_salon_id(user_id, mock_db)
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    @patch('app.core.auth.get_user_salon_id')
    async def test_verify_salon_access_owner(self, mock_get_salon_id, mocker):
        """Test salon access verification for salon owner"""
        mock_db = mocker.Mock()
        user = TokenData(
            user_id="test-user-id",
            email="vendor@test.com",
            user_role="vendor"
        )
        salon_id = "test-salon-id"

        mock_get_salon_id.return_value = salon_id

        # Should not raise exception - but function returns bool
        result = await verify_salon_access(user, salon_id, mock_db)
        assert result is True

    @pytest.mark.asyncio
    @patch('app.core.auth.get_user_salon_id')
    async def test_verify_salon_access_denied(self, mock_get_salon_id, mocker):
        """Test salon access verification for non-owner"""
        mock_db = mocker.Mock()
        user = TokenData(
            user_id="test-user-id",
            email="vendor@test.com",
            user_role="vendor"
        )
        salon_id = "test-salon-id"

        mock_get_salon_id.return_value = "different-salon-id"

        result = await verify_salon_access(user, salon_id, mock_db)
        assert result is False


class TestDependencyInjection:
    """Test FastAPI dependency injection functions"""

    @pytest.mark.asyncio
    @patch('app.core.auth.verify_token')
    async def test_get_current_user(self, mock_verify, mocker):
        """Test get_current_user dependency"""
        mock_db = mocker.Mock()
        token_data = TokenPayload(
            sub="test-id",
            email="user@test.com",
            user_role="customer",
            jti="test-jti",
            exp=1234567890
        )
        mock_verify.return_value = token_data
        
        mock_user_response = Mock()
        mock_user_response.data = {
            "id": "test-id",
            "email": "user@test.com", 
            "user_role": "customer",
            "is_active": True
        }
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_user_response

        from fastapi.security import HTTPAuthorizationCredentials
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-token")

        result = await get_current_user(credentials, mock_db)
        assert result.user_id == "test-id"
        assert result.email == "user@test.com"
        assert result.user_role == "customer"
        mock_verify.assert_called_once_with("test-token", mock_db)

    @pytest.mark.asyncio
    async def test_get_current_user_id(self):
        """Test get_current_user_id dependency"""
        token_data = TokenData(
            user_id="test-id",
            email="user@test.com",
            user_role="customer"
        )

        result = await get_current_user_id(token_data)
        assert result == "test-id"