"""
Email Service
Handles sending emails using SMTP with HTML templates
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from urllib.parse import urlsplit
from jinja2 import Environment, FileSystemLoader, select_autoescape
from app.core.config import settings
from app.services.activity_log_service import ActivityLogService
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)


# =====================================================
# SMTP BEHAVIOUR
# =====================================================
# smtplib defaults to socket._GLOBAL_DEFAULT_TIMEOUT (i.e. no timeout), so a
# silently-dropped connection to the SMTP host hangs the calling request until
# the OS gives up (minutes). Every SMTP step below is bounded by this instead.
SMTP_TIMEOUT_SECONDS = 15

# Errors that will never succeed on retry — bad credentials, rejected sender or
# recipient. Retrying these just burns time (and can get the sender rate-limited).
PERMANENT_SMTP_ERRORS = (
    smtplib.SMTPAuthenticationError,
    smtplib.SMTPRecipientsRefused,
    smtplib.SMTPSenderRefused,
    smtplib.SMTPNotSupportedError,
)


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


def _format_booking_services_html(services: list) -> str:
    """Format booking services as HTML lines for confirmation emails."""
    lines = []
    for service in services:
        if not isinstance(service, dict):
            lines.append(f"• {service}")
            continue

        name = service.get("name") or service.get("service_name", "Service")
        price = float(service.get("price") or service.get("unit_price") or 0)
        quantity = int(service.get("quantity") or 1)

        if quantity > 1:
            lines.append(f"• {name} (x{quantity}) — ₹{price:.2f} each")
        else:
            lines.append(f"• {name} — ₹{price:.2f}")

    return "<br>".join(lines) if lines else "• Service"


class EmailService:
    """Email service for sending templated emails"""
    
    def __init__(self):
        # Use shared Jinja2 template environment (singleton)
        # This prevents creating new environments on every instantiation
        self.env = _jinja2_env

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
        Send email via SMTP with retry logic (async)

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
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
            msg['To'] = to_email
            
            # Add text body if provided
            if text_body:
                text_part = MIMEText(text_body, 'plain')
                msg.attach(text_part)
            
            # Add HTML body
            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)
            
            # Send email with retry logic
            last_error = "unknown error"
            for attempt in range(max_retries + 1):
                success, error, permanent = await asyncio.to_thread(
                    self._send_email_sync, msg, to_email, subject
                )

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

    def _send_email_sync(self, msg, to_email: str, subject: str) -> tuple:
        """
        Synchronous email sending (called from thread pool).

        Returns:
            (success, error_message, is_permanent) - is_permanent means retrying
            the same message will fail the same way (auth / rejected address).

        ⚠️ TODO: BLOCKING I/O IN ASYNC CONTEXT - Fix when traffic grows
        
        CURRENT ISSUE:
        - Using smtplib (synchronous) with asyncio.to_thread() causes blocking I/O
        - Each email blocks a thread pool worker for 1-5 seconds
        - Default thread pool = 32 threads max
        - 100 concurrent emails = 68 emails queued and waiting
        
        WHY IT'S OK FOR NOW:
        - Low traffic (<10 emails/minute) works fine with current approach
        - Thread pool sufficient for current load
        
        WHEN TO FIX:
        - Traffic exceeds 50+ emails/minute
        - Noticeable email delivery delays
        - Thread pool exhaustion warnings in logs
        
        HOW TO FIX:
        1. Migrate to aiosmtplib for true async email:
           async def _send_email_async(self, msg, to_email):
               async with aiosmtplib.SMTP(hostname=settings.SMTP_HOST, port=settings.SMTP_PORT) as smtp:
                   await smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                   await smtp.send_message(msg)
        
        2. Or implement Celery/Redis task queue for production scalability
        
        RESOURCES:
        - aiosmtplib docs: https://aiosmtplib.readthedocs.io/
        - Current blocking location: Lines 186-192 (SMTP connection & send)
        """
        server = None
        try:
            # Send email
            if settings.SMTP_SSL:
                server = smtplib.SMTP_SSL(
                    settings.SMTP_HOST, settings.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS
                )
            else:
                server = smtplib.SMTP(
                    settings.SMTP_HOST, settings.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS
                )
                if settings.SMTP_TLS:
                    server.starttls()

            # Only login if credentials are provided (Mailpit doesn't need auth)
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

            server.send_message(msg)

            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True, None, False

        except PERMANENT_SMTP_ERRORS as e:
            # Log the SMTP host/port/user in use — the usual cause is a rotated or
            # revoked app password, and the message alone doesn't say which account.
            logger.error(
                f"Permanent SMTP failure sending to {to_email} via "
                f"{settings.SMTP_HOST}:{settings.SMTP_PORT} as '{settings.SMTP_USER}': "
                f"{type(e).__name__}: {e}"
            )
            return False, f"{type(e).__name__}: {e}", True

        except Exception as e:
            logger.error(
                f"Failed to send email to {to_email} via "
                f"{settings.SMTP_HOST}:{settings.SMTP_PORT}: {type(e).__name__}: {e}"
            )
            return False, f"{type(e).__name__}: {e}", False


        finally:
            # Always close connection to prevent memory leaks
            if server:
                try:
                    server.quit()
                except Exception as e:
                    logger.warning(f"Error closing SMTP connection: {str(e)}")
    
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
            template = self.env.get_template('vendor_approval.html')
            
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
            
            html_body = template.render(
                owner_name=owner_name,
                salon_name=salon_name,
                registration_url=registration_url,
                registration_fee=registration_fee,
                support_email=settings.EMAIL_FROM,
                current_year=2025
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
            template = self.env.get_template('rm_salon_approved.html')
            
            html_body = template.render(
                rm_name=rm_name,
                salon_name=salon_name,
                owner_name=owner_name,
                owner_email=owner_email,
                points_awarded=points_awarded,
                new_total_score=new_total_score,
                registration_fee=registration_fee,
                support_email=settings.EMAIL_FROM,
                current_year=2025
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
            template = self.env.get_template('vendor_rejection.html')
            
            html_body = template.render(
                rm_name=rm_name,
                salon_name=salon_name,
                owner_name=owner_name,
                rejection_reason=rejection_reason,
                support_email=settings.EMAIL_FROM,
                current_year=2025
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
            template = self.env.get_template('booking_cancellation.html')
            
            html_body = template.render(
                customer_name=customer_name,
                salon_name=salon_name,
                service_name=service_name,
                booking_date=booking_date,
                booking_time=booking_time,
                cancellation_reason=cancellation_reason,
                support_email=settings.EMAIL_FROM,
                current_year=2025
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
            reason_block = ""
            if cancellation_reason:
                reason_block = f"""
                    <p><strong>Cancellation Reason:</strong> {cancellation_reason}</p>
                """

            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #ff6b6b;">Booking Cancelled</h2>
                    <p>Hi {salon_name} Team,</p>
                    <p>A customer has cancelled their booking. The appointment slot is now available again.</p>

                    <div style="background: #fff5f5; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ff6b6b;">
                        <h3 style="margin-top: 0;">Cancelled Booking Details</h3>
                        <p><strong>Booking Number:</strong> {booking_number}</p>
                        <p><strong>Customer:</strong> {customer_name}</p>
                        <p><strong>Phone:</strong> {customer_phone}</p>
                        <p><strong>Date:</strong> {booking_date}</p>
                        <p><strong>Time:</strong> {booking_time}</p>
                        <p><strong>Services:</strong><br>{_format_booking_services_html(services)}</p>
                        {reason_block}
                    </div>

                    <p style="text-align: center; margin-top: 30px;">
                        <a href="{settings.VENDOR_PORTAL_URL}/bookings"
                           style="background: #2196F3; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            View in Dashboard
                        </a>
                    </p>

                    <p style="color: #666; font-size: 14px; margin-top: 30px;">
                        This is an automated notification from Lubist.
                    </p>
                </div>
            </body>
            </html>
            """

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
            template = self.env.get_template('payment_reminder.html')
            
            # Vendor login URL (normalize VENDOR_PORTAL_URL to the correct login path)
            vendor_portal_url = settings.VENDOR_PORTAL_URL.strip()
            parsed = urlsplit(vendor_portal_url if vendor_portal_url.startswith(('http://', 'https://')) else f"https://{vendor_portal_url}")
            portal_path = parsed.path.rstrip('/')

            if portal_path.endswith('/vendor-login'):
                vendor_login_url = vendor_portal_url.rstrip('/')
            elif portal_path.endswith('/vendor') or portal_path == '':
                base = parsed.netloc if not vendor_portal_url.startswith(('http://', 'https://')) else f"{parsed.scheme}://{parsed.netloc}"
                vendor_login_url = f"{base}/vendor-login"
            else:
                vendor_login_url = f"{vendor_portal_url.rstrip('/')}/vendor-login"
            
            # Log reminder
            logger.info("=" * 100)
            logger.info("PAYMENT REMINDER EMAIL")
            logger.info(f"To: {to_email}")
            logger.info(f"Salon: {salon_name}")
            logger.info(f"Amount: Rs. {registration_fee}")
            logger.info("=" * 100)
            
            html_body = template.render(
                salon_name=salon_name,
                vendor_login_url=vendor_login_url,
                registration_fee=registration_fee,
                support_email=settings.EMAIL_FROM,
                current_year=2025
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
            template = self.env.get_template('career_application_confirmation.html')
            
            from datetime import datetime
            current_date = datetime.now().strftime("%B %d, %Y")
            
            html_body = template.render(
                applicant_name=applicant_name,
                position=position,
                application_number=application_number,
                current_date=current_date,
                support_email=settings.EMAIL_FROM,
                current_year=2025
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
            template = self.env.get_template('new_career_application_admin.html')
            
            from datetime import datetime
            current_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")
            
            # Admin email from settings
            admin_email = settings.ADMIN_EMAIL
            
            html_body = template.render(
                applicant_name=applicant_name,
                position=position,
                email=email,
                phone=phone,
                experience_years=experience_years,
                application_id=application_id,
                current_date=current_date,
                admin_panel_url=settings.ADMIN_PANEL_URL,
                current_year=2025,
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
        coupon_code: Optional[str] = None
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

        Returns:
            bool: Success status
        """
        try:
            # Build the discount lines only when a coupon was actually applied.
            total_savings = (discount_amount or 0) + (convenience_fee_discount or 0)
            discount_rows = ""
            if coupon_code and total_savings > 0:
                pre_discount_service = (
                    subtotal_service_price
                    if subtotal_service_price is not None
                    else service_price + (discount_amount or 0)
                )
                fee_before = convenience_fee + (convenience_fee_discount or 0)
                discount_rows = f"""
                        <p style="margin:4px 0;color:#666;">Service Total: <span style="text-decoration:line-through;">₹{pre_discount_service:.2f}</span></p>"""
                if discount_amount and discount_amount > 0:
                    discount_rows += f"""
                        <p style="margin:4px 0;color:#2e7d32;">Service Discount: −₹{discount_amount:.2f}</p>"""
                if convenience_fee_discount and convenience_fee_discount > 0:
                    discount_rows += f"""
                        <p style="margin:4px 0;color:#666;">Convenience Fee: <span style="text-decoration:line-through;">₹{fee_before:.2f}</span></p>
                        <p style="margin:4px 0;color:#2e7d32;">Fee Discount: −₹{convenience_fee_discount:.2f}</p>"""

            coupon_badge = ""
            if coupon_code and total_savings > 0:
                coupon_badge = f"""
                    <div style="background:#e8f5e9;border:1px solid #a5d6a7;color:#2e7d32;padding:10px 14px;border-radius:6px;margin:16px 0;font-weight:bold;">
                        🎉 Coupon <strong>{coupon_code}</strong> applied — you saved ₹{total_savings:.2f}!
                    </div>"""

            # Simple HTML email (template can be created later)
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #4CAF50;">✅ Booking Confirmed!</h2>
                    <p>Hi {customer_name},</p>
                    <p>Your booking at <strong>{salon_name}</strong> has been confirmed.</p>
                    {coupon_badge}
                    <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3>Booking Details:</h3>
                        <p><strong>Booking Number:</strong> {booking_number}</p>
                        <p><strong>Date:</strong> {booking_date}</p>
                        <p><strong>Time:</strong> {booking_time}</p>
                        <p><strong>Services:</strong><br>{_format_booking_services_html(services)}</p>
                    </div>

                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3>Payment Details:</h3>
                        {discount_rows}
                        <p><strong>Convenience Fee (Paid Online):</strong> ₹{convenience_fee:.2f}</p>
                        <p><strong>Service Amount (Pay at Salon):</strong> ₹{service_price:.2f}</p>
                        <p><strong>Total Amount:</strong> ₹{total_amount:.2f}</p>
                    </div>

                    <p style="color: #666; font-size: 14px;">
                        Please arrive 5 minutes before your appointment time.
                        Remember to pay the service amount (₹{service_price:.2f}) at the salon after your service.
                    </p>

                    <p>See you soon!<br><strong>Lubist Team</strong></p>
                </div>
            </body>
            </html>
            """
            
            subject = f"Booking Confirmed - {salon_name} ({booking_number})"
            
            result = await self._send_email(
                customer_email, 
                subject, 
                html_body,
                email_type="booking_confirmation_customer",
                related_entity_type="booking",
                related_entity_id=None  # Would need booking_id passed in
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
            # Simple HTML email (template can be created later)
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2196F3;"> New Booking Received!</h2>
                    <p>Hi {salon_name} Team,</p>
                    <p>You have received a new booking. Please check your dashboard for details.</p>
                    
                    <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3>Booking Details:</h3>
                        <p><strong>Booking Number:</strong> {booking_number}</p>
                        <p><strong>Customer:</strong> {customer_name}</p>
                        <p><strong>Phone:</strong> {customer_phone}</p>
                        <p><strong>Date:</strong> {booking_date}</p>
                        <p><strong>Time:</strong> {booking_time}</p>
                        <p><strong>Services:</strong><br>{_format_booking_services_html(services)}</p>
                    </div>

                    <div style="background: #e8f5e9; padding: 15px; border-radius: 5px; margin: 20px 0; border: 1px solid #c8e6c9;">
                        <h3 style="margin-top: 0; color: #2e7d32;">Amount to Collect at Salon</h3>
                        <p style="margin-bottom: 0; font-size: 18px; font-weight: bold; color: #2e7d32;">
                            ₹{service_price:.2f}
                        </p>
                    </div>
                    
                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p><strong>⚠️ Action Required:</strong></p>
                        <p>Please confirm this booking from your vendor dashboard.</p>
                        <p>Collect <strong>₹{service_price:.2f}</strong> from the customer at the salon after service.</p>
                    </div>
                    
                    <p style="text-align: center; margin-top: 30px;">
                        <a href="{settings.VENDOR_PORTAL_URL}/bookings" 
                           style="background: #2196F3; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            View in Dashboard
                        </a>
                    </p>
                    
                    <p style="color: #666; font-size: 14px; margin-top: 30px;">
                        This is an automated notification from Lubist.
                    </p>
                </div>
            </body>
            </html>
            """
            
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
