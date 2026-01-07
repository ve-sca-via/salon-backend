"""
Integration tests for authentication API endpoints
"""
import os
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

# Set test environment
os.environ["ENVIRONMENT"] = "test"

from app.core.database import MockSupabaseClient


class TestAuthAPI:
    """Test authentication API endpoints"""

    def test_login_success(self, client):
        """Test successful login"""
        # Mock the AuthService.authenticate_user method
        with patch('app.services.auth_service.AuthService.authenticate_user', new_callable=AsyncMock) as mock_authenticate:
            mock_authenticate.return_value = {
                "success": True,
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "token_type": "bearer",
                "user": {
                    "id": "user123",
                    "email": "test@example.com",
                    "user_role": "customer",
                    "full_name": "Test User"
                }
            }

            response = client.post("/api/v1/auth/login", json={
                "email": "test@example.com",
                "password": "password123"
            })

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["user"]["email"] == "test@example.com"

    def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials"""
        with patch('app.services.auth_service.AuthService.authenticate_user', new_callable=AsyncMock) as mock_authenticate:
            mock_authenticate.side_effect = HTTPException(status_code=401, detail="Invalid credentials")

            response = client.post("/api/v1/auth/login", json={
                "email": "test@example.com",
                "password": "wrongpassword"
            })

            assert response.status_code == 401

    def test_signup_success(self, client):
        """Test successful user registration"""
        with patch('app.services.auth_service.AuthService.register_user', new_callable=AsyncMock) as mock_register:
            mock_register.return_value = {
                "success": True,
                "message": "User registered successfully",
                "user_id": "user123",
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "user": {
                    "id": "user123",
                    "email": "newuser@example.com",
                    "user_role": "customer",
                    "full_name": "New User"
                }
            }

            response = client.post("/api/v1/auth/signup", json={
                "email": "newuser@example.com",
                "password": "password123",
                "full_name": "New User",
                "phone": "+1234567890",
                "user_role": "customer"
            })

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["user"]["email"] == "newuser@example.com"

    def test_refresh_token_success(self, client):
        """Test successful token refresh"""
        with patch('app.services.auth_service.AuthService.refresh_user_session', new_callable=AsyncMock) as mock_refresh:
            mock_refresh.return_value = {
                "success": True,
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token",
                "token_type": "bearer"
            }

            response = client.post("/api/v1/auth/refresh", json={
                "refresh_token": "valid_refresh_token"
            })

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert "refresh_token" in data

    def test_get_current_user_profile(self, client):
        """Test getting current user profile"""
        with patch('app.services.auth_service.AuthService.get_user_profile', new_callable=AsyncMock) as mock_profile:
            mock_profile.return_value = {
                "id": "user123",
                "email": "test@example.com",
                "user_role": "customer",
                "full_name": "Test User",
                "phone": "+1234567890"
            }

            with patch('app.core.auth.get_current_user') as mock_get_current_user:

                # Mock current user
                mock_user = Mock()
                mock_user.user_id = "user123"
                mock_get_current_user.return_value = mock_user

                response = client.get("/api/v1/auth/me")

                assert response.status_code == 200
                data = response.json()
                assert data["email"] == "test@example.com"

    def test_logout_success(self, client):
        """Test successful logout"""
        with patch('app.services.auth_service.AuthService.logout_user', new_callable=AsyncMock) as mock_logout:
            mock_logout.return_value = {
                "success": True,
                "message": "Successfully logged out"
            }

            with patch('app.core.auth.get_current_user') as mock_get_current_user:

                mock_user = Mock()
                mock_user.user_id = "user123"
                mock_user.jti = "token_jti"
                mock_user.exp = 1234567890
                mock_get_current_user.return_value = mock_user

                response = client.post("/api/v1/auth/logout")

                assert response.status_code == 200
                data = response.json()
                assert "success" in data
                assert "message" in data

    def test_logout_all_devices_success(self, client):
        """Test logout from all devices"""
        with patch('app.services.auth_service.AuthService.logout_all_devices', new_callable=AsyncMock) as mock_logout_all:
            mock_logout_all.return_value = {
                "success": True,
                "message": "Successfully logged out from all devices"
            }

            with patch('app.core.auth.get_current_user') as mock_get_current_user:

                mock_user = Mock()
                mock_user.user_id = "user123"
                mock_user.email = "test@example.com"
                mock_user.jti = "token_jti"
                mock_user.exp = 1234567890
                mock_get_current_user.return_value = mock_user

                response = client.post("/api/v1/auth/logout-all", json={
                    "password": "current_password"
                })

                assert response.status_code == 200
                data = response.json()
                assert "success" in data
                assert "message" in data

    def test_password_reset_initiate(self, client):
        """Test initiating password reset"""
        with patch('app.services.auth_service.AuthService.initiate_password_reset', new_callable=AsyncMock) as mock_reset:
            mock_reset.return_value = {
                "success": True,
                "message": "If an account with this email exists, a password reset link has been sent."
            }

            response = client.post("/api/v1/auth/password-reset", json={
                "email": "test@example.com"
            })

            assert response.status_code == 200
            data = response.json()
            assert "success" in data
            assert "message" in data

    def test_password_reset_confirm(self, client):
        """Test confirming password reset"""
        with patch('app.services.auth_service.AuthService.confirm_password_reset', new_callable=AsyncMock) as mock_confirm:
            mock_confirm.return_value = {
                "success": True,
                "message": "Password reset successfully",
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token",
                "user": {
                    "id": "user123",
                    "email": "test@example.com",
                    "user_role": "customer"
                }
            }

            response = client.post("/api/v1/auth/password-reset/confirm", json={
                "token": "reset_token",
                "new_password": "newpassword123"
            })

            assert response.status_code == 200
            data = response.json()
            assert "success" in data
            assert "message" in data
            assert "access_token" in data
            assert "refresh_token" in data