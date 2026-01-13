"""
Email Service
Handles sending emails using SMTP with HTML templates
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from app.core.config import settings
from app.services.email_logger import EmailLogger
from app.services.activity_log_service import ActivityLogService
from app.core.database import get_db
import logging
import asyncio
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


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



class EmailService:
    """Email service for sending templated emails"""
    
    def __init__(self, email_logger: Optional[EmailLogger] = None):
        # Use shared Jinja2 template environment (singleton)
        # This prevents creating new environments on every instantiation
        self.env = _jinja2_env
        # Email logger for tracking sent emails
        self.email_logger = email_logger
        
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
        related_entity_id: Optional[str] = None,
        email_data: Optional[Dict[str, Any]] = None
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
            email_type: Type of email for logging (vendor_approval, booking_confirmation, etc.)
            related_entity_type: Type of related entity (booking, salon, payment, etc.)
            related_entity_id: UUID of related entity
            email_data: Template variables for email (for resending)
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        log_id = None
        
        try:
            # Log email attempt (pending status)
            if self.email_logger:
                log_id = await self.email_logger.log_email_attempt(
                    recipient_email=to_email,
                    email_type=email_type,
                    subject=subject,
                    status="pending",
                    related_entity_type=related_entity_type,
                    related_entity_id=related_entity_id,
                    email_data=email_data,
                    retry_count=0
                )
            
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
            for attempt in range(max_retries + 1):
                try:
                    success = await asyncio.to_thread(self._send_email_sync, msg, to_email, subject)
                    if success:
                        # Update log status to sent
                        if self.email_logger and log_id:
                            await self.email_logger.update_email_status(log_id, "sent")
                        
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
                    
                    # If this wasn't the last attempt, wait before retrying
                    if attempt < max_retries:
                        delay = retry_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(f"Email send failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.1f}s...")
                        await asyncio.sleep(delay)
                        
                except Exception as e:
                    logger.error(f"Email send error (attempt {attempt + 1}/{max_retries + 1}): {str(e)}")
                    
                    # If this wasn't the last attempt, wait before retrying
                    if attempt < max_retries:
                        delay = retry_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(f"Retrying email send in {delay:.1f}s...")
                        await asyncio.sleep(delay)
            
            # All retries exhausted
            logger.error(f"Failed to send email to {to_email} after {max_retries + 1} attempts")
            
            # Update log status to failed
            if self.email_logger and log_id:
                await self.email_logger.update_email_status(
                    log_id, 
                    "failed", 
                    f"Failed after {max_retries + 1} attempts"
                )
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            
            # Update log status to failed
            if self.email_logger and log_id:
                await self.email_logger.update_email_status(log_id, "failed", str(e))
            
            return False
    
    def _send_email_sync(self, msg, to_email: str, subject: str) -> bool:
        """
        Synchronous email sending (called from thread pool)
        """
        try:
            # Send email
            if settings.SMTP_SSL:
                server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)
            else:
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
                if settings.SMTP_TLS:
                    server.starttls()
            
            # Only login if credentials are provided (Mailpit doesn't need auth)
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False
    
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
            logger.info(f"VENDOR APPROVAL EMAIL")
            logger.info(f"To: {to_email}")
            logger.info(f"Subject: Congratulations! {salon_name} has been approved")
            logger.info("-" * 100)
            logger.info(f"REGISTRATION URL:")
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
                related_entity_id=salon_id,
                email_data={
                    "owner_name": owner_name,
                    "salon_name": salon_name,
                    "registration_fee": registration_fee
                }
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
                related_entity_id=salon_id,
                email_data={
                    "rm_name": rm_name,
                    "salon_name": salon_name,
                    "points_awarded": points_awarded,
                    "new_total_score": new_total_score
                }
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
                related_entity_id=request_id,
                email_data={
                    "rm_name": rm_name,
                    "salon_name": salon_name,
                    "rejection_reason": rejection_reason
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to send vendor rejection email: {str(e)}")
            return False
    
    async def send_booking_confirmation_email(
        self,
        to_email: str,
        customer_name: str,
        salon_name: str,
        services: list,
        booking_date: str,
        booking_time: str,
        total_amount: float,
        booking_id: str
    ) -> bool:
        """
        Send booking confirmation email
        
        Args:
            to_email: Customer email
            customer_name: Customer name
            salon_name: Salon name
            services: List of service dictionaries with 'name' and 'price' keys
            booking_date: Booking date
            booking_time: Booking time
            total_amount: Total payment amount
            booking_id: Booking ID
            
        Returns:
            bool: Success status
        """
        try:
            template = self.env.get_template('booking_confirmation.html')
            
            # Format services for template
            services_list = []
            for service in services:
                if isinstance(service, dict):
                    services_list.append({
                        'name': service.get('name', 'Unknown Service'),
                        'price': service.get('unit_price', 0)  # Use unit_price from booking service
                    })
                else:
                    # Handle legacy string format
                    services_list.append({
                        'name': str(service),
                        'price': 0
                    })
            
            html_body = template.render(
                customer_name=customer_name,
                salon_name=salon_name,
                services=services_list,
                booking_date=booking_date,
                booking_time=booking_time,
                total_amount=total_amount,
                booking_id=booking_id,
                support_email=settings.EMAIL_FROM,
                current_year=2025
            )
            
            subject = f"Booking Confirmed at {salon_name}"
            
            return await self._send_email(
                to_email, 
                subject, 
                html_body,
                email_type="booking_confirmation",
                related_entity_type="booking",
                related_entity_id=booking_id,
                email_data={
                    "customer_name": customer_name,
                    "salon_name": salon_name,
                    "booking_date": booking_date,
                    "booking_time": booking_time,
                    "services": services_list,
                    "total_amount": total_amount
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to send booking confirmation email: {str(e)}")
            return False
    
    async def send_booking_cancellation_email(
        self,
        to_email: str,
        customer_name: str,
        salon_name: str,
        service_name: str,
        booking_date: str,
        booking_time: str,
        refund_amount: float,
        cancellation_reason: str = None
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
            refund_amount: Refund amount
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
                refund_amount=refund_amount,
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
                related_entity_id=None,  # Would need booking_id passed in
                email_data={
                    "customer_name": customer_name,
                    "salon_name": salon_name,
                    "service_name": service_name,
                    "refund_amount": refund_amount
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to send booking cancellation email: {str(e)}")
            return False
    
    async def send_payment_receipt_email(
        self,
        to_email: str,
        customer_name: str,
        payment_id: str,
        payment_type: str,
        amount: float,
        service_amount: float = None,
        convenience_fee: float = None,
        payment_date: str = None,
        salon_name: str = None
    ) -> bool:
        """
        Send payment receipt email
        
        Args:
            to_email: Customer email
            customer_name: Customer name
            payment_id: Razorpay payment ID
            payment_type: Type of payment (registration/booking)
            amount: Total amount paid
            service_amount: Service amount (for booking)
            convenience_fee: Convenience fee (for booking)
            payment_date: Payment date
            salon_name: Salon name (for vendor registration)
            
        Returns:
            bool: Success status
        """
        try:
            template = self.env.get_template('payment_receipt.html')
            
            html_body = template.render(
                customer_name=customer_name,
                payment_id=payment_id,
                payment_type=payment_type,
                amount=amount,
                service_amount=service_amount,
                convenience_fee=convenience_fee,
                payment_date=payment_date,
                salon_name=salon_name,
                support_email=settings.EMAIL_FROM,
                current_year=2025
            )
            
            subject = f"Payment Receipt - {payment_id}"
            
            return await self._send_email(
                to_email, 
                subject, 
                html_body,
                email_type="payment_receipt",
                related_entity_type="payment",
                related_entity_id=payment_id,
                email_data={
                    "customer_name": customer_name,
                    "payment_type": payment_type,
                    "amount": amount
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to send payment receipt email: {str(e)}")
            return False
    
    async def send_welcome_vendor_email(
        self,
        to_email: str,
        owner_name: str,
        salon_name: str
    ) -> bool:
        """
        Send welcome email to vendor after payment completion
        
        Args:
            to_email: Vendor email
            owner_name: Salon owner name
            salon_name: Salon name
            
        Returns:
            bool: Success status
        """
        try:
            template = self.env.get_template('welcome_vendor.html')
            
            vendor_portal_url = settings.VENDOR_PORTAL_URL
            
            html_body = template.render(
                owner_name=owner_name,
                salon_name=salon_name,
                vendor_portal_url=vendor_portal_url,
                support_email=settings.EMAIL_FROM,
                current_year=2025
            )
            
            subject = f"Welcome to Salon Platform - {salon_name} is now active!"
            
            return await self._send_email(
                to_email, 
                subject, 
                html_body,
                email_type="welcome_vendor",
                related_entity_type="salon",
                related_entity_id=None,  # Would need salon_id passed in
                email_data={
                    "owner_name": owner_name,
                    "salon_name": salon_name
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to send welcome vendor email: {str(e)}")
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
                related_entity_id=None,  # Would need application_id passed in
                email_data={
                    "applicant_name": applicant_name,
                    "position": position,
                    "application_number": application_number
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to send career application confirmation: {str(e)}")
            return False
    
    def send_new_career_application_notification(
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
            
            subject = f" New Career Application - {position}"
            
            return self._send_email(admin_email, subject, html_body)
            
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
        service_price: float
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
            convenience_fee: Online convenience fee paid
            service_price: Service price to be paid at salon
            
        Returns:
            bool: Success status
        """
        try:
            # Simple HTML email (template can be created later)
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #4CAF50;">✅ Booking Confirmed!</h2>
                    <p>Hi {customer_name},</p>
                    <p>Your booking at <strong>{salon_name}</strong> has been confirmed.</p>
                    
                    <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3>Booking Details:</h3>
                        <p><strong>Booking Number:</strong> {booking_number}</p>
                        <p><strong>Date:</strong> {booking_date}</p>
                        <p><strong>Time:</strong> {booking_time}</p>
                        <p><strong>Services:</strong><br>{'<br>'.join([f"• {{s.get('name', 'Service')}} (₹{{s.get('price', 0)}})" for s in services])}</p>
                    </div>
                    
                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3>Payment Details:</h3>
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
                related_entity_id=None,  # Would need booking_id passed in
                email_data={
                    "customer_name": customer_name,
                    "salon_name": salon_name,
                    "booking_number": booking_number,
                    "booking_date": booking_date,
                    "booking_time": booking_time,
                    "total_amount": total_amount,
                    "convenience_fee": convenience_fee,
                    "service_price": service_price
                }
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
        total_amount: float,
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
            total_amount: Total booking amount
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
                        <p><strong>Services:</strong><br>{'<br>'.join([f"• {{s.get('name', 'Service')}} (₹{{s.get('price', 0)}})" for s in services])}</p>
                        <p><strong>Total Amount:</strong> ₹{total_amount:.2f}</p>
                    </div>
                    
                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p><strong>⚠️ Action Required:</strong></p>
                        <p>Please confirm this booking from your vendor dashboard.</p>
                        <p>Customer has already paid the convenience fee online.</p>
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
                related_entity_id=booking_id,
                email_data={
                    "salon_name": salon_name,
                    "customer_name": customer_name,
                    "customer_phone": customer_phone,
                    "booking_number": booking_number,
                    "booking_date": booking_date,
                    "booking_time": booking_time,
                    "total_amount": total_amount
                }
            )
            logger.info(f"New booking notification email sent to vendor {vendor_email} for booking {booking_number}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to send vendor booking notification: {str(e)}")
            return False


# =====================================================
# GLOBAL INSTANCE
# =====================================================

email_service = EmailService()
