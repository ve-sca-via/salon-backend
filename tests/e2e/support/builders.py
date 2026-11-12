"""Payload builders + small multi-step helpers shared by several flows."""
from __future__ import annotations

import datetime as dt
from typing import Any

from .client import ApiClient, expect
from .tokens import phone_verification_token
from .world import DAYS, World


def salon_request_payload(world: World, kind: str = "salon", suffix: str = "") -> dict[str, Any]:
    run = world.cfg.run_id
    phone = world.unique_phone()
    label = "Salon" if kind == "salon" else "Buyer"
    payload: dict[str, Any] = {
        "business_name": f"E2E {label} {run}{suffix}",
        "business_type": "salon" if kind == "salon" else "retail_shop",
        "owner_name": f"E2E {label} Owner {run}{suffix}",
        "owner_phone": phone,
        "business_address": "42 E2E Test Road, Indiranagar, Bengaluru",
        "city": "Bengaluru",
        "state": "Karnataka",
        "pincode": "560038",
        "latitude": 12.9784,
        "longitude": 77.6408,
        "outlet": "Company owned",
        "is_gst": False,
        "pan_number": world.pan(),
        "request_type": kind,
        "documents": {"description": f"Automated E2E {kind} request ({run}). Not a real business."},
    }
    if kind == "salon":
        payload.update({
            "owner_email": f"e2e.owner+{world.cfg.run_tag}{suffix.lower()}@example.com",
            "opening_time": "09:00:00",
            "closing_time": "21:00:00",
            "working_days": [d.capitalize() for d in DAYS],
            "documents": {**payload["documents"],
                          "business_hours": {d: "9:00 AM - 9:00 PM" for d in DAYS}},
        })
    else:
        # Buyer intake fields (Nov 2026): age, gender and a phone-verification
        # token proving the RM OTP-verified the owner's phone. We mint the
        # token instead of sending a real SMS (see support/tokens.py).
        payload.update({
            "owner_age": 34,
            "owner_gender": "female",
            "owner_phone_verification_token": phone_verification_token(
                world.cfg.jwt_secret, "+91" + phone, world.cfg.jwt_algorithm),
        })
    return payload


def submit_request(api: ApiClient, world: World, kind: str, suffix: str = "") -> dict:
    payload = salon_request_payload(world, kind, suffix=suffix)
    resp = api.post("/rm/vendor-requests", token=world.token("rm"), params={"is_draft": "false"}, json=payload)
    data = expect(resp, 200, 201, what=f"RM submits {kind} request")
    data = data.get("data", data) if isinstance(data, dict) else data
    assert data.get("id"), f"no request id in response: {data}"
    data["_payload"] = payload
    return data


def approve(api: ApiClient, world: World, request_id: str, **body: Any) -> dict:
    resp = api.post(f"/admin/vendor-requests/{request_id}/approve", token=world.token("admin"),
                    json={"admin_notes": f"Approved by E2E {world.cfg.run_id}", **body})
    return expect(resp, 200, what="admin approves request")


def future_date(days: int = 3) -> str:
    return (dt.date.today() + dt.timedelta(days=days)).isoformat()
