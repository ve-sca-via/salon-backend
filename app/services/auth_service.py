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
from app.services.activity_log_service import ActivityLogService

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
            
            # Check if it's an authentication error from Supabase
            if "invalid login credentials" in error_message or "invalid credentials" in error_message:
                logger.warning(f"Failed login attempt for email: {email}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password. Please check your credentials and try again."
                )
            
            # Log unexpected errors with full traceback
            logger.error(f"Authentication error: {str(e)}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            
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
        age: int = None,
        gender: str = None,
        user_role: str = "customer"
    ) -> Dict:
        """
        Register a new user (customer only)
        
        Args:
            email: User's email address
            password: User's password
            full_name: User's full name
            phone: User's phone number (optional)
            age: User's age (required, 13-120)
            gender: User's gender (required: male, female, other)
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
            
            # Validate and sanitize gender (REQUIRED)
            if not gender:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Gender is required"
                )
            
            gender_lower = gender.lower().strip()
            if gender_lower not in ['male', 'female', 'other']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid gender. Must be 'male', 'female', or 'other'."
                )
            sanitized_gender = gender_lower
            
            # Validate age (REQUIRED)
            if age is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Age is required"
                )
            
            if age < 13 or age > 120:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Age must be between 13 and 120"
                )
            
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
                "age": age,
                "gender": sanitized_gender,
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
                "age": age,
                "gender": sanitized_gender,
                "is_active": True
            }
            
            logger.info(f"New user registered: {email}")
            
            # Log activity for new user signup
            try:
                await ActivityLogService.log(
                    user_id=user.id,
                    action="user_signup",
                    entity_type="user",
                    entity_id=user.id,
                    details={
                        "email": email,
                        "full_name": sanitized_full_name,
                        "user_role": user_role,
                        "signup_method": "email_password"
                    }
                )
            except Exception as log_error:
                logger.warning(f"Failed to log signup activity: {log_error}")
            
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
            # Only revoke if we have a JTI
            if token_jti:
                # Revoke the access token by adding to blacklist
                revoke_token(
                    db=self.db,
                    token_jti=token_jti,
                    user_id=user_id,
                    token_type="access",
                    expires_at=expires_at,
                    reason="logout"
                )
            else:
                logger.warning(f"Logout attempted without JTI for user: {user_id}")
            
            logger.info(f"User logged out: {user_id}")
            
            return {
                "success": True,
                "message": "Successfully logged out"
            }
            
        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            # Don't fail logout if blacklist fails - user can still clear client-side
            logger.warning("Logout completed with errors, but allowing client-side cleanup")
            return {
                "success": True,
                "message": "Logged out (with warnings)"
            }
    
    async def logout_all_devices(
        self,
        user_id: str,
        email: str,
        password: str,
        current_token_jti: Optional[str],
        current_token_exp: datetime
    ) -> Dict:
        """
        Logout user from all devices by invalidating all tokens issued before now
        
        Strategy: Sets token_valid_after timestamp in profiles table to NOW.
        All tokens (access and refresh) issued before this timestamp will be rejected
        during verification in verify_token() and verify_refresh_token().
        
        This is more efficient and complete than blacklisting individual tokens.
        
        Args:
            user_id: User's unique identifier
            email: User's email for password verification
            password: User's password for confirmation
            current_token_jti: Current token ID (unused - all tokens invalidated via timestamp)
            current_token_exp: Current token expiration (unused - all tokens invalidated via timestamp)
            
        Returns:
            Dict with success message
            
        Raises:
            HTTPException: If password is invalid or database update fails
        """
        try:
            # Verify password before invalidating all tokens
            auth_response = self.auth_client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if not auth_response.user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid password"
                )
            
            # Set token_valid_after to NOW - this invalidates ALL tokens issued before now
            now = datetime.utcnow()
            update_response = self.db.table("profiles").update({
                "token_valid_after": now.isoformat()
            }).eq("id", user_id).execute()
            
            if not update_response.data:
                logger.error(f"Failed to update token_valid_after for user {user_id}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to logout from all devices"
                )
            
            logger.warning(f"All tokens invalidated for user {user_id} via token_valid_after: {now.isoformat()}")
            
            # Log activity for security audit
            await ActivityLogService.log(
                db=self.db,
                user_id=user_id,
                action="logout_all_devices",
                entity_type="auth",
                entity_id=user_id,
                details={"timestamp": now.isoformat(), "method": "token_valid_after"}
            )
            
            return {
                "success": True,
                "message": "Successfully logged out from all devices. Please login again."
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
            Dict with success message (always returns success for security)
            
        Note:
            Always returns success message to prevent account enumeration
        """
        try:
            # Check if user exists
            response = self.db.table("profiles").select("id, email").eq("email", email).single().execute()
            
            if not response.data:
                # Don't reveal if email exists for security
                logger.info(f"Password reset requested for non-existent email (redacted)")
                return {
                    "success": True,
                    "message": "If an account with this email exists, a password reset link has been sent."
                }
            
            user_id = response.data["id"]
            
            # Hash user_id for logging to prevent account enumeration via logs
            import hashlib
            user_id_hash = hashlib.sha256(user_id.encode()).hexdigest()[:12]
            
            # Determine which password reset method is available (explicit feature detection)
            reset_method = None
            if hasattr(self.auth_client.auth, 'reset_password_email'):
                reset_method = 'reset_password_email'
            elif hasattr(self.auth_client.auth, 'reset_password_for_email'):
                reset_method = 'reset_password_for_email'
            else:
                logger.error(
                    f"No supported password reset method found in Supabase client. "
                    f"User hash: {user_id_hash}. Returning success for security but reset will fail."
                )
                return {
                    "success": True,
                    "message": "If an account with this email exists, a password reset link has been sent."
                }
            
            # Send password reset email using detected method
            reset_options = {"redirect_to": f"{settings.FRONTEND_URL}/reset-password"}
            try:
                if reset_method == 'reset_password_email':
                    self.auth_client.auth.reset_password_email(email, options=reset_options)
                else:  # reset_password_for_email
                    self.auth_client.auth.reset_password_for_email(email, reset_options)
                
                logger.info(f"Password reset email sent successfully (user hash: {user_id_hash})")
                
            except Exception as e:
                # Log error with context but still return success for security
                logger.error(
                    f"Failed to send password reset email. "
                    f"Method: {reset_method}, User hash: {user_id_hash}, Error: {str(e)}"
                )
                # Explicitly return success to prevent account enumeration
            
            return {
                "success": True,
                "message": "If an account with this email exists, a password reset link has been sent."
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Password reset initiation error: {str(e)}")
            # Return success even on unexpected errors to prevent account enumeration
            return {
                "success": True,
                "message": "If an account with this email exists, a password reset link has been sent."
            }
    
    async def confirm_password_reset(self, token: str, new_password: str) -> Dict:
        """
        Confirm password reset with token
        
        Args:
            token: Reset token from email (access_token from hash)
            new_password: New password
            
        Returns:
            Dict with success message and new tokens
            
        Raises:
            HTTPException: If token is invalid or reset fails
        """
        try:
            # First, set the session using the access token from the reset email
            # This authenticates the user for password update
            try:
                session_response = self.auth_client.auth.set_session(token, token)
                if not session_response.user:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid or expired reset token"
                    )
            except Exception as session_error:
                logger.error(f"Session error: {str(session_error)}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired reset token"
                )
            
            user_id = session_response.user.id
            user_email = session_response.user.email
            
            # Now update the password using the authenticated session
            try:
                update_response = self.auth_client.auth.update_user({
                    "password": new_password
                })
                
                if not update_response.user:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to update password"
                    )
            except Exception as update_error:
                logger.error(f"Password update error: {str(update_error)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update password"
                )
            
            # Fetch user profile
            profile_response = self.db.table("profiles").select(
                "*"
            ).eq("id", user_id).single().execute()
            
            if not profile_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User profile not found"
                )
            
            profile = profile_response.data
            
            # Generate new JWT tokens for auto-login
            token_data = {
                "sub": user_id,
                "email": user_email,
                "user_role": profile.get("user_role", "customer")
            }
            
            access_token = create_access_token(token_data)
            refresh_token = create_refresh_token(token_data)
            
            # Sanitize user data
            user_data = {
                "id": user_id,
                "email": user_email,
                "full_name": html.escape(profile.get("full_name") or ""),
                "user_role": profile.get("user_role", "customer"),
                "role": profile.get("user_role", "customer"),
                "phone": html.escape(profile.get("phone") or ""),
                "is_active": profile.get("is_active", True)
            }
            
            logger.info(f"Password reset confirmed for user: {user_id}")
            
            return {
                "success": True,
                "message": "Password reset successfully",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": user_data
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Password reset confirmation error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reset password"
            )
    async def resend_verification_email(self, user_id: str, email: str) -> Dict:
        """
        Resend email verification link to user
        
        Args:
            user_id: User's ID
            email: User's email address
            
        Returns:
            Dict with success status and message
            
        Raises:
            HTTPException: If resend fails
        """
        try:
            # Use Supabase's resend functionality
            response = self.auth_client.auth.resend({
                "type": "signup",
                "email": email,
                "options": {
                    "email_redirect_to": f"{settings.FRONTEND_URL}"
                }
            })
            
            logger.info(f"Verification email resent to: {email}")
            
            return {
                "success": True,
                "message": "Verification email sent successfully. Please check your inbox."
            }
            
        except Exception as e:
            logger.error(f"Failed to resend verification email: {str(e)}")
            # Don't expose detailed error to user
            return {
                "success": True,
                "message": "If your email is registered and unverified, you will receive a verification email shortly."
            }