"""
Email Logging Service
Tracks all email sending attempts in database for audit trail and retry mechanism
"""
from supabase import Client
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging
import json

logger = logging.getLogger(__name__)


class EmailLogger:
    """Service for logging email sending attempts to database"""
    
    def __init__(self, db: Client):
        self.db = db
    
    async def log_email_attempt(
        self,
        recipient_email: str,
        email_type: str,
        subject: str,
        status: str,
        error_message: Optional[str] = None,
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[str] = None,
        email_data: Optional[Dict[str, Any]] = None,
        retry_count: int = 0
    ) -> Optional[str]:
        """
        Log an email sending attempt to database
        
        Args:
            recipient_email: Email address of recipient
            email_type: Type of email (vendor_approval, booking_confirmation, etc.)
            subject: Email subject line
            status: 'sent', 'failed', or 'pending'
            error_message: Error message if failed
            related_entity_type: Type of related entity (booking, salon, payment, etc.)
            related_entity_id: UUID of related entity
            email_data: Template variables used for email (for resending)
            retry_count: Number of retry attempts
            
        Returns:
            UUID of created email log entry, or None if failed
        """
        try:
            log_data = {
                "recipient_email": recipient_email,
                "email_type": email_type,
                "subject": subject,
                "status": status,
                "error_message": error_message,
                "related_entity_type": related_entity_type,
                "related_entity_id": related_entity_id,
                "email_data": json.dumps(email_data) if email_data else None,
                "retry_count": retry_count,
                "sent_at": datetime.utcnow().isoformat() if status == "sent" else None
            }
            
            # Calculate next retry time if failed
            if status == "failed" and retry_count < 3:
                # Exponential backoff: 5min, 15min, 60min
                retry_delays = [5, 15, 60]
                delay_minutes = retry_delays[min(retry_count, len(retry_delays) - 1)]
                next_retry = datetime.utcnow() + timedelta(minutes=delay_minutes)
                log_data["next_retry_at"] = next_retry.isoformat()
            
            response = self.db.table("email_logs").insert(log_data).execute()
            
            if response.data:
                log_id = response.data[0].get("id")
                logger.info(f"📧 Email log created: {log_id} ({email_type} to {recipient_email}) - Status: {status}")
                return log_id
            else:
                logger.error(f"Failed to create email log: No data returned")
                return None
                
        except Exception as e:
            logger.error(f"Failed to log email attempt: {str(e)}")
            return None
    
    async def update_email_status(
        self,
        log_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Update status of an existing email log entry
        
        Args:
            log_id: UUID of email log entry
            status: New status ('sent', 'failed', 'pending')
            error_message: Error message if failed
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            update_data = {
                "status": status,
                "error_message": error_message
            }
            
            if status == "sent":
                update_data["sent_at"] = datetime.utcnow().isoformat()
            
            response = self.db.table("email_logs")\
                .update(update_data)\
                .eq("id", log_id)\
                .execute()
            
            if response.data:
                logger.info(f"📧 Email log updated: {log_id} - Status: {status}")
                return True
            else:
                logger.error(f"Failed to update email log {log_id}: No data returned")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update email log {log_id}: {str(e)}")
            return False
    
    async def increment_retry_count(self, log_id: str) -> bool:
        """
        Increment retry count for a failed email
        
        Args:
            log_id: UUID of email log entry
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            # Get current retry count
            response = self.db.table("email_logs")\
                .select("retry_count")\
                .eq("id", log_id)\
                .single()\
                .execute()
            
            if not response.data:
                logger.error(f"Email log {log_id} not found")
                return False
            
            current_retry = response.data.get("retry_count", 0)
            new_retry = current_retry + 1
            
            # Calculate next retry time
            retry_delays = [5, 15, 60]  # minutes
            delay_minutes = retry_delays[min(new_retry, len(retry_delays) - 1)]
            next_retry = datetime.utcnow() + timedelta(minutes=delay_minutes)
            
            # Update retry count and next retry time
            update_response = self.db.table("email_logs")\
                .update({
                    "retry_count": new_retry,
                    "next_retry_at": next_retry.isoformat()
                })\
                .eq("id", log_id)\
                .execute()
            
            if update_response.data:
                logger.info(f"📧 Email log retry count incremented: {log_id} - Retry #{new_retry}")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Failed to increment retry count for {log_id}: {str(e)}")
            return False
    
    async def get_failed_emails_for_retry(self) -> list:
        """
        Get all failed emails that are ready for retry
        
        Returns:
            List of email log entries ready for retry
        """
        try:
            now = datetime.utcnow().isoformat()
            
            response = self.db.table("email_logs")\
                .select("*")\
                .eq("status", "failed")\
                .lt("retry_count", 3)\
                .lte("next_retry_at", now)\
                .execute()
            
            if response.data:
                logger.info(f"📧 Found {len(response.data)} failed emails ready for retry")
                return response.data
            else:
                return []
                
        except Exception as e:
            logger.error(f"Failed to get failed emails for retry: {str(e)}")
            return []
    
    async def get_email_logs_by_entity(
        self,
        entity_type: str,
        entity_id: str
    ) -> list:
        """
        Get all email logs for a specific entity
        
        Args:
            entity_type: Type of entity (booking, salon, payment, etc.)
            entity_id: UUID of entity
            
        Returns:
            List of email log entries
        """
        try:
            response = self.db.table("email_logs")\
                .select("*")\
                .eq("related_entity_type", entity_type)\
                .eq("related_entity_id", entity_id)\
                .order("created_at", desc=True)\
                .execute()
            
            return response.data if response.data else []
                
        except Exception as e:
            logger.error(f"Failed to get email logs for {entity_type}/{entity_id}: {str(e)}")
            return []


def get_email_logger(db: Client) -> EmailLogger:
    """
    Factory function to get email logger instance
    
    Args:
        db: Supabase client instance
        
    Returns:
        EmailLogger instance
    """
    return EmailLogger(db)
