from fastapi import APIRouter, HTTPException, Depends, status, Request
from supabase import Client
from app.core.config import settings
from app.core.auth import get_current_user, TokenData
from app.core.rate_limit import limiter, RateLimits
from app.schemas import (
    LoginRequest,
    LoginResponse,
    SignupRequest,
    SignupResponse,
    LogoutAllRequest,
    RefreshTokenRequest,
    PasswordResetRequest,
    PasswordResetResponse,
    PasswordResetConfirm,
    PasswordResetConfirmResponse
)
from app.services.auth_service import AuthService
from app.core.database import get_db_client, get_auth_client
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# --- Supabase Initialization ---
if not all([settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY, settings.SUPABASE_SERVICE_ROLE_KEY]):
    raise RuntimeError("Missing Supabase environment variables")


# --- Auth Routes ---
@router.post("/login", response_model=LoginResponse)
@limiter.limit(RateLimits.AUTH_LOGIN)  # Max 5 attempts per minute
async def login(
    request: Request,  # Required for rate limiter
    credentials: LoginRequest,
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Authenticate user and return JWT tokens
    - Validates credentials with Supabase Auth
    - Returns access token and refresh token
    - Includes user profile data
    - Rate limited: 5 attempts per minute to prevent brute-force
    """
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    result = await auth_service.authenticate_user(
        email=credentials.email,
        password=credentials.password
    )
    return LoginResponse(**result)


@router.post("/signup", response_model=SignupResponse)
@limiter.limit(RateLimits.AUTH_SIGNUP)  # Max 3 signups per minute
async def signup(
    request: Request,  # Required for rate limiter
    signup_data: SignupRequest,
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Register new user (customer only)
    - Creates Supabase auth user
    - Creates profile entry
    - Role defaults to 'customer'
    - Rate limited: 3 signups per minute to prevent abuse
    """
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    result = await auth_service.register_user(
        email=signup_data.email,
        password=signup_data.password,
        full_name=signup_data.full_name,
        phone=signup_data.phone,
        user_role=signup_data.user_role
    )
    return SignupResponse(**result)


@router.post("/refresh")
@limiter.limit(RateLimits.AUTH_REFRESH)  # Max 10 refreshes per minute
async def refresh_access_token(
    request: Request,  # Required for rate limiter
    refresh_data: RefreshTokenRequest,
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Refresh access token using refresh token
    - Validates refresh token
    - Returns new access token
    - Extends session
    - Rate limited: 10 refreshes per minute
    """
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    return await auth_service.refresh_user_session(refresh_data.refresh_token)


@router.get("/me")
async def get_current_user_profile(
    current_user: TokenData = Depends(get_current_user),
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Get current authenticated user profile
    - Requires valid JWT token
    - Returns user data
    """
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    return await auth_service.get_user_profile(current_user.user_id)


@router.post("/logout")
async def logout(
    current_user: TokenData = Depends(get_current_user),
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Logout user by revoking their access token
    
    - Adds current token to blacklist to prevent reuse
    - Client should also delete refresh token
    - Returns success message
    """
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    return await auth_service.logout_user(
        user_id=current_user.user_id,
        token_jti=current_user.jti if hasattr(current_user, 'jti') else None,
        expires_at=current_user.exp
    )


@router.post("/logout-all")
async def logout_all_devices(
    request: LogoutAllRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Logout user from all devices by revoking all their tokens
    
    - Requires password confirmation for security
    - Revokes current token and invalidates all sessions
    - User must login again on all devices
    """
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    return await auth_service.logout_all_devices(
        user_id=current_user.user_id,
        email=current_user.email,
        password=request.password,
        current_token_jti=current_user.jti if hasattr(current_user, 'jti') else None,
        current_token_exp=current_user.exp
    )


@router.post("/password-reset", response_model=PasswordResetResponse)
@limiter.limit(RateLimits.AUTH_PASSWORD_RESET)  # Max 3 attempts per hour
async def initiate_password_reset(
    request: Request,  # Required for rate limiter
    reset_data: PasswordResetRequest,
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Initiate password reset process
    
    Sends password reset email to user if account exists
    Returns success message regardless for security
    Rate limited: 3 attempts per hour to prevent abuse
    """
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    return await auth_service.initiate_password_reset(reset_data.email)


@router.post("/password-reset/confirm", response_model=PasswordResetConfirmResponse)
async def confirm_password_reset(
    request: PasswordResetConfirm,
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Confirm password reset with token
    
    Validates reset token and updates password
    Returns new access tokens for immediate login
    """
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    return await auth_service.confirm_password_reset(
        token=request.token,
        new_password=request.new_password
    )


@router.post("/resend-verification")
@limiter.limit(RateLimits.AUTH_PASSWORD_RESET)  # Max 3 attempts per hour
async def resend_verification_email(
    request: Request,  # Required for rate limiter
    current_user: TokenData = Depends(get_current_user),
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Resend email verification link
    
    Sends a new verification email to the user if their email is not yet confirmed
    Rate limited: 3 attempts per hour to prevent abuse
    """
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    return await auth_service.resend_verification_email(current_user.user_id, current_user.email)
