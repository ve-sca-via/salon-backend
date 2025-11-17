"""
Authentication Service
Handles all authentication and user profile operations
"""
from typing import Dict, Optional
from fastapi import HTTPException, status
from datetime import datetime
import html
import logging
import asyncio

from app.core.database import get_auth_client, get_db
from app.core.auth import create_access_token, create_refresh_token, revoke_token, verify_refresh_token
from app.core.config import settings

logger = logging.getLogger(__name__)


class AuthService:
    """Service for authentication and user management"""
    
    def __init__(self, db_client, auth_client):
        """Initialize service with database clients"""
        self.db = db_client
        self.auth_client = auth_client
    
    async def authenticate_user(self, email: str, password: str) -> Dict:
        """
        Authenticate user with email and password
        
        Args:
            email: User's email address
            password: User's password
            
        Returns:
            Dict containing tokens and user data
            
        Raises:
            HTTPException: If credentials are invalid or user is inactive
        """
        try:
            # Authenticate with Supabase
            auth_response = self.auth_client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            user = getattr(auth_response, "user", None)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )
            
            # Fetch user profile
            profile_response = self.db.table("profiles").select(
                "*"
            ).eq("id", user.id).single().execute()
            
            if not profile_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User profile not found"
                )
            
            profile = profile_response.data
            
            # Check if user is active
            if not profile.get("is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is inactive. Please contact support."
                )
            
            # Create JWT tokens
            token_data = {
                "sub": user.id,
                "email": user.email,
                "user_role": profile.get("user_role", "customer")
            }
            
            access_token = create_access_token(token_data)
            refresh_token = create_refresh_token(token_data)
            
            # Sanitize user data (XSS protection)
            user_data = {
                "id": user.id,
                "email": user.email,
                "full_name": html.escape(profile.get("full_name") or ""),
                "user_role": profile.get("user_role", "customer"),
                "role": profile.get("user_role", "customer"),  # Backward compatibility for frontend
                "phone": html.escape(profile.get("phone") or ""),
                "is_active": profile.get("is_active", True)
            }
            
            logger.info(f"User authenticated: {user.email} (role: {profile.get('user_role')})")
            
            return {
                "success": True,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": user_data
            }
            
        except HTTPException:
            raise
        except Exception as e:
            import traceback
            error_message = str(e).lower()
            logger.error(f"Authentication error: {str(e)}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            
            # Check if it's an authentication error from Supabase
            if "invalid login credentials" in error_message or "invalid credentials" in error_message:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication failed"
            )
    
    async def register_user(
        self,
        email: str,
        password: str,
        full_name: str,
        phone: Optional[str] = None,
        user_role: str = "customer"
    ) -> Dict:
        """
        Register a new user (customer only)
        
        Args:
            email: User's email address
            password: User's password
            full_name: User's full name
            phone: User's phone number (optional)
            user_role: User role (defaults to customer)
            
        Returns:
            Dict containing tokens and user data
            
        Raises:
            HTTPException: If registration fails or email exists
        """
        try:
            # Sanitize inputs (XSS protection)
            sanitized_full_name = html.escape(full_name.strip())
            sanitized_phone = html.escape(phone.strip()) if phone else None
            
            # Only allow customer signups
            if user_role not in ["customer"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid role. Use customer signup only."
                )
            
            # Check if email already exists
            try:
                existing = self.db.table("profiles").select("id").eq("email", email).execute()
                if existing.data:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already registered"
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"Could not check existing user: {e}")
            
            # Create auth user
            auth_response = self.auth_client.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": {
                        "full_name": sanitized_full_name,
                        "phone": sanitized_phone,
                        "user_role": user_role
                    }
                }
            })
            
            user = getattr(auth_response, "user", None)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to create user account"
                )
            
            # Wait for auth user creation to propagate (async sleep)
            await asyncio.sleep(0.1)  # Much shorter delay, non-blocking
            
            # Create or update profile
            profile_data = {
                "id": user.id,
                "email": email,
                "full_name": sanitized_full_name,
                "phone": sanitized_phone,
                "user_role": user_role,
                "is_active": True
            }
            
            try:
                # Try insert first
                profile_response = self.db.table("profiles").insert(profile_data).execute()
            except Exception as insert_error:
                error_str = str(insert_error)
                
                # Check for duplicate email error
                if "duplicate key" in error_str and "profiles_email_key" in error_str:
                    logger.warning(f"Duplicate email during signup: {email}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already registered"
                    )
                
                logger.warning(f"Profile insert failed, trying upsert: {insert_error}")
                
                # Try upsert if insert fails (trigger might have created it)
                try:
                    profile_response = self.db.table("profiles").upsert(profile_data).execute()
                except Exception as upsert_error:
                    logger.error(f"Profile upsert also failed: {upsert_error}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Unable to create account. Please try again."
                    )
            
            # Create JWT tokens for auto-login
            token_data = {
                "sub": user.id,
                "email": email,
                "user_role": user_role
            }
            
            access_token = create_access_token(token_data)
            refresh_token = create_refresh_token(token_data)
            
            # Build user response
            user_data = {
                "id": user.id,
                "email": email,
                "full_name": sanitized_full_name,
                "user_role": user_role,
                "role": user_role,  # Backward compatibility for frontend
                "phone": sanitized_phone,
                "is_active": True
            }
            
            logger.info(f"New user registered: {email}")
            
            return {
                "success": True,
                "message": "Account created successfully!",
                "user_id": user.id,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": user_data
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Registration error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Registration failed: {str(e)}"
            )
    
    async def refresh_user_session(self, refresh_token: str) -> Dict:
        """
        Refresh access token using refresh token
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            Dict containing new tokens
            
        Raises:
            HTTPException: If token is invalid or user is inactive
        """
        try:
            # Verify refresh token
            token_data = verify_refresh_token(refresh_token, self.db)
            
            # Fetch current user profile
            profile_response = self.db.table("profiles").select(
                "*"
            ).eq("id", token_data["sub"]).single().execute()
            
            if not profile_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            profile = profile_response.data
            
            # Check if user is still active
            if not profile.get("is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is inactive"
                )
            
            # Create new tokens with updated data
            new_token_data = {
                "sub": profile["id"],
                "email": profile["email"],
                "user_role": profile.get("user_role", "customer")
            }
            
            new_access_token = create_access_token(new_token_data)
            new_refresh_token = create_refresh_token(new_token_data)
            
            logger.info(f"Token refreshed for user: {profile['email']}")
            
            return {
                "success": True,
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "token_type": "bearer"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token"
            )
    
    async def get_user_profile(self, user_id: str) -> Dict:
        """
        Get user profile by ID
        
        Args:
            user_id: User's unique identifier
            
        Returns:
            Dict containing user profile data
            
        Raises:
            HTTPException: If profile not found
        """
        try:
            response = self.db.table("profiles").select(
                "*"
            ).eq("id", user_id).single().execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Profile not found"
                )
            
            profile = response.data
            # Add 'role' field for frontend backward compatibility
            profile['role'] = profile.get('user_role', 'customer')
            
            return {
                "success": True,
                "user": profile
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Get profile error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch profile"
            )
    
    async def logout_user(
        self,
        user_id: str,
        token_jti: Optional[str],
        expires_at: datetime
    ) -> Dict:
        """
        Logout user by revoking their access token
        
        Args:
            user_id: User's unique identifier
            token_jti: JWT token ID (jti claim)
            expires_at: Token expiration timestamp
            
        Returns:
            Dict with success message
        """
        try:
            # Revoke the access token by adding to blacklist
            revoke_token(
                db=self.db,
                token_jti=token_jti,
                user_id=user_id,
                token_type="access",
                expires_at=expires_at,
                reason="logout"
            )
            
            logger.info(f"User logged out: {user_id}")
            
            return {
                "success": True,
                "message": "Successfully logged out"
            }
            
        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Logout failed"
            )
    
    async def logout_all_devices(
        self,
        user_id: str,
        email: str,
        password: str,
        current_token_jti: Optional[str],
        current_token_exp: datetime
    ) -> Dict:
        """
        Logout user from all devices by revoking all tokens
        
        Args:
            user_id: User's unique identifier
            email: User's email for password verification
            password: User's password for confirmation
            current_token_jti: Current token ID
            current_token_exp: Current token expiration
            
        Returns:
            Dict with success message
            
        Raises:
            HTTPException: If password is invalid
        """
        try:
            # Verify password before revoking all tokens
            auth_response = self.auth_client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if not auth_response.user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid password"
                )
            
            # Revoke current token
            if current_token_jti:
                revoke_token(
                    db=self.db,
                    token_jti=current_token_jti,
                    user_id=user_id,
                    token_type="access",
                    expires_at=current_token_exp,
                    reason="logout_all"
                )
            
            logger.warning(f"Logout all devices requested for user: {user_id}")
            
            return {
                "success": True,
                "message": "Successfully logged out from all devices"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Logout all error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to logout from all devices"
            )
    
    async def initiate_password_reset(self, email: str) -> Dict:
        """
        Initiate password reset process
        
        Args:
            email: User's email address
            
        Returns:
            Dict with success message
            
        Raises:
            HTTPException: If user not found or email sending fails
        """
        try:
            # Check if user exists
            response = self.db.table("profiles").select("id, email").eq("email", email).single().execute()
            
            if not response.data:
                # Don't reveal if email exists for security
                return {
                    "success": True,
                    "message": "If an account with this email exists, a password reset link has been sent."
                }
            
            user_id = response.data["id"]
            
            # Generate reset token (using Supabase auth reset)
            try:
                self.auth_client.auth.reset_password_for_email(
                    email,
                    redirect_to=f"{settings.FRONTEND_URL}/reset-password"
                )
            except Exception as e:
                logger.error(f"Supabase password reset error: {str(e)}")
                # Still return success for security
                pass
            
            logger.info(f"Password reset initiated for user: {user_id}")
            
            return {
                "success": True,
                "message": "If an account with this email exists, a password reset link has been sent."
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Password reset initiation error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initiate password reset"
            )
    
    async def confirm_password_reset(self, token: str, new_password: str) -> Dict:
        """
        Confirm password reset with token
        
        Args:
            token: Reset token from email
            new_password: New password
            
        Returns:
            Dict with success message and new tokens
            
        Raises:
            HTTPException: If token is invalid or reset fails
        """
        try:
            # Verify and update password using Supabase
            auth_response = self.auth_client.auth.verify_otp({
                "token_hash": token,
                "type": "recovery"
            })
            
            if not auth_response.user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired reset token"
                )
            
            user_id = auth_response.user.id
            
            # Update password in Supabase
            self.auth_client.auth.update_user({
                "password": new_password
            })
            
            # Generate new tokens
            access_token = create_access_token(user_id)
            refresh_token = create_refresh_token(user_id)
            
            # Get user profile
            user_profile = await self.get_user_profile(user_id)
            
            logger.info(f"Password reset confirmed for user: {user_id}")
            
            return {
                "success": True,
                "message": "Password reset successfully",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": user_profile
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Password reset confirmation error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reset password"
            )
