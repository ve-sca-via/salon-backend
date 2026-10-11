"""
Tests for ConfigService's short-lived config cache (payment audit 10.3).

The cache sits in front of three hot keys — the two Razorpay credentials and
convenience_fee_percentage — which a single cart checkout read six times
between them, four of those Fernet-decrypted. These tests pin the two
properties that make the cache safe to have at all:

  * an admin edit is visible on the very next read, not after the TTL;
  * a failed read is never cached, so one transient DB blip cannot turn into a
    full minute of "payment service is not configured".

No marker -> runs in the fast (no-stack) job. The autouse _clear_config_cache
fixture in conftest.py keeps these from leaking into each other.
"""
import asyncio
import uuid

import pytest

from app.schemas.request.admin import SystemConfigUpdate
from app.services import config_service as config_service_module
from app.services.config_service import (
    CONVENIENCE_FEE_CONFIG_KEY,
    ConfigService,
    clear_config_cache,
)


# =====================================================================
# Counting fake (only the ops ConfigService uses)
# =====================================================================
class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table):
        self._table = table
        self._filters = []
        self._op = ("select", "*")
        self._single = False
        self._maybe = False

    def select(self, cols="*", count=None):
        self._op = ("select", cols)
        return self

    def update(self, payload):
        self._op = ("update", payload)
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def order(self, col, desc=False):
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._maybe = True
        return self

    def _match(self, row):
        return all(row.get(c) == v for c, v in self._filters)

    def execute(self):
        op, payload = self._op
        self._table.reads.append(op)

        if self._table.fail_next:
            self._table.fail_next = False
            raise Exception("transient database error")

        matched = [dict(r) for r in self._table.rows if self._match(r)]

        if op == "update":
            for r in self._table.rows:
                if self._match(r):
                    r.update(payload)
            return _Resp([dict(r) for r in self._table.rows if self._match(r)])

        if self._single:
            if len(matched) != 1:
                raise Exception("PGRST116: results contain 0 or multiple rows")
            return _Resp(matched[0])
        if self._maybe:
            return _Resp(matched[0] if matched else None)
        return _Resp(matched)


class _Table:
    def __init__(self):
        self.rows = []
        self.reads = []
        self.fail_next = False

    def select(self, cols="*", count=None):
        return _Query(self).select(cols)

    def update(self, payload):
        return _Query(self).update(payload)


class FakeSupabase:
    def __init__(self):
        self._tables = {}

    def table(self, name):
        return self._tables.setdefault(name, _Table())


@pytest.fixture()
def cfg():
    db = FakeSupabase()

    class Handle:
        def __init__(self):
            self.db = db
            self.table = db.table("system_config")

        def seed(self, key, value, is_active=True, config_type="number"):
            self.table.rows.append({
                "id": str(uuid.uuid4()),
                "config_key": key,
                "config_value": value,
                "config_type": config_type,
                "is_active": is_active,
            })

        def service(self):
            return ConfigService(db_client=db)

        @property
        def reads(self):
            return len(self.table.reads)

    return Handle()


# =====================================================================
# convenience_fee_percentage
# =====================================================================
def test_fee_is_read_once_then_served_from_cache(cfg):
    cfg.seed(CONVENIENCE_FEE_CONFIG_KEY, "6")
    svc = cfg.service()

    first = asyncio.run(svc.get_convenience_fee_percentage())
    reads_after_first = cfg.reads
    second = asyncio.run(svc.get_convenience_fee_percentage())

    assert first == second == 6.0
    assert reads_after_first == 1
    assert cfg.reads == 1, "second call should not have touched the database"


def test_fee_cache_is_shared_across_service_instances(cfg):
    """
    The cache has to be process-level, not per-instance: the duplicate reads it
    exists to remove came from *different* service objects in one request.
    """
    cfg.seed(CONVENIENCE_FEE_CONFIG_KEY, "6")

    asyncio.run(cfg.service().get_convenience_fee_percentage())
    asyncio.run(cfg.service().get_convenience_fee_percentage())

    assert cfg.reads == 1


def test_fee_missing_raises_value_error(cfg):
    with pytest.raises(ValueError):
        asyncio.run(cfg.service().get_convenience_fee_percentage())


def test_fee_inactive_row_is_treated_as_missing(cfg):
    """An admin switching the config off must stop it being used."""
    cfg.seed(CONVENIENCE_FEE_CONFIG_KEY, "6", is_active=False)

    with pytest.raises(ValueError):
        asyncio.run(cfg.service().get_convenience_fee_percentage())


def test_fee_non_numeric_raises_value_error(cfg):
    cfg.seed(CONVENIENCE_FEE_CONFIG_KEY, "six percent")

    with pytest.raises(ValueError):
        asyncio.run(cfg.service().get_convenience_fee_percentage())


def test_fee_failure_is_not_cached(cfg):
    """
    One failed read must not stick. Otherwise a transient blip would 500 every
    checkout for the whole TTL.
    """
    cfg.seed(CONVENIENCE_FEE_CONFIG_KEY, "6")
    cfg.table.fail_next = True

    with pytest.raises(Exception):
        asyncio.run(cfg.service().get_convenience_fee_percentage())

    assert asyncio.run(cfg.service().get_convenience_fee_percentage()) == 6.0


def test_admin_update_is_visible_immediately(cfg):
    """A write through ConfigService drops the key, so the TTL never hides it."""
    cfg.seed(CONVENIENCE_FEE_CONFIG_KEY, "6")
    svc = cfg.service()

    assert asyncio.run(svc.get_convenience_fee_percentage()) == 6.0

    asyncio.run(svc.update_config(
        CONVENIENCE_FEE_CONFIG_KEY,
        SystemConfigUpdate(config_value="9"),
    ))

    assert asyncio.run(svc.get_convenience_fee_percentage()) == 9.0


def test_fee_is_reread_after_the_ttl_expires(cfg, monkeypatch):
    cfg.seed(CONVENIENCE_FEE_CONFIG_KEY, "6")
    svc = cfg.service()

    assert asyncio.run(svc.get_convenience_fee_percentage()) == 6.0
    assert cfg.reads == 1

    # Jump past the TTL instead of sleeping through it.
    now = config_service_module.monotonic()
    monkeypatch.setattr(
        config_service_module, "monotonic",
        lambda: now + config_service_module.CONFIG_CACHE_TTL_SECONDS + 1,
    )

    assert asyncio.run(svc.get_convenience_fee_percentage()) == 6.0
    assert cfg.reads == 2


# =====================================================================
# get_cached_config_value (the Razorpay credentials)
# =====================================================================
def test_razorpay_key_is_cached(cfg):
    cfg.seed("razorpay_key_id", "rzp_test_abc", config_type="string")
    svc = cfg.service()

    assert asyncio.run(svc.get_cached_config_value("razorpay_key_id")) == "rzp_test_abc"
    assert asyncio.run(svc.get_cached_config_value("razorpay_key_id")) == "rzp_test_abc"
    assert cfg.reads == 1


def test_uncacheable_keys_pass_straight_through(cfg):
    """Only the three hot payment keys are cached; everything else is not."""
    cfg.seed("registration_fee_amount", "1500")
    svc = cfg.service()

    asyncio.run(svc.get_cached_config_value("registration_fee_amount"))
    asyncio.run(svc.get_cached_config_value("registration_fee_amount"))

    assert cfg.reads == 2


def test_missing_credential_is_not_cached(cfg):
    """
    get_config_value swallows a missing key and returns the default, so caching
    that None would keep payments unconfigured for the whole TTL even after the
    admin sets the key directly in the database.
    """
    svc = cfg.service()

    assert asyncio.run(svc.get_cached_config_value("razorpay_key_id")) is None
    cfg.seed("razorpay_key_id", "rzp_test_late", config_type="string")
    assert asyncio.run(svc.get_cached_config_value("razorpay_key_id")) == "rzp_test_late"


def test_clear_config_cache_drops_one_key_or_all(cfg):
    cfg.seed("razorpay_key_id", "rzp_test_abc", config_type="string")
    cfg.seed(CONVENIENCE_FEE_CONFIG_KEY, "6")
    svc = cfg.service()

    asyncio.run(svc.get_cached_config_value("razorpay_key_id"))
    asyncio.run(svc.get_convenience_fee_percentage())
    assert cfg.reads == 2

    clear_config_cache("razorpay_key_id")
    asyncio.run(svc.get_cached_config_value("razorpay_key_id"))
    asyncio.run(svc.get_convenience_fee_percentage())   # still cached
    assert cfg.reads == 3

    clear_config_cache()
    asyncio.run(svc.get_cached_config_value("razorpay_key_id"))
    asyncio.run(svc.get_convenience_fee_percentage())
    assert cfg.reads == 5
