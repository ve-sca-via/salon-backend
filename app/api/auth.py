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
    AccountDeleteRequest,
    AccountDeleteResponse,
    RefreshTokenRequest,
    PasswordResetRequest,
    PasswordResetResponse,
    PasswordResetConfirm,
    PasswordResetConfirmResponse,
    UserProfileUpdate,
    PhoneLoginSendOTPRequest,
    PhoneLoginSendOTPResponse,
    PhoneLoginVerifyOTPRequest,
    PhoneLoginVerifyOTPResponse,
    PhoneVerificationSendOTPRequest,
    PhoneVerificationSendOTPResponse,
    PhoneVerificationConfirmRequest,
    PhoneVerificationConfirmResponse,
    PhoneSignupSendOTPRequest,
    PhoneSignupVerifyOTPRequest
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
        age=signup_data.age,
        gender=signup_data.gender,
        user_role=signup_data.user_role,
        verification_token=signup_data.verification_token
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


@router.put("/me")
async def update_current_user_profile(
    profile_data: UserProfileUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Update current authenticated user profile
    - Requires valid JWT token
    - Restricted to 'customer' role
    - Returns updated user data
    """
    if current_user.user_role != 'customer':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only customers can update their profile via this endpoint"
        )
        
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    return await auth_service.update_user_profile(
        user_id=current_user.user_id,
        profile_data=profile_data.model_dump(exclude_unset=True)
    )



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


@router.delete("/me", response_model=AccountDeleteResponse)
@limiter.limit(RateLimits.AUTH_ACCOUNT_DELETE)
async def delete_own_account(
    request: Request,  # Required for rate limiter
    delete_request: AccountDeleteRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Permanently delete the signed-in user's own account (Google Play requirement)

    - Requires the literal text "DELETE" plus identity proof: either the password,
      or an OTP from /auth/me/delete/send-otp (phone-first signups have no password
      they know)
    - Erases personal data; booking/payment records are kept anonymised where
      retention is legally required
    - Irreversible: the user must sign up again to use Lubist
    """
    if delete_request.confirmation.strip().upper() != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Please type "DELETE" to confirm account deletion.'
        )

    auth_service = AuthService(db_client=db, auth_client=auth_client)
    return await auth_service.delete_own_account(
        user_id=current_user.user_id,
        email=current_user.email,
        password=delete_request.password,
        verification_id=delete_request.verification_id,
        otp=delete_request.otp
    )


@router.post("/me/delete/send-otp", response_model=PhoneVerificationSendOTPResponse)
@limiter.limit("3 per 5 minutes")
async def send_account_deletion_otp(
    request: Request,  # Required for rate limiter
    current_user: TokenData = Depends(get_current_user),
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Send an account-deletion confirmation OTP to the phone on file

    For users who signed up with a phone number and therefore have no password
    they know. The number is read from the profile, never taken from the caller.
    """
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    return await auth_service.send_account_deletion_otp(user_id=current_user.user_id)


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


# =====================================================
# PHONE SIGNUP (UNAUTHENTICATED)
# =====================================================

@router.post("/signup/phone/send-otp", response_model=PhoneLoginSendOTPResponse)
@limiter.limit("3 per 5 minutes")
async def send_phone_signup_otp(
    request: Request,
    phone_data: PhoneSignupSendOTPRequest,
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Send OTP to phone number for unauthenticated signup
    """
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    return await auth_service.send_phone_signup_otp(
        phone=phone_data.phone,
        country_code=phone_data.country_code or "91"
    )

@router.post("/signup/phone/verify-otp")
@limiter.limit("5 per 5 minutes")
async def verify_phone_signup_otp(
    request: Request,
    verify_data: PhoneSignupVerifyOTPRequest,
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Verify OTP during phone signup process
    """
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    return await auth_service.verify_phone_signup_otp(
        phone=verify_data.phone,
        otp=verify_data.otp,
        verification_id=verify_data.verification_id,
        country_code="91"
    )

# =====================================================
# PHONE OTP LOGIN (CUSTOMERS ONLY)
# =====================================================

@router.post("/login/phone/send-otp", response_model=PhoneLoginSendOTPResponse)
@limiter.limit("3 per 5 minutes")  # Prevent OTP spam
async def send_phone_login_otp(
    request: Request,  # Required for rate limiter
    phone_data: PhoneLoginSendOTPRequest,
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Send OTP to phone number for login (CUSTOMERS ONLY)

    - Validates that phone exists and is verified in database
    - Validates user is a customer (other roles must use email login)
    - Sends 6-digit OTP via MessageCentral SMS
    - Returns verification_id for OTP verification step
    - Rate limited: 3 OTP sends per 5 minutes per IP

    **Note**: Only customer accounts can log in via phone. Admin, RM, and Vendor
    users must use email login.
    """
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    return await auth_service.send_phone_login_otp(
        phone=phone_data.phone,
        country_code=phone_data.country_code or "91"
    )


@router.post("/login/phone/verify-otp", response_model=PhoneLoginVerifyOTPResponse)
@limiter.limit("5 per 5 minutes")  # Allow retries for wrong OTP
async def verify_phone_login_otp(
    request: Request,  # Required for rate limiter
    verify_data: PhoneLoginVerifyOTPRequest,
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Verify OTP and login user via phone (CUSTOMERS ONLY)

    - Verifies OTP with MessageCentral
    - Validates user is customer and account is active
    - Generates JWT tokens (access + refresh)
    - Returns same response as email login
    - Rate limited: 5 verification attempts per 5 minutes

    **Note**: Only customer accounts can log in via phone.
    """
    auth_service = AuthService(db_client=db, auth_client=auth_client)
    return await auth_service.verify_phone_login_otp(
        phone=verify_data.phone,
        otp=verify_data.otp,
        verification_id=verify_data.verification_id,
        country_code=verify_data.country_code or "91"
    )


# =====================================================
# PHONE VERIFICATION (FOR UPDATING PROFILE)
# =====================================================

@router.post("/verify-phone/send-otp", response_model=PhoneVerificationSendOTPResponse)
@limiter.limit("3 per 5 minutes")
async def send_phone_verification_otp(
    request: Request,
    phone_data: PhoneVerificationSendOTPRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Send OTP for phone verification (for authenticated users)

    - User must be logged in (JWT token required)
    - Sends 6-digit OTP to new phone number
    - Returns verification_id for OTP verification step
    - Rate limited: 3 sends per 5 minutes

    **Use Case**: When user wants to update their phone number and verify it
    """
    try:
        auth_service = AuthService(db_client=db, auth_client=auth_client)
        return await auth_service.send_phone_verification_otp(
            user_id=current_user.user_id,
            phone=phone_data.phone,
            country_code=phone_data.country_code or "91"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending phone verification OTP: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP. Please try again."
        )


@router.post("/verify-phone/confirm-otp", response_model=PhoneVerificationConfirmResponse)
@limiter.limit("5 per 5 minutes")
async def confirm_phone_verification_otp(
    request: Request,
    verify_data: PhoneVerificationConfirmRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Client = Depends(get_db_client),
    auth_client: Client = Depends(get_auth_client)
):
    """
    Verify phone number with OTP and update profile

    - User must be logged in (JWT token required)
    - Validates 6-digit OTP with MessageCentral
    - Updates user profile with verified phone
    - Sets phone_verified = true and phone_verification_method = "otp"
    - Rate limited: 5 attempts per 5 minutes

    **Use Case**: Completing phone verification after OTP sent
    """
    try:
        auth_service = AuthService(db_client=db, auth_client=auth_client)
        return await auth_service.verify_phone_otp(
            user_id=current_user.user_id,
            phone=verify_data.phone,
            otp=verify_data.otp,
            verification_id=verify_data.verification_id,
            country_code="91"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error confirming phone verification OTP: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify phone number. Please try again."
        )