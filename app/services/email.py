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
import logging

logger = logging.getLogger(__name__)


class EmailService:
    """Email service for sending templated emails"""
    
    def __init__(self):
        # Setup Jinja2 template environment
        template_dir = Path(__file__).parent.parent / "templates" / "email"
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(['html', 'xml'])
        )
        
    def _send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str = None
    ) -> bool:
        """
        Send email via SMTP
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body (optional)
            
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
            
            # Send email
            if settings.SMTP_SSL:
                server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)
            else:
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
                if settings.SMTP_TLS:
                    server.starttls()
            
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False
    
    def send_vendor_approval_email(
        self,
        to_email: str,
        owner_name: str,
        salon_name: str,
        registration_token: str,
        registration_fee: float
    ) -> bool:
        """
        Send vendor approval email with registration link
        
        Args:
            to_email: Vendor email
            owner_name: Salon owner name
            salon_name: Salon name
            registration_token: JWT token for registration link
            registration_fee: Amount to pay for registration
            
        Returns:
            bool: Success status
        """
        try:
            template = self.env.get_template('vendor_approval.html')
            
            registration_url = f"{settings.VENDOR_PORTAL_URL}/complete-registration?token={registration_token}"
            
            html_body = template.render(
                owner_name=owner_name,
                salon_name=salon_name,
                registration_url=registration_url,
                registration_fee=registration_fee,
                support_email=settings.EMAIL_FROM,
                current_year=2025
            )
            
            subject = f"🎉 Congratulations! {salon_name} has been approved"
            
            return self._send_email(to_email, subject, html_body)
            
        except Exception as e:
            logger.error(f"Failed to send vendor approval email: {str(e)}")
            return False
    
    def send_vendor_rejection_email(
        self,
        to_email: str,
        owner_name: str,
        salon_name: str,
        rejection_reason: str,
        rm_name: str
    ) -> bool:
        """
        Send vendor rejection email to RM
        
        Args:
            to_email: RM email
            owner_name: Salon owner name
            salon_name: Salon name
            rejection_reason: Admin's rejection reason
            rm_name: RM name
            
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
            
            return self._send_email(to_email, subject, html_body)
            
        except Exception as e:
            logger.error(f"Failed to send vendor rejection email: {str(e)}")
            return False
    
    def send_booking_confirmation_email(
        self,
        to_email: str,
        customer_name: str,
        salon_name: str,
        service_name: str,
        booking_date: str,
        booking_time: str,
        staff_name: str,
        total_amount: float,
        booking_id: str
    ) -> bool:
        """
        Send booking confirmation email
        
        Args:
            to_email: Customer email
            customer_name: Customer name
            salon_name: Salon name
            service_name: Service name
            booking_date: Booking date
            booking_time: Booking time
            staff_name: Staff member name
            total_amount: Total payment amount
            booking_id: Booking ID
            
        Returns:
            bool: Success status
        """
        try:
            template = self.env.get_template('booking_confirmation.html')
            
            html_body = template.render(
                customer_name=customer_name,
                salon_name=salon_name,
                service_name=service_name,
                booking_date=booking_date,
                booking_time=booking_time,
                staff_name=staff_name,
                total_amount=total_amount,
                booking_id=booking_id,
                support_email=settings.EMAIL_FROM,
                current_year=2025
            )
            
            subject = f"✅ Booking Confirmed at {salon_name}"
            
            return self._send_email(to_email, subject, html_body)
            
        except Exception as e:
            logger.error(f"Failed to send booking confirmation email: {str(e)}")
            return False
    
    def send_booking_cancellation_email(
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
            
            return self._send_email(to_email, subject, html_body)
            
        except Exception as e:
            logger.error(f"Failed to send booking cancellation email: {str(e)}")
            return False
    
    def send_payment_receipt_email(
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
            
            return self._send_email(to_email, subject, html_body)
            
        except Exception as e:
            logger.error(f"Failed to send payment receipt email: {str(e)}")
            return False
    
    def send_welcome_vendor_email(
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
            
            subject = f"🎊 Welcome to Salon Platform - {salon_name} is now active!"
            
            return self._send_email(to_email, subject, html_body)
            
        except Exception as e:
            logger.error(f"Failed to send welcome vendor email: {str(e)}")
            return False


# Create singleton instance
email_service = EmailService()
