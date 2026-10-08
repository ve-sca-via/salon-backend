"""
Tests for how many times authentication reads the profiles row (payment audit M-1).

verify_token has to load the profile anyway — to reject a deleted account, an
inactive one, and a token issued before logout_all — and get_current_user then
read the very same row again, on *every* authenticated request in the app.
verify_token now selects the union of both column sets and passes the row on.

These tests drive the real dependency chain (no overridden get_current_user)
against a counting fake, because the thing being asserted is a round-trip count
that no behavioural test would notice losing.

No marker -> runs in the fast (no-stack) job.
"""
import asyncio
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.core.auth import (
    TokenPayload,
    create_access_token,
    get_current_user,
    get_optional_user,
    verify_token,
)


# =====================================================================
# Counting fake (only what the auth dependencies touch)
# =====================================================================
class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table):
        self._table = table
        self._filters = []
        self._maybe = False

    def select(self, cols="*", count=None):
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def maybe_single(self):
        self._maybe = True
        return self

    def execute(self):
        self._table.reads += 1
        matched = [
            dict(r) for r in self._table.rows
            if all(r.get(c) == v for c, v in self._filters)
        ]
        if self._maybe:
            return _Resp(matched[0] if matched else None)
        return _Resp(matched)


class _Table:
    def __init__(self):
        self.rows = []
        self.reads = 0

    def select(self, cols="*", count=None):
        return _Query(self).select(cols)


class FakeSupabase:
    def __init__(self):
        self._tables = {}

    def table(self, name):
        return self._tables.setdefault(name, _Table())


@pytest.fixture()
def auth_db():
    db = FakeSupabase()

    class Handle:
        def __init__(self):
            self.db = db
            self.profiles = db.table("profiles")
            self.blacklist = db.table("token_blacklist")

        def seed_user(self, role="customer", is_active=True, is_internal=False):
            user_id = str(uuid.uuid4())
            self.profiles.rows.append({
                "id": user_id,
                "email": f"user+{user_id[:8]}@example.com",
                "user_role": role,
                "is_active": is_active,
                "is_internal": is_internal,
                "token_valid_after": None,
            })
            return self.profiles.rows[-1]

        def token_for(self, user):
            return create_access_token({
                "sub": user["id"],
                "email": user["email"],
                "user_role": user["user_role"],
            })

        def creds(self, token):
            return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    return Handle()


# =====================================================================
# get_current_user
# =====================================================================
def test_authenticating_reads_the_profile_once(auth_db):
    user = auth_db.seed_user()
    token = auth_db.token_for(user)

    current = asyncio.run(get_current_user(auth_db.creds(token), auth_db.db))

    assert current.user_id == user["id"]
    assert current.email == user["email"]
    assert current.user_role == "customer"
    assert auth_db.profiles.reads == 1, "the profiles row should be read once per request"


def test_is_internal_still_comes_from_the_row_not_the_token(auth_db):
    """
    is_internal is deliberately read per request so flipping it takes effect at
    once; serving it from verify_token's row must not change that.
    """
    user = auth_db.seed_user(is_internal=True)

    current = asyncio.run(get_current_user(auth_db.creds(auth_db.token_for(user)), auth_db.db))
    assert current.is_internal is True

    user["is_internal"] = False
    current = asyncio.run(get_current_user(auth_db.creds(auth_db.token_for(user)), auth_db.db))
    assert current.is_internal is False


def test_deleted_account_is_rejected(auth_db):
    user = auth_db.seed_user()
    token = auth_db.token_for(user)
    auth_db.profiles.rows.clear()

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_user(auth_db.creds(token), auth_db.db))
    assert exc.value.status_code == 401


def test_inactive_account_is_rejected(auth_db):
    user = auth_db.seed_user(is_active=False)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_user(auth_db.creds(auth_db.token_for(user)), auth_db.db))
    assert exc.value.status_code == 401


def test_blacklisted_token_is_rejected(auth_db):
    user = auth_db.seed_user()
    token = auth_db.token_for(user)
    payload = verify_token(token, auth_db.db)
    auth_db.blacklist.rows.append({"id": 1, "token_jti": payload.jti})

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_user(auth_db.creds(token), auth_db.db))
    assert exc.value.status_code == 401


def test_token_issued_before_logout_all_is_rejected(auth_db):
    user = auth_db.seed_user()
    token = auth_db.token_for(user)
    user["token_valid_after"] = (datetime.utcnow() + timedelta(minutes=5)).isoformat()

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_user(auth_db.creds(token), auth_db.db))
    assert exc.value.status_code == 401


def test_falls_back_to_its_own_read_without_a_carried_profile(auth_db, monkeypatch):
    """
    The carried profile is an optimisation, not a requirement: a TokenPayload
    built anywhere else must still authenticate.
    """
    user = auth_db.seed_user()
    token = auth_db.token_for(user)
    payload = verify_token(token, auth_db.db)
    auth_db.profiles.reads = 0

    stripped = TokenPayload(
        sub=payload.sub, email=payload.email, user_role=payload.user_role,
        jti=payload.jti, exp=payload.exp, profile=None,
    )
    monkeypatch.setattr("app.core.auth.verify_token", lambda token, db: stripped)

    current = asyncio.run(get_current_user(auth_db.creds(token), auth_db.db))

    assert current.user_id == user["id"]
    assert auth_db.profiles.reads == 1


# =====================================================================
# get_optional_user
# =====================================================================
def test_optional_user_reads_the_profile_once(auth_db):
    user = auth_db.seed_user()

    current = asyncio.run(get_optional_user(auth_db.creds(auth_db.token_for(user)), auth_db.db))

    assert current is not None
    assert current.user_id == user["id"]
    assert auth_db.profiles.reads == 1


def test_optional_user_is_none_without_credentials(auth_db):
    assert asyncio.run(get_optional_user(None, auth_db.db)) is None


def test_optional_user_is_none_for_an_inactive_account(auth_db):
    user = auth_db.seed_user(is_active=False)

    assert asyncio.run(
        get_optional_user(auth_db.creds(auth_db.token_for(user)), auth_db.db)
    ) is None
