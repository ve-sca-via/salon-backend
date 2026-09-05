"""
OTP Service using MessageCentral API
Handles OTP generation, sending, and verification for phone-based authentication
"""
import logging
import secrets
import httpx
from typing import Dict, Optional
from datetime import datetime, timedelta
from uuid import uuid4
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


class OTPService:
    """Service for handling OTP operations via MessageCentral API"""

    # Auth token cache (MessageCentral tokens are valid for ~5 years)
    _auth_token: Optional[str] = None
    _token_expires_at: Optional[datetime] = None

    # Dev-mode OTP store: verification_id -> {"code": str, "expires_at": datetime}.
    # In-memory only; used when settings.otp_dev_enabled is true.
    _dev_otps: Dict[str, Dict[str, object]] = {}

    BASE_URL = "https://cpaas.messagecentral.com"

    # Keep total request time well under typical platform gateway timeouts (~30s)
    # so a slow/unreachable provider yields a clean JSON error the frontend can
    # render, instead of the edge returning a raw 503 HTML page.
    HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

    # =====================================================
    # DEV MODE (no SMS — OTP is generated + logged locally)
    # =====================================================
    @classmethod
    def _dev_send_otp(cls, clean_phone: str, country_code: str) -> Dict[str, object]:
        """Generate an OTP locally, log it, and return a fake verification payload."""
        code = "".join(secrets.choice("0123456789") for _ in range(settings.MESSAGECENTRAL_OTP_LENGTH))
        verification_id = f"dev-{uuid4().hex[:16]}"
        expires_in = settings.MESSAGECENTRAL_OTP_EXPIRY_SECONDS
        cls._dev_otps[verification_id] = {
            "code": code,
            "expires_at": datetime.utcnow() + timedelta(seconds=expires_in),
        }
        logger.warning(
            "\n"
            "============================================================\n"
            "  [OTP DEV MODE] No SMS sent. Use this code to verify:\n"
            "    phone:          +%s%s\n"
            "    otp:            %s\n"
            "    verificationId: %s\n"
            "============================================================",
            country_code, clean_phone, code, verification_id,
        )
        masked = f"+{country_code}{'*' * max(len(clean_phone) - 4, 0)}{clean_phone[-4:]}"
        return {
            "verification_id": verification_id,
            "expires_in": expires_in,
            "phone": masked,
        }

    @classmethod
    def _dev_verify_otp(cls, verification_id: str, otp_code: str) -> bool:
        """Verify an OTP against the locally stored dev code."""
        entry = cls._dev_otps.get(verification_id)
        if not entry:
            logger.warning("[OTP DEV MODE] Unknown verificationId: %s", verification_id)
            return False
        if datetime.utcnow() > entry["expires_at"]:
            logger.warning("[OTP DEV MODE] OTP expired for verificationId: %s", verification_id)
            cls._dev_otps.pop(verification_id, None)
            return False
        if otp_code == entry["code"]:
            cls._dev_otps.pop(verification_id, None)  # single-use
            logger.info("[OTP DEV MODE] OTP verified for verificationId: %s", verification_id)
            return True
        logger.warning("[OTP DEV MODE] Incorrect OTP for verificationId: %s", verification_id)
        return False

    @classmethod
    async def _get_auth_token(cls) -> str:
        """
        Get MessageCentral auth token (cached for reuse)
        Token is valid for ~5 years, so we cache it

        Returns:
            str: Authentication token

        Raises:
            HTTPException: If token generation fails
        """
        # Preferred path: use the long-lived Auth Token from the MessageCentral
        # dashboard directly. Newer accounts issue this token outright (no
        # password/key generation step), so there is nothing to fetch or cache.
        if settings.MESSAGECENTRAL_AUTH_TOKEN:
            return settings.MESSAGECENTRAL_AUTH_TOKEN

        # Check if cached token is still valid (with 1 day buffer)
        if cls._auth_token and cls._token_expires_at:
            if datetime.utcnow() < (cls._token_expires_at - timedelta(days=1)):
                logger.debug("Using cached MessageCentral auth token")
                return cls._auth_token

        # Legacy fallback: generate a token from the Base64 password (KEY) + email.
        if not settings.MESSAGECENTRAL_KEY:
            logger.error(
                "MessageCentral is not configured: set MESSAGECENTRAL_AUTH_TOKEN "
                "(preferred) or the legacy MESSAGECENTRAL_KEY + MESSAGECENTRAL_EMAIL."
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OTP service is not configured. Please contact support."
            )

        try:
            logger.info("Fetching new MessageCentral auth token")

            url = f"{cls.BASE_URL}/auth/v1/authentication/token"
            params = {
                "customerId": settings.MESSAGECENTRAL_CUSTOMER_ID,
                "key": settings.MESSAGECENTRAL_KEY,
                "scope": "NEW",
                "country": settings.MESSAGECENTRAL_DEFAULT_COUNTRY_CODE,
                "email": settings.MESSAGECENTRAL_EMAIL
            }

            async with httpx.AsyncClient(timeout=cls.HTTP_TIMEOUT) as client:
                response = await client.get(url, params=params)

                if response.status_code != 200:
                    logger.error(f"MessageCentral auth failed: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="OTP service unavailable. Please try again later."
                    )

                data = response.json()
                token = data.get("token")

                if not token:
                    # MessageCentral returns HTTP 200 with an in-body error for bad
                    # credentials (e.g. {"status":400,"error":"password is wrong"}),
                    # which means MESSAGECENTRAL_KEY (the Base64-encoded account
                    # password) or another credential is wrong/stale — not a transient
                    # outage. Surface the provider's own message so it's obvious in logs.
                    provider_error = data.get("error") or data.get("message")
                    provider_status = data.get("status")
                    logger.error(
                        "MessageCentral did not return a token "
                        "(status=%s, error=%r). Check MESSAGECENTRAL_KEY/CUSTOMER_ID/EMAIL. "
                        "Full body: %s",
                        provider_status, provider_error, data,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="OTP service is misconfigured. Please contact support."
                    )

                # Cache the token (assume 5 year validity as per collection)
                cls._auth_token = token
                cls._token_expires_at = datetime.utcnow() + timedelta(days=365 * 5)  # 5 years

                logger.info("MessageCentral auth token cached successfully")
                return token

        except httpx.RequestError as e:
            logger.error(f"Network error while fetching auth token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to connect to OTP service. Please try again later."
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching auth token: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OTP service error. Please contact support."
            )

    @classmethod
    async def _call_with_token_refresh(cls, make_request, action: str) -> httpx.Response:
        """
        Call MessageCentral via `make_request(auth_token)`, refreshing the cached
        auth token and retrying once if it's rejected (401/403). Self-heals a
        stale cached token without a process restart.
        """
        response = None
        for attempt in range(2):
            auth_token = await cls._get_auth_token()
            response = await make_request(auth_token)

            if response.status_code in (401, 403) and attempt == 0:
                logger.warning(
                    "MessageCentral rejected auth token on %s (status %s); "
                    "refreshing token and retrying once.", action, response.status_code
                )
                cls.clear_token_cache()
                continue
            break
        return response

    @classmethod
    async def send_otp(
        cls,
        phone: str,
        country_code: str = None
    ) -> Dict[str, any]:
        """
        Send OTP to phone number via MessageCentral

        Args:
            phone: Phone number (10 digits without country code)
            country_code: Country code (default: 91 for India)

        Returns:
            Dict containing:
                - verification_id: ID to use for verification
                - expires_in: Seconds until OTP expires

        Raises:
            HTTPException: If OTP sending fails
        """
        if country_code is None:
            country_code = settings.MESSAGECENTRAL_DEFAULT_COUNTRY_CODE

        # Clean phone number (remove +, spaces, dashes)
        clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")

        # Remove country code only when present as a prefix on a longer number.
        # A bare 10-digit number that itself begins with the country code
        # (e.g. "9123456789" starts with "91") must not be stripped, otherwise
        # MessageCentral receives an 8-digit number and rejects it with a 400.
        if clean_phone.startswith(country_code) and len(clean_phone) > 10:
            clean_phone = clean_phone[len(country_code):]

        # Dev mode: generate + log the OTP locally instead of calling MessageCentral.
        if settings.otp_dev_enabled:
            return cls._dev_send_otp(clean_phone, country_code)

        try:
            logger.info(f"Sending OTP to phone: +{country_code}{clean_phone[-4:]}")  # Log last 4 digits only

            url = f"{cls.BASE_URL}/verification/v3/send"
            params = {
                "countryCode": country_code,
                "customerId": settings.MESSAGECENTRAL_CUSTOMER_ID,
                "flowType": "SMS",
                "mobileNumber": clean_phone,
                "otpLength": settings.MESSAGECENTRAL_OTP_LENGTH
            }

            async def _make_request(auth_token: str) -> httpx.Response:
                headers = {"authToken": auth_token}
                async with httpx.AsyncClient(timeout=cls.HTTP_TIMEOUT) as client:
                    return await client.post(url, params=params, headers=headers)

            response = await cls._call_with_token_refresh(_make_request, "send")

            if response.status_code != 200:
                logger.error(f"MessageCentral send OTP failed: {response.status_code} - {response.text}")

                # Check for specific errors
                if response.status_code == 429:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many OTP requests. Please try again after some time."
                    )

                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Failed to send OTP. Please try again."
                )

            data = response.json()
            provider_response_code = str(data.get("responseCode", ""))
            verification_payload = data.get("data", {}) or {}
            verification_id = verification_payload.get("verificationId")
            provider_timeout = verification_payload.get("timeout")
            transaction_id = verification_payload.get("transactionId")
            reference_id = verification_payload.get("referenceId")

            # MessageCentral may still return HTTP 200 for logical failures.
            # Validate both HTTP and provider-level response codes.
            if provider_response_code and provider_response_code != "200":
                logger.error(
                    f"MessageCentral provider error while sending OTP. "
                    f"responseCode={provider_response_code}, body={data}"
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="OTP provider rejected the request. Please try again."
                )

            if not verification_id:
                logger.error(f"No verificationId in MessageCentral response: {data}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="OTP service error. Please try again."
                )

            try:
                expires_in = int(float(provider_timeout)) if provider_timeout is not None else settings.MESSAGECENTRAL_OTP_EXPIRY_SECONDS
            except (ValueError, TypeError):
                expires_in = settings.MESSAGECENTRAL_OTP_EXPIRY_SECONDS

            logger.info(
                f"OTP accepted by provider. "
                f"verificationId={verification_id}, transactionId={transaction_id}, "
                f"referenceId={reference_id}, timeout={expires_in}s"
            )

            return {
                "verification_id": str(verification_id),
                "expires_in": expires_in,
                "phone": f"+{country_code}{'*' * (len(clean_phone) - 4)}{clean_phone[-4:]}"  # Masked phone
            }

        except httpx.RequestError as e:
            logger.error(f"Network error while sending OTP: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to send OTP. Please check your connection."
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error sending OTP: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send OTP. Please contact support."
            )

    @classmethod
    async def verify_otp(
        cls,
        verification_id: str,
        otp_code: str
    ) -> bool:
        """
        Verify OTP code via MessageCentral

        Args:
            verification_id: Verification ID from send_otp
            otp_code: 6-digit OTP code entered by user

        Returns:
            bool: True if OTP is valid, False otherwise

        Raises:
            HTTPException: If verification service fails
        """
        # Dev mode: verify against the locally stored OTP.
        if settings.otp_dev_enabled:
            return cls._dev_verify_otp(verification_id, otp_code)

        try:
            logger.info(f"Verifying OTP for verificationId: {verification_id}")

            url = f"{cls.BASE_URL}/verification/v3/validateOtp"
            params = {
                "verificationId": verification_id,
                "code": otp_code,
                "flowType": "SMS"
            }

            async def _make_request(auth_token: str) -> httpx.Response:
                headers = {"authToken": auth_token, "accept": "*/*"}
                async with httpx.AsyncClient(timeout=cls.HTTP_TIMEOUT) as client:
                    return await client.get(url, params=params, headers=headers)

            response = await cls._call_with_token_refresh(_make_request, "verify")

            if response.status_code != 200:
                logger.warning(f"MessageCentral verify OTP failed: {response.status_code} - {response.text}")

                # Don't reveal specific errors to prevent enumeration
                if response.status_code == 429:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many verification attempts. Please try again later."
                    )

                # Return False for invalid OTP (don't raise exception)
                return False

            data = response.json()

            # Check if verification was successful
            # MessageCentral returns different response formats
            # Check both 'status' and 'responseCode'
            # Note: MessageCentral may return `"data": null` (key present, value
            # null) on a wrong/expired OTP, so `.get("data", {})` is not safe —
            # the default only applies when the key is absent. Coerce explicitly.
            inner = data.get("data") or {}
            verified = (
                inner.get("verificationStatus") == "VERIFICATION_COMPLETED" or
                data.get("responseCode") == 200 or
                data.get("status") == "success"
            )

            if verified:
                logger.info(f"OTP verified successfully for verificationId: {verification_id}")
            else:
                logger.warning(f"OTP verification failed for verificationId: {verification_id}")

            return verified

        except httpx.RequestError as e:
            logger.error(f"Network error while verifying OTP: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to verify OTP. Please check your connection."
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error verifying OTP: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OTP verification failed. Please try again."
            )

    @classmethod
    def clear_token_cache(cls):
        """Clear cached auth token (useful for testing or token refresh)"""
        cls._auth_token = None
        cls._token_expires_at = None
        logger.info("MessageCentral auth token cache cleared")
