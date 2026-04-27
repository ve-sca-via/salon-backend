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
from app.services.otp_service import OTPService
from app.core.database import get_db_client, get_auth_client
import logging
import html

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
        from fastapi import HTTPException, status
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
    db: Client = Depends(get_db_client)
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
    try:
        # Sanitize and clean phone number
        clean_phone = html.escape(phone_data.phone.strip())
        clean_phone = clean_phone.replace("+", "").replace(" ", "").replace("-", "")
        country_code = phone_data.country_code or "91"

        # Remove country code if present at start
        if clean_phone.startswith(country_code):
            clean_phone = clean_phone[len(country_code):]

        # Build full phone number for database lookup
        full_phone = f"+{country_code}{clean_phone}"

        # Check if phone exists in profiles table
        logger.info(f"Checking phone in database: {full_phone[-4:]}")  # Log last 4 digits only

        profile_response = db.table("profiles").select(
            "id, email, full_name, phone, phone_verified, user_role, is_active"
        ).eq("phone", full_phone).execute()

        if not profile_response.data or len(profile_response.data) == 0:
            # Don't reveal if phone exists for security
            logger.warning(f"Phone login attempt for non-existent phone")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Phone number not registered. Please sign up first."
            )

        profile = profile_response.data[0]

        # Check if phone is verified
        if not profile.get("phone_verified", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Phone number not verified. Please verify your phone first."
            )

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

        return PhoneLoginSendOTPResponse(
            success=True,
            message=f"OTP sent successfully to {otp_result['phone']}",
            verification_id=otp_result["verification_id"],
            expires_in=otp_result["expires_in"],
            phone=otp_result["phone"],
            customer_name=html.escape(profile.get("full_name") or "")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending phone login OTP: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP. Please try again."
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
    try:
        # Sanitize inputs
        clean_phone = html.escape(verify_data.phone.strip())
        clean_phone = clean_phone.replace("+", "").replace(" ", "").replace("-", "")
        clean_otp = verify_data.otp.strip()
        verification_id = verify_data.verification_id.strip()

        # Validate OTP format (6 digits)
        if not clean_otp.isdigit() or len(clean_otp) != 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP format. Please enter 6 digits."
            )

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

        # OTP is valid - fetch user profile
        # Try to find by phone (try with and without + prefix)
        phone_variants = [
            clean_phone,
            f"+{clean_phone}",
            f"+91{clean_phone}" if not clean_phone.startswith("91") else clean_phone
        ]

        profile = None
        for phone_variant in phone_variants:
            profile_response = db.table("profiles").select(
                "*"
            ).eq("phone", phone_variant).eq("phone_verified", True).execute()

            if profile_response.data and len(profile_response.data) > 0:
                profile = profile_response.data[0]
                break

        if not profile:
            logger.error(f"Phone verified but profile not found for phone")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found. Please contact support."
            )

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

        # Generate JWT tokens
        from app.core.auth import create_access_token, create_refresh_token

        token_data = {
            "sub": profile["id"],
            "email": profile["email"],
            "user_role": profile.get("user_role", "customer")
        }

        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        # Sanitize user data for response
        user_data = {
            "id": profile["id"],
            "email": profile["email"],
            "full_name": html.escape(profile.get("full_name") or ""),
            "user_role": profile.get("user_role", "customer"),
            "role": profile.get("user_role", "customer"),  # Backward compatibility
            "phone": html.escape(profile.get("phone") or ""),
            "is_active": profile.get("is_active", True)
        }

        logger.info(f"User logged in via phone OTP: {profile['email']}")

        # Log activity for phone login
        from app.services.activity_log_service import ActivityLogService
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

        return PhoneLoginVerifyOTPResponse(
            success=True,
            message="Login successful",
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=user_data
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying phone login OTP: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify OTP. Please try again."
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