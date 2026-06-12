"""
Integration tests for the booking flow — the core revenue path.

A customer books a seeded salon/service through the real BookingService against
the live local stack: customer-profile JOIN, salon lookup, service pricing,
convenience-fee math, and the bookings insert all run for real. If a migration
breaks any column these rely on, these tests go red before merge.

Note: the public HTTP create endpoint (`POST /customers/bookings`) was removed —
the live create path is the cart checkout, which calls BookingService.create_booking
in-process. These tests exercise that same method directly (so they stay focused
on the booking_service module, not the cart layer). Listing + cancel are still
covered over HTTP. Payment (Razorpay) is intentionally out of scope.
"""
import asyncio
import uuid

import pytest

from app.core.config import settings
from app.core.exceptions import AppException
from app.schemas import BookingCreate
from app.schemas.request.booking import ServiceItem
from app.services.booking_service import BookingService
from tests.conftest import auth_header

pytestmark = pytest.mark.integration

API = settings.API_PREFIX


def _login(client, user):
    resp = client.post(f"{API}/auth/login",
                       json={"email": user["email"], "password": user["password"]})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _booking_payload(salon_id, service_id, quantity=1, booking_date="2026-07-01"):
    return BookingCreate(
        salon_id=salon_id,
        booking_date=booking_date,
        booking_time="10:00",            # deprecated field, still required by schema
        time_slots=["10:00"],
        services=[ServiceItem(service_id=service_id, quantity=quantity)],
        notes="Integration test booking",
    )


def test_customer_creates_booking(service_client, make_user, make_service):
    """Happy path: customer books one service; pricing + persistence are correct."""
    customer = make_user(role="customer")
    service = make_service(price=500.0, duration_minutes=45)

    svc = BookingService(db_client=service_client)
    booking = asyncio.run(svc.create_booking(
        _booking_payload(service["salon_id"], service["id"], quantity=2),
        current_user_id=customer["id"],
    ))

    assert booking["booking_number"]
    assert booking["salon_id"] == service["salon_id"]
    assert booking["customer_id"] == customer["id"]
    assert booking["status"] == "pending"           # no payment => pending
    assert booking["service_price"] == 1000.0        # 500 * quantity 2
    assert booking["duration_minutes"] == 90         # 45 * 2
    assert booking["convenience_fee"] > 0            # fee applied
    assert len(booking["services"]) == 1


def test_booking_unknown_service_rejected(service_client, make_user, make_salon):
    """Booking a service id that doesn't exist must fail, not silently succeed."""
    customer = make_user(role="customer")
    salon = make_salon()

    svc = BookingService(db_client=service_client)
    with pytest.raises(AppException):
        asyncio.run(svc.create_booking(
            _booking_payload(salon["id"], str(uuid.uuid4())),
            current_user_id=customer["id"],
        ))


def test_cancel_endpoint_requires_authentication(integration_client):
    """The cancel endpoint must reject unauthenticated callers."""
    resp = integration_client.put(f"{API}/customers/bookings/{uuid.uuid4()}/cancel")
    assert resp.status_code in (401, 403), resp.text


def test_customer_sees_own_booking_in_list(service_client, integration_client,
                                           make_user, make_service):
    """After booking, the customer's own-bookings list returns it (over HTTP)."""
    customer = make_user(role="customer")
    token = _login(integration_client, customer)
    service = make_service(price=300.0)

    svc = BookingService(db_client=service_client)
    created = asyncio.run(svc.create_booking(
        _booking_payload(service["salon_id"], service["id"], booking_date="2026-07-02"),
        current_user_id=customer["id"],
    ))
    created_number = created["booking_number"]

    listing = integration_client.get(
        f"{API}/customers/bookings/my-bookings", headers=auth_header(token)
    )
    assert listing.status_code == 200, listing.text
    data = listing.json()
    bookings = data["data"] if isinstance(data, dict) and "data" in data else data
    numbers = [b["booking_number"] for b in bookings]
    assert created_number in numbers


def test_customer_cancels_own_booking(service_client, integration_client,
                                      make_user, make_service):
    """Customer can cancel an upcoming booking over HTTP; status flips to cancelled."""
    customer = make_user(role="customer")
    token = _login(integration_client, customer)
    service = make_service(price=300.0)

    svc = BookingService(db_client=service_client)
    created = asyncio.run(svc.create_booking(
        _booking_payload(service["salon_id"], service["id"], booking_date="2026-12-31"),
        current_user_id=customer["id"],
    ))

    resp = integration_client.put(
        f"{API}/customers/bookings/{created['id']}/cancel", headers=auth_header(token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["booking"]["status"] == "cancelled"
