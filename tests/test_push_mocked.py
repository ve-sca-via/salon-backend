"""
Mocked tests for push notifications (app/api/notifications.py +
app/services/push_service.py).

The Supabase client is an in-memory fake and the Expo HTTP call is replaced, so
nothing leaves the process. No marker -> runs in the fast job.
"""
import asyncio
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.auth import TokenData, get_current_user
from app.core.config import settings
from app.core.database import get_db_client
from app.services import push_service as push_module
from app.services.push_service import PushService, is_valid_expo_token

DEVICES = f"{settings.API_PREFIX}/notifications/devices"
TOKEN_A = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]"
TOKEN_B = "ExponentPushToken[bbbbbbbbbbbbbbbbbbbbbb]"


class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self._op = ("select", None)
        self._eq = []
        self._in = []

    def select(self, *_a, **_k):
        return self

    def upsert(self, payload, on_conflict=None):
        self._op = ("upsert", (payload, on_conflict))
        return self

    def update(self, payload):
        self._op = ("update", payload)
        return self

    def delete(self):
        self._op = ("delete", None)
        return self

    def eq(self, col, val):
        self._eq.append((col, val))
        return self

    def in_(self, col, vals):
        self._in.append((col, vals))
        return self

    def _match(self, r):
        return all(r.get(c) == v for c, v in self._eq) and all(r.get(c) in vs for c, vs in self._in)

    def execute(self):
        op, payload = self._op
        if op == "upsert":
            row, key = payload
            existing = next((r for r in self.rows if r[key] == row[key]), None)
            if existing:
                existing.update(row)
            else:
                self.rows.append({"id": str(uuid.uuid4()), **row})
            return _Resp([row])
        if op == "update":
            hit = [r for r in self.rows if self._match(r)]
            for r in hit:
                r.update(payload)
            return _Resp(hit)
        if op == "delete":
            hit = [r for r in self.rows if self._match(r)]
            self.rows[:] = [r for r in self.rows if not self._match(r)]
            return _Resp(hit)
        return _Resp([dict(r) for r in self.rows if self._match(r)])


class FakeDB:
    def __init__(self):
        self.rows = []

    def table(self, name):
        assert name == "device_tokens"
        return _Query(self.rows)


class FakeExpo:
    """Stands in for httpx.AsyncClient; records calls and replies per token."""

    calls = []
    replies = {}  # token -> ticket dict (default: ok)
    status = 200

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        FakeExpo.calls.append({"url": url, "messages": json, "headers": headers})
        tickets = [FakeExpo.replies.get(m["to"], {"status": "ok", "id": "x"}) for m in json]

        class R:
            status_code = FakeExpo.status
            text = "err"

            def json(self_inner):
                return {"data": tickets}

        return R()


@pytest.fixture()
def fake_expo(monkeypatch):
    FakeExpo.calls, FakeExpo.replies, FakeExpo.status = [], {}, 200
    monkeypatch.setattr(push_module.httpx, "AsyncClient", FakeExpo)
    return FakeExpo


@pytest.fixture()
def api(app):
    db = FakeDB()
    td = TokenData(user_id="vendor-1", email="v@example.com", user_role="vendor",
                   jti="j", exp=datetime.utcnow() + timedelta(hours=1))
    app.dependency_overrides[get_db_client] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: td
    yield TestClient(app), db
    app.dependency_overrides.pop(get_db_client, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_token_format():
    assert is_valid_expo_token(TOKEN_A)
    assert is_valid_expo_token("ExpoPushToken[abc]")
    assert not is_valid_expo_token("garbage")
    assert not is_valid_expo_token("")


def test_register_stores_token_and_is_idempotent(api):
    client, db = api
    body = {"expo_push_token": TOKEN_A, "platform": "android", "app": "partner-app"}
    assert client.post(DEVICES, json=body).status_code == 200
    assert client.post(DEVICES, json=body).status_code == 200
    assert len(db.rows) == 1
    assert db.rows[0]["user_id"] == "vendor-1" and db.rows[0]["is_active"] is True


def test_register_rejects_bad_token(api):
    client, _ = api
    r = client.post(DEVICES, json={"expo_push_token": "nope", "platform": "android", "app": "partner-app"})
    assert r.status_code == 422


def test_register_moves_token_to_new_user(api):
    client, db = api
    db.rows.append({"id": "1", "user_id": "someone-else", "expo_push_token": TOKEN_A, "is_active": False})
    client.post(DEVICES, json={"expo_push_token": TOKEN_A, "platform": "android", "app": "partner-app"})
    assert len(db.rows) == 1
    assert db.rows[0]["user_id"] == "vendor-1" and db.rows[0]["is_active"] is True


def test_unregister_only_removes_own_token(api):
    client, db = api
    db.rows.append({"id": "1", "user_id": "vendor-1", "expo_push_token": TOKEN_A})
    db.rows.append({"id": "2", "user_id": "other", "expo_push_token": TOKEN_B})
    assert client.request("DELETE", DEVICES, json={"expo_push_token": TOKEN_B}).status_code == 200
    assert len(db.rows) == 2  # not vendor-1's, untouched
    client.request("DELETE", DEVICES, json={"expo_push_token": TOKEN_A})
    assert [r["expo_push_token"] for r in db.rows] == [TOKEN_B]


def test_send_pushes_to_every_active_device(fake_expo):
    db = FakeDB()
    db.rows += [
        {"user_id": "v", "expo_push_token": TOKEN_A, "is_active": True},
        {"user_id": "v", "expo_push_token": TOKEN_B, "is_active": False},
        {"user_id": "x", "expo_push_token": "ExponentPushToken[cc]", "is_active": True},
    ]
    n = asyncio.run(PushService(db).send_to_user("v", "New booking", "hi", {"type": "booking"}))
    assert n == 1
    msg = fake_expo.calls[0]["messages"][0]
    assert msg["to"] == TOKEN_A and msg["title"] == "New booking"
    assert msg["data"] == {"type": "booking"} and msg["channelId"] == "bookings"


def test_dead_token_is_deactivated(fake_expo):
    db = FakeDB()
    db.rows.append({"user_id": "v", "expo_push_token": TOKEN_A, "is_active": True})
    fake_expo.replies[TOKEN_A] = {"status": "error", "message": "gone", "details": {"error": "DeviceNotRegistered"}}
    assert asyncio.run(PushService(db).send_to_user("v", "t", "b")) == 0
    assert db.rows[0]["is_active"] is False


def test_send_never_raises(monkeypatch):
    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr(push_module.httpx, "AsyncClient", Boom)
    db = FakeDB()
    db.rows.append({"user_id": "v", "expo_push_token": TOKEN_A, "is_active": True})
    assert asyncio.run(PushService(db).send_to_user("v", "t", "b")) == 0
    assert asyncio.run(PushService(db).send_to_user(None, "t", "b")) == 0


def test_expo_http_error_is_swallowed(fake_expo):
    fake_expo.status = 500
    db = FakeDB()
    db.rows.append({"user_id": "v", "expo_push_token": TOKEN_A, "is_active": True})
    assert asyncio.run(PushService(db).send_to_user("v", "t", "b")) == 0
