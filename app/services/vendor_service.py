"""
Vendor Service - Business Logic Layer
Handles vendor salon management, services CRUD, staff management
"""
import logging
from typing import Dict, Any, Optional, List
from fastapi import HTTPException, status

from app.core.database import get_db
from app.core.auth import (
    verify_registration_token,
    create_access_token,
    create_refresh_token
)
from app.schemas import (
    ServiceCreate,
    ServiceUpdate,
    SalonUpdate,
    SalonStaffCreate,
    SalonStaffUpdate
)
from app.services.activity_log_service import ActivityLogService

logger = logging.getLogger(__name__)


class VendorService:
    """
    Service class for vendor operations.
    Handles salon management, services CRUD, staff, and bookings.
    """
    
    def __init__(self, db_client):
        """Initialize service with database client"""
        self.db = db_client
    
    # =====================================================
    # SALON OPERATIONS
    # =====================================================
    
    async def get_vendor_salon(self, vendor_id: str) -> Dict[str, Any]:
        """
        Get salon details for a vendor.
        
        Args:
            vendor_id: Vendor user ID
            
        Returns:
            Salon data
            
        Raises:
            HTTPException: If salon not found
        """
        response = self.db.table("salons").select("*").eq("vendor_id", vendor_id).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        return response.data
    
    async def update_vendor_salon(
        self,
        vendor_id: str,
        update: SalonUpdate
    ) -> Dict[str, Any]:
        """
        Update vendor's salon details.
        
        Args:
            vendor_id: Vendor user ID
            update: Salon update data
            
        Returns:
            Updated salon data
            
        Raises:
            HTTPException: If salon not found or update fails
        """
        try:
            # Verify salon exists
            await self.get_vendor_salon(vendor_id)
            
            # Update salon
            update_data = update.model_dump(exclude_unset=True)
            
            response = self.db.table("salons").update(update_data).eq("vendor_id", vendor_id).execute()
            
            logger.info(f"Vendor {vendor_id} updated salon: {list(update_data.keys())}")
            
            return response.data[0] if response.data else None
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update salon for vendor {vendor_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update salon"
            )
    
    async def get_vendor_salon_id(self, vendor_id: str) -> int:
        """
        Get salon ID for a vendor.
        
        Args:
            vendor_id: Vendor user ID
            
        Returns:
            Salon ID
            
        Raises:
            HTTPException: If salon not found
        """
        response = self.db.table("salons").select("id").eq("vendor_id", vendor_id).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found. Please create a salon first."
            )
        
        return response.data["id"]
    
    # =====================================================
    # SERVICE OPERATIONS
    # =====================================================
    
    async def get_services(self, vendor_id: str) -> List[Dict[str, Any]]:
        """
        Get all services for vendor's salon.
        
        Args:
            vendor_id: Vendor user ID
            
        Returns:
            List of services with category details
            
        Raises:
            HTTPException: If salon not found or query fails
        """
        try:
            # Get salon ID
            salon_id = await self.get_vendor_salon_id(vendor_id)
            
            # Get services with category details
            response = self.db.table("services").select(
                "*, service_categories(*)"
            ).eq("salon_id", salon_id).order("created_at", desc=True).execute()
            
            return response.data or []
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch services for vendor {vendor_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch services"
            )
    
    async def create_service(
        self,
        vendor_id: str,
        service: ServiceCreate
    ) -> Dict[str, Any]:
        """
        Create new service for vendor's salon.
        
        Args:
            vendor_id: Vendor user ID
            service: Service creation data
            
        Returns:
            Created service data
            
        Raises:
            HTTPException: If validation fails or creation fails
        """
        try:
            # Get salon ID and verify vendor owns a salon
            salon_id = await self.get_vendor_salon_id(vendor_id)
            
            # Validate category_id if provided
            if service.category_id:
                await self._validate_service_category(service.category_id)
            
            # Create service with auto-assigned salon_id
            service_data = service.model_dump(exclude={'salon_id'})  # Exclude client-provided salon_id
            service_data['salon_id'] = salon_id  # Auto-assign from authenticated vendor
            
            response = self.db.table("services").insert(service_data).execute()
            
            created_service = response.data[0] if response.data else None
            
            logger.info(
                f"Vendor {vendor_id} created service: {service.name} "
                f"(category: {service.category_id or 'none'})"
            )
            
            return created_service
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create service for vendor {vendor_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create service"
            )
    
    async def update_service(
        self,
        vendor_id: str,
        service_id: str,
        update: ServiceUpdate
    ) -> Dict[str, Any]:
        """
        Update existing service.
        
        Args:
            vendor_id: Vendor user ID
            service_id: Service ID to update
            update: Service update data
            
        Returns:
            Updated service data
            
        Raises:
            HTTPException: If service not found, access denied, or update fails
        """
        try:
            # Get salon ID
            salon_id = await self.get_vendor_salon_id(vendor_id)
            
            # Verify service belongs to vendor's salon
            await self._verify_service_ownership(service_id, salon_id)
            
            # Validate category_id if being updated
            if update.category_id is not None:
                await self._validate_service_category(update.category_id)
            
            # Prepare update data
            update_data = update.model_dump(exclude_unset=True)
            
            if not update_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No fields provided for update"
                )
            
            # Update service
            response = self.db.table("services").update(update_data).eq("id", service_id).execute()
            
            updated_service = response.data[0] if response.data else None
            
            logger.info(
                f"Vendor {vendor_id} updated service {service_id}: "
                f"{list(update_data.keys())}"
            )
            
            return updated_service
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update service {service_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update service"
            )
    
    async def delete_service(
        self,
        vendor_id: str,
        service_id: str
    ) -> Dict[str, Any]:
        """
        Delete service.
        
        Args:
            vendor_id: Vendor user ID
            service_id: Service ID to delete
            
        Returns:
            Success response
            
        Raises:
            HTTPException: If service not found, access denied, or deletion fails
        """
        try:
            # Get salon ID
            salon_id = await self.get_vendor_salon_id(vendor_id)
            
            # Verify service belongs to vendor's salon
            await self._verify_service_ownership(service_id, salon_id)
            
            # Delete service
            self.db.table("services").delete().eq("id", service_id).execute()
            
            logger.info(f"Vendor {vendor_id} deleted service {service_id}")
            
            return {
                "success": True,
                "message": "Service deleted successfully"
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete service {service_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete service"
            )
    
    # =====================================================
    # STAFF OPERATIONS
    # =====================================================
    
    async def get_staff(self, vendor_id: str) -> List[Dict[str, Any]]:
        """
        Get all staff for vendor's salon.
        
        Args:
            vendor_id: Vendor user ID
            
        Returns:
            List of staff members
            
        Raises:
            HTTPException: If salon not found or query fails
        """
        try:
            # Get salon ID
            salon_id = await self.get_vendor_salon_id(vendor_id)
            
            # Get staff
            response = self.db.table("salon_staff").select("*").eq(
                "salon_id", salon_id
            ).order("created_at", desc=True).execute()
            
            return response.data or []
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch staff for vendor {vendor_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch staff"
            )
    
    async def create_staff(
        self,
        vendor_id: str,
        staff: SalonStaffCreate
    ) -> Dict[str, Any]:
        """
        Add new staff member to vendor's salon.
        
        Args:
            vendor_id: Vendor user ID
            staff: Staff creation data
            
        Returns:
            Created staff data
            
        Raises:
            HTTPException: If validation fails or creation fails
        """
        try:
            # Get salon ID and verify ownership
            salon_id = await self.get_vendor_salon_id(vendor_id)
            
            # Verify staff is for own salon (security check)
            if staff.salon_id != salon_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot add staff to other salons"
                )
            
            # Create staff
            staff_data = staff.model_dump()
            
            response = self.db.table("salon_staff").insert(staff_data).execute()
            
            created_staff = response.data[0] if response.data else None
            
            logger.info(f"Vendor {vendor_id} added staff: {staff.full_name}")
            
            return created_staff
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create staff for vendor {vendor_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create staff"
            )
    
    async def update_staff(
        self,
        vendor_id: str,
        staff_id: str,
        update: SalonStaffUpdate
    ) -> Dict[str, Any]:
        """
        Update staff member.
        
        Args:
            vendor_id: Vendor user ID
            staff_id: Staff ID to update
            update: Staff update data
            
        Returns:
            Updated staff data
            
        Raises:
            HTTPException: If staff not found, access denied, or update fails
        """
        try:
            # Get salon ID
            salon_id = await self.get_vendor_salon_id(vendor_id)
            
            # Verify staff belongs to vendor's salon
            await self._verify_staff_ownership(staff_id, salon_id)
            
            # Update staff
            update_data = update.model_dump(exclude_unset=True)
            
            response = self.db.table("salon_staff").update(update_data).eq("id", staff_id).execute()
            
            updated_staff = response.data[0] if response.data else None
            
            logger.info(f"Vendor {vendor_id} updated staff {staff_id}")
            
            return updated_staff
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update staff {staff_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update staff"
            )
    
    async def delete_staff(
        self,
        vendor_id: str,
        staff_id: str
    ) -> Dict[str, Any]:
        """
        Delete staff member.
        
        Args:
            vendor_id: Vendor user ID
            staff_id: Staff ID to delete
            
        Returns:
            Success response
            
        Raises:
            HTTPException: If staff not found, access denied, or deletion fails
        """
        try:
            # Get salon ID
            salon_id = await self.get_vendor_salon_id(vendor_id)
            
            # Verify staff belongs to vendor's salon
            await self._verify_staff_ownership(staff_id, salon_id)
            
            # Delete staff
            self.db.table("salon_staff").delete().eq("id", staff_id).execute()
            
            logger.info(f"Vendor {vendor_id} deleted staff {staff_id}")
            
            return {
                "success": True,
                "message": "Staff deleted successfully"
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete staff {staff_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete staff"
            )
    
    # =====================================================
    # BOOKING OPERATIONS
    # =====================================================
    
    async def get_salon_bookings(
        self,
        vendor_id: str,
        status_filter: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get all bookings for vendor's salon.
        
        Args:
            vendor_id: Vendor user ID
            status_filter: Filter by booking status
            date_from: Filter bookings from this date
            date_to: Filter bookings to this date
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of bookings with related data
            
        Raises:
            HTTPException: If salon not found or query fails
        """
        try:
            # Get salon ID
            salon_id = await self.get_vendor_salon_id(vendor_id)
            
            # Build query - Note: customer details are denormalized in bookings table
            # (customer_name, customer_phone, customer_email columns)
            query = self.db.table("bookings").select(
                "*, services(*)"
            ).eq("salon_id", salon_id)
            
            if status_filter:
                query = query.eq("status", status_filter)
            
            if date_from:
                query = query.gte("booking_date", date_from)
            
            if date_to:
                query = query.lte("booking_date", date_to)
            
            response = query.order("booking_date", desc=True).order(
                "booking_time", desc=True
            ).range(offset, offset + limit - 1).execute()
            
            return response.data or []
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch bookings for vendor {vendor_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch bookings"
            )
    
    async def update_booking_status(
        self,
        vendor_id: str,
        booking_id: str,
        new_status: str
    ) -> Dict[str, Any]:
        """
        Update booking status.
        
        Args:
            vendor_id: Vendor user ID
            booking_id: Booking ID to update
            new_status: New status (confirmed, completed, no_show)
            
        Returns:
            Success response with updated booking
            
        Raises:
            HTTPException: If booking not found, access denied, or invalid status
        """
        try:
            # Validate status
            valid_statuses = ["confirmed", "completed", "no_show"]
            if new_status not in valid_statuses:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status. Must be one of: {valid_statuses}"
                )
            
            # Get salon ID
            salon_id = await self.get_vendor_salon_id(vendor_id)
            
            # Verify booking belongs to vendor's salon
            await self._verify_booking_ownership(booking_id, salon_id)
            
            # Update status
            update_data = {"status": new_status}
            
            if new_status == "confirmed":
                update_data["confirmed_at"] = "now()"
            elif new_status == "completed":
                update_data["completed_at"] = "now()"
            
            response = self.db.table("bookings").update(update_data).eq("id", booking_id).execute()
            
            logger.info(f"Vendor {vendor_id} updated booking {booking_id} status to {new_status}")
            
            return {
                "success": True,
                "message": f"Booking status updated to {new_status}",
                "data": response.data[0] if response.data else None
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update booking status: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update booking status"
            )
    
    # =====================================================
    # DASHBOARD & ANALYTICS
    # =====================================================
    
    async def get_dashboard_stats(self, vendor_id: str) -> Dict[str, Any]:
        """
        Get vendor dashboard statistics.
        
        Args:
            vendor_id: Vendor user ID
            
        Returns:
            Dashboard data with salon info and statistics
            
        Raises:
            HTTPException: If salon not found or query fails
        """
        try:
            # Get salon
            salon = await self.get_vendor_salon(vendor_id)
            salon_id = salon["id"]
            
            # Get counts
            total_services = self.db.table("services").select("id", count="exact").eq("salon_id", salon_id).execute()
            total_staff = self.db.table("salon_staff").select("id", count="exact").eq("salon_id", salon_id).execute()
            total_bookings = self.db.table("bookings").select("id", count="exact").eq("salon_id", salon_id).execute()
            pending_bookings = self.db.table("bookings").select("id", count="exact").eq("salon_id", salon_id).eq("status", "pending").execute()
            
            # Today's bookings
            today_bookings = self.db.table("bookings").select("id", count="exact").eq("salon_id", salon_id).gte("booking_date", "today").execute()
            
            return {
                "salon": salon,
                "statistics": {
                    "total_services": total_services.count if total_services else 0,
                    "total_staff": total_staff.count if total_staff else 0,
                    "total_bookings": total_bookings.count if total_bookings else 0,
                    "pending_bookings": pending_bookings.count if pending_bookings else 0,
                    "today_bookings": today_bookings.count if today_bookings else 0,
                    "average_rating": salon.get("average_rating", 0),
                    "total_reviews": salon.get("total_reviews", 0)
                }
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch dashboard stats: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch vendor dashboard"
            )
    
    async def get_analytics(self, vendor_id: str) -> Dict[str, Any]:
        """
        Get vendor analytics for dashboard.
        
        Args:
            vendor_id: Vendor user ID
            
        Returns:
            Analytics data (bookings, revenue, ratings)
            
        Raises:
            HTTPException: If salon not found or query fails
        """
        try:
            # Get salon
            salon = await self.get_vendor_salon(vendor_id)
            salon_id = salon["id"]
            
            # Get counts
            services_response = self.db.table("services").select("id", count="exact").eq("salon_id", salon_id).eq("is_active", True).execute()
            staff_response = self.db.table("salon_staff").select("id", count="exact").eq("salon_id", salon_id).eq("is_active", True).execute()
            bookings_response = self.db.table("bookings").select("id, total_amount", count="exact").eq("salon_id", salon_id).execute()
            pending_response = self.db.table("bookings").select("id", count="exact").eq("salon_id", salon_id).eq("status", "pending").execute()
            
            # Calculate total revenue from completed bookings
            completed_bookings = self.db.table("bookings").select("total_amount").eq("salon_id", salon_id).eq("status", "completed").execute()
            total_revenue = sum([b.get("total_amount", 0) for b in completed_bookings.data]) if completed_bookings.data else 0
            
            return {
                "total_bookings": bookings_response.count if bookings_response else 0,
                "total_revenue": total_revenue,
                "active_services": services_response.count if services_response else 0,
                "total_staff": staff_response.count if staff_response else 0,
                "average_rating": salon.get("average_rating", 0.0),
                "pending_bookings": pending_response.count if pending_response else 0
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch analytics: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch vendor analytics"
            )
    
    # =====================================================
    # HELPER METHODS
    # =====================================================
    
    async def _validate_service_category(self, category_id: str) -> None:
        """
        Validate that category_id exists.
        
        Args:
            category_id: Category UUID to validate
            
        Raises:
            HTTPException: If category not found
        """
        category_check = self.db.table("service_categories").select("id").eq(
            "id", category_id
        ).execute()
        
        if not category_check.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category_id: {category_id}"
            )
    
    async def _verify_service_ownership(self, service_id: str, salon_id: int) -> None:
        """
        Verify that service belongs to the vendor's salon.
        
        Args:
            service_id: Service ID to verify
            salon_id: Vendor's salon ID
            
        Raises:
            HTTPException: If service not found or doesn't belong to salon
        """
        service_check = self.db.table("services").select("salon_id").eq("id", service_id).single().execute()
        
        if not service_check.data or service_check.data["salon_id"] != salon_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found or access denied"
            )
    
    async def _verify_staff_ownership(self, staff_id: str, salon_id: int) -> None:
        """
        Verify that staff belongs to the vendor's salon.
        
        Args:
            staff_id: Staff ID to verify
            salon_id: Vendor's salon ID
            
        Raises:
            HTTPException: If staff not found or doesn't belong to salon
        """
        staff_check = self.db.table("salon_staff").select("salon_id").eq("id", staff_id).single().execute()
        
        if not staff_check.data or staff_check.data["salon_id"] != salon_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Staff not found or access denied"
            )
    
    async def _verify_booking_ownership(self, booking_id: str, salon_id: int) -> None:
        """
        Verify that booking belongs to the vendor's salon.
        
        Args:
            booking_id: Booking ID to verify
            salon_id: Vendor's salon ID
            
        Raises:
            HTTPException: If booking not found or doesn't belong to salon
        """
        booking_check = self.db.table("bookings").select("salon_id, status").eq("id", booking_id).single().execute()
        
        if not booking_check.data or booking_check.data["salon_id"] != salon_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found or access denied"
            )
    
    # =====================================================
    # VENDOR REGISTRATION & PAYMENT
    # =====================================================
    
    async def create_vendor_profile(
        self,
        user_id: str,
        email: str,
        full_name: str
    ) -> Dict[str, Any]:
        """
        Create vendor profile in profiles table.
        
        Args:
            user_id: User ID from Supabase auth
            email: Vendor email
            full_name: Vendor full name
            
        Returns:
            Created profile data
        """
        profile_data = {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "user_role": "vendor",
            "is_active": True
        }
        
        response = self.db.table("profiles").insert(profile_data).execute()
        
        logger.info(f"✅ Vendor profile created for {email}")
        
        return response.data[0] if response.data else profile_data
    
    async def link_vendor_to_salon(
        self,
        user_id: str,
        salon_id: str
    ) -> Dict[str, Any]:
        """
        Link vendor to salon and auto-verify the salon.
        
        Args:
            user_id: Vendor user ID
            salon_id: Salon ID to link
            
        Returns:
            Updated salon data
        """
        update_data = {
            "vendor_id": user_id,
            "is_verified": True
        }
        
        response = self.db.table("salons").update(update_data).eq("id", salon_id).execute()
        
        logger.info(f"🔗 Vendor {user_id} linked to salon {salon_id}")
        logger.info(f"✅ Salon automatically verified upon vendor registration")
        
        return response.data[0] if response.data else update_data
    
    async def process_vendor_payment(
        self,
        vendor_id: str
    ) -> Dict[str, Any]:
        """
        Process vendor payment and activate salon.
        In production, this would integrate with actual payment gateway.
        
        Args:
            vendor_id: Vendor user ID
            
        Returns:
            Payment status details
            
        Raises:
            HTTPException: If salon not found
        """
        from datetime import datetime
        
        # Get vendor's salon
        salon = await self.get_vendor_salon(vendor_id)
        salon_id = salon["id"]
        business_name = salon.get("business_name", "Salon")
        
        logger.info(f"💳 Processing payment for vendor: {vendor_id}, salon: {business_name}")
        
        # Prepare payment data (match actual schema - no subscription fields in salons table)
        payment_data = {
            "registration_fee_paid": True,
            "is_active": True,  # Activate salon after successful payment
            "is_verified": True
        }
        
        # Update salon with payment info
        response = self.db.table("salons").update(payment_data).eq("id", salon_id).execute()
        
        logger.info(f"✅ Payment processed successfully for salon: {business_name}")
        
        return {
            "payment_status": "success",
            "payment_amount": 5000.00,
            "salon_name": business_name,
            "salon_id": salon_id
        }
    
    async def complete_registration(
        self,
        token: str,
        full_name: str,
        password: str,
        confirm_password: str
    ) -> Dict[str, Any]:
        """
        Complete vendor registration after admin approval.
        
        Args:
            token: JWT registration token
            full_name: Vendor's full name
            password: Password for the account
            confirm_password: Password confirmation
            
        Returns:
            Registration completion data with tokens
            
        Raises:
            HTTPException: If registration fails
        """
        logger.info("🔍 Starting vendor registration completion...")
        
        # Verify JWT registration token
        token_data = verify_registration_token(token)
        salon_id = token_data["salon_id"]
        request_id = token_data["request_id"]
        vendor_email = token_data["email"]
        
        logger.info(f"✅ Token verified for {vendor_email}, salon_id: {salon_id}")
        
        # Use full_name from registration request (provided by vendor)
        vendor_full_name = full_name.strip()
        
        logger.info(f"📝 Vendor name: {vendor_full_name}")
        
        if password != confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )
        
        logger.info(f"🔐 Creating db auth user for {vendor_email}...")
        
        # Create db auth user using admin API
        auth_user_created = False
        try:
            auth_response = self.db.auth.admin.create_user({
                "email": vendor_email,
                "password": password,
                "email_confirm": True,  # Auto-confirm email
                "user_metadata": {
                    "role": "vendor",
                    "full_name": vendor_full_name
                }
            })
            auth_user_created = True
            logger.info("✅ Auth user created successfully")
        except Exception as auth_error:
            logger.error(f"❌ Auth user creation failed: {str(auth_error)}")
            # Try alternative approach: sign up the user
            logger.info("🔄 Attempting alternative signup method...")
            try:
                auth_response = self.db.auth.sign_up({
                    "email": vendor_email,
                    "password": password,
                    "options": {
                        "data": {
                            "role": "vendor",
                            "full_name": vendor_full_name
                        }
                    }
                })
                auth_user_created = True
                logger.info("✅ User signed up successfully")
            except Exception as signup_error:
                logger.error(f"❌ User signup also failed: {str(signup_error)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create user account"
                )
        
        # Extract user ID from response
        if hasattr(auth_response, 'user') and auth_response.user:
            user_id = auth_response.user.id
        elif isinstance(auth_response, dict) and 'user' in auth_response:
            user_id = auth_response['user']['id']
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user account"
            )
        
        logger.info(f"👤 User ID: {user_id}")
        
        # Create vendor profile using service
        try:
            await self.create_vendor_profile(
                user_id=user_id,
                email=vendor_email,
                full_name=vendor_full_name
            )
            logger.info("✅ Vendor profile created successfully")
        except Exception as profile_error:
            logger.error(f"❌ Vendor profile creation failed: {str(profile_error)}")
            # Cleanup: Delete the auth user if profile creation failed
            if auth_user_created:
                try:
                    self.db.auth.admin.delete_user(user_id)
                    logger.info("🧹 Cleaned up auth user after profile creation failure")
                except Exception as cleanup_error:
                    logger.error(f"❌ Failed to cleanup auth user: {str(cleanup_error)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create vendor profile"
            )
        
        # Link vendor to salon and auto-verify using service
        try:
            await self.link_vendor_to_salon(
                user_id=user_id,
                salon_id=salon_id
            )
            logger.info("✅ Vendor linked to salon successfully")
        except Exception as link_error:
            logger.error(f"❌ Vendor-salon linking failed: {str(link_error)}")
            # Cleanup: Delete the auth user and profile if linking failed
            if auth_user_created:
                try:
                    self.db.auth.admin.delete_user(user_id)
                    logger.info("🧹 Cleaned up auth user after salon linking failure")
                except Exception as cleanup_error:
                    logger.error(f"❌ Failed to cleanup auth user: {str(cleanup_error)}")
            # Try to delete vendor profile as well
            try:
                self.db.table("vendors").delete().eq("user_id", user_id).execute()
                logger.info("🧹 Cleaned up vendor profile after salon linking failure")
            except Exception as cleanup_error:
                logger.error(f"❌ Failed to cleanup vendor profile: {str(cleanup_error)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to link vendor to salon"
            )
        
        # Generate access and refresh tokens
        token_data = {
            "sub": user_id,
            "email": vendor_email,
            "user_role": "vendor"
        }
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        logger.info(f"🎉 Vendor registration completed successfully for {vendor_email}")
        
        # Log activity for vendor registration completion
        try:
            await ActivityLogService.log(
                user_id=user_id,
                action="vendor_registration_completed",
                entity_type="vendor",
                entity_id=user_id,
                details={
                    "email": vendor_email,
                    "full_name": vendor_full_name,
                    "salon_id": salon_id,
                    "request_id": request_id
                }
            )
        except Exception as log_error:
            logger.warning(f"Failed to log vendor registration activity: {log_error}")
        
        return {
            "success": True,
            "message": "Registration completed successfully!",
            "data": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": {
                    "id": user_id,
                    "email": vendor_email,
                    "full_name": vendor_full_name,
                    "role": "vendor"
                }
            }
        }
    
    async def get_service_categories(self) -> List[Dict[str, Any]]:
        """
        Get all active service categories.
        
        Returns:
            List of service categories ordered by display_order
        """
        response = self.db.table("service_categories").select(
            "*"
        ).eq("is_active", True).order("display_order").execute()
        
        categories = response.data or []
        
        logger.info(f"📋 Retrieved {len(categories)} service categories")
        
        return categories
