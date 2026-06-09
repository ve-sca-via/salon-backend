"""
Integration tests for the booking flow — the core revenue path.

A customer books a seeded salon/service through the real BookingService:
customer-profile JOIN, salon lookup, service pricing, convenience-fee math, and
the bookings insert all run against the live local stack. If a migration breaks
any column these rely on, these tests go red before merge.

Payment (Razorpay) is intentionally out of scope here: create-order calls the
real Razorpay API, so it needs a mock — see the note at the bottom.
"""
import uuid

import pytest

from app.core.config import settings
from tests.conftest import auth_header

pytestmark = pytest.mark.integration

API = settings.API_PREFIX


def _login(client, user):
    resp = client.post(f"{API}/auth/login",
                       json={"email": user["email"], "password": user["password"]})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_customer_creates_booking(integration_client, make_user, make_service):
    """Happy path: customer books one service; pricing + persistence are correct."""
    customer = make_user(role="customer")
    token = _login(integration_client, customer)

    service = make_service(price=500.0, duration_minutes=45)

    payload = {
        "salon_id": service["salon_id"],
        "booking_date": "2026-07-01",
        "booking_time": "10:00",          # deprecated field, still required by schema
        "time_slots": ["10:00"],
        "services": [{"service_id": service["id"], "quantity": 2}],
        "notes": "Integration test booking",
    }
    resp = integration_client.post(f"{API}/customers/bookings", json=payload,
                                   headers=auth_header(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["booking_number"]
    assert body["salon_id"] == service["salon_id"]
    assert body["customer_id"] == customer["id"]
    assert body["status"] == "pending"          # no payment => pending
    assert body["service_price"] == 1000.0       # 500 * quantity 2
    assert body["duration_minutes"] == 90        # 45 * 2
    assert body["convenience_fee"] > 0           # fee applied
    assert len(body["services"]) == 1


def test_booking_requires_authentication(integration_client, make_service):
    service = make_service()
    payload = {
        "salon_id": service["salon_id"],
        "booking_date": "2026-07-01",
        "booking_time": "10:00",
        "time_slots": ["10:00"],
        "services": [{"service_id": service["id"], "quantity": 1}],
    }
    resp = integration_client.post(f"{API}/customers/bookings", json=payload)
    assert resp.status_code in (401, 403), resp.text


def test_booking_unknown_service_rejected(integration_client, make_user, make_salon):
    """Booking a service id that doesn't exist must fail, not silently succeed."""
    customer = make_user(role="customer")
    token = _login(integration_client, customer)
    salon = make_salon()

    payload = {
        "salon_id": salon["id"],
        "booking_date": "2026-07-01",
        "booking_time": "10:00",
        "time_slots": ["10:00"],
        "services": [{"service_id": str(uuid.uuid4()), "quantity": 1}],
    }
    resp = integration_client.post(f"{API}/customers/bookings", json=payload,
                                   headers=auth_header(token))
    assert resp.status_code >= 400, resp.text


def test_customer_sees_own_booking_in_list(integration_client, make_user, make_service):
    """After booking, the customer's own-bookings list returns it."""
    customer = make_user(role="customer")
    token = _login(integration_client, customer)
    service = make_service(price=300.0)

    create = integration_client.post(
        f"{API}/customers/bookings",
        json={
            "salon_id": service["salon_id"],
            "booking_date": "2026-07-02",
            "booking_time": "11:00",
            "time_slots": ["11:00"],
            "services": [{"service_id": service["id"], "quantity": 1}],
        },
        headers=auth_header(token),
    )
    assert create.status_code == 200, create.text
    created_number = create.json()["booking_number"]

    # The customer lists their own bookings (ownership is the authenticated user).
    listing = integration_client.get(
        f"{API}/customers/bookings/my-bookings", headers=auth_header(token)
    )
    assert listing.status_code == 200, listing.text
    data = listing.json()
    bookings = data["data"] if isinstance(data, dict) and "data" in data else data
    numbers = [b["booking_number"] for b in bookings]
    assert created_number in numbers
