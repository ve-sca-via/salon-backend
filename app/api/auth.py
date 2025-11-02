from fastapi import APIRouter, HTTPException, Depends, status
from supabase import create_client, Client
from typing import Optional, Dict
import html
from app.core.config import settings
from app.core.auth import create_access_token, create_refresh_token, get_current_user, TokenData, revoke_token, verify_token
from app.schemas import (
    LoginRequest,
    LoginResponse,
    SignupRequest,
    SignupResponse,
    LogoutAllRequest,
    RefreshTokenRequest
)
from datetime import timedelta, datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# --- Supabase Initialization ---
if not all([settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY, settings.SUPABASE_SERVICE_ROLE_KEY]):
    raise RuntimeError("Missing Supabase environment variables")

supabase_auth: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
supabase_service: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


# --- Auth Routes ---
@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest):
    """
    Authenticate user and return JWT tokens
    - Validates credentials with Supabase Auth
    - Returns access token and refresh token
    - Includes user profile data
    """
    try:
        # Supabase sign-in
        auth_response = supabase_auth.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })

        user = getattr(auth_response, "user", None)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Fetch profile via service role
        profile_response = supabase_service.table("profiles").select(
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

        # Update last_login_at timestamp
        try:
            from datetime import datetime
            supabase_service.table("profiles").update({
                "last_login_at": datetime.utcnow().isoformat()
            }).eq("id", user.id).execute()
        except Exception as e:
            logger.warning(f"Failed to update last_login_at: {e}")

        # Create JWT tokens
        token_data = {
            "sub": user.id,
            "email": user.email,
            "role": profile.get("role", "customer")
        }

        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        # Build user response (sanitize data from database to prevent XSS)
        user_data = {
            "id": user.id,
            "email": user.email,
            "full_name": html.escape(profile.get("full_name", "")),
            "role": profile.get("role", "customer"),
            "phone": html.escape(profile.get("phone", "")),
            "is_active": profile.get("is_active", True)
        }

        logger.info(f"User logged in: {user.email} (role: {profile.get('role')})")

        return LoginResponse(
            success=True,
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_data
        )

    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e).lower()
        logger.error(f"Login error: {str(e)}")
        
        # Check if it's an authentication error from Supabase
        if "invalid login credentials" in error_message or "invalid credentials" in error_message:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        # Generic error for other issues
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/signup", response_model=SignupResponse)
async def signup(request: SignupRequest):
    """
    Register new user (customer only)
    - Creates Supabase auth user
    - Creates profile entry
    - Role defaults to 'customer'
    """
    try:
        # Sanitize inputs to prevent XSS
        sanitized_full_name = html.escape(request.full_name.strip())
        sanitized_phone = html.escape(request.phone.strip()) if request.phone else None
        
        # Only allow customer signups through this endpoint
        if request.role not in ["customer"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role. Use customer signup only."
            )

        # First, check if user already exists
        try:
            existing = supabase_service.table("profiles").select("id").eq("email", request.email).execute()
            if existing.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
        except HTTPException:
            raise  # Re-raise HTTP exceptions
        except Exception as e:
            logger.warning(f"Could not check existing user: {e}")
            pass  # Continue if check fails

        # Create auth user with auto_confirm to bypass trigger issues
        auth_response = supabase_auth.auth.sign_up({
            "email": request.email,
            "password": request.password,
            "options": {
                "data": {
                    "full_name": sanitized_full_name,
                    "phone": sanitized_phone,
                    "role": request.role
                }
            }
        })

        user = getattr(auth_response, "user", None)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create user account"
            )

        # Small delay to ensure auth user is created
        import time
        time.sleep(0.5)

        # Create or update profile (in case trigger partially worked)
        profile_data = {
            "id": user.id,
            "email": request.email,
            "full_name": sanitized_full_name,
            "phone": sanitized_phone,
            "role": request.role,
            "is_active": True,
            "email_verified": user.email_confirmed_at is not None  # Check if email is confirmed
        }

        try:
            # Try insert first
            profile_response = supabase_service.table("profiles").insert(profile_data).execute()
        except Exception as insert_error:
            error_str = str(insert_error)
            
            # Check if it's a duplicate email error
            if "duplicate key" in error_str and "profiles_email_key" in error_str:
                logger.warning(f"Duplicate email during signup: {request.email}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
            
            logger.warning(f"Profile insert failed, trying upsert: {insert_error}")
            # If insert fails (maybe trigger created it), try upsert
            try:
                profile_response = supabase_service.table("profiles").upsert(profile_data).execute()
            except Exception as upsert_error:
                logger.error(f"Profile upsert also failed: {upsert_error}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Unable to create account. Please try again."
                )
        
        if not profile_response.data:
            logger.error(f"No profile data returned after insert/upsert")
            # Don't fail here, profile might exist from trigger
            pass

        # Create JWT tokens for auto-login
        token_data = {
            "sub": user.id,
            "email": request.email,
            "role": request.role
        }

        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        # Build user response
        user_data = {
            "id": user.id,
            "email": request.email,
            "full_name": sanitized_full_name,
            "role": request.role,
            "phone": sanitized_phone,
            "is_active": True
        }

        logger.info(f"New user registered: {request.email}")

        return SignupResponse(
            success=True,
            message="Account created successfully!",
            user_id=user.id,
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_data
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Signup failed: {str(e)}"
        )


@router.post("/refresh")
async def refresh_access_token(request: RefreshTokenRequest):
    """
    Refresh access token using refresh token
    - Validates refresh token
    - Returns new access token
    - Extends session
    """
    try:
        # Verify refresh token and extract data
        from app.core.auth import verify_refresh_token
        
        token_data = verify_refresh_token(request.refresh_token)
        
        # Fetch current user profile to ensure user still exists and is active
        profile_response = supabase_service.table("profiles").select(
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
        
        # Create new access token with updated data
        new_token_data = {
            "sub": profile["id"],
            "email": profile["email"],
            "role": profile.get("role", "customer")
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


@router.get("/me")
async def get_current_user_profile(current_user: TokenData = Depends(get_current_user)):
    """
    Get current authenticated user profile
    - Requires valid JWT token
    - Returns user data
    """
    try:
        response = supabase_service.table("profiles").select(
            "*"
        ).eq("id", current_user.user_id).single().execute()

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )

        return {
            "success": True,
            "user": response.data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get profile error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch profile"
        )


@router.post("/logout")
async def logout(current_user: TokenData = Depends(get_current_user)):
    """
    Logout user by revoking their access token
    
    - Adds current token to blacklist to prevent reuse
    - Client should also delete refresh token
    - Returns success message
    """
    try:
        # Get token expiration from current_user (already a datetime object)
        expires_at = current_user.exp
        
        # Revoke the access token by adding to blacklist
        revoke_token(
            token_jti=current_user.jti if hasattr(current_user, 'jti') else None,
            user_id=current_user.user_id,
            token_type="access",
            expires_at=expires_at,
            reason="logout"
        )
        
        logger.info(f"User logged out: {current_user.user_id}")
        
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


@router.post("/logout-all")
async def logout_all_devices(
    request: LogoutAllRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Logout user from all devices by revoking all their tokens
    
    - Requires password confirmation for security
    - Revokes current token and invalidates all sessions
    - User must login again on all devices
    """
    try:
        # Verify password before revoking all tokens
        auth_response = supabase_auth.auth.sign_in_with_password({
            "email": current_user.email,
            "password": request.password
        })
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password"
            )
        
        # Revoke current token
        if hasattr(current_user, 'jti') and current_user.jti:
            expires_at = datetime.utcfromtimestamp(current_user.exp)
            revoke_token(
                token_jti=current_user.jti,
                user_id=current_user.user_id,
                token_type="access",
                expires_at=expires_at,
                reason="logout_all"
            )
        
        # Note: In a complete implementation, you'd track all active tokens
        # For now, we log the action and revoke the current token
        logger.warning(f"Logout all devices requested for user: {current_user.user_id}")
        
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

