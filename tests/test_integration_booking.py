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
from datetime import date, timedelta

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


# Bookings must be dated today-or-later (DB check constraint `valid_booking_datetime`).
# Use a relative near-future date so these fixtures never expire as the calendar rolls on.
_DEFAULT_BOOKING_DATE = (date.today() + timedelta(days=7)).isoformat()


def _booking_payload(salon_id, service_id, quantity=1, booking_date=_DEFAULT_BOOKING_DATE):
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
        _booking_payload(service["salon_id"], service["id"],
                         booking_date=(date.today() + timedelta(days=8)).isoformat()),
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
        _booking_payload(service["salon_id"], service["id"],
                         booking_date=(date.today() + timedelta(days=180)).isoformat()),
        current_user_id=customer["id"],
    ))

    resp = integration_client.put(
        f"{API}/customers/bookings/{created['id']}/cancel", headers=auth_header(token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["booking"]["status"] == "cancelled"


def test_booking_with_service_coupon_records_discount_and_redemption(
    service_client, make_user, make_service
):
    """
    End-to-end coupon path against the live stack: a platform service coupon is
    applied at booking time, the booking records the discount, and a
    coupon_redemptions row is created (proving redeem_coupon() ran).
    """
    customer = make_user(role="customer")
    service = make_service(price=1000.0)

    code = f"SAVE20_{uuid.uuid4().hex[:6].upper()}"
    coupon = service_client.table("coupons").insert({
        "code": code,
        "title": "Integration 20% off services",
        "scope": "platform",
        "funded_by": "platform",
        "applies_to": "service",
        "discount_type": "percentage",
        "discount_value": 20,
        "usage_limit_per_user": 1,
    }).execute().data[0]

    try:
        payload = _booking_payload(service["salon_id"], service["id"],
                                   booking_date=(date.today() + timedelta(days=30)).isoformat())
        payload.coupon_code = code
        # Redemption only happens for a PAID booking (D2): unpaid/pending bookings
        # must not consume coupon usage. Mark this one paid.
        payload.payment_status = "paid"
        payload.razorpay_payment_id = f"pay_test_{uuid.uuid4().hex[:12]}"

        svc = BookingService(db_client=service_client)
        booking = asyncio.run(svc.create_booking(payload, current_user_id=customer["id"]))

        # 20% off 1000 -> pay-at-salon 800, discount 200
        assert booking["service_price"] == 800.0
        assert booking["discount_amount"] == 200.0
        assert booking["coupon_id"] == coupon["id"]
        assert booking["coupon_code"] == code

        redemptions = service_client.table("coupon_redemptions").select("*").eq(
            "coupon_id", coupon["id"]
        ).eq("booking_id", booking["id"]).execute()
        assert len(redemptions.data) == 1
        # Snapshot + gross discount recorded for settlement/reporting (H6)
        redemption = redemptions.data[0]
        assert float(redemption["gross_discount"]) == 200.0
        assert redemption["coupon_code"] == code
        assert redemption["scope"] == "platform"
        assert redemption["funded_by"] == "platform"

        used = service_client.table("coupons").select("used_count").eq(
            "id", coupon["id"]
        ).single().execute()
        assert used.data["used_count"] == 1

        # An UNPAID booking with the same coupon must NOT redeem — proving
        # redemption is gated on payment (D2).
        customer2 = make_user(role="customer")
        payload2 = _booking_payload(service["salon_id"], service["id"],
                                    booking_date=(date.today() + timedelta(days=31)).isoformat())
        payload2.coupon_code = code  # payment_status defaults to unpaid/pending
        booking2 = asyncio.run(
            BookingService(db_client=service_client).create_booking(
                payload2, current_user_id=customer2["id"]
            )
        )
        redemptions2 = service_client.table("coupon_redemptions").select("id").eq(
            "coupon_id", coupon["id"]
        ).eq("booking_id", booking2["id"]).execute()
        assert len(redemptions2.data) == 0
    finally:
        # Bookings (and their cascading redemptions) are cleaned by make_service's
        # salon teardown; drop the coupon reference + row we added here.
        service_client.table("coupon_redemptions").delete().eq("coupon_id", coupon["id"]).execute()
        service_client.table("bookings").update({"coupon_id": None}).eq("coupon_id", coupon["id"]).execute()
        service_client.table("coupons").delete().eq("id", coupon["id"]).execute()
