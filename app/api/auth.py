from fastapi import APIRouter, HTTPException, Depends, status
from app.core.config import settings
from app.core.auth import get_current_user, TokenData
from app.schemas import (
    LoginRequest,
    LoginResponse,
    SignupRequest,
    SignupResponse,
    LogoutAllRequest,
    RefreshTokenRequest
)
from app.services.auth_service import AuthService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])
auth_service = AuthService()

# --- Supabase Initialization ---
if not all([settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY, settings.SUPABASE_SERVICE_ROLE_KEY]):
    raise RuntimeError("Missing Supabase environment variables")


# --- Auth Routes ---
@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest):
    """
    Authenticate user and return JWT tokens
    - Validates credentials with Supabase Auth
    - Returns access token and refresh token
    - Includes user profile data
    """
    result = await auth_service.authenticate_user(
        email=credentials.email,
        password=credentials.password
    )
    return LoginResponse(**result)


@router.post("/signup", response_model=SignupResponse)
async def signup(request: SignupRequest):
    """
    Register new user (customer only)
    - Creates Supabase auth user
    - Creates profile entry
    - Role defaults to 'customer'
    """
    result = await auth_service.register_user(
        email=request.email,
        password=request.password,
        full_name=request.full_name,
        phone=request.phone,
        role=request.role
    )
    return SignupResponse(**result)


@router.post("/refresh")
async def refresh_access_token(request: RefreshTokenRequest):
    """
    Refresh access token using refresh token
    - Validates refresh token
    - Returns new access token
    - Extends session
    """
    return await auth_service.refresh_user_session(request.refresh_token)


@router.get("/me")
async def get_current_user_profile(current_user: TokenData = Depends(get_current_user)):
    """
    Get current authenticated user profile
    - Requires valid JWT token
    - Returns user data
    """
    return await auth_service.get_user_profile(current_user.user_id)


@router.post("/logout")
async def logout(current_user: TokenData = Depends(get_current_user)):
    """
    Logout user by revoking their access token
    
    - Adds current token to blacklist to prevent reuse
    - Client should also delete refresh token
    - Returns success message
    """
    return await auth_service.logout_user(
        user_id=current_user.user_id,
        token_jti=current_user.jti if hasattr(current_user, 'jti') else None,
        expires_at=current_user.exp
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
    return await auth_service.logout_all_devices(
        user_id=current_user.user_id,
        email=current_user.email,
        password=request.password,
        current_token_jti=current_user.jti if hasattr(current_user, 'jti') else None,
        current_token_exp=current_user.exp
    )

