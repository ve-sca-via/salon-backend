"""
Thin HTTP client for the deployed API.

* Throttles every request (min interval) to stay under slowapi's global
  100/min-per-IP default limit.
* Retries 429s with backoff (honours Retry-After), so the 5/min login limit
  slows the run down instead of failing it.
* Keeps a short trace of recent calls so a failed assertion can show exactly
  what was sent and what came back.
"""
from __future__ import annotations

import json
import time
from collections import deque
from typing import Any

import httpx
import pytest


class ApiClient:
    def __init__(self, api_base: str, min_interval: float = 0.65, timeout: float = 60.0,
                 max_429_wait: float = 150.0):
        self.api_base = api_base.rstrip("/")
        self.root = self.api_base.rsplit("/api/", 1)[0]
        self.min_interval = min_interval
        self.max_429_wait = max_429_wait
        self._http = httpx.Client(timeout=timeout, headers={"User-Agent": "lubist-e2e-suite"})
        self._last = 0.0
        self.trace: deque[str] = deque(maxlen=6)
        self.calls = 0

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------
    def request(self, method: str, path: str, *, token: str | None = None,
                absolute: bool = False, **kwargs: Any) -> httpx.Response:
        url = path if path.startswith("http") else (
            (self.root if absolute else self.api_base) + (path if path.startswith("/") else "/" + path)
        )
        headers = dict(kwargs.pop("headers", {}) or {})
        if token:
            headers["Authorization"] = f"Bearer {token}"

        waited = 0.0
        attempt = 0
        while True:
            gap = time.monotonic() - self._last
            if gap < self.min_interval:
                time.sleep(self.min_interval - gap)
            try:
                resp = self._http.request(method, url, headers=headers, **kwargs)
            except httpx.TransportError as exc:
                self._last = time.monotonic()
                attempt += 1
                if attempt <= 2:
                    time.sleep(3 * attempt)
                    continue
                raise AssertionError(f"{method} {url} -> transport error: {exc!r}") from exc
            self._last = time.monotonic()
            self.calls += 1
            if resp.status_code == 429 and waited < self.max_429_wait:
                retry_after = resp.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 0.0
                except ValueError:
                    delay = 0.0
                delay = max(delay, 15.0 if attempt == 0 else 20.0)
                delay = min(delay, self.max_429_wait - waited)
                attempt += 1
                print(f"\n[e2e] 429 on {method} {path}; backing off {delay:.0f}s", flush=True)
                time.sleep(delay)
                waited += delay
                continue
            break
        self.trace.append(describe(resp))
        return resp

    def get(self, path: str, **kw: Any) -> httpx.Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> httpx.Response:
        return self.request("POST", path, **kw)

    def put(self, path: str, **kw: Any) -> httpx.Response:
        return self.request("PUT", path, **kw)

    def patch(self, path: str, **kw: Any) -> httpx.Response:
        return self.request("PATCH", path, **kw)

    def delete(self, path: str, **kw: Any) -> httpx.Response:
        return self.request("DELETE", path, **kw)


# ----------------------------------------------------------------------
# Assertion helpers
# ----------------------------------------------------------------------
def body_text(resp: httpx.Response, limit: int = 600) -> str:
    text = resp.text or ""
    return text if len(text) <= limit else text[:limit] + "...(truncated)"


def describe(resp: httpx.Response) -> str:
    req = resp.request
    body = ""
    if req.content:
        try:
            payload = json.loads(req.content)
            # Never echo credentials / tokens into reports.
            for k in ("password", "confirm_password", "token", "refresh_token",
                      "owner_phone_verification_token", "razorpay_signature"):
                if isinstance(payload, dict) and k in payload:
                    payload[k] = "***"
            body = " body=" + json.dumps(payload)[:300]
        except Exception:
            body = ""
    return f"{req.method} {req.url.path}{('?' + req.url.query.decode()) if req.url.query else ''}{body} -> {resp.status_code} {body_text(resp, 400)}"


def expect(resp: httpx.Response, *codes: int, what: str = "") -> Any:
    """Assert the status code is one of `codes`; return parsed JSON (or None)."""
    if resp.status_code not in codes:
        raise AssertionError(
            f"{what + ': ' if what else ''}expected HTTP {'/'.join(map(str, codes))}, got "
            f"{resp.status_code}\n  {describe(resp)}"
        )
    try:
        return resp.json()
    except ValueError:
        return None


def xfail_if(condition: bool, reason: str) -> None:
    """Runtime xfail for a known backend bug / incomplete feature.

    `reason` must start with "BUG:" or "INCOMPLETE:" so the report can list
    them. Because it only fires when the bad behaviour is actually observed,
    the step turns green on its own once the backend is fixed.
    """
    assert reason.startswith(("BUG:", "INCOMPLETE:")), reason
    if condition:
        pytest.xfail(reason)


def detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text or ""
    if isinstance(data, dict):
        for key in ("detail", "message", "error"):
            if key in data:
                value = data[key]
                return value if isinstance(value, str) else json.dumps(value)
    return json.dumps(data)


def dig(data, key):
    """Find `key` at the top level or inside a nested 'breakdown'/'data'/'pricing' dict."""
    if not isinstance(data, dict):
        return None
    if key in data:
        return data[key]
    for sub in ("breakdown", "data", "pricing"):
        if isinstance(data.get(sub), dict) and key in data[sub]:
            return data[sub][key]
    return None
