"""
Access vs refresh token separation (e2e finding: the two were interchangeable).

Access and refresh tokens used to carry identical claims, so `verify_token`
accepted a refresh token as a Bearer token and `verify_refresh_token` accepted
an access token at /auth/refresh. Both now carry a `type` claim and each
verifier rejects the other kind. Untyped (pre-change) tokens are still accepted
by both — the legacy allowance documented in app/core/auth.py.

No marker -> runs in the fast (no-stack) job.
"""
import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

from app.core.auth import (
    create_access_token,
    create_refresh_token,
    create_registration_token,
    verify_refresh_token,
    verify_token,
)
from app.core.config import settings

# Reuse the counting fake + seeded-user fixture from the profile-read tests.
from tests.test_auth_profile_reads import auth_db  # noqa: F401  (pytest fixture)


def _claims(user):
    return {"sub": user["id"], "email": user["email"], "user_role": user["user_role"]}


def _decode(token):
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def _legacy_token(user, *, with_iat=True):
    """A token as minted before the `type` claim existed."""
    now = datetime.utcnow()
    payload = {**_claims(user), "jti": "legacy-jti", "exp": now + timedelta(minutes=30)}
    if with_iat:
        payload["iat"] = now
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def test_new_tokens_carry_their_type():
    user = {"id": "u1", "email": "u@example.com", "user_role": "customer"}
    assert _decode(create_access_token(_claims(user)))["type"] == "access"
    assert _decode(create_refresh_token(_claims(user)))["type"] == "refresh"


def test_caller_data_cannot_override_the_type():
    user = {"id": "u1", "email": "u@example.com", "user_role": "customer"}
    assert _decode(create_access_token({**_claims(user), "type": "refresh"}))["type"] == "access"
    assert _decode(create_refresh_token({**_claims(user), "type": "access"}))["type"] == "refresh"


def test_access_token_verifies_as_access(auth_db):
    user = auth_db.seed_user()
    payload = asyncio.run(verify_token(create_access_token(_claims(user)), auth_db.db))
    assert payload.sub == user["id"]


def test_refresh_token_rejected_as_bearer(auth_db):
    user = auth_db.seed_user()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(verify_token(create_refresh_token(_claims(user)), auth_db.db))
    assert exc.value.status_code == 401


def test_refresh_token_verifies_at_refresh(auth_db):
    user = auth_db.seed_user()
    data = asyncio.run(verify_refresh_token(create_refresh_token(_claims(user)), auth_db.db))
    assert data


def test_access_token_rejected_at_refresh(auth_db):
    user = auth_db.seed_user()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(verify_refresh_token(create_access_token(_claims(user)), auth_db.db))
    assert exc.value.status_code == 401


def test_legacy_untyped_token_still_accepted_by_both(auth_db):
    # Live sessions minted before the deploy have no `type`; they must keep
    # working until they expire (see _reject_wrong_token_type).
    user = auth_db.seed_user()
    token = _legacy_token(user)
    assert asyncio.run(verify_token(token, auth_db.db)).sub == user["id"]
    assert asyncio.run(verify_refresh_token(_legacy_token(user, with_iat=False), auth_db.db))


def test_other_token_kinds_rejected_by_both_verifiers(auth_db):
    token = create_registration_token("req-1", "salon-1", "owner@example.com")
    for verifier in (verify_token, verify_refresh_token):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(verifier(token, auth_db.db))
        assert exc.value.status_code == 401
