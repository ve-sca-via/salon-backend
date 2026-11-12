"""
Mint the two stateless "proof" JWTs the real flows get from places a test
cannot reach:

* phone-verification token - normally returned by the MessageCentral OTP flow
  (POST /auth/signup/phone/verify-otp). Sending a real OTP from a test is off
  limits (real SMS), so we sign the same claims with the server's JWT secret.
  Mirrors app/core/auth.py:create_phone_verification_token.
* registration token - normally only delivered inside the approval email
  (never persisted anywhere). Mirrors app/core/auth.py:create_registration_token.

Both are plain HS256 JWTs; nothing about them is stored server-side, so a
token minted here is indistinguishable from one the server issued.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from jose import jwt


def phone_verification_token(secret: str, phone_e164: str, algorithm: str = "HS256") -> str:
    return jwt.encode(
        {"sub": phone_e164, "type": "phone_verification",
         "exp": datetime.utcnow() + timedelta(minutes=15)},
        secret, algorithm=algorithm,
    )


def registration_token(secret: str, *, request_id: str, salon_id: str, email: str,
                       request_type: str = "salon", algorithm: str = "HS256") -> str:
    return jwt.encode(
        {"sub": "registration", "request_id": request_id, "salon_id": salon_id,
         "email": email, "request_type": request_type, "type": "registration",
         "exp": datetime.utcnow() + timedelta(days=7)},
        secret, algorithm=algorithm,
    )


def razorpay_signature(key_secret: str, order_id: str, payment_id: str) -> str:
    """Signature Razorpay's checkout returns: HMAC_SHA256(order_id|payment_id)."""
    import hashlib
    import hmac
    return hmac.new(key_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
