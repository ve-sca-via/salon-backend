from app.schemas.request.booking import (
    ServiceSummary, Totals, BookingForCancellation, ServiceItem
)


def test_service_item_parsing():
    raw = {"service_id": "svc_123", "quantity": 2}
    item = ServiceItem.model_validate(raw)
    assert item.service_id == "svc_123"
    assert item.quantity == 2


def test_totals_and_service_summary():
    totals_raw = {
        "service_price": 100.0,
        "convenience_fee": 10.0,
        "total_amount": 110.0,
        "convenience_fee_paid": True,
        "service_paid": False,
        "payment_completed_at": None,
    }
    totals = Totals.model_validate(totals_raw)
    assert totals.total_amount == 110.0

    svc = {"service_id": "s1", "quantity": 1, "unit_price": 100.0, "line_total": 100.0}
    svc_summary = ServiceSummary.model_validate(svc)
    assert svc_summary.service_id == "s1"
    assert svc_summary.quantity == 1


def test_booking_for_cancellation_parsing():
    raw = {
        "id": "b1",
        "booking_date": "2025-11-17",
        "booking_time": "10:00",
        "convenience_fee": 5.0,
        "profiles": {"email": "c@example.com", "full_name": "Client"},
        "services": {"name": "Haircut"},
        "salons": {"business_name": "Top Salon"}
    }
    bc = BookingForCancellation.model_validate(raw)
    assert bc.profiles.email == "c@example.com"
    assert bc.services.name == "Haircut"
    assert bc.salons.business_name == "Top Salon"
