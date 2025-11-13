"""
Admin Service
Handles admin-specific operations including dashboard statistics and vendor request management
"""
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

# Get database client using factory function
db = get_db()


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
    
    def __init__(self):
        self.db = db
    
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
            
            # Count total active RMs
            total_rms_response = self.db.table("rm_profiles").select(
                "id", count="exact"
            ).eq("is_active", True).execute()
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
        Calculate total and monthly revenue from completed payments
        
        Returns:
            Dict with 'total' and 'this_month' revenue amounts
        """
        total_revenue = 0.0
        this_month_revenue = 0.0
        
        try:
            # Get all completed payments with amount
            payments_response = self.db.table("payments").select(
                "amount, created_at"
            ).eq("status", "completed").execute()
            
            if payments_response.data:
                current_month = datetime.now().month
                current_year = datetime.now().year
                
                for payment in payments_response.data:
                    amount = float(payment.get("amount", 0))
                    total_revenue += amount
                    
                    # Check if payment is from current month
                    created_at = payment.get("created_at")
                    if created_at:
                        try:
                            payment_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            if payment_date.month == current_month and payment_date.year == current_year:
                                this_month_revenue += amount
                        except (ValueError, AttributeError) as date_error:
                            logger.warning(f"Invalid payment date format: {created_at}")
                            continue
        
        except Exception as rev_error:
            logger.error(f"Failed to calculate revenue: {str(rev_error)}")
            # Return 0 values on error
        
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
                offset, offset + limit - 1
            ).execute()
            
            # Enrich with RM profile data
            enriched_requests = []
            for request in response.data:
                enriched_request = await self._enrich_vendor_request_with_rm_profile(request)
                enriched_requests.append(enriched_request)
            
            logger.info(f"Retrieved {len(enriched_requests)} vendor requests (status: {status_filter})")
            
            return enriched_requests
            
        except Exception as e:
            logger.error(f"Failed to fetch vendor requests: {str(e)}")
            raise Exception(f"Failed to fetch vendor requests: {str(e)}")
    
    async def get_vendor_request(self, request_id: str) -> Dict[str, Any]:
        """
        Get single vendor request with RM profile information
        
        Args:
            request_id: The vendor request ID
            
        Returns:
            Vendor request data with RM profile
            
        Raises:
            ValueError: If request not found
            Exception: If database query fails
        """
        try:
            # Attempt to use Supabase's relationship join syntax
            response = self.db.table("vendor_join_requests").select(
                "*, rm_profiles(*, profiles(*))"
            ).eq("id", request_id).single().execute()
            
            if not response.data:
                raise ValueError(f"Vendor request not found: {request_id}")
            
            logger.info(f"Retrieved vendor request: {request_id}")
            
            return response.data
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch vendor request {request_id}: {str(e)}")
            raise Exception(f"Failed to fetch vendor request: {str(e)}")
    
    async def _enrich_vendor_request_with_rm_profile(
        self,
        request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enrich a vendor request with RM profile data
        
        Args:
            request: The vendor request dictionary
            
        Returns:
            Request with rm_profile field added
        """
        rm_id = request.get('rm_id')
        
        if not rm_id:
            request['rm_profile'] = None
            return request
        
        try:
            # Fetch RM profile
            rm_response = self.db.table("rm_profiles").select("*").eq("id", rm_id).execute()
            
            if rm_response.data and len(rm_response.data) > 0:
                rm_data = rm_response.data[0]
                
                # Fetch user profile
                profile_response = self.db.table("profiles").select("*").eq("id", rm_id).execute()
                profile_data = profile_response.data[0] if profile_response.data else None
                
                # Combine data - use 'profiles' (plural) to match frontend expectation
                request['rm_profile'] = {
                    **rm_data,
                    'profiles': profile_data
                }
            else:
                request['rm_profile'] = None
                
        except Exception as e:
            logger.error(f"Failed to fetch RM profile for {rm_id}: {str(e)}")
            request['rm_profile'] = None
        
        return request
    
    # =====================================================
    # ANALYTICS & REPORTING
    # =====================================================
    
    async def get_system_health(self) -> Dict[str, Any]:
        """
        Get system health metrics
        
        Returns:
            Dictionary with system health indicators
        """
        try:
            stats = await self.get_dashboard_stats()
            
            # Calculate health metrics
            salon_activation_rate = (
                (stats.active_salons / stats.total_salons * 100)
                if stats.total_salons > 0 else 0
            )
            
            payment_completion_rate = (
                ((stats.total_salons - stats.pending_payment_salons) / stats.total_salons * 100)
                if stats.total_salons > 0 else 0
            )
            
            avg_bookings_per_salon = (
                stats.total_bookings / stats.active_salons
                if stats.active_salons > 0 else 0
            )
            
            return {
                "salon_activation_rate": round(salon_activation_rate, 2),
                "payment_completion_rate": round(payment_completion_rate, 2),
                "avg_bookings_per_salon": round(avg_bookings_per_salon, 2),
                "pending_requests": stats.pending_requests,
                "active_rms": stats.total_rms,
                "today_bookings": stats.today_bookings
            }
            
        except Exception as e:
            logger.error(f"Failed to calculate system health: {str(e)}")
            raise Exception(f"Failed to calculate system health: {str(e)}")
    
    async def get_revenue_breakdown(self) -> Dict[str, Any]:
        """
        Get detailed revenue breakdown
        
        Returns:
            Dictionary with revenue metrics
        """
        try:
            revenue = await self._calculate_revenue()
            
            # Calculate growth rate (simplified - would need historical data)
            monthly_avg = revenue["total"] / 12 if revenue["total"] > 0 else 0
            
            return {
                "total_revenue": revenue["total"],
                "this_month_revenue": revenue["this_month"],
                "monthly_average": round(monthly_avg, 2),
                "currency": "INR"  # Adjust based on your settings
            }
            
        except Exception as e:
            logger.error(f"Failed to calculate revenue breakdown: {str(e)}")
            raise Exception(f"Failed to calculate revenue breakdown: {str(e)}")
    
    # =====================================================
    # SERVICES MANAGEMENT
    # =====================================================
    
    async def get_all_services(self) -> List[Dict[str, Any]]:
        """
        Get all services ordered by name
        
        Returns:
            List of all services
            
        Raises:
            Exception: If query fails
        """
        try:
            response = self.db.table("services").select("*").order("name").execute()
            
            logger.info(f"✅ Fetched {len(response.data)} services")
            return response.data
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch services: {str(e)}")
            raise Exception(f"Failed to fetch services: {str(e)}")
    
    async def create_service(self, service_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create new service
        
        Args:
            service_data: Service data to insert
            
        Returns:
            Created service data
            
        Raises:
            Exception: If creation fails
        """
        try:
            response = self.db.table("services").insert(service_data).execute()
            
            if not response.data:
                raise Exception("No data returned from insert")
            
            logger.info(f"✅ Created service: {service_data.get('name', 'Unknown')}")
            return response.data[0]
            
        except Exception as e:
            logger.error(f"❌ Failed to create service: {str(e)}")
            raise Exception(f"Failed to create service: {str(e)}")
    
    async def update_service(self, service_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update service by ID
        
        Args:
            service_id: Service ID to update
            updates: Fields to update
            
        Returns:
            Updated service data
            
        Raises:
            Exception: If service not found or update fails
        """
        try:
            response = self.db.table("services").update(updates).eq("id", service_id).execute()
            
            if not response.data:
                raise Exception(f"Service not found: {service_id}")
            
            logger.info(f"✅ Updated service: {service_id}")
            return response.data[0]
            
        except Exception as e:
            logger.error(f"❌ Failed to update service {service_id}: {str(e)}")
            raise Exception(f"Failed to update service: {str(e)}")
    
    async def delete_service(self, service_id: str) -> bool:
        """
        Delete service by ID
        
        Args:
            service_id: Service ID to delete
            
        Returns:
            True if successful
            
        Raises:
            Exception: If deletion fails
        """
        try:
            response = self.db.table("services").delete().eq("id", service_id).execute()
            
            logger.info(f"✅ Deleted service: {service_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to delete service {service_id}: {str(e)}")
            raise Exception(f"Failed to delete service: {str(e)}")
    
    # =====================================================
    # STAFF MANAGEMENT
    # =====================================================
    
    async def get_all_staff(self) -> List[Dict[str, Any]]:
        """
        Get all staff members ordered by full name
        
        Returns:
            List of all staff profiles
            
        Raises:
            Exception: If query fails
        """
        try:
            response = self.db.table("profiles").select("*").eq("role", "staff").order("full_name").execute()
            
            logger.info(f"✅ Fetched {len(response.data)} staff members")
            return response.data
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch staff: {str(e)}")
            raise Exception(f"Failed to fetch staff: {str(e)}")
    
    async def update_staff(self, staff_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update staff member by ID
        
        Args:
            staff_id: Staff profile ID to update
            updates: Fields to update
            
        Returns:
            Updated staff profile data
            
        Raises:
            Exception: If staff not found or update fails
        """
        try:
            response = self.db.table("profiles").update(updates).eq("id", staff_id).eq("role", "staff").execute()
            
            if not response.data:
                raise Exception(f"Staff member not found: {staff_id}")
            
            logger.info(f"✅ Updated staff: {staff_id}")
            return response.data[0]
            
        except Exception as e:
            logger.error(f"❌ Failed to update staff {staff_id}: {str(e)}")
            raise Exception(f"Failed to update staff: {str(e)}")
    
    async def delete_staff(self, staff_id: str) -> Dict[str, Any]:
        """
        Delete (soft delete) staff member by ID
        
        Sets is_active to False instead of hard delete
        
        Args:
            staff_id: Staff profile ID to delete
            
        Returns:
            Updated staff profile data
            
        Raises:
            Exception: If staff not found or deletion fails
        """
        try:
            response = self.db.table("profiles").update({
                "is_active": False
            }).eq("id", staff_id).eq("role", "staff").execute()
            
            if not response.data:
                raise Exception(f"Staff member not found: {staff_id}")
            
            logger.info(f"✅ Soft deleted staff: {staff_id}")
            return response.data[0]
            
        except Exception as e:
            logger.error(f"❌ Failed to delete staff {staff_id}: {str(e)}")
            raise Exception(f"Failed to delete staff: {str(e)}")
