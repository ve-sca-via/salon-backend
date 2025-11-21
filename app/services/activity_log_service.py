"""
Activity Log Service - Track critical admin actions and system events
Simple implementation for audit trail on dashboard
"""
import logging
from typing import Optional, Dict, Any, List
from app.core.database import get_db

logger = logging.getLogger(__name__)


class ActivityLogService:
    """Service for logging and retrieving user/system activities"""
    
    @staticmethod
    async def log(
        user_id: Optional[str],
        action: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Log an activity/action
        
        Args:
            user_id: ID of user performing action (None for system actions)
            action: Action identifier (e.g., 'salon_approved', 'payment_confirmed')
            entity_type: Type of entity affected (e.g., 'salon', 'booking', 'user')
            entity_id: ID of affected entity
            details: Additional metadata as JSON
            ip_address: IP address of user (optional)
            
        Returns:
            bool: True if logged successfully
        """
        try:
            db = get_db()
            
            log_data = {
                "user_id": user_id,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "details": details,
                "ip_address": ip_address
            }
            
            logger.info(f"📝 Attempting to log activity: {action} by {user_id or 'system'}, entity: {entity_type}/{entity_id}")
            response = db.table("activity_logs").insert(log_data).execute()
            logger.info(f"✅ Activity logged successfully: {action} (response: {len(response.data) if response.data else 0} rows)")
            return True
            
        except Exception as e:
            # Don't fail the main operation if logging fails
            logger.error(f"❌ Failed to log activity '{action}': {type(e).__name__}: {str(e)}")
            logger.error(f"   Data attempted: user_id={user_id}, entity={entity_type}/{entity_id}")
            return False
    
    @staticmethod
    async def get_recent(limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent activity logs
        
        Args:
            limit: Number of recent logs to fetch
            
        Returns:
            List of activity log entries with user details
        """
        try:
            db = get_db()
            
            # Join with profiles to get user names
            response = db.table("activity_logs").select(
                "*, profiles(full_name, email)"
            ).order("created_at", desc=True).limit(limit).execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"Failed to fetch activity logs: {str(e)}")
            return []
    
    @staticmethod
    async def get_by_entity(
        entity_type: str,
        entity_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get activity logs for a specific entity (e.g., all actions on a salon)
        
        Args:
            entity_type: Type of entity
            entity_id: ID of entity
            limit: Max number of logs
            
        Returns:
            List of activity logs
        """
        try:
            db = get_db()
            
            response = db.table("activity_logs").select(
                "*, profiles(full_name, email)"
            ).eq("entity_type", entity_type).eq(
                "entity_id", entity_id
            ).order("created_at", desc=True).limit(limit).execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"Failed to fetch entity activity logs: {str(e)}")
            return []


# Convenience functions for common actions
class ActivityLogger:
    """High-level helper for logging specific actions"""
    
    @staticmethod
    async def salon_approved(user_id: str, salon_id: str, salon_name: str):
        """Log salon approval"""
        await ActivityLogService.log(
            user_id=user_id,
            action="salon_approved",
            entity_type="salon",
            entity_id=salon_id,
            details={"salon_name": salon_name}
        )
    
    @staticmethod
    async def salon_rejected(user_id: str, salon_id: str, salon_name: str, reason: str):
        """Log salon rejection"""
        await ActivityLogService.log(
            user_id=user_id,
            action="salon_rejected",
            entity_type="salon",
            entity_id=salon_id,
            details={"salon_name": salon_name, "reason": reason}
        )
    
    @staticmethod
    async def payment_confirmed(user_id: Optional[str], payment_id: str, amount: float, salon_id: str):
        """Log payment confirmation"""
        await ActivityLogService.log(
            user_id=user_id,
            action="payment_confirmed",
            entity_type="payment",
            entity_id=payment_id,
            details={"amount": amount, "salon_id": salon_id}
        )
    
    @staticmethod
    async def user_created(admin_id: str, new_user_id: str, role: str, email: str):
        """Log user creation"""
        await ActivityLogService.log(
            user_id=admin_id,
            action="user_created",
            entity_type="user",
            entity_id=new_user_id,
            details={"role": role, "email": email}
        )
    
    @staticmethod
    async def config_updated(user_id: str, config_key: str, old_value: Any, new_value: Any):
        """Log config changes"""
        await ActivityLogService.log(
            user_id=user_id,
            action="config_updated",
            entity_type="config",
            entity_id=config_key,
            details={"old_value": old_value, "new_value": new_value}
        )
    
    @staticmethod
    async def rm_assigned(admin_id: str, salon_id: str, rm_id: str, salon_name: str, rm_name: str):
        """Log RM assignment to salon"""
        await ActivityLogService.log(
            user_id=admin_id,
            action="rm_assigned",
            entity_type="salon",
            entity_id=salon_id,
            details={"salon_name": salon_name, "rm_id": rm_id, "rm_name": rm_name}
        )
