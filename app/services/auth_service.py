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
import httpx

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

    @staticmethod
    def format_public_user(
        profile: dict,
        email: str | None = None,
        email_verified: bool | None = None,
    ) -> dict:
        """
        Build sanitized user payload returned from auth endpoints.

        `email_verified` is None when the caller could not determine it. Clients
        must treat None as "unknown" and stay silent rather than warn the user —
        only False means the address is genuinely unconfirmed.
        """
        phone = profile.get("phone") or ""
        return {
            "email_verified": email_verified,
            "id": profile.get("id"),
            "email": email or profile.get("email"),
            "full_name": html.escape(profile.get("full_name") or ""),
            "user_role": profile.get("user_role", "customer"),
            "role": profile.get("user_role", "customer"),
            "phone": html.escape(phone) if phone else "",
            "age": profile.get("age"),
            "gender": profile.get("gender"),
            "created_at": profile.get("created_at"),
            "phone_verified": profile.get("phone_verified", False),
            "is_active": profile.get("is_active", True),
        }
    
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
            
            # Fetch user profile. Use maybe_single() so a missing profile returns
            # empty data (-> 404 below) instead of raising PGRST116, which the
            # broad except would otherwise mask as a generic 500.
            profile_response = self.db.table("profiles").select(
                "*"
            ).eq("id", user.id).maybe_single().execute()

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
            
            # Sanitize user data (XSS protection). The Supabase user object is
            # already loaded here, so the confirmation flag costs nothing.
            user_data = self.format_public_user(
                profile,
                email=user.email,
                email_verified=bool(getattr(user, "email_confirmed_at", None)),
            )
            
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

            # Supabase refuses sign_in_with_password until the address is
            # confirmed. Say so plainly instead of masking it as a generic 500
            # below, which reads as "wrong password" to the user. Resending the
            # link needs a token (/resend-verification is authenticated), so the
            # only self-service route from the login screen is the original email.
            if "email not confirmed" in error_message:
                logger.warning(f"Login blocked, email not confirmed: {email}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Please confirm your email address before logging in. We sent a confirmation link when you signed up — check your inbox and spam folder."
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
        user_role: str = "customer",
        verification_token: Optional[str] = None
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
            # Verify and extract phone if token is provided
            phone_verified = False
            verified_phone = None
            if verification_token:
                from app.core.auth import verify_phone_verification_token
                verified_phone = verify_phone_verification_token(verification_token)
                phone_verified = True
                
            # Sanitize inputs (XSS protection)
            sanitized_full_name = html.escape(full_name.strip())
            
            # Use verified phone if available, otherwise use provided phone
            target_phone = verified_phone if phone_verified else phone
            sanitized_phone = html.escape(target_phone.strip()) if target_phone else None

            # Normalize phone to E.164 format if provided
            if sanitized_phone:
                from app.utils.phone import normalize_phone, find_profile_by_phone
                normalized_phone = normalize_phone(sanitized_phone)
                if normalized_phone:
                    sanitized_phone = normalized_phone
                    existing_phone, _ = find_profile_by_phone(self.db, sanitized_phone)
                    if existing_phone and existing_phone.get("phone_verified"):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Phone number already registered"
                        )
                # If normalization fails, keep original (user can verify later)

            
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
                    "email_redirect_to": f"{settings.FRONTEND_URL.rstrip('/')}/",
                    "data": {
                        "full_name": sanitized_full_name,
                        "phone": sanitized_phone,
                        "phone_verified": phone_verified,
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
                "phone_verified": phone_verified,
                "age": age,
                "gender": sanitized_gender,
                "user_role": user_role,
                "is_active": True
            }
            
            if phone_verified:
                profile_data["phone_verification_method"] = "otp"
                profile_data["phone_verified_at"] = datetime.utcnow().isoformat()
            
            try:
                # Try insert first
                self.db.table("profiles").insert(profile_data).execute()
            except Exception as insert_error:
                error_str = str(insert_error)
                
                # Check for duplicate email error
                if "duplicate key" in error_str and "profiles_email_key" in error_str:
                    logger.warning(f"Duplicate email during signup: {email}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already registered"
                    )
                
                logger.warning(f"Profile insert failed, trying update: {insert_error}")
                
                # Try update if insert fails (trigger might have created it)
                try:
                    self.db.table("profiles").update(profile_data).eq("id", user.id).execute()
                except Exception as update_error:
                    logger.error(f"Profile update also failed: {update_error}")
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
            
            # Build user response. Fresh signups are unconfirmed until the emailed
            # link is clicked, which is exactly what the client banner keys off.
            user_data = self.format_public_user(
                profile_data,
                email=email,
                email_verified=bool(getattr(user, "email_confirmed_at", None)),
            )
            
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
            
    async def send_phone_signup_otp(self, phone: str, country_code: str = "91") -> Dict:
        """
        Send OTP for unauthenticated phone signup
        """
        from app.utils.phone import normalize_phone, mask_phone, find_profile_by_phone, split_e164
        from app.services.otp_service import OTPService

        try:
            normalized_phone = normalize_phone(phone, country_code)
            if not normalized_phone:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid phone number format"
                )

            # Check if phone is already registered and verified
            existing_phone, _ = find_profile_by_phone(self.db, phone, country_code)
            if existing_phone and existing_phone.get("phone_verified"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This phone number is already registered to an account. Please sign in."
                )

            country_code_clean, clean_phone = split_e164(normalized_phone, country_code)

            logger.info("Sending phone signup OTP to unauthenticated user")
            otp_result = await OTPService.send_otp(
                phone=clean_phone,
                country_code=country_code_clean
            )

            return {
                "success": True,
                "message": f"OTP sent to {mask_phone(normalized_phone)}",
                "verification_id": otp_result["verification_id"],
                "expires_in": otp_result["expires_in"],
                "phone": otp_result["phone"]
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error sending phone signup OTP: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send OTP. Please try again."
            )

    async def verify_phone_signup_otp(self, phone: str, otp: str, verification_id: str, country_code: str = "91") -> Dict:
        """
        Verify phone OTP for signup and return a verification token
        """
        from app.utils.phone import normalize_phone
        from app.services.otp_service import OTPService
        from app.core.auth import create_phone_verification_token

        try:
            if not otp.isdigit() or len(otp) != 6:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid OTP format. Please enter 6 digits."
                )

            logger.info(f"Verifying phone signup OTP for phone: ****{str(phone)[-4:]}")
            is_valid = await OTPService.verify_otp(
                verification_id=verification_id,
                otp_code=otp
            )

            if not is_valid:
                logger.warning("Invalid signup OTP attempt")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired OTP. Please try again."
                )

            normalized_phone = normalize_phone(phone, country_code)
            if not normalized_phone:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid phone number format"
                )

            # Optional: check again if registered
            from app.utils.phone import find_profile_by_phone
            existing_phone, _ = find_profile_by_phone(self.db, phone, country_code)
            if existing_phone and existing_phone.get("phone_verified"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This phone number is already registered to an account. Please sign in."
                )

            # Generate verification token
            verification_token = create_phone_verification_token(normalized_phone)

            return {
                "success": True,
                "message": "Phone number verified successfully",
                "verification_token": verification_token,
                "phone": normalized_phone
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error verifying phone signup OTP: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to verify phone number. Please try again."
            )

    async def send_phone_login_otp(self, phone: str, country_code: str = "91") -> Dict:
        """
        Send OTP for phone-based login (CUSTOMERS ONLY).

        Validates that the phone exists, is verified, and belongs to an active
        customer account, then dispatches an OTP via MessageCentral.
        """
        from app.utils.phone import (
            normalize_phone,
            find_profile_by_phone,
            reconcile_profile_phone,
            split_e164,
        )
        from app.services.otp_service import OTPService

        try:
            canonical_phone = normalize_phone(phone.strip(), country_code)
            if not canonical_phone:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Please enter a valid 10-digit phone number."
                )

            logger.info(f"Checking phone in database: {canonical_phone[-4:]}")

            profile, _ = find_profile_by_phone(
                self.db,
                phone.strip(),
                country_code=country_code,
                select="id, email, full_name, phone, phone_verified, user_role, is_active",
            )

            if not profile:
                logger.warning("Phone login attempt for non-existent phone")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Phone number not registered. Please sign up first."
                )

            reconcile_profile_phone(self.db, profile["id"], profile.get("phone"), country_code)
            profile["phone"] = canonical_phone

            _, clean_phone = split_e164(canonical_phone, country_code)

            # An unverified number is NOT rejected here. The number is already on
            # this account, and receiving the OTP proves the caller holds it - so
            # the OTP itself is the verification (promoted in verify_phone_login_otp).
            # Blocking here only dead-ended users whose account was made with email.

            # CRITICAL: Only allow customers to login via phone
            if profile.get("user_role") != "customer":
                logger.warning(f"Non-customer user attempted phone login: {profile.get('user_role')}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Phone login is only available for customer accounts. Please use email login."
                )

            # Check if user is active
            if not profile.get("is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is inactive. Please contact support."
                )

            # Send OTP via MessageCentral
            logger.info(f"Sending OTP to verified phone for user: {profile.get('id')}")
            otp_result = await OTPService.send_otp(
                phone=clean_phone,
                country_code=country_code
            )

            return {
                "success": True,
                "message": f"OTP sent successfully to {otp_result['phone']}",
                "verification_id": otp_result["verification_id"],
                "expires_in": otp_result["expires_in"],
                "phone": otp_result["phone"],
                "customer_name": html.escape(profile.get("full_name") or "")
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error sending phone login OTP: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send OTP. Please try again."
            )

    async def verify_phone_login_otp(
        self,
        phone: str,
        otp: str,
        verification_id: str,
        country_code: str = "91"
    ) -> Dict:
        """
        Verify a login OTP and issue JWT tokens (CUSTOMERS ONLY).

        Mirrors the email-login response shape on success.
        """
        from app.utils.phone import (
            normalize_phone,
            find_profile_by_phone,
            reconcile_profile_phone,
        )
        from app.services.otp_service import OTPService

        try:
            clean_otp = otp.strip()
            verification_id = verification_id.strip()

            canonical_phone = normalize_phone(phone.strip(), country_code)
            if not canonical_phone:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Please enter a valid 10-digit phone number."
                )

            # OTP format (6 digits) is already enforced by the request schema.

            # Verify OTP with MessageCentral
            logger.info(f"Verifying OTP for verificationId: {verification_id}")
            is_valid = await OTPService.verify_otp(
                verification_id=verification_id,
                otp_code=clean_otp
            )

            if not is_valid:
                logger.warning(f"Invalid OTP attempt for verificationId: {verification_id}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired OTP. Please try again."
                )

            profile, _ = find_profile_by_phone(
                self.db,
                phone.strip(),
                country_code=country_code,
                select="*",
            )

            if not profile:
                logger.error("Phone verified but profile not found for phone")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found. Please contact support."
                )

            reconcile_profile_phone(self.db, profile["id"], profile.get("phone"), country_code)
            profile["phone"] = canonical_phone

            # Validate user role (MUST be customer)
            if profile.get("user_role") != "customer":
                logger.warning(f"Non-customer user attempted phone login: {profile.get('user_role')}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Phone login is only available for customer accounts."
                )

            # Check if user is active
            if not profile.get("is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is inactive. Please contact support."
                )

            # A correct OTP on a number already held by this account IS the
            # verification, so promote it instead of turning the user away.
            # Accounts created with email keep an unverified number until now.
            if not profile.get("phone_verified", False):
                try:
                    self.db.table("profiles").update({
                        "phone_verified": True,
                        "phone_verified_at": datetime.utcnow().isoformat(),
                        "phone_verification_method": "otp",
                    }).eq("id", profile["id"]).execute()
                    profile["phone_verified"] = True
                    logger.info(f"Phone verified via login OTP for user: {profile['id']}")
                except Exception as e:
                    # The partial unique index means this can only fail when a
                    # DIFFERENT live account already owns the number as verified.
                    # Issuing tokens anyway would hand over the wrong account.
                    logger.error(f"Failed promoting phone to verified for {profile['id']}: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This number is already verified on another account. Please contact support@lubist.com."
                    )

            # Generate JWT tokens
            token_data = {
                "sub": profile["id"],
                "email": profile["email"],
                "user_role": profile.get("user_role", "customer")
            }

            access_token = create_access_token(token_data)
            refresh_token = create_refresh_token(token_data)

            # Sanitize user data for response. Phone-OTP users often never confirm
            # their email, so the flag matters most here.
            user_data = self.format_public_user(
                profile,
                email_verified=await self._is_auth_user_email_confirmed(profile["id"]),
            )

            logger.info(f"User logged in via phone OTP: {profile['email']}")

            # Log activity for phone login (best-effort)
            try:
                await ActivityLogService.log(
                    user_id=profile["id"],
                    action="phone_login",
                    entity_type="auth",
                    entity_id=profile["id"],
                    details={
                        "login_method": "phone_otp",
                        "phone": profile.get("phone", "")[-4:]  # Last 4 digits only
                    }
                )
            except Exception as log_error:
                logger.warning(f"Failed to log phone login activity: {log_error}")

            return {
                "success": True,
                "message": "Login successful",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "user": user_data
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error verifying phone login OTP: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to verify OTP. Please try again."
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
            
            # Fetch current user profile (maybe_single -> empty data, not PGRST116, when missing)
            profile_response = self.db.table("profiles").select(
                "*"
            ).eq("id", token_data["sub"]).maybe_single().execute()
            
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
            ).eq("id", user_id).maybe_single().execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Profile not found"
                )
            
            profile = response.data
            # Add 'role' field for frontend backward compatibility
            profile['role'] = profile.get('user_role', 'customer')

            # `profiles` has no email-confirmation column, so this comes from
            # Supabase's auth.users. It costs one extra call, but /auth/me is the
            # only endpoint a long-lived session re-checks, so it is where a
            # "confirm your email" banner has to get its truth from.
            profile['email_verified'] = await self._is_auth_user_email_confirmed(user_id)

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
            
    async def update_user_profile(self, user_id: str, profile_data: dict) -> Dict:
        """
        Update user profile by ID
        
        Args:
            user_id: User's unique identifier
            profile_data: Dictionary of fields to update
            
        Returns:
            Dict containing updated user profile data
            
        Raises:
            HTTPException: If profile not found or update fails
        """
        try:
            # First verify the user exists
            existing = self.db.table("profiles").select(
                "id, phone, phone_verified"
            ).eq("id", user_id).execute()

            if not existing.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Profile not found"
                )
                
            # Sanitize inputs if present
            update_data = {}
            if "full_name" in profile_data and profile_data["full_name"] is not None:
                update_data["full_name"] = html.escape(profile_data["full_name"].strip())
            if "phone" in profile_data and profile_data["phone"] is not None:
                from app.utils.phone import normalize_phone
                raw_phone = html.escape(profile_data["phone"].strip())
                normalized = normalize_phone(raw_phone)
                if not normalized:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Please enter a valid 10-digit phone number."
                    )
                update_data["phone"] = normalized

                # Moving to a different number drops the verified flag - it was
                # earned by an OTP sent to the OLD number. Carrying it over would
                # let anyone point a verified phone at a number they don't own,
                # and OTP login for that number would then land on this account.
                # Re-saving the SAME number must not reset anything, otherwise a
                # plain name edit would lock the user out of phone login.
                current_phone = normalize_phone(existing.data[0].get("phone")) or existing.data[0].get("phone")
                if existing.data[0].get("phone_verified") and current_phone != normalized:
                    update_data["phone_verified"] = False
                    update_data["phone_verified_at"] = None
                    update_data["phone_verification_method"] = None
            if "age" in profile_data and profile_data["age"] is not None:
                update_data["age"] = profile_data["age"]
            if "gender" in profile_data and profile_data["gender"] is not None:
                gender_lower = profile_data["gender"].lower().strip()
                if gender_lower in ['male', 'female', 'other']:
                    update_data["gender"] = gender_lower
            
            if not update_data:
                return await self.get_user_profile(user_id)
                
            # Perform update
            response = self.db.table("profiles").update(update_data).eq("id", user_id).execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update profile"
                )
            
            profile = response.data[0]
            # Add 'role' field for frontend backward compatibility
            profile['role'] = profile.get('user_role', 'customer')
            
            logger.info(f"User profile updated: {user_id}")
            
            return {
                "success": True,
                "message": "Profile updated successfully",
                "user": profile
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Update profile error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update profile"
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
            
            # Log activity for security audit (best-effort: never fail logout on log error)
            try:
                await ActivityLogService.log(
                    user_id=user_id,
                    action="logout_all_devices",
                    entity_type="auth",
                    entity_id=user_id,
                    details={"timestamp": now.isoformat(), "method": "token_valid_after"}
                )
            except Exception as log_error:
                logger.warning(f"Failed to log logout_all_devices activity: {log_error}")
            
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
    
    # Roles allowed to delete their own account from the apps. Vendors, RMs and
    # admins hold business records (salons, payouts, approvals) that need a human
    # to unwind, so they are routed to support instead.
    SELF_DELETE_ROLES = {"customer", "regular_buyer"}

    async def send_account_deletion_otp(self, user_id: str) -> Dict:
        """
        Send a deletion-confirmation OTP to the phone already on the account.

        Deliberately does NOT take a phone number from the caller: the whole point
        is to prove the requester holds the number we have on file.
        """
        from app.utils.phone import mask_phone, split_e164
        from app.services.otp_service import OTPService

        profile_response = self.db.table("profiles").select(
            "id, phone, phone_verified, deleted_at"
        ).eq("id", user_id).maybe_single().execute()
        profile = getattr(profile_response, "data", None)

        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found"
            )

        if profile.get("deleted_at"):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This account has already been deleted."
            )

        phone = profile.get("phone")
        if not phone or not profile.get("phone_verified"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No verified phone number on this account. Confirm with your password instead."
            )

        country_code_clean, clean_phone = split_e164(phone, "91")
        otp_result = await OTPService.send_otp(phone=clean_phone, country_code=country_code_clean)

        logger.info(f"Account-deletion OTP sent for user {user_id}")
        return {
            "success": True,
            "message": f"OTP sent to {mask_phone(phone)}",
            "verification_id": otp_result["verification_id"],
            "expires_in": otp_result["expires_in"],
            "phone": otp_result["phone"],
        }

    async def _verify_deletion_identity(
        self,
        user_id: str,
        email: str,
        password: Optional[str],
        verification_id: Optional[str],
        otp: Optional[str],
    ) -> None:
        """
        Re-prove identity before an irreversible delete, by password or by OTP.

        Phone-first signups never choose a password - the client generates a
        throwaway one the user never sees - so demanding a password there would
        make deletion impossible for the app's primary signup path.
        """
        from app.services.otp_service import OTPService

        if verification_id and otp:
            profile_response = self.db.table("profiles").select(
                "phone, phone_verified"
            ).eq("id", user_id).maybe_single().execute()
            profile = getattr(profile_response, "data", None) or {}

            if not profile.get("phone") or not profile.get("phone_verified"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No verified phone number on this account."
                )

            if not await OTPService.verify_otp(verification_id=verification_id, otp_code=otp):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired OTP. Please try again."
                )
            return

        if password:
            try:
                auth_response = self.auth_client.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })
            except Exception as e:
                logger.warning(f"Account deletion blocked: password check failed for {user_id}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect password. Please try again."
                )

            if not auth_response.user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect password. Please try again."
                )
            return

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirm deletion with your password or with an OTP sent to your phone."
        )

    async def delete_own_account(
        self,
        user_id: str,
        email: str,
        password: Optional[str] = None,
        verification_id: Optional[str] = None,
        otp: Optional[str] = None,
    ) -> Dict:
        """
        Permanently delete the caller's own account (Google Play account-deletion
        requirement).

        Booking and payment rows carry ON DELETE RESTRICT and must be kept for tax
        and payment-reconciliation purposes, so a customer with history cannot be
        row-deleted. Instead we:

          1. re-prove identity by password or phone OTP (deletion is irreversible),
          2. refuse while an upcoming booking is still open - money is involved,
          3. hard-delete everything purely personal (cart, favourites),
          4. scrub every identifying field from the profile and mark it deleted,
          5. rewrite the Supabase auth user so the credentials stop working and the
             email/phone are freed for reuse.

        What survives is an anonymous booking/payment row with no path back to the
        person. Accounts with no history at all are hard-deleted outright.
        """
        import secrets
        import uuid

        await self._verify_deletion_identity(user_id, email, password, verification_id, otp)

        profile_response = self.db.table("profiles").select(
            "id, user_role, email, deleted_at"
        ).eq("id", user_id).maybe_single().execute()
        profile = getattr(profile_response, "data", None)

        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found"
            )

        if profile.get("deleted_at"):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This account has already been deleted."
            )

        user_role = profile.get("user_role")
        if user_role not in self.SELF_DELETE_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Business accounts cannot be deleted from the app because they hold "
                    "salon and payout records. Email support@lubist.com and we will "
                    "process your deletion request."
                )
            )

        # 2. Block while money is in flight - an upcoming booking is a live commitment
        #    to a salon, and deleting the payer mid-flight strands both sides.
        today = datetime.utcnow().date().isoformat()
        upcoming = self.db.table("bookings").select("id", count="exact") \
            .eq("customer_id", user_id) \
            .gte("booking_date", today) \
            .in_("status", ["pending", "confirmed"]) \
            .is_("deleted_at", "null") \
            .execute()

        if upcoming.count and upcoming.count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"You have {upcoming.count} upcoming booking(s). Please cancel or "
                    "complete them before deleting your account."
                )
            )

        # 3. Drop everything that is purely personal and has no retention duty.
        for table, column in (
            ("cart_items", "user_id"),
            ("product_cart_items", "user_id"),
            ("favorites", "user_id"),
            ("product_favorites", "user_id"),
        ):
            try:
                self.db.table(table).delete().eq(column, user_id).execute()
            except Exception as e:
                # Never abort the deletion over a leftover cart row.
                logger.warning(f"Account deletion: failed clearing {table} for {user_id}: {e}")

        # Count what we are legally obliged to keep, so the user can be told plainly.
        retained = {}
        for label, table in (("bookings", "bookings"), ("payments", "payments")):
            try:
                res = self.db.table(table).select("id", count="exact") \
                    .eq("customer_id", user_id).execute()
                retained[label] = res.count or 0
            except Exception as e:
                logger.warning(f"Account deletion: failed counting {table} for {user_id}: {e}")
                retained[label] = 0

        has_history = any(count > 0 for count in retained.values())

        # Reviews are authored content: unpublish them rather than leave a named review behind.
        try:
            self.db.table("reviews").update({
                "deleted_at": datetime.utcnow().isoformat()
            }).eq("customer_id", user_id).is_("deleted_at", "null").execute()
        except Exception as e:
            logger.warning(f"Account deletion: failed soft-deleting reviews for {user_id}: {e}")

        now = datetime.utcnow()
        anon_email = f"deleted-{uuid.uuid4().hex[:16]}@deleted.lubist.com"

        # 4a. No history at all -> nothing to retain, so remove the rows outright.
        #     Deleting the auth user CASCADEs to profiles.
        if not has_history:
            try:
                self.db.auth.admin.delete_user(user_id)
                logger.info(f"Account {user_id} hard-deleted (no retained records)")
                await self._log_account_deletion(user_id, "hard_delete", now, retained)
                return {
                    "success": True,
                    "message": "Your account and all associated data have been permanently deleted.",
                    "deleted_at": now.isoformat(),
                    "retained_records": retained,
                }
            except Exception as e:
                # Fall through to anonymisation - the user still gets their deletion.
                logger.warning(f"Hard delete failed for {user_id}, anonymising instead: {e}")

        # 4b. Scrub every identifying field. age/gender are NOT NULL, so they are
        #     reset to neutral placeholders rather than nulled.
        try:
            self.db.table("profiles").update({
                "full_name": "Deleted User",
                "email": anon_email,
                "phone": None,
                "avatar_url": None,
                "address_line1": None,
                "address_line2": None,
                "city": None,
                "state": None,
                "pincode": None,
                "age": 18,
                "gender": "other",
                "phone_verified": False,
                "phone_verified_at": None,
                "phone_verification_method": None,
                "is_active": False,
                "deleted_at": now.isoformat(),
                "deleted_by": user_id,
                "token_valid_after": now.isoformat(),
            }).eq("id", user_id).execute()
        except Exception as e:
            logger.error(f"Account deletion: failed anonymising profile {user_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not delete your account. Please contact support@lubist.com."
            )

        # 5. Kill the credentials and free the email/phone for reuse. The auth row
        #    itself must stay because profiles.id -> auth.users.id CASCADEs.
        try:
            self.db.auth.admin.update_user_by_id(user_id, {
                "email": anon_email,
                "email_confirm": True,
                "phone": None,
                "password": secrets.token_urlsafe(32),
                "user_metadata": {"deleted": True},
            })
        except Exception as e:
            # The profile is already deactivated, so no login can succeed regardless.
            logger.error(f"Account deletion: failed scrubbing auth user {user_id}: {e}")

        logger.info(f"Account {user_id} deleted (anonymised, retained={retained})")
        await self._log_account_deletion(user_id, "anonymised", now, retained)

        return {
            "success": True,
            "message": (
                "Your account has been deleted and your personal details erased. "
                "Booking and payment records are kept in anonymous form only where "
                "the law requires it."
            ),
            "deleted_at": now.isoformat(),
            "retained_records": retained,
        }

    async def _log_account_deletion(
        self, user_id: str, method: str, when: datetime, retained: Dict
    ) -> None:
        """Best-effort audit trail for a self-service deletion (never fails the request)."""
        try:
            await ActivityLogService.log(
                user_id=None if method == "hard_delete" else user_id,
                action="account_self_deleted",
                entity_type="auth",
                entity_id=user_id,
                details={"method": method, "timestamp": when.isoformat(), "retained": retained},
            )
        except Exception as e:
            logger.warning(f"Failed to log account deletion for {user_id}: {e}")

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
            response = self.db.table("profiles").select("id, email").eq("email", email).maybe_single().execute()
            
            if not response.data:
                # Don't reveal if email exists for security
                logger.info("Password reset requested for non-existent email (redacted)")
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
            
            # Fetch user profile (maybe_single -> empty data, not PGRST116, when missing)
            profile_response = self.db.table("profiles").select(
                "*"
            ).eq("id", user_id).maybe_single().execute()
            
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
            
            # Sanitize user data. Completing a password reset proves control of the
            # inbox, so Supabase may have confirmed the address as a side effect —
            # re-read it rather than assuming either way.
            user_data = self.format_public_user(
                profile,
                email=user_email,
                email_verified=await self._is_auth_user_email_confirmed(user_id),
            )
            
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
    def _email_verification_redirect_url(self) -> str:
        return f"{settings.FRONTEND_URL.rstrip('/')}/"

    async def _is_auth_user_email_confirmed(self, user_id: str) -> Optional[bool]:
        """
        Return True/False when known, or None if auth user could not be loaded.

        `email_confirmed_at` lives only in Supabase's `auth.users`; there is no
        mirrored column on `profiles`, so callers that hold a Supabase user object
        should read it from there instead of paying for this extra round trip.
        """
        url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/admin/users/{user_id}"
        headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=headers)
            if response.status_code != 200:
                logger.warning(
                    "Could not load auth user %s for verification check: %s %s",
                    user_id,
                    response.status_code,
                    response.text,
                )
                return None
            data = response.json()
            return bool(data.get("email_confirmed_at"))
        except Exception as exc:
            logger.warning("Auth user lookup failed for %s: %s", user_id, exc)
            return None

    async def _supabase_resend_signup_confirmation(self, email: str) -> None:
        """
        Call Supabase GoTrue /resend directly.

        supabase==2.0.3 does not expose auth.resend on the Python client, so the
        previous implementation always failed while still returning success.
        """
        url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/resend"
        headers = {
            "apikey": settings.SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "type": "signup",
            "email": email,
            "options": {
                "email_redirect_to": self._email_verification_redirect_url(),
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code < 400:
            return

        try:
            error_body = response.json()
        except Exception:
            error_body = {}

        error_text = (
            error_body.get("msg")
            or error_body.get("error_description")
            or error_body.get("message")
            or response.text
            or "Unknown error"
        ).lower()
        logger.error(
            "Supabase resend failed for %s: status=%s body=%s",
            email,
            response.status_code,
            error_body or response.text,
        )

        if response.status_code == 429 or "rate" in error_text:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many verification emails requested. Please try again later.",
            )

        if "already" in error_text and ("confirm" in error_text or "verified" in error_text):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email address is already verified.",
            )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send verification email right now. Please try again in a few minutes.",
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
        email_confirmed = await self._is_auth_user_email_confirmed(user_id)
        if email_confirmed is True:
            return {
                "success": True,
                "already_verified": True,
                "message": "Your email is already verified.",
            }

        await self._supabase_resend_signup_confirmation(email)

        logger.info("Verification email resent to: %s", email)
        return {
            "success": True,
            "message": "Verification email sent successfully. Please check your inbox.",
        }

    def _ensure_phone_available(self, phone: str, country_code: str, exclude_user_id: str, error_detail: str) -> None:
        """Raise 400 if `phone` is already verified on a different user's profile."""
        from app.utils.phone import find_profile_by_phone

        existing_phone, _ = find_profile_by_phone(self.db, phone, country_code)
        if existing_phone and existing_phone.get("phone_verified") and existing_phone["id"] != exclude_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail
            )

    async def send_phone_verification_otp(self, user_id: str, phone: str, country_code: str = "91") -> Dict:
        """
        Send OTP to verify phone number (for authenticated users updating their phone)

        Args:
            user_id: User's unique identifier
            phone: Phone number to verify
            country_code: Country code (default: 91 for India)

        Returns:
            Dict with verification_id and masked phone

        Raises:
            HTTPException: If user not found or OTP sending fails
        """
        from app.utils.phone import normalize_phone, mask_phone, find_profile_by_phone, split_e164
        from app.services.otp_service import OTPService

        try:
            # Verify user exists
            profile_response = self.db.table("profiles").select("id, email").eq("id", user_id).execute()
            if not profile_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )

            # Normalize phone to E.164 format
            normalized_phone = normalize_phone(phone, country_code)
            if not normalized_phone:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid phone number format"
                )

            # Check if phone is already registered by another verified user
            self._ensure_phone_available(
                phone, country_code, exclude_user_id=user_id,
                error_detail="This phone number is already registered"
            )

            # Extract country code and local phone number from normalized E.164.
            country_code_clean, clean_phone = split_e164(normalized_phone, country_code)

            # Send OTP via MessageCentral
            logger.info(f"Sending phone verification OTP for user: {user_id}")
            otp_result = await OTPService.send_otp(
                phone=clean_phone,
                country_code=country_code_clean
            )

            return {
                "success": True,
                "message": f"OTP sent to {mask_phone(normalized_phone)}",
                "verification_id": otp_result["verification_id"],
                "expires_in": otp_result["expires_in"],
                "phone": otp_result["phone"]
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error sending phone verification OTP: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send OTP. Please try again."
            )

    async def verify_phone_otp(
        self,
        user_id: str,
        phone: str,
        otp: str,
        verification_id: str,
        country_code: str = "91"
    ) -> Dict:
        """
        Verify phone number with OTP and update profile

        Args:
            user_id: User's unique identifier
            phone: Phone number being verified
            otp: 6-digit OTP code
            verification_id: Verification ID from send_otp
            country_code: Country code (default: 91 for India)

        Returns:
            Dict with updated phone and phone_verified status

        Raises:
            HTTPException: If verification fails or OTP invalid
        """
        from app.utils.phone import normalize_phone
        from app.services.otp_service import OTPService

        try:
            # Verify user exists
            profile_response = self.db.table("profiles").select("id, email").eq("id", user_id).execute()
            if not profile_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )

            # Validate OTP format
            if not otp.isdigit() or len(otp) != 6:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid OTP format. Please enter 6 digits."
                )

            # Verify OTP with MessageCentral
            logger.info(f"Verifying phone OTP for user: {user_id}")
            is_valid = await OTPService.verify_otp(
                verification_id=verification_id,
                otp_code=otp
            )

            if not is_valid:
                logger.warning(f"Invalid OTP attempt for user: {user_id}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired OTP. Please try again."
                )

            # Normalize phone to E.164 format
            normalized_phone = normalize_phone(phone, country_code)
            if not normalized_phone:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid phone number format"
                )

            # Check if phone is already registered by another verified user
            self._ensure_phone_available(
                phone, country_code, exclude_user_id=user_id,
                error_detail="This phone number is already registered by another user"
            )

            # Update user profile with verified phone
            now = datetime.utcnow()
            update_response = self.db.table("profiles").update({
                "phone": normalized_phone,
                "phone_verified": True,
                "phone_verified_at": now.isoformat(),
                "phone_verification_method": "otp"
            }).eq("id", user_id).execute()

            if not update_response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update phone number"
                )

            profile = update_response.data[0]

            logger.info(f"Phone verified for user: {user_id}")

            # Log activity
            try:
                await ActivityLogService.log(
                    user_id=user_id,
                    action="phone_verified",
                    entity_type="auth",
                    entity_id=user_id,
                    details={
                        "phone": normalized_phone[-4:]  # Last 4 digits only
                    }
                )
            except Exception as log_error:
                logger.warning(f"Failed to log phone verification: {log_error}")

            return {
                "success": True,
                "message": "Phone number verified successfully",
                "phone_verified": True,
                "phone": normalized_phone,
                "user": {
                    "id": profile["id"],
                    "email": profile["email"],
                    "phone": profile.get("phone"),
                    "phone_verified": profile.get("phone_verified", False),
                    "phone_verified_at": profile.get("phone_verified_at")
                }
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error verifying phone OTP: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to verify phone number. Please try again."
            )
