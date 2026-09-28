"""
Tests for pincode verification (tester bug #3).

The RM salon form only ever checked that a pincode was six digits, so "999999"
onboarded fine. `GET /location/pincode/{pincode}` resolves a PIN against India
Post so the form can fill in City/State and warn on a mismatch.

The rule these tests protect: the lookup is *advisory*. India Post being slow,
down or unparseable must never turn into an error the RM has to get past, so
every failure path answers 200 with `valid: null`.

No marker -> runs in the fast (no-stack) job. India Post is never actually called.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.pincode_service import PincodeLookup, PincodeService, pincode_service

API = settings.API_PREFIX
PINCODE = f"{API}/location/pincode"


@pytest.fixture()
def lookups(monkeypatch):
    """Replace the network call, and clear the process-wide cache between tests."""
    calls = []
    answers = {}

    async def _fake_fetch(self, pincode):
        calls.append(pincode)
        return answers.get(pincode, PincodeLookup(pincode=pincode, valid=False))

    monkeypatch.setattr(PincodeService, "_fetch", _fake_fetch)
    pincode_service._cache.clear()

    handle = type("Handle", (), {"calls": calls, "answers": answers})()
    yield handle
    pincode_service._cache.clear()


@pytest.fixture()
def api(app):
    return TestClient(app)


# =====================================================================
# The endpoint
# =====================================================================
def test_known_pincode_returns_city_and_state(api, lookups):
    lookups.answers["400001"] = PincodeLookup(
        pincode="400001", valid=True, city="Mumbai", state="Maharashtra",
        district="Mumbai", localities=["Bazargate", "Stock Exchange"],
    )

    r = api.get(f"{PINCODE}/400001")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert body["city"] == "Mumbai"
    assert body["state"] == "Maharashtra"
    assert "Bazargate" in body["localities"]


def test_unknown_pincode_is_a_200_saying_false(api, lookups):
    """A PIN that doesn't exist is an answer, not an error."""
    r = api.get(f"{PINCODE}/999999")

    assert r.status_code == 200, r.text
    assert r.json()["valid"] is False
    assert r.json()["city"] is None


def test_lookup_failure_is_reported_as_unknown(api, lookups):
    """India Post down must not block a salon submission."""
    lookups.answers["400001"] = PincodeLookup(
        pincode="400001", valid=None, error="lookup unavailable"
    )

    r = api.get(f"{PINCODE}/400001")

    assert r.status_code == 200, r.text
    assert r.json()["valid"] is None


@pytest.mark.parametrize("bad", ["12345", "1234567", "abcdef", "40000a"])
def test_a_malformed_pincode_is_422(api, lookups, bad):
    r = api.get(f"{PINCODE}/{bad}")
    assert r.status_code == 422, r.text
    assert lookups.calls == [], "a malformed PIN must not reach India Post"


def test_the_endpoint_is_public(api, lookups):
    """The RM form calls it while typing, before anything is submitted."""
    lookups.answers["560001"] = PincodeLookup(pincode="560001", valid=True, city="Bengaluru")
    r = api.get(f"{PINCODE}/560001")
    assert r.status_code == 200, r.text


# =====================================================================
# Caching
# =====================================================================
def test_answers_are_cached(api, lookups):
    lookups.answers["400001"] = PincodeLookup(pincode="400001", valid=True, city="Mumbai")

    api.get(f"{PINCODE}/400001")
    api.get(f"{PINCODE}/400001")

    assert lookups.calls == ["400001"], "the second call must come from the cache"


def test_a_failed_lookup_is_not_cached(api, lookups):
    """Otherwise one timeout would pin that PIN as unknown for 30 days."""
    lookups.answers["400001"] = PincodeLookup(pincode="400001", valid=None, error="lookup unavailable")

    api.get(f"{PINCODE}/400001")
    api.get(f"{PINCODE}/400001")

    assert lookups.calls == ["400001", "400001"]


# =====================================================================
# Parsing India Post's actual response shapes
# =====================================================================
def test_parse_success_payload():
    payload = [{
        "Message": "Number of pincode(s) found:2",
        "Status": "Success",
        "PostOffice": [
            {"Name": "Bazargate", "District": "Mumbai", "State": "Maharashtra"},
            {"Name": "Stock Exchange", "District": "Mumbai", "State": "Maharashtra"},
        ],
    }]

    result = PincodeService._parse("400001", payload)

    assert result.valid is True
    assert (result.city, result.state, result.district) == ("Mumbai", "Maharashtra", "Mumbai")
    assert result.localities == ["Bazargate", "Stock Exchange"]


def test_parse_no_records_payload():
    payload = [{"Message": "No records found", "Status": "Error", "PostOffice": None}]

    result = PincodeService._parse("999999", payload)

    assert result.valid is False
    assert result.city is None


def test_parse_unexpected_payload_is_unknown_not_invalid():
    """A shape change at India Post must not start rejecting real pincodes."""
    result = PincodeService._parse("400001", "a plain string")

    assert result.valid is None
    assert result.error
