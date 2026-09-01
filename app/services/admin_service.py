"""
Admin Service
Handles admin-specific operations including dashboard statistics and vendor request management
"""
from typing import List, Optional, Dict, Any
from datetime import date, datetime
import logging

logger = logging.getLogger(__name__)



class DashboardStats:
    """Dashboard statistics data model"""
    def __init__(
        self,
        pending_requests: int = 0,
        total_salons: int = 0,
        active_salons: int = 0,
        pending_payment_salons: int = 0,
        total_rms: int = 0,
        total_bookings: int = 0,
        today_bookings: int = 0,
        total_revenue: float = 0.0,
        this_month_revenue: float = 0.0
    ):
        self.pending_requests = pending_requests
        self.total_salons = total_salons
        self.active_salons = active_salons
        self.pending_payment_salons = pending_payment_salons
        self.total_rms = total_rms
        self.total_bookings = total_bookings
        self.today_bookings = today_bookings
        self.total_revenue = total_revenue
        self.this_month_revenue = this_month_revenue
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "pending_requests": self.pending_requests,
            "total_salons": self.total_salons,
            "active_salons": self.active_salons,
            "pending_payment_salons": self.pending_payment_salons,
            "total_rms": self.total_rms,
            "total_bookings": self.total_bookings,
            "today_bookings": self.today_bookings,
            "total_revenue": self.total_revenue,
            "this_month_revenue": self.this_month_revenue
        }


class AdminService:
    """Service for admin operations"""
    
    def __init__(self, db_client):
        self.db = db_client
    
    # =====================================================
    # DASHBOARD STATISTICS
    # =====================================================
    
    async def get_dashboard_stats(self) -> DashboardStats:
        """
        Get comprehensive admin dashboard statistics
        
        Returns:
            DashboardStats: Complete dashboard statistics
            
        Raises:
            Exception: If database queries fail
        """
        try:
            stats = DashboardStats()
            
            # Count pending vendor requests
            pending_requests_response = self.db.table("vendor_join_requests").select(
                "id", count="exact"
            ).eq("status", "pending").execute()
            stats.pending_requests = pending_requests_response.count if pending_requests_response.count is not None else 0
            
            # Count total salons
            total_salons_response = self.db.table("salons").select(
                "id", count="exact"
            ).execute()
            stats.total_salons = total_salons_response.count if total_salons_response.count is not None else 0
            
            # Count active salons (is_active = true)
            active_salons_response = self.db.table("salons").select(
                "id", count="exact"
            ).eq("is_active", True).execute()
            stats.active_salons = active_salons_response.count if active_salons_response.count is not None else 0
            
            # Count salons with pending payment (registration_fee_paid = false)
            pending_payment_response = self.db.table("salons").select(
                "id", count="exact"
            ).eq("registration_fee_paid", False).execute()
            stats.pending_payment_salons = pending_payment_response.count if pending_payment_response.count is not None else 0
            
            # Count total active RMs from profiles table
            total_rms_response = self.db.table("profiles").select(
                "id", count="exact"
            ).eq("user_role", "relationship_manager").eq("is_active", True).execute()
            stats.total_rms = total_rms_response.count if total_rms_response.count is not None else 0
            
            # Count total bookings
            total_bookings_response = self.db.table("bookings").select(
                "id", count="exact"
            ).execute()
            stats.total_bookings = total_bookings_response.count if total_bookings_response.count is not None else 0
            
            # Count today's bookings
            today = date.today().isoformat()
            today_bookings_response = self.db.table("bookings").select(
                "id", count="exact"
            ).gte("booking_date", today).lte("booking_date", today).execute()
            stats.today_bookings = today_bookings_response.count if today_bookings_response.count is not None else 0
            
            # Calculate revenue
            revenue_stats = await self._calculate_revenue()
            stats.total_revenue = revenue_stats["total"]
            stats.this_month_revenue = revenue_stats["this_month"]
            
            logger.info(f"Dashboard stats calculated: {stats.total_salons} salons, {stats.total_rms} RMs, {stats.total_bookings} bookings")
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to calculate dashboard stats: {str(e)}")
            raise Exception(f"Failed to fetch dashboard stats: {str(e)}")
    
    async def _calculate_revenue(self) -> Dict[str, float]:
        """
        Calculate total and monthly revenue from completed payments.
        
        Sources:
        - 'payments' table: booking convenience fees (status = 'success')
        - 'vendor_registration_payments' table: registration fees (status = 'success')
        
        Returns:
            Dict with 'total' and 'this_month' revenue amounts
        """
        total_revenue = 0.0
        this_month_revenue = 0.0
        
        current_month = datetime.now().month
        current_year = datetime.now().year

        def _add_payments(records):
            nonlocal total_revenue, this_month_revenue
            for payment in records:
                amount = float(payment.get("amount", 0))
                total_revenue += amount
                
                # Check if payment is from current month
                created_at = payment.get("created_at") or payment.get("payment_completed_at")
                if created_at:
                    try:
                        payment_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        if payment_date.month == current_month and payment_date.year == current_year:
                            this_month_revenue += amount
                    except (ValueError, AttributeError):
                        logger.warning(f"Invalid payment date format: {created_at}")
        
        try:
            # 1. Booking convenience fee payments (status = 'success')
            payments_response = self.db.table("payments").select(
                "amount, created_at"
            ).eq("status", "success").execute()
            
            if payments_response.data:
                _add_payments(payments_response.data)
        
        except Exception as rev_error:
            logger.error(f"Failed to calculate booking payments revenue: {str(rev_error)}")

        try:
            # 2. Vendor registration fee payments (status = 'success')
            reg_payments_response = self.db.table("vendor_registration_payments").select(
                "amount, payment_completed_at"
            ).eq("status", "success").execute()
            
            if reg_payments_response.data:
                # Map payment_completed_at -> created_at for uniform processing
                for p in reg_payments_response.data:
                    p["created_at"] = p.get("payment_completed_at")
                _add_payments(reg_payments_response.data)

        except Exception as reg_error:
            logger.error(f"Failed to calculate registration payments revenue: {str(reg_error)}")
        
        logger.info(f"Revenue calculated: total={total_revenue}, this_month={this_month_revenue}")
        return {
            "total": total_revenue,
            "this_month": this_month_revenue
        }
    
    # =====================================================
    # VENDOR REQUEST MANAGEMENT
    # =====================================================
    
    async def get_vendor_requests(
        self,
        status_filter: Optional[str] = "pending",
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get vendor join requests with RM profile enrichment
        
        Args:
            status_filter: Filter by status (pending, approved, rejected)
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of vendor requests with enriched RM profile data
            
        Raises:
            Exception: If database queries fail
        """
        try:
            # Fetch vendor requests
            query = self.db.table("vendor_join_requests").select("*")

            if status_filter:
                query = query.eq("status", status_filter)

            response = query.order("created_at", desc=True).range(
                offset, offset + limit
            ).execute()
            requests = response.data or []

            # Batch-fetch RM profiles for all requests in one query, then map by id
            rm_ids = list({r["rm_id"] for r in requests if r.get("rm_id")})
            rm_map: Dict[str, Any] = {}
            if rm_ids:
                rm_response = self.db.table("rm_profiles").select(
                    "*, profiles(id, full_name, email, phone, is_active, avatar_url)"
                ).in_("id", rm_ids).execute()
                rm_map = {rm["id"]: rm for rm in (rm_response.data or [])}

            for request in requests:
                request["rm_profile"] = rm_map.get(request.get("rm_id"))

            logger.info(f"Retrieved {len(requests)} vendor requests (status: {status_filter})")

            return requests

        except Exception as e:
            logger.error(f"Failed to fetch vendor requests: {str(e)}")
            raise Exception(f"Failed to fetch vendor requests: {str(e)}")
