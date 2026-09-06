"""
Email Service
Handles sending emails through the Resend HTTP API with HTML templates.
"""
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape
from app.core.config import settings
from app.services.activity_log_service import ActivityLogService
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)


# =====================================================
# RESEND TRANSPORT
# =====================================================
RESEND_API_URL = "https://api.resend.com/emails"

# Bound every send so a stalled connection can't hang the calling request.
RESEND_TIMEOUT_SECONDS = 15

# Statuses that will never succeed on retry: bad API key (401/403), or a payload
# Resend refuses outright (422 — almost always an unverified `from` domain, 400 —
# malformed body). Retrying these just burns time and request quota.
PERMANENT_STATUS_CODES = frozenset({400, 401, 403, 404, 422})


# =====================================================
# JINJA2 TEMPLATE ENVIRONMENT (SINGLETON)
# =====================================================
# Created once at module load time and shared across all EmailService instances
# This prevents creating new Jinja2 environments (500KB-1MB each) on every instantiation

template_dir = Path(__file__).parent.parent / "templates" / "email"
_jinja2_env = Environment(
    loader=FileSystemLoader(str(template_dir)),
    autoescape=select_autoescape(['html', 'xml'])
)

logger.info("Initialized shared Jinja2 template environment (singleton)")


def _normalize_booking_services(services: list) -> list:
    """
    Normalize booking services into plain {name, price, quantity} dicts for
    template rendering - names go through Jinja2's autoescaping this way,
    instead of being interpolated into raw HTML via f-strings.
    """
    normalized = []
    for service in services:
        if not isinstance(service, dict):
            normalized.append({"name": str(service), "price": 0.0, "quantity": 1})
            continue

        normalized.append({
            "name": service.get("name") or service.get("service_name", "Service"),
            "price": float(service.get("price") or service.get("unit_price") or 0),
            "quantity": int(service.get("quantity") or 1),
        })

    return normalized


class EmailService:
    """Email service for sending templated emails"""
    
    def __init__(self):
        # Use shared Jinja2 template environment (singleton)
        # This prevents creating new environments on every instantiation
        self.env = _jinja2_env

    def _render(self, template_name: str, **context) -> str:
        """Render a template, injecting current_year once so no call site hardcodes it."""
        from datetime import datetime
        template = self.env.get_template(template_name)
        return template.render(current_year=datetime.now().year, **context)

    async def _send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        email_type: str = "unknown",
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[str] = None
    ) -> bool:
        """
        Send email via the Resend API with retry logic (async)

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body (optional)
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries (exponential backoff)
            email_type: Type of email for activity logging (vendor_approval, booking_confirmation, etc.)
            related_entity_type: Type of related entity (booking, salon, payment, etc.)
            related_entity_id: UUID of related entity

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            payload = {
                "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>",
                "to": [to_email],
                "subject": subject,
                "html": html_body,
            }
            if text_body:
                payload["text"] = text_body

            # Send email with retry logic
            last_error = "unknown error"
            for attempt in range(max_retries + 1):
                success, error, permanent = await self._deliver(payload, to_email, subject)

                if success:
                    # Log activity for admin dashboard
                    try:
                        await ActivityLogService.log(
                            user_id=None,  # System action
                            action="email_sent",
                            entity_type=related_entity_type,
                            entity_id=related_entity_id,
                            details={
                                "email_type": email_type,
                                "recipient": to_email,
                                "subject": subject
                            }
                        )
                    except Exception as e:
                        logger.error(f"Failed to log email activity: {e}")

                    return True

                last_error = error or "unknown error"

                # Bad credentials / rejected address will fail identically on every
                # retry — give up now so the caller isn't blocked for another ~7s.
                if permanent:
                    logger.error(
                        f"Email to {to_email} ({email_type}) rejected permanently, not retrying: {last_error}"
                    )
                    break

                # If this wasn't the last attempt, wait before retrying
                if attempt < max_retries:
                    delay = retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Email send failed (attempt {attempt + 1}/{max_retries + 1}): {last_error}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)

            # All retries exhausted (or a permanent failure short-circuited them)
            logger.error(
                f"Failed to send '{email_type}' email to {to_email}: {last_error}"
            )
            await self._log_email_failure(
                to_email, subject, email_type, last_error, related_entity_type, related_entity_id
            )
            return False

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {type(e).__name__}: {str(e)}", exc_info=True)
            await self._log_email_failure(
                to_email, subject, email_type, f"{type(e).__name__}: {e}",
                related_entity_type, related_entity_id
            )
            return False

    @staticmethod
    async def _log_email_failure(
        to_email: str,
        subject: str,
        email_type: str,
        error: str,
        related_entity_type: Optional[str],
        related_entity_id: Optional[str]
    ) -> None:
        """
        Record a failed send in activity_logs so silent email loss is visible on the
        admin dashboard instead of only in server logs.
        """
        try:
            await ActivityLogService.log(
                user_id=None,  # System action
                action="email_failed",
                entity_type=related_entity_type,
                entity_id=related_entity_id,
                details={
                    "email_type": email_type,
                    "recipient": to_email,
                    "subject": subject,
                    "error": error[:500]
                }
            )
        except Exception as e:
            logger.error(f"Failed to log email failure activity: {e}")

    async def _deliver(self, payload: dict, to_email: str, subject: str) -> tuple:
        """
        Hand a single message to the Resend API.

        Returns:
            (success, error_message, is_permanent) - is_permanent means retrying
            the same message will fail the same way (bad API key / unverified
            sender domain), so the caller should stop rather than back off.
        """
        if not settings.RESEND_API_KEY:
            # No key configured (typical for local dev). Don't pretend it was
            # delivered — say so loudly and surface the recipient/subject so the
            # flow can still be followed from the logs.
            logger.warning(
                f"RESEND_API_KEY is not set — email NOT sent to {to_email}: {subject}"
            )
            return False, "RESEND_API_KEY is not configured", True

        try:
            async with httpx.AsyncClient(timeout=RESEND_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    RESEND_API_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                        "Content-Type": "application/json",
                    },
                )

            if response.is_success:
                # Resend returns the message id; log it so a delivery can be
                # traced in the Resend dashboard from our logs alone.
                try:
                    message_id = response.json().get("id", "unknown")
                except Exception:
                    message_id = "unknown"
                logger.info(
                    f"Email sent successfully to {to_email}: {subject} (resend_id={message_id})"
                )
                return True, None, False

            # Resend puts a human-readable cause in the body — keep it, it's the
            # difference between "bad key" and "domain not verified".
            error = f"HTTP {response.status_code}: {response.text[:300]}"
            permanent = response.status_code in PERMANENT_STATUS_CODES

            log = logger.error if permanent else logger.warning
            log(
                f"Resend rejected email to {to_email} "
                f"(from '{payload.get('from')}'): {error}"
            )
            return False, error, permanent

        except Exception as e:
            # Network/timeout — worth retrying.
            logger.error(
                f"Failed to reach Resend while sending to {to_email}: {type(e).__name__}: {e}"
            )
            return False, f"{type(e).__name__}: {e}", False


    async def send_vendor_approval_email(
        self,
        to_email: str,
        owner_name: str,
        salon_name: str,
        registration_token: str,
        registration_fee: float,
        salon_id: Optional[str] = None
    ) -> bool:
        """
        Send vendor approval email with registration link
        
        Args:
            to_email: Vendor email
            owner_name: Salon owner name
            salon_name: Salon name
            registration_token: JWT token for registration link
            registration_fee: Amount to pay for registration
            salon_id: Salon ID for logging
            
        Returns:
            bool: Success status
        """
        try:
            registration_url = f"{settings.VENDOR_PORTAL_URL}/complete-registration?token={registration_token}"

            # Log registration URL for easy access (in all environments)
            logger.info("=" * 100)
            logger.info("VENDOR APPROVAL EMAIL")
            logger.info(f"To: {to_email}")
            logger.info(f"Subject: Congratulations! {salon_name} has been approved")
            logger.info("-" * 100)
            logger.info("REGISTRATION URL:")
            logger.info(f"   {registration_url}")
            logger.info("=" * 100)

            html_body = self._render(
                'vendor_approval.html',
                owner_name=owner_name,
                salon_name=salon_name,
                registration_url=registration_url,
                registration_fee=registration_fee,
                support_email=settings.EMAIL_FROM,
            )
            
            subject = f"Congratulations! {salon_name} has been approved"
            
            return await self._send_email(
                to_email, 
                subject, 
                html_body,
                email_type="vendor_approval",
                related_entity_type="salon",
                related_entity_id=salon_id
            )
            
        except Exception as e:
            logger.error(f"Failed to send vendor approval email: {str(e)}")
            return False
    
    async def send_rm_salon_approved_email(
        self,
        to_email: str,
        rm_name: str,
        salon_name: str,
        owner_name: str,
        owner_email: str,
        points_awarded: int,
        new_total_score: int,
        registration_fee: float,
        salon_id: Optional[str] = None
    ) -> bool:
        """
        Send salon approval notification email to RM
        
        Args:
            to_email: RM email
            rm_name: RM name
            salon_name: Salon name
            owner_name: Salon owner name
            owner_email: Salon owner email
            points_awarded: Points awarded to RM
            new_total_score: RM's new total score
            registration_fee: Registration fee amount
            salon_id: Salon ID for logging
            
        Returns:
            bool: Success status
        """
        try:
            html_body = self._render(
                'rm_salon_approved.html',
                rm_name=rm_name,
                salon_name=salon_name,
                owner_name=owner_name,
                owner_email=owner_email,
                points_awarded=points_awarded,
                new_total_score=new_total_score,
                registration_fee=registration_fee,
                support_email=settings.EMAIL_FROM,
            )
            
            subject = f"Salon Approved: {salon_name} - You've earned {points_awarded} points!"
            
            return await self._send_email(
                to_email, 
                subject, 
                html_body,
                email_type="rm_notification",
                related_entity_type="salon",
                related_entity_id=salon_id
            )
            
        except Exception as e:
            logger.error(f"Failed to send RM approval notification email: {str(e)}")
            return False
    
    async def send_vendor_rejection_email(
        self,
        to_email: str,
        owner_name: str,
        salon_name: str,
        rejection_reason: str,
        rm_name: str,
        request_id: Optional[str] = None
    ) -> bool:
        """
        Send vendor rejection email to RM
        
        Args:
            to_email: RM email
            owner_name: Salon owner name
            salon_name: Salon name
            rejection_reason: Admin's rejection reason
            rm_name: RM name
            request_id: Vendor request ID for logging
            
        Returns:
            bool: Success status
        """
        try:
            html_body = self._render(
                'vendor_rejection.html',
                rm_name=rm_name,
                salon_name=salon_name,
                owner_name=owner_name,
                rejection_reason=rejection_reason,
                support_email=settings.EMAIL_FROM,
            )
            
            subject = f"Salon Submission Update: {salon_name}"
            
            return await self._send_email(
                to_email, 
                subject, 
                html_body,
                email_type="vendor_rejection",
                related_entity_type="vendor_request",
                related_entity_id=request_id
            )
            
        except Exception as e:
            logger.error(f"Failed to send vendor rejection email: {str(e)}")
            return False
    
    async def send_booking_cancellation_email(
        self,
        to_email: str,
        customer_name: str,
        salon_name: str,
        service_name: str,
        booking_date: str,
        booking_time: str,
        cancellation_reason: str = None,
        booking_id: str = None,
        booking_number: str = None,
    ) -> bool:
        """
        Send booking cancellation email
        
        Args:
            to_email: Customer email
            customer_name: Customer name
            salon_name: Salon name
            service_name: Service name
            booking_date: Booking date
            booking_time: Booking time
            cancellation_reason: Reason for cancellation
            
        Returns:
            bool: Success status
        """
        try:
            html_body = self._render(
                'booking_cancellation.html',
                customer_name=customer_name,
                salon_name=salon_name,
                service_name=service_name,
                booking_date=booking_date,
                booking_time=booking_time,
                cancellation_reason=cancellation_reason,
                support_email=settings.EMAIL_FROM,
            )
            
            subject = f"Booking Cancelled: {salon_name}"
            
            return await self._send_email(
                to_email, 
                subject, 
                html_body,
                email_type="booking_cancellation",
                related_entity_type="booking",
                related_entity_id=booking_id
            )
            
        except Exception as e:
            logger.error(f"Failed to send booking cancellation email: {str(e)}")
            return False

    async def send_booking_cancellation_notification_to_vendor(
        self,
        vendor_email: str,
        salon_name: str,
        customer_name: str,
        customer_phone: str,
        booking_number: str,
        booking_date: str,
        booking_time: str,
        services: list,
        cancellation_reason: str = None,
        booking_id: str = None,
    ) -> bool:
        """Notify vendor/salon that a customer cancelled a booking."""
        try:
            html_body = self._render(
                'booking_cancellation_vendor.html',
                salon_name=salon_name,
                customer_name=customer_name,
                customer_phone=customer_phone,
                booking_number=booking_number,
                booking_date=booking_date,
                booking_time=booking_time,
                services=_normalize_booking_services(services),
                cancellation_reason=cancellation_reason,
                vendor_portal_url=settings.VENDOR_PORTAL_URL,
            )

            subject = f"Booking Cancelled - {customer_name} ({booking_number})"

            result = await self._send_email(
                vendor_email,
                subject,
                html_body,
                email_type="booking_cancellation_vendor",
                related_entity_type="booking",
                related_entity_id=booking_id
            )
            logger.info(f"Booking cancellation notification sent to vendor {vendor_email} for booking {booking_number}")
            return result

        except Exception as e:
            logger.error(f"Failed to send vendor booking cancellation notification: {str(e)}")
            return False
    
    def _vendor_login_url(self) -> str:
        """Normalize VENDOR_PORTAL_URL (whatever path it points to) to the vendor login page."""
        vendor_portal_url = settings.VENDOR_PORTAL_URL.strip()
        parsed = urlsplit(vendor_portal_url if vendor_portal_url.startswith(('http://', 'https://')) else f"https://{vendor_portal_url}")
        portal_path = parsed.path.rstrip('/')

        if portal_path.endswith('/vendor-login'):
            return vendor_portal_url.rstrip('/')
        elif portal_path.endswith('/vendor') or portal_path == '':
            base = parsed.netloc if not vendor_portal_url.startswith(('http://', 'https://')) else f"{parsed.scheme}://{parsed.netloc}"
            return f"{base}/vendor-login"
        else:
            return f"{vendor_portal_url.rstrip('/')}/vendor-login"

    async def send_payment_reminder_email(
        self,
        to_email: str,
        salon_name: str,
        registration_fee: float,
        salon_id: Optional[str] = None
    ) -> bool:
        """
        Send payment reminder email to vendor with pending registration fee
        Vendor already has account, just needs to login and pay from dashboard

        Args:
            to_email: Vendor email
            salon_name: Salon name
            registration_fee: Amount to pay for registration
            salon_id: Salon ID for logging

        Returns:
            bool: Success status
        """
        try:
            vendor_login_url = self._vendor_login_url()

            # Log reminder
            logger.info("=" * 100)
            logger.info("PAYMENT REMINDER EMAIL")
            logger.info(f"To: {to_email}")
            logger.info(f"Salon: {salon_name}")
            logger.info(f"Amount: Rs. {registration_fee}")
            logger.info("=" * 100)
            
            html_body = self._render(
                'payment_reminder.html',
                salon_name=salon_name,
                vendor_login_url=vendor_login_url,
                registration_fee=registration_fee,
                support_email=settings.EMAIL_FROM,
            )
            
            subject = f"Payment Reminder - Complete registration for {salon_name}"
            
            return await self._send_email(
                to_email, 
                subject, 
                html_body,
                email_type="payment_reminder",
                related_entity_type="salon",
                related_entity_id=salon_id
            )
            
        except Exception as e:
            logger.error(f"Failed to send payment reminder email: {str(e)}")
            return False

    async def send_vendor_registration_receipt_email(
        self,
        to_email: str,
        owner_name: str,
        salon_name: str,
        amount: float,
        razorpay_payment_id: str,
        salon_id: Optional[str] = None
    ) -> bool:
        """
        Send payment receipt + welcome email once a vendor's registration fee
        payment is verified and their salon is activated.

        Args:
            to_email: Vendor email
            owner_name: Salon owner name
            salon_name: Salon name
            amount: Registration fee amount paid
            razorpay_payment_id: Razorpay payment ID (receipt reference)
            salon_id: Salon ID for logging

        Returns:
            bool: Success status
        """
        try:
            html_body = self._render(
                'vendor_registration_receipt.html',
                owner_name=owner_name,
                salon_name=salon_name,
                amount=amount,
                razorpay_payment_id=razorpay_payment_id,
                vendor_login_url=self._vendor_login_url(),
                support_email=settings.EMAIL_FROM,
            )

            subject = f"Payment Receipt & Welcome to {settings.EMAIL_FROM_NAME} - {salon_name} is now live!"

            return await self._send_email(
                to_email,
                subject,
                html_body,
                email_type="vendor_registration_receipt",
                related_entity_type="salon",
                related_entity_id=salon_id
            )

        except Exception as e:
            logger.error(f"Failed to send vendor registration receipt email: {str(e)}")
            return False

    async def send_career_application_confirmation(
        self,
        to_email: str,
        applicant_name: str,
        position: str,
        application_number: str
    ) -> bool:
        """
        Send confirmation email to career applicant
        
        Args:
            to_email: Applicant email
            applicant_name: Applicant's full name
            position: Position applied for
            application_number: Unique application number
            
        Returns:
            bool: Success status
        """
        try:
            from datetime import datetime
            current_date = datetime.now().strftime("%B %d, %Y")

            html_body = self._render(
                'career_application_confirmation.html',
                applicant_name=applicant_name,
                position=position,
                application_number=application_number,
                current_date=current_date,
                support_email=settings.EMAIL_FROM,
            )
            
            subject = f"Application Received - {position}"
            
            return await self._send_email(
                to_email, 
                subject, 
                html_body,
                email_type="career_application_confirmation",
                related_entity_type="career_application",
                related_entity_id=None  # Would need application_id passed in
            )
            
        except Exception as e:
            logger.error(f"Failed to send career application confirmation: {str(e)}")
            return False
    
    async def send_new_career_application_notification(
        self,
        applicant_name: str,
        position: str,
        email: str,
        phone: str,
        experience_years: int,
        application_id: str
    ) -> bool:
        """
        Send notification to admin about new career application
        
        Args:
            applicant_name: Applicant's full name
            position: Position applied for
            email: Applicant email
            phone: Applicant phone
            experience_years: Years of experience
            application_id: Application UUID
            
        Returns:
            bool: Success status
        """
        try:
            from datetime import datetime
            current_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")

            # Admin email from settings
            admin_email = settings.ADMIN_EMAIL

            html_body = self._render(
                'new_career_application_admin.html',
                applicant_name=applicant_name,
                position=position,
                email=email,
                phone=phone,
                experience_years=experience_years,
                application_id=application_id,
                current_date=current_date,
                admin_panel_url=settings.ADMIN_PANEL_URL,
                has_educational_certificates=True,
                has_experience_letter=experience_years > 0,
                has_salary_slip=experience_years > 0
            )
            
            subject = f"New Career Application - {position}"

            return await self._send_email(
                admin_email,
                subject,
                html_body,
                email_type="career_application_admin",
                related_entity_type="career_application",
                related_entity_id=application_id
            )

        except Exception as e:
            logger.error(f"Failed to send career application admin notification: {str(e)}")
            return False

    async def _send_admin_notification(
        self,
        *,
        badge: str,
        title: str,
        heading: str,
        intro: str,
        rows: list,
        action_note: str,
        cta_url: str,
        cta_label: str,
        subject: str,
        email_type: str,
        related_entity_type: str,
        related_entity_id: Optional[str] = None,
    ) -> bool:
        """
        Render and send an admin alert via the shared admin_notification template.

        Every admin-facing notification goes to settings.ADMIN_EMAIL — the single
        inbox the admin panel operators watch.
        """
        try:
            html_body = self._render(
                'admin_notification.html',
                badge=badge,
                title=title,
                heading=heading,
                intro=intro,
                rows=rows,
                action_note=action_note,
                cta_url=cta_url,
                cta_label=cta_label,
            )

            return await self._send_email(
                settings.ADMIN_EMAIL,
                subject,
                html_body,
                email_type=email_type,
                related_entity_type=related_entity_type,
                related_entity_id=related_entity_id,
            )

        except Exception as e:
            logger.error(f"Failed to send admin '{email_type}' notification: {str(e)}")
            return False

    async def send_new_vendor_request_notification_to_admin(
        self,
        business_name: str,
        business_type: str,
        owner_name: str,
        owner_email: str,
        owner_phone: str,
        city: str,
        rm_name: str,
        request_id: str,
    ) -> bool:
        """Alert admin that an RM submitted a new salon for approval."""
        return await self._send_admin_notification(
            badge="New Request",
            title="New Vendor Join Request",
            heading=f"{business_name} is awaiting approval",
            intro=(
                f"{rm_name} has submitted a new business for approval. "
                f"It is now pending review in the admin panel."
            ),
            rows=[
                ("Business Name", business_name),
                ("Business Type", business_type),
                ("Owner Name", owner_name),
                ("Owner Email", owner_email),
                ("Owner Phone", owner_phone),
                ("City", city),
                ("Submitted By (RM)", rm_name),
            ],
            action_note="Review this request and approve or reject it in the admin panel.",
            cta_url=f"{settings.ADMIN_PANEL_URL}/pending-salons",
            cta_label="Review Request",
            subject=f"New Vendor Request - {business_name} ({city})",
            email_type="vendor_request_admin",
            related_entity_type="vendor_request",
            related_entity_id=request_id,
        )

    async def send_new_partner_request_notification_to_admin(
        self,
        owner_name: str,
        shop_name: str,
        shop_type: str,
        email: str,
        phone: str,
        location: str,
        request_id: str,
    ) -> bool:
        """Alert admin that someone submitted the public 'Partner with us' form."""
        return await self._send_admin_notification(
            badge="New Lead",
            title="New Partner Request",
            heading=f"{shop_name} wants to partner with Lubist",
            intro=(
                "A new partner enquiry has been submitted through the public "
                "'Partner with us' form."
            ),
            rows=[
                ("Owner Name", owner_name),
                ("Shop Name", shop_name),
                ("Shop Type", shop_type),
                ("Email", email),
                ("Phone", phone),
                ("Location", location),
            ],
            action_note="Follow up with this lead and update its status in the admin panel.",
            cta_url=f"{settings.ADMIN_PANEL_URL}/partner-requests",
            cta_label="View Lead",
            subject=f"New Partner Request - {shop_name} ({location})",
            email_type="partner_request_admin",
            related_entity_type="partner_request",
            related_entity_id=request_id,
        )

    async def send_booking_confirmation_to_customer(
        self,
        customer_email: str,
        customer_name: str,
        salon_name: str,
        booking_number: str,
        booking_date: str,
        booking_time: str,
        services: list,
        total_amount: float,
        convenience_fee: float,
        service_price: float,
        subtotal_service_price: Optional[float] = None,
        discount_amount: float = 0,
        convenience_fee_discount: float = 0,
        coupon_code: Optional[str] = None,
        booking_id: Optional[str] = None
    ) -> bool:
        """
        Send booking confirmation email to customer

        Args:
            customer_email: Customer's email
            customer_name: Customer's name
            salon_name: Salon name
            booking_number: Booking reference number
            booking_date: Booking date
            booking_time: Booking time
            services: List of services booked
            total_amount: Total booking amount
            convenience_fee: Online convenience fee paid (after any discount)
            service_price: Service price to be paid at salon (after any discount)
            subtotal_service_price: Service total before coupon discount (optional)
            discount_amount: Coupon discount applied to the service price
            convenience_fee_discount: Coupon discount applied to the convenience fee
            coupon_code: Applied coupon code, if any
            booking_id: Booking UUID, for activity-log tracing on failed sends

        Returns:
            bool: Success status
        """
        try:
            total_savings = (discount_amount or 0) + (convenience_fee_discount or 0)
            pre_discount_service = (
                subtotal_service_price
                if subtotal_service_price is not None
                else service_price + (discount_amount or 0)
            )
            fee_before = convenience_fee + (convenience_fee_discount or 0)

            html_body = self._render(
                'booking_confirmation.html',
                customer_name=customer_name,
                salon_name=salon_name,
                booking_number=booking_number,
                booking_date=booking_date,
                booking_time=booking_time,
                services=_normalize_booking_services(services),
                total_amount=total_amount,
                convenience_fee=convenience_fee,
                service_price=service_price,
                pre_discount_service=pre_discount_service,
                discount_amount=discount_amount,
                fee_before=fee_before,
                convenience_fee_discount=convenience_fee_discount,
                coupon_code=coupon_code,
                total_savings=total_savings,
            )

            subject = f"Booking Confirmed - {salon_name} ({booking_number})"

            result = await self._send_email(
                customer_email,
                subject,
                html_body,
                email_type="booking_confirmation_customer",
                related_entity_type="booking",
                related_entity_id=booking_id
            )
            logger.info(f"Booking confirmation email sent to {customer_email} for booking {booking_number}")
            return result

        except Exception as e:
            logger.error(f"Failed to send customer booking confirmation: {str(e)}")
            return False
    
    async def send_new_booking_notification_to_vendor(
        self,
        vendor_email: str,
        salon_name: str,
        customer_name: str,
        customer_phone: str,
        booking_number: str,
        booking_date: str,
        booking_time: str,
        services: list,
        service_price: float,
        booking_id: str
    ) -> bool:
        """
        Send new booking notification email to vendor
        
        Args:
            vendor_email: Vendor's email
            salon_name: Salon name
            customer_name: Customer's name
            customer_phone: Customer's phone
            booking_number: Booking reference number
            booking_date: Booking date
            booking_time: Booking time
            services: List of services booked
            service_price: Discounted service total to collect from customer at salon
            booking_id: Booking UUID
            
        Returns:
            bool: Success status
        """
        try:
            html_body = self._render(
                'new_booking_vendor.html',
                salon_name=salon_name,
                customer_name=customer_name,
                customer_phone=customer_phone,
                booking_number=booking_number,
                booking_date=booking_date,
                booking_time=booking_time,
                services=_normalize_booking_services(services),
                service_price=service_price,
                vendor_portal_url=settings.VENDOR_PORTAL_URL,
            )

            subject = f"New Booking - {customer_name} ({booking_number})"

            result = await self._send_email(
                vendor_email,
                subject,
                html_body,
                email_type="booking_notification_vendor",
                related_entity_type="booking",
                related_entity_id=booking_id
            )
            logger.info(f"New booking notification email sent to vendor {vendor_email} for booking {booking_number}")
            return result

        except Exception as e:
            logger.error(f"Failed to send vendor booking notification: {str(e)}")
            return False

    async def send_review_request_email(
        self,
        customer_email: str,
        customer_name: str,
        salon_name: str,
        booking_number: str,
        booking_date: str,
        feedback_url: str,
        booking_id: str
    ) -> bool:
        """
        Send a thank-you email with a review link after service completion.
        """
        try:
            template = self.env.get_template('review_request.html')
            html_body = template.render(
                customer_name=customer_name,
                salon_name=salon_name,
                booking_number=booking_number,
                booking_date=booking_date,
                feedback_url=feedback_url,
                support_email=settings.EMAIL_FROM
            )

            subject = f"Thanks for visiting {salon_name} - Share your feedback"

            return await self._send_email(
                customer_email,
                subject,
                html_body,
                email_type="review_request_customer",
                related_entity_type="booking",
                related_entity_id=booking_id
            )
        except Exception as e:
            logger.error(f"Failed to send review request email: {str(e)}")
            return False


# =====================================================
# GLOBAL INSTANCE
# =====================================================

email_service = EmailService()
