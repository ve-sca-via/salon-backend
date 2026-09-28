"""
Mocked unit tests for the email service module (app/services/email.py).

The email module exposes NO HTTP endpoints — it is an internal service invoked
as a side effect by booking/vendor/career/payment flows. So these tests drive
``EmailService`` directly:

    EmailService.send_*  ->  real Jinja2 template render  ->  _send_email (retry)
                          ->  _deliver (Resend API, FAKED)  ->  ActivityLog (FAKED)

Only the Resend transport (``_deliver``), the retry ``asyncio.sleep`` and
``ActivityLogService.log`` are stubbed, so the template rendering and the
subject/recipient/From wiring of every sender are exercised for real. Nothing
leaves the process.

They also lock in the email-module cleanup (P1/P2/P0/P3):
  * the email-logging subsystem (EmailLogger / app.services.email_logger) is gone,
  * the orphaned senders (booking_confirmation_email / payment_receipt /
    welcome_vendor) are gone,
  * the broken ``send_booking_confirmation`` alias never existed,
  * ``send_new_career_application_notification`` is now a coroutine.

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
import asyncio
import importlib

import pytest

import app.services.email as email_module
from app.services.email import EmailService, email_service
from app.core.config import settings


# =====================================================================
# Fixture: a fresh EmailService with SMTP + activity log + sleep faked
# =====================================================================
class SentBox:
    """Captures everything a sender would otherwise push to the outside world."""
    def __init__(self):
        self.messages = []      # [{"to", "subject", "payload"}]
        self.activities = []    # ActivityLogService.log kwargs
        self.attempts = 0       # transport calls that reported failure
        self.fail = False       # _deliver reports failure (delivery fails)
        self.permanent = False  # ...and reports it as non-retryable (bad key/domain)
        self.raise_exc = False  # _deliver raises (transport error)
        self.service = None

    def last_html(self):
        return self.messages[-1]["payload"].get("html", "")


@pytest.fixture()
def mail(monkeypatch):
    box = SentBox()

    async def _fake_deliver(self, payload, to_email, subject):
        # Mirrors the real transport contract: (success, error, is_permanent)
        if box.raise_exc:
            raise RuntimeError("resend boom")
        if box.fail:
            box.attempts += 1
            return False, "HTTP 500: upstream error", box.permanent
        box.messages.append({"to": to_email, "subject": subject, "payload": payload})
        return True, None, False

    monkeypatch.setattr(EmailService, "_deliver", _fake_deliver)

    # Don't actually wait between retries.
    async def _no_sleep(*a, **k):
        return None
    monkeypatch.setattr(email_module.asyncio, "sleep", _no_sleep)

    # Capture activity logging instead of hitting the DB.
    async def _log(**kwargs):
        box.activities.append(kwargs)
        return True
    monkeypatch.setattr(email_module.ActivityLogService, "log", staticmethod(_log))

    box.service = EmailService()
    return box


def run(coro):
    return asyncio.run(coro)


def _services():
    return [{"name": "Haircut", "unit_price": 200.0, "quantity": 1},
            {"name": "Shave", "unit_price": 100.0, "quantity": 2}]


EXPECTED_FROM = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"


# =====================================================================
# Happy path — one test per remaining sender
# =====================================================================
def test_vendor_approval_happy(mail):
    ok = run(mail.service.send_vendor_approval_email(
        to_email="owner@example.com", owner_name="Owner",
        salon_name="Glow Salon", registration_token="tok123",
        registration_fee=999.0, salon_id="salon-1",
    ))
    assert ok is True
    assert len(mail.messages) == 1
    sent = mail.messages[0]
    assert sent["to"] == "owner@example.com"
    assert "Glow Salon" in sent["subject"]
    assert sent["payload"]["from"] == EXPECTED_FROM
    assert sent["payload"]["to"] == ["owner@example.com"]
    # Registration link (built from VENDOR_PORTAL_URL + token) made it into the body.
    assert "tok123" in mail.last_html()
    # Activity logged for the admin dashboard.
    assert mail.activities[-1]["action"] == "email_sent"
    assert mail.activities[-1]["details"]["email_type"] == "vendor_approval"
    assert mail.activities[-1]["entity_type"] == "salon"
    assert mail.activities[-1]["entity_id"] == "salon-1"


def test_rm_salon_approved_happy(mail):
    ok = run(mail.service.send_rm_salon_approved_email(
        to_email="rm@example.com", rm_name="RM", salon_name="Glow Salon",
        owner_name="Owner", owner_email="owner@example.com",
        points_awarded=50, new_total_score=150, registration_fee=999.0,
        salon_id="salon-1",
    ))
    assert ok is True
    assert mail.messages[0]["to"] == "rm@example.com"
    assert "50 points" in mail.messages[0]["subject"]
    assert mail.activities[-1]["details"]["email_type"] == "rm_notification"


def test_vendor_rejection_happy(mail):
    ok = run(mail.service.send_vendor_rejection_email(
        to_email="rm@example.com", owner_name="Owner", salon_name="Glow Salon",
        rejection_reason="Incomplete docs", rm_name="RM", request_id="req-1",
    ))
    assert ok is True
    assert mail.messages[0]["to"] == "rm@example.com"
    assert mail.activities[-1]["entity_type"] == "vendor_request"
    assert mail.activities[-1]["entity_id"] == "req-1"


def test_booking_cancellation_happy(mail):
    ok = run(mail.service.send_booking_cancellation_email(
        to_email="cust@example.com", customer_name="Cust", salon_name="Glow Salon",
        service_name="Haircut", booking_date="2026-06-12", booking_time="10:00",
        cancellation_reason="Changed plans", booking_id="bk-1", booking_number="B-100",
    ))
    assert ok is True
    assert "Glow Salon" in mail.messages[0]["subject"]
    assert mail.activities[-1]["details"]["email_type"] == "booking_cancellation"


def test_booking_cancellation_vendor_happy(mail):
    ok = run(mail.service.send_booking_cancellation_notification_to_vendor(
        vendor_email="vendor@example.com", salon_name="Glow Salon",
        customer_name="Cust", customer_phone="+91999", booking_number="B-100",
        booking_date="2026-06-12", booking_time="10:00", services=_services(),
        cancellation_reason="Changed plans", booking_id="bk-1",
    ))
    assert ok is True
    assert mail.messages[0]["to"] == "vendor@example.com"
    html = mail.last_html()
    assert "B-100" in html and "Haircut" in html
    assert mail.activities[-1]["details"]["email_type"] == "booking_cancellation_vendor"


def test_payment_reminder_happy(mail):
    ok = run(mail.service.send_payment_reminder_email(
        to_email="vendor@example.com", salon_name="Glow Salon",
        registration_fee=999.0, salon_id="salon-1",
    ))
    assert ok is True
    # VENDOR_PORTAL_URL (no path) is normalised to a /vendor-login link in the body.
    assert "/vendor-login" in mail.last_html()
    assert mail.activities[-1]["details"]["email_type"] == "payment_reminder"


def test_vendor_registration_receipt_happy(mail):
    ok = run(mail.service.send_vendor_registration_receipt_email(
        to_email="owner@example.com", owner_name="Owner", salon_name="Glow Salon",
        amount=1500.0, razorpay_payment_id="pay_reg_1", salon_id="salon-1",
    ))
    assert ok is True
    sent = mail.messages[0]
    assert sent["to"] == "owner@example.com"
    assert "Glow Salon" in sent["subject"]
    html = mail.last_html()
    assert "pay_reg_1" in html and "1500.00" in html
    # Same VENDOR_PORTAL_URL normalisation as the payment reminder email.
    assert "/vendor-login" in html
    assert mail.activities[-1]["details"]["email_type"] == "vendor_registration_receipt"
    assert mail.activities[-1]["entity_type"] == "salon"
    assert mail.activities[-1]["entity_id"] == "salon-1"


def test_career_application_confirmation_happy(mail):
    ok = run(mail.service.send_career_application_confirmation(
        to_email="applicant@example.com", applicant_name="Jane",
        position="Relationship Manager", application_number="CA-2026-0001",
    ))
    assert ok is True
    assert "Relationship Manager" in mail.messages[0]["subject"]
    assert mail.activities[-1]["details"]["email_type"] == "career_application_confirmation"


def test_new_career_application_admin_notification_happy(mail):
    # P3: this is now async and sends to ADMIN_EMAIL with proper logging args.
    ok = run(mail.service.send_new_career_application_notification(
        applicant_name="Jane", position="Relationship Manager",
        email="applicant@example.com", phone="9999999999",
        experience_years=3, application_id="app-1",
    ))
    assert ok is True
    assert mail.messages[0]["to"] == settings.ADMIN_EMAIL
    assert mail.activities[-1]["details"]["email_type"] == "career_application_admin"
    assert mail.activities[-1]["entity_id"] == "app-1"


def test_booking_confirmation_to_customer_happy(mail):
    ok = run(mail.service.send_booking_confirmation_to_customer(
        customer_email="cust@example.com", customer_name="Cust",
        salon_name="Glow Salon", booking_number="B-100",
        booking_date="2026-06-12", booking_time="10:00", services=_services(),
        total_amount=400.0, convenience_fee=40.0, service_price=360.0,
    ))
    assert ok is True
    assert "B-100" in mail.messages[0]["subject"]
    html = mail.last_html()
    assert "Haircut" in html and "360" in html
    assert mail.activities[-1]["details"]["email_type"] == "booking_confirmation_customer"


def test_new_booking_notification_to_vendor_happy(mail):
    ok = run(mail.service.send_new_booking_notification_to_vendor(
        vendor_email="vendor@example.com", salon_name="Glow Salon",
        customer_name="Cust", customer_phone="+91999", booking_number="B-100",
        booking_date="2026-06-12", booking_time="10:00", services=_services(),
        service_price=360.0, booking_id="bk-1",
    ))
    assert ok is True
    assert mail.messages[0]["to"] == "vendor@example.com"
    assert mail.activities[-1]["details"]["email_type"] == "booking_notification_vendor"
    assert mail.activities[-1]["entity_id"] == "bk-1"


def test_review_request_happy(mail):
    ok = run(mail.service.send_review_request_email(
        customer_email="cust@example.com", customer_name="Cust",
        salon_name="Glow Salon", booking_number="B-100",
        booking_date="2026-06-12", feedback_url="https://app/feedback/xyz",
        booking_id="bk-1",
    ))
    assert ok is True
    assert "https://app/feedback/xyz" in mail.last_html()
    assert mail.activities[-1]["details"]["email_type"] == "review_request_customer"


# =====================================================================
# Error cases
# =====================================================================
def test_delivery_failure_returns_false_and_logs_email_failed(mail):
    mail.fail = True
    ok = run(mail.service.send_vendor_approval_email(
        to_email="owner@example.com", owner_name="Owner", salon_name="Glow Salon",
        registration_token="tok", registration_fee=1.0, salon_id="salon-1",
    ))
    assert ok is False
    assert mail.messages == []        # nothing captured as "sent"
    # Silent loss is the bug being fixed: a failed send must leave a trail.
    assert mail.activities[-1]["action"] == "email_failed"
    assert mail.activities[-1]["details"]["email_type"] == "vendor_approval"
    assert mail.activities[-1]["entity_id"] == "salon-1"
    assert "HTTP 500" in mail.activities[-1]["details"]["error"]
    assert mail.attempts == 4         # 1 initial + 3 retries


def test_permanent_failure_is_not_retried(mail):
    # Bad credentials / rejected address fail identically every time — retrying
    # only keeps the caller's request open longer.
    mail.fail = True
    mail.permanent = True
    ok = run(mail.service.send_vendor_approval_email(
        to_email="owner@example.com", owner_name="Owner", salon_name="Glow Salon",
        registration_token="tok", registration_fee=1.0, salon_id="salon-1",
    ))
    assert ok is False
    assert mail.attempts == 1
    assert mail.activities[-1]["action"] == "email_failed"


def test_transport_exception_returns_false(mail):
    mail.raise_exc = True
    ok = run(mail.service.send_review_request_email(
        customer_email="cust@example.com", customer_name="Cust",
        salon_name="Glow Salon", booking_number="B-100",
        booking_date="2026-06-12", feedback_url="https://app/feedback/xyz",
        booking_id="bk-1",
    ))
    assert ok is False
    assert mail.activities[-1]["action"] == "email_failed"


def test_template_render_error_is_caught(mail, monkeypatch):
    def _boom(_name):
        raise RuntimeError("missing template")
    monkeypatch.setattr(mail.service.env, "get_template", _boom)

    ok = run(mail.service.send_vendor_approval_email(
        to_email="owner@example.com", owner_name="Owner", salon_name="Glow Salon",
        registration_token="tok", registration_fee=1.0, salon_id="salon-1",
    ))
    assert ok is False
    assert mail.messages == []


# =====================================================================
# Cleanup regressions (P0 / P1 / P2 / P3)
# =====================================================================
def test_email_logging_subsystem_removed():
    # P1: the EmailLogger module is gone entirely.
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.services.email_logger")


def test_email_service_has_no_logger_wiring(mail):
    # P1: the singleton/instances no longer carry an email_logger.
    assert not hasattr(mail.service, "email_logger")
    assert not hasattr(email_service, "email_logger")


@pytest.mark.parametrize("name", [
    "send_booking_confirmation_email",
    "send_payment_receipt_email",
    "send_welcome_vendor_email",
])
def test_orphaned_senders_removed(name):
    # P2: the three never-called senders are gone.
    assert not hasattr(EmailService, name)


def test_broken_alias_never_existed():
    # P0: payment_service used to call this non-existent method.
    assert not hasattr(EmailService, "send_booking_confirmation")


def test_career_admin_notification_is_async():
    # P3: sync def returning an un-awaited coroutine -> proper coroutine function.
    assert asyncio.iscoroutinefunction(
        EmailService.send_new_career_application_notification
    )


# =====================================================================
# Links and the support address (audit of 2026-09-27)
#
# Every link in an email must resolve in BOTH frontends — the production SPA and
# the Next.js app that replaces it — which is why these assert the legacy paths
# (/my-bookings, not /account/bookings). See
# salon_management_next/docs/LAUNCH_CHECKLIST.md, section L1.
# =====================================================================
def test_no_template_ships_a_dead_link():
    """Three templates shipped href="#" buttons that did nothing when clicked."""
    dead = [
        path.name
        for path in email_module.template_dir.glob("*.html")
        if 'href="#"' in path.read_text(encoding="utf-8")
    ]
    assert dead == [], f"dead href=\"#\" links in: {dead}"


def test_booking_confirmation_links_to_the_customers_bookings(mail):
    run(mail.service.send_booking_confirmation_to_customer(
        customer_email="cust@example.com", customer_name="Cust",
        salon_name="Glow Salon", booking_number="B-100",
        booking_date="2026-06-12", booking_time="10:00", services=_services(),
        total_amount=400.0, convenience_fee=40.0, service_price=360.0,
    ))
    # This email had no link at all until 2026-09-27.
    assert f'href="{settings.FRONTEND_URL.rstrip("/")}/my-bookings"' in mail.last_html()


def test_booking_cancellation_links_to_the_salon_listing(mail):
    run(mail.service.send_booking_cancellation_email(
        to_email="cust@example.com", customer_name="Cust", salon_name="Glow Salon",
        service_name="Haircut", booking_date="2026-06-12", booking_time="10:00",
    ))
    assert f'href="{settings.FRONTEND_URL.rstrip("/")}/salons"' in mail.last_html()


def test_career_confirmation_links_to_the_real_legal_pages(mail):
    run(mail.service.send_career_application_confirmation(
        to_email="applicant@example.com", applicant_name="Jane",
        position="Relationship Manager", application_number="CA-2026-0001",
    ))
    html = mail.last_html()
    base = settings.FRONTEND_URL.rstrip("/")
    assert f'href="{base}/privacy-policy"' in html
    assert f'href="{base}/terms-of-service"' in html


@pytest.mark.parametrize("send", [
    lambda s: s.send_vendor_approval_email(
        to_email="o@example.com", owner_name="O", salon_name="Glow",
        registration_token="t", registration_fee=1.0),
    lambda s: s.send_booking_cancellation_email(
        to_email="c@example.com", customer_name="C", salon_name="Glow",
        service_name="Haircut", booking_date="2026-06-12", booking_time="10:00"),
    lambda s: s.send_payment_reminder_email(
        to_email="v@example.com", salon_name="Glow", registration_fee=1.0),
    lambda s: s.send_review_request_email(
        customer_email="c@example.com", customer_name="C", salon_name="Glow",
        booking_number="B-1", booking_date="2026-06-12", feedback_url="https://x/y",
        booking_id="bk-1"),
])
def test_support_line_never_shows_the_noreply_sender(mail, send):
    """`support_email` was settings.EMAIL_FROM, i.e. a noreply nobody reads."""
    run(send(mail.service))
    html = mail.last_html()
    assert settings.SUPPORT_EMAIL in html
    assert settings.EMAIL_FROM not in html


def test_render_injects_shared_context_without_call_sites_passing_it(mail):
    """_render owns year/support/links, so no sender has to remember them."""
    html = mail.service._render("booking_cancellation.html", customer_name="C")
    assert settings.SUPPORT_EMAIL in html
    assert f"{settings.FRONTEND_URL.rstrip('/')}/salons" in html

    # An explicit keyword still wins over the injected default.
    overridden = mail.service._render(
        "booking_cancellation.html", customer_name="C", support_email="x@y.z"
    )
    assert "x@y.z" in overridden


# =====================================================================
# Vendor links survive however VENDOR_PORTAL_URL is set (tester bug #7)
# =====================================================================
# The approval email built "{VENDOR_PORTAL_URL}/complete-registration", so a
# deployment whose env var was the bare origin sent approved owners to
# https://host/complete-registration - a page that exists in neither frontend.
# Every vendor link is now built from the origin plus a canonical path.

VENDOR_URL_SHAPES = [
    "https://www.lubist.com/vendor",     # documented form
    "https://www.lubist.com",            # the bare origin that caused the 404
    "https://www.lubist.com/",
    "www.lubist.com/vendor",             # no scheme
    "https://www.lubist.com/vendor-login",
]


@pytest.mark.parametrize("portal_url", VENDOR_URL_SHAPES)
def test_registration_link_always_points_at_the_real_page(mail, monkeypatch, portal_url):
    monkeypatch.setattr(email_module.settings, "VENDOR_PORTAL_URL", portal_url)

    ok = run(mail.service.send_vendor_approval_email(
        to_email="owner@example.com", owner_name="Owner", salon_name="Glow Salon",
        registration_token="tok123", registration_fee=999.0, salon_id="salon-1",
    ))

    assert ok is True
    html = mail.last_html()
    assert "https://www.lubist.com/vendor/complete-registration?token=tok123" in html
    assert "lubist.com/complete-registration" not in html


@pytest.mark.parametrize("portal_url", VENDOR_URL_SHAPES)
def test_vendor_login_link_always_points_at_the_real_page(mail, monkeypatch, portal_url):
    monkeypatch.setattr(email_module.settings, "VENDOR_PORTAL_URL", portal_url)

    ok = run(mail.service.send_payment_reminder_email(
        to_email="vendor@example.com", salon_name="Glow Salon",
        registration_fee=999.0, salon_id="salon-1",
    ))

    assert ok is True
    assert "https://www.lubist.com/vendor-login" in mail.last_html()


@pytest.mark.parametrize("portal_url", ["https://www.lubist.com/vendor", "https://www.lubist.com"])
def test_vendor_dashboard_link_in_booking_emails_keeps_the_vendor_segment(mail, monkeypatch, portal_url):
    """`{{ vendor_portal_url }}/bookings` had the same flaw as the approval link."""
    monkeypatch.setattr(email_module.settings, "VENDOR_PORTAL_URL", portal_url)

    ok = run(mail.service.send_new_booking_notification_to_vendor(
        vendor_email="vendor@example.com", salon_name="Glow Salon",
        customer_name="Cust", customer_phone="+919999999999", booking_number="B-100",
        booking_date="2026-06-12", booking_time="10:00", services=_services(),
        service_price=300.0, booking_id="bk-1",
    ))

    assert ok is True
    assert "https://www.lubist.com/vendor/bookings" in mail.last_html()


def test_a_sub_path_deployment_keeps_its_prefix(mail, monkeypatch):
    """`https://host/app/vendor` is still served under /app after normalisation."""
    monkeypatch.setattr(email_module.settings, "VENDOR_PORTAL_URL", "https://host/app/vendor")

    ok = run(mail.service.send_vendor_approval_email(
        to_email="owner@example.com", owner_name="Owner", salon_name="Glow Salon",
        registration_token="tok", registration_fee=1.0, salon_id="salon-1",
    ))

    assert ok is True
    assert "https://host/app/vendor/complete-registration?token=tok" in mail.last_html()
