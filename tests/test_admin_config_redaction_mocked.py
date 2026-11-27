"""
PUT /admin/config/{key} must never write a secret's value to the app log or the
activity log. ConfigService hands back sensitive values decrypted, so the route
redacts them before logging. Plain settings keep their values in the log.

No marker -> runs in the fast (no-stack) job.
"""
import logging
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.admin import config as config_api
from app.core.auth import require_admin, TokenData
from app.core.config import settings
from app.services.config_service import SENSITIVE_CONFIG_KEYS, AVAILABLE_SYSTEM_CONFIGS

API = settings.API_PREFIX


class _FakeConfigService:
    def __init__(self):
        self.values = {}

    async def get_config(self, key):
        return {"config_key": key, "config_value": self.values.get(key, "old-plain-secret")}

    async def update_config(self, key, update):
        self.values[key] = update.config_value
        return {"id": "1", "config_key": key, "config_value": update.config_value,
                "config_type": "string", "description": None, "is_active": True,
                "created_at": None, "updated_at": None}


@pytest.fixture()
def client(app, monkeypatch):
    calls = []

    async def capture(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(config_api.ActivityLogger, "config_updated", staticmethod(capture))
    svc = _FakeConfigService()
    td = TokenData(user_id="admin-1", email="a@example.com", user_role="admin",
                   jti="jti", exp=datetime.utcnow() + timedelta(hours=1))
    app.dependency_overrides[require_admin] = lambda: td
    app.dependency_overrides[config_api.get_config_service] = lambda: svc
    yield TestClient(app), calls
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(config_api.get_config_service, None)


def test_delivery_webhook_secret_is_sensitive_and_offered():
    assert "delivery_webhook_secret" in SENSITIVE_CONFIG_KEYS
    assert any(c["config_key"] == "delivery_webhook_secret" for c in AVAILABLE_SYSTEM_CONFIGS)


@pytest.mark.parametrize("key", sorted(SENSITIVE_CONFIG_KEYS))
def test_secret_values_are_redacted(client, caplog, key):
    http, calls = client
    with caplog.at_level(logging.INFO):
        r = http.put(f"{API}/admin/config/{key}", json={"config_value": "new-plain-secret"})
    assert r.status_code == 200, r.text
    assert calls == [{"user_id": "admin-1", "config_key": key,
                      "old_value": "[redacted]", "new_value": "[redacted]"}]
    assert "new-plain-secret" not in caplog.text
    assert "old-plain-secret" not in caplog.text


def test_plain_values_are_still_logged(client):
    http, calls = client
    r = http.put(f"{API}/admin/config/convenience_fee_percentage", json={"config_value": "2.5"})
    assert r.status_code == 200, r.text
    assert calls[0]["new_value"] == "2.5"
