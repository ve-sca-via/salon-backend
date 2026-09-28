"""
Pincode verification against India Post.

Why
---
The RM salon form only ever checked that a pincode was six digits, so "999999"
sailed through onboarding and nobody noticed until a customer tried to find the
place. This resolves a PIN to its real district and state so the form can fill
those in and flag a mismatch.

Deliberately advisory, not authoritative: India Post's open API is free and
unauthenticated, which also means it is occasionally slow or down. Every failure
path returns "unknown" rather than an error, and the caller treats unknown as
"carry on" - a salon submission must never be blocked by someone else's uptime.
Results are cached in-process because the same few PINs get typed repeatedly and
the data changes about never.
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

PINCODE_PATTERN = re.compile(r"^\d{6}$")
API_URL = "https://api.postalpincode.in/pincode/{pincode}"
REQUEST_TIMEOUT_SECONDS = 5.0
CACHE_TTL = timedelta(days=30)
#: Cap the cache so a scripted sweep of every PIN can't grow it without bound.
CACHE_MAX_ENTRIES = 2000


@dataclass
class PincodeLookup:
    """What a lookup could establish about a pincode."""

    pincode: str
    #: True = India Post knows it, False = it says no such PIN, None = couldn't ask.
    valid: Optional[bool]
    city: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    localities: List[str] = field(default_factory=list)
    #: Present when the lookup itself failed, for the client to log, not to show.
    error: Optional[str] = None

    @property
    def resolved(self) -> bool:
        return self.valid is True


class PincodeService:
    """Looks up Indian PINs, with an in-process TTL cache."""

    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[PincodeLookup, datetime]] = {}
        self._lock = asyncio.Lock()

    async def lookup(self, pincode: str) -> PincodeLookup:
        """
        Resolve a six-digit PIN to its district and state.

        Never raises: an unreachable API comes back as ``valid=None``.
        """
        pincode = (pincode or "").strip()

        if not PINCODE_PATTERN.match(pincode):
            return PincodeLookup(pincode=pincode, valid=False, error="not a 6-digit pincode")

        cached = self._cached(pincode)
        if cached:
            return cached

        result = await self._fetch(pincode)

        # Only cache answers; a timeout must not pin itself for 30 days.
        if result.valid is not None:
            await self._store(pincode, result)

        return result

    def _cached(self, pincode: str) -> Optional[PincodeLookup]:
        entry = self._cache.get(pincode)
        if not entry:
            return None

        result, stored_at = entry
        if datetime.utcnow() - stored_at > CACHE_TTL:
            self._cache.pop(pincode, None)
            return None

        return result

    async def _store(self, pincode: str, result: PincodeLookup) -> None:
        async with self._lock:
            if len(self._cache) >= CACHE_MAX_ENTRIES:
                oldest = min(self._cache, key=lambda key: self._cache[key][1])
                self._cache.pop(oldest, None)
            self._cache[pincode] = (result, datetime.utcnow())

    async def _fetch(self, pincode: str) -> PincodeLookup:
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(API_URL.format(pincode=pincode))
        except Exception as e:
            logger.warning(f"Pincode lookup for {pincode} failed to reach India Post: {type(e).__name__}: {e}")
            return PincodeLookup(pincode=pincode, valid=None, error="lookup unavailable")

        if response.status_code != 200:
            logger.warning(f"Pincode lookup for {pincode} returned HTTP {response.status_code}")
            return PincodeLookup(pincode=pincode, valid=None, error="lookup unavailable")

        try:
            payload = response.json()
        except Exception:
            logger.warning(f"Pincode lookup for {pincode} returned a non-JSON body")
            return PincodeLookup(pincode=pincode, valid=None, error="lookup unavailable")

        return self._parse(pincode, payload)

    @staticmethod
    def _parse(pincode: str, payload) -> PincodeLookup:
        """
        India Post answers with a single-element list:

            [{"Status": "Success", "PostOffice": [{"District": ..., "State": ...}]}]
            [{"Status": "Error", "Message": "No records found", "PostOffice": null}]
        """
        record = payload[0] if isinstance(payload, list) and payload else payload
        if not isinstance(record, dict):
            return PincodeLookup(pincode=pincode, valid=None, error="unexpected response")

        offices = record.get("PostOffice") or []
        if record.get("Status") != "Success" or not offices:
            return PincodeLookup(pincode=pincode, valid=False)

        first = offices[0] if isinstance(offices[0], dict) else {}
        district = (first.get("District") or "").strip() or None
        state = (first.get("State") or "").strip() or None

        localities = []
        for office in offices:
            if not isinstance(office, dict):
                continue
            name = (office.get("Name") or "").strip()
            if name and name not in localities:
                localities.append(name)

        return PincodeLookup(
            pincode=pincode,
            valid=True,
            # India Post has no "city" field; the district is the closest thing to
            # one, and it is what the RM form's City input expects.
            city=district,
            state=state,
            district=district,
            localities=localities[:20],
        )


pincode_service = PincodeService()
