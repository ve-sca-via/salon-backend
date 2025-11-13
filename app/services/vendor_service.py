"""
Vendor Service - Business Logic Layer
Handles vendor salon management, services CRUD, staff management
"""
import logging
from typing import Dict, Any, Optional, List
from fastapi import HTTPException, status

from app.core.database import get_db
from app.schemas import (
    ServiceCreate,
    ServiceUpdate,
    SalonUpdate,
    SalonStaffCreate,
    SalonStaffUpdate
)

logger = logging.getLogger(__name__)

# Get database client using factory function
db = get_db()


class VendorService:
    """
    Service class for vendor operations.
    Handles salon management, services CRUD, staff, and bookings.
    """
    
    def __init__(self):
        """Initialize service - uses centralized db client"""
        pass
    
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
        response = db.table("salons").select("*").eq("vendor_id", vendor_id).single().execute()
        
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
            
            response = db.table("salons").update(update_data).eq("vendor_id", vendor_id).execute()
            
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
        response = db.table("salons").select("id").eq("vendor_id", vendor_id).single().execute()
        
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
            response = db.table("services").select(
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
            
            response = db.table("services").insert(service_data).execute()
            
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
            response = db.table("services").update(update_data).eq("id", service_id).execute()
            
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
            db.table("services").delete().eq("id", service_id).execute()
            
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
            response = db.table("salon_staff").select("*").eq(
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
            
            response = db.table("salon_staff").insert(staff_data).execute()
            
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
            
            response = db.table("salon_staff").update(update_data).eq("id", staff_id).execute()
            
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
            db.table("salon_staff").delete().eq("id", staff_id).execute()
            
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
            
            # Build query
            query = db.table("bookings").select(
                "*, services(*), salon_staff(*), profiles(*)"
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
            
            response = db.table("bookings").update(update_data).eq("id", booking_id).execute()
            
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
            total_services = db.table("services").select("id", count="exact").eq("salon_id", salon_id).execute()
            total_staff = db.table("salon_staff").select("id", count="exact").eq("salon_id", salon_id).execute()
            total_bookings = db.table("bookings").select("id", count="exact").eq("salon_id", salon_id).execute()
            pending_bookings = db.table("bookings").select("id", count="exact").eq("salon_id", salon_id).eq("status", "pending").execute()
            
            # Today's bookings
            today_bookings = db.table("bookings").select("id", count="exact").eq("salon_id", salon_id).gte("booking_date", "today").execute()
            
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
            services_response = db.table("services").select("id", count="exact").eq("salon_id", salon_id).eq("is_active", True).execute()
            staff_response = db.table("salon_staff").select("id", count="exact").eq("salon_id", salon_id).eq("is_active", True).execute()
            bookings_response = db.table("bookings").select("id, total_amount", count="exact").eq("salon_id", salon_id).execute()
            pending_response = db.table("bookings").select("id", count="exact").eq("salon_id", salon_id).eq("status", "pending").execute()
            
            # Calculate total revenue from completed bookings
            completed_bookings = db.table("bookings").select("total_amount").eq("salon_id", salon_id).eq("status", "completed").execute()
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
        category_check = db.table("service_categories").select("id").eq(
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
        service_check = db.table("services").select("salon_id").eq("id", service_id).single().execute()
        
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
        staff_check = db.table("salon_staff").select("salon_id").eq("id", staff_id).single().execute()
        
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
        booking_check = db.table("bookings").select("salon_id, status").eq("id", booking_id).single().execute()
        
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
            "role": "vendor",
            "is_active": True,
            "email_verified": True
        }
        
        response = db.table("profiles").insert(profile_data).execute()
        
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
        
        response = db.table("salons").update(update_data).eq("id", salon_id).execute()
        
        logger.info(f"🔗 Vendor {user_id} linked to salon {salon_id}")
        logger.info(f"✅ Salon automatically verified upon vendor registration")
        
        return response.data[0] if response.data else update_data
    
    async def process_vendor_payment(
        self,
        vendor_id: str
    ) -> Dict[str, Any]:
        """
        Process vendor payment and activate salon (DEMO MODE).
        In production, this would integrate with actual payment gateway.
        
        Args:
            vendor_id: Vendor user ID
            
        Returns:
            Payment and subscription details
            
        Raises:
            HTTPException: If salon not found
        """
        from datetime import datetime, timedelta
        
        # Get vendor's salon
        salon = await self.get_vendor_salon(vendor_id)
        salon_id = salon["id"]
        business_name = salon.get("business_name", "Salon")
        
        logger.info(f"💳 Processing payment for vendor: {vendor_id}, salon: {business_name}")
        
        # Prepare payment data
        payment_data = {
            "subscription_status": "active",
            "subscription_start_date": datetime.utcnow().isoformat(),
            "subscription_end_date": (datetime.utcnow() + timedelta(days=365)).isoformat(),  # 1 year
            "payment_amount": 5000.00,
            "payment_date": datetime.utcnow().isoformat(),
            "registration_fee_paid": True,
            "registration_paid_at": datetime.utcnow().isoformat(),
            "is_active": True  # Activate salon after successful payment
        }
        
        # Update salon with payment info
        response = db.table("salons").update(payment_data).eq("id", salon_id).execute()
        
        logger.info(f"✅ Payment processed successfully for salon: {business_name}")
        logger.info(f"📅 Subscription active until: {payment_data['subscription_end_date']}")
        
        return {
            "subscription_status": "active",
            "subscription_start_date": payment_data["subscription_start_date"],
            "subscription_end_date": payment_data["subscription_end_date"],
            "payment_amount": payment_data["payment_amount"],
            "salon_name": business_name
        }
    
    async def get_service_categories(self) -> List[Dict[str, Any]]:
        """
        Get all active service categories.
        
        Returns:
            List of service categories ordered by display_order
        """
        response = db.table("service_categories").select(
            "*"
        ).eq("is_active", True).order("display_order").execute()
        
        categories = response.data or []
        
        logger.info(f"📋 Retrieved {len(categories)} service categories")
        
        return categories
