"""
Booking Service - Business Logic Layer
Handles booking CRUD, cancellations, completions, and email notifications
"""
import logging
import json
import random
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import HTTPException, status

from app.core.database import get_db
from app.schemas import BookingCreate, BookingUpdate
from app.services.email import email_service

logger = logging.getLogger(__name__)

# Get database client using factory function
db = get_db()


class BookingService:
    """
    Service class for booking operations.
    Handles booking lifecycle, validations, and notifications.
    """
    
    def __init__(self):
        """Initialize service - uses centralized db client"""
        pass
    
    # =====================================================
    # BOOKING RETRIEVAL
    # =====================================================
    
    async def get_bookings(
        self,
        user_id: Optional[str] = None,
        salon_id: Optional[int] = None,
        current_user_id: str = None,
        current_user_role: str = None
    ) -> Dict[str, Any]:
        """
        Get bookings filtered by user or salon.
        
        Args:
            user_id: Filter by customer user ID
            salon_id: Filter by salon ID
            current_user_id: Current authenticated user ID
            current_user_role: Current user role (admin, vendor, customer)
            
        Returns:
            Dict with bookings list and count
            
        Raises:
            HTTPException: If authorization fails or invalid parameters
        """
        try:
            if user_id:
                # Verify user can access these bookings
                if current_user_role not in ["admin"] and current_user_id != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Cannot access other users' bookings"
                    )
                
                response = db.table("bookings").select("*").eq(
                    "customer_id", user_id
                ).order("booking_date", desc=True).execute()
                
            elif salon_id:
                # Verify salon access
                if current_user_role == "vendor":
                    await self._verify_salon_ownership(salon_id, current_user_id)
                elif current_user_role not in ["admin"]:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Insufficient permissions to view salon bookings"
                    )
                
                response = db.table("bookings").select("*").eq(
                    "salon_id", salon_id
                ).order("booking_date", desc=True).execute()
                
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Must provide user_id or salon_id"
                )
            
            bookings = response.data or []
            
            return {
                "bookings": bookings,
                "count": len(bookings)
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch bookings: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch bookings"
            )
    
    async def get_booking(
        self,
        booking_id: str,
        current_user_id: str,
        current_user_role: str
    ) -> Dict[str, Any]:
        """
        Get single booking by ID.
        
        Args:
            booking_id: Booking ID
            current_user_id: Current authenticated user ID
            current_user_role: Current user role
            
        Returns:
            Booking data with related info
            
        Raises:
            HTTPException: If not found or access denied
        """
        try:
            response = db.table("bookings").select(
                "*, services(*), salon_staff(*), profiles(*)"
            ).eq("id", booking_id).single().execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found"
                )
            
            booking = response.data
            
            # Verify access
            await self._verify_booking_access(booking, current_user_id, current_user_role)
            
            return booking
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch booking: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch booking"
            )
    
    # =====================================================
    # BOOKING CREATION
    # =====================================================
    
    async def create_booking(
        self,
        booking: BookingCreate,
        current_user_id: str
    ) -> Dict[str, Any]:
        """
        Create new booking with all validations and email notification.
        
        Args:
            booking: Booking creation data
            current_user_id: Customer user ID
            
        Returns:
            Created booking data
            
        Raises:
            HTTPException: If validation fails or creation fails
        """
        try:
            # Get customer details
            customer_data = await self._get_customer_profile(current_user_id)
            
            # Get salon details
            salon_data = await self._get_salon_details(booking.salon_id)
            
            # Calculate totals
            totals = self._calculate_booking_totals(booking)
            
            # Parse and format booking time
            db_time = self._parse_booking_time(booking.booking_time)
            
            # Generate unique booking number
            booking_number = self._generate_booking_number()
            
            # Prepare metadata
            metadata = self._build_booking_metadata(
                booking=booking,
                totals=totals,
                salon_name=salon_data["business_name"]
            )
            
            # Get first service ID for schema compatibility
            first_service_id = booking.services[0].get("service_id") if booking.services else None
            
            # Prepare database data
            db_booking_data = {
                "booking_number": booking_number,
                "customer_id": current_user_id,
                "salon_id": booking.salon_id,
                "service_id": first_service_id,
                "booking_date": booking.booking_date,
                "booking_time": db_time,
                "duration_minutes": totals["total_duration"],
                "status": "confirmed" if booking.payment_status == "paid" else "pending",
                "service_price": totals["service_price"],
                "convenience_fee": booking.booking_fee or 0,
                "total_amount": totals["final_amount"],
                "customer_name": customer_data["full_name"],
                "customer_phone": customer_data["phone"],
                "customer_email": customer_data["email"],
                "special_requests": json.dumps(metadata)
            }
            
            # Create booking
            response = db.table("bookings").insert(db_booking_data).execute()
            created_booking = response.data[0] if response.data else None
            
            if not created_booking:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create booking"
                )
            
            # Enhance response with metadata
            created_booking = self._enhance_booking_with_metadata(created_booking)
            
            # Send confirmation email
            await self._send_booking_confirmation(
                customer_email=customer_data["email"],
                customer_name=customer_data["full_name"],
                salon_name=salon_data["business_name"],
                booking=booking,
                totals=totals,
                booking_id=created_booking.get("id", "N/A")
            )
            
            logger.info(f"Booking created: {booking_number} for customer {current_user_id}")
            
            return created_booking
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create booking: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create booking: {str(e)}"
            )
    
    # =====================================================
    # BOOKING UPDATES
    # =====================================================
    
    async def update_booking(
        self,
        booking_id: str,
        updates: BookingUpdate,
        current_user_id: str,
        current_user_role: str
    ) -> Dict[str, Any]:
        """
        Update booking details.
        
        Args:
            booking_id: Booking ID to update
            updates: Update data
            current_user_id: Current user ID
            current_user_role: Current user role
            
        Returns:
            Updated booking data
            
        Raises:
            HTTPException: If not found or access denied
        """
        try:
            # Get booking and verify access
            booking = await self._get_booking_for_update(booking_id)
            await self._verify_booking_access(booking, current_user_id, current_user_role)
            
            # Prepare update data
            update_data = {}
            if updates.status:
                update_data["status"] = updates.status
            if updates.notes is not None:
                update_data["notes"] = updates.notes
            if updates.cancellation_reason:
                update_data["cancellation_reason"] = updates.cancellation_reason
            
            # Update booking
            response = db.table("bookings").update(update_data).eq("id", booking_id).execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found"
                )
            
            logger.info(f"Booking {booking_id} updated by user {current_user_id}")
            
            return response.data[0]
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update booking: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update booking"
            )
    
    async def cancel_booking(
        self,
        booking_id: str,
        reason: Optional[str],
        current_user_id: str,
        current_user_role: str
    ) -> Dict[str, Any]:
        """
        Cancel booking and send notification.
        
        Args:
            booking_id: Booking ID to cancel
            reason: Cancellation reason
            current_user_id: Current user ID
            current_user_role: Current user role
            
        Returns:
            Success response
            
        Raises:
            HTTPException: If not found or access denied
        """
        try:
            # Get booking details with profile
            booking_response = db.table("bookings").select(
                "*, profiles(email, full_name)"
            ).eq("id", booking_id).single().execute()
            
            if not booking_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found"
                )
            
            booking_data = booking_response.data
            
            # Verify ownership (only customer or admin can cancel)
            if current_user_role != "admin" and booking_data["customer_id"] != current_user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot cancel other users' bookings"
                )
            
            # Cancel booking
            update_data = {
                "status": "cancelled",
                "cancellation_reason": reason
            }
            response = db.table("bookings").update(update_data).eq("id", booking_id).execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to cancel booking"
                )
            
            # Calculate refund amount (full refund for now)
            refund_amount = booking_data.get("total_amount", 0.0)
            
            # Send cancellation email
            await self._send_cancellation_email(booking_data, reason, refund_amount)
            
            logger.info(f"Booking {booking_id} cancelled by user {current_user_id}")
            
            return {"success": True, "message": "Booking cancelled"}
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to cancel booking: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to cancel booking"
            )
    
    async def complete_booking(
        self,
        booking_id: str,
        current_user_id: str,
        current_user_role: str
    ) -> Dict[str, Any]:
        """
        Mark booking as completed (vendor only).
        
        Args:
            booking_id: Booking ID to complete
            current_user_id: Current user ID
            current_user_role: Current user role
            
        Returns:
            Success response
            
        Raises:
            HTTPException: If not vendor's booking or not found
        """
        try:
            # Get booking salon
            booking_check = db.table("bookings").select("salon_id").eq("id", booking_id).single().execute()
            
            if not booking_check.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found"
                )
            
            salon_id = booking_check.data["salon_id"]
            
            # Verify vendor owns the salon
            if current_user_role == "vendor":
                await self._verify_salon_ownership(salon_id, current_user_id)
            elif current_user_role not in ["admin"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only salon vendors and admins can complete bookings"
                )
            
            # Complete booking
            update_data = {"status": "completed"}
            response = db.table("bookings").update(update_data).eq("id", booking_id).execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to complete booking"
                )
            
            logger.info(f"Booking {booking_id} completed by user {current_user_id}")
            
            return {"success": True, "message": "Booking completed"}
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to complete booking: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to complete booking"
            )
    
    # =====================================================
    # HELPER METHODS
    # =====================================================
    
    async def _get_customer_profile(self, user_id: str) -> Dict[str, Any]:
        """Get customer profile data."""
        response = db.table("profiles").select("email, full_name, phone").eq(
            "id", user_id
        ).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer profile not found"
            )
        
        return {
            "full_name": response.data.get("full_name", "Customer"),
            "email": response.data.get("email", ""),
            "phone": response.data.get("phone", "")
        }
    
    async def _get_salon_details(self, salon_id: int) -> Dict[str, Any]:
        """Get salon details."""
        response = db.table("salons").select("id, business_name").eq(
            "id", salon_id
        ).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        return response.data
    
    def _calculate_booking_totals(self, booking: BookingCreate) -> Dict[str, Any]:
        """Calculate booking totals and duration."""
        final_amount = (
            booking.amount_paid + booking.remaining_amount 
            if booking.amount_paid and booking.remaining_amount 
            else booking.total_amount
        )
        
        total_duration = sum(
            service.get("duration", 0) 
            for service in booking.services
        )
        
        # Default to 60 minutes if not specified
        if total_duration == 0:
            total_duration = 60
        
        service_price = booking.total_amount
        
        return {
            "final_amount": final_amount,
            "total_duration": total_duration,
            "service_price": service_price
        }
    
    def _parse_booking_time(self, booking_time: str) -> str:
        """Parse and convert booking time to 24-hour format."""
        # Handle multiple time slots - use first one
        first_time_slot = booking_time.split(",")[0].strip() if "," in booking_time else booking_time
        
        # Convert 12-hour format to 24-hour format
        try:
            from datetime import datetime as dt
            parsed_time = dt.strptime(first_time_slot, "%I:%M %p")
            return parsed_time.strftime("%H:%M:%S")
        except:
            # Fallback - assume it's already in correct format
            return first_time_slot
    
    def _generate_booking_number(self) -> str:
        """Generate unique booking number."""
        date_part = datetime.now().strftime('%Y%m%d')
        random_part = random.randint(1000, 9999)
        return f"BK{date_part}{random_part}"
    
    def _build_booking_metadata(
        self,
        booking: BookingCreate,
        totals: Dict[str, Any],
        salon_name: str
    ) -> Dict[str, Any]:
        """Build booking metadata for storage."""
        metadata = {
            "services": booking.services,
            "booking_fee": booking.booking_fee,
            "gst_amount": booking.gst_amount,
            "amount_paid": booking.amount_paid,
            "remaining_amount": booking.remaining_amount,
            "payment_status": booking.payment_status,
            "payment_method": booking.payment_method,
            "total_amount": booking.total_amount,
            "final_amount": totals["final_amount"],
            "salon_name": salon_name,
            "all_booking_times": booking.booking_time
        }
        
        if booking.notes:
            metadata["original_notes"] = booking.notes
        
        return metadata
    
    def _enhance_booking_with_metadata(self, booking: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and merge metadata into booking response."""
        if booking.get("special_requests"):
            try:
                metadata = json.loads(booking["special_requests"])
                booking.update(metadata)
            except:
                pass
        
        return booking
    
    async def _send_booking_confirmation(
        self,
        customer_email: str,
        customer_name: str,
        salon_name: str,
        booking: BookingCreate,
        totals: Dict[str, Any],
        booking_id: str
    ) -> None:
        """Send booking confirmation email."""
        if not customer_email:
            return
        
        service_name = (
            booking.services[0].get("service_name", "Service") 
            if booking.services 
            else "Service"
        )
        
        try:
            email_sent = await email_service.send_booking_confirmation_email(
                to_email=customer_email,
                customer_name=customer_name,
                salon_name=salon_name,
                service_name=service_name,
                booking_date=booking.booking_date,
                booking_time=booking.booking_time,
                staff_name="Our Team",
                total_amount=totals["final_amount"],
                booking_id=booking_id
            )
            
            if not email_sent:
                logger.warning(f"Failed to send booking confirmation email to {customer_email}")
        except Exception as e:
            logger.warning(f"Error sending booking confirmation email: {str(e)}")
    
    async def _send_cancellation_email(
        self,
        booking_data: Dict[str, Any],
        reason: Optional[str],
        refund_amount: float
    ) -> None:
        """Send cancellation email."""
        if not booking_data.get("profiles"):
            return
        
        customer_email = booking_data["profiles"].get("email")
        customer_name = booking_data["profiles"].get("full_name", "Customer")
        
        if not customer_email:
            return
        
        # Get service name from booking
        services = booking_data.get("services", [])
        service_name = services[0].get("name", "Service") if services else "Service"
        
        try:
            email_sent = await email_service.send_booking_cancellation_email(
                to_email=customer_email,
                customer_name=customer_name,
                salon_name=booking_data.get("salon_name", "Salon"),
                service_name=service_name,
                booking_date=booking_data.get("booking_date", "N/A"),
                booking_time=booking_data.get("booking_time", "N/A"),
                refund_amount=refund_amount,
                cancellation_reason=reason
            )
            
            if not email_sent:
                logger.warning(f"Failed to send cancellation email to {customer_email}")
        except Exception as e:
            logger.warning(f"Error sending cancellation email: {str(e)}")
    
    async def _get_booking_for_update(self, booking_id: str) -> Dict[str, Any]:
        """Get booking for update operations."""
        response = db.table("bookings").select("customer_id, salon_id").eq(
            "id", booking_id
        ).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )
        
        return response.data
    
    async def _verify_booking_access(
        self,
        booking: Dict[str, Any],
        user_id: str,
        role: str
    ) -> None:
        """Verify user has access to booking."""
        is_owner = booking.get("customer_id") == user_id
        is_admin = role == "admin"
        is_vendor = False
        
        if role == "vendor":
            salon_id = booking.get("salon_id")
            if salon_id:
                salon_check = db.table("salons").select("vendor_id").eq(
                    "id", salon_id
                ).single().execute()
                is_vendor = salon_check.data and salon_check.data["vendor_id"] == user_id
        
        if not (is_owner or is_admin or is_vendor):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access this booking"
            )
    
    async def _verify_salon_ownership(self, salon_id: int, vendor_id: str) -> None:
        """Verify vendor owns the salon."""
        salon_check = db.table("salons").select("vendor_id").eq("id", salon_id).single().execute()
        
        if not salon_check.data or salon_check.data["vendor_id"] != vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access other salons' bookings"
            )
    
    # =====================================================
    # ADMIN-SPECIFIC METHODS
    # =====================================================
    
    async def get_admin_bookings(
        self,
        page: int = 1,
        limit: int = 20,
        status_filter: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get all bookings with filters (admin only).
        
        Args:
            page: Page number (1-indexed)
            limit: Results per page
            status_filter: Filter by booking status
            date_from: Filter bookings from this date (ISO format)
            date_to: Filter bookings until this date (ISO format)
            
        Returns:
            Dict with bookings, total count, and pagination info
            
        Raises:
            HTTPException: If query fails
        """
        try:
            offset = (page - 1) * limit
            query = db.table("bookings").select("*", count="exact")
            
            # Apply filters
            if status_filter:
                query = query.eq("status", status_filter)
            
            if date_from:
                query = query.gte("booking_date", date_from)
            
            if date_to:
                query = query.lte("booking_date", date_to)
            
            # Execute with pagination
            response = query.order("booking_date", desc=True).range(
                offset, offset + limit - 1
            ).execute()
            
            logger.info(
                f"Admin bookings query - Page: {page}, Total: {response.count}, "
                f"Filters: status={status_filter}, date_from={date_from}, date_to={date_to}"
            )
            
            return {
                "success": True,
                "data": response.data or [],
                "total": response.count or 0,
                "page": page,
                "limit": limit
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch admin bookings: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch bookings: {str(e)}"
            )
    
    async def update_booking_status_admin(
        self,
        booking_id: str,
        new_status: str
    ) -> Dict[str, Any]:
        """
        Update booking status (admin only).
        
        Args:
            booking_id: Booking ID to update
            new_status: New status value
            
        Returns:
            Dict with success flag, message, and updated booking
            
        Raises:
            HTTPException: If booking not found or update fails
        """
        try:
            # Update booking status
            response = db.table("bookings").update({
                "status": new_status
            }).eq("id", booking_id).execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found"
                )
            
            updated_booking = response.data[0]
            
            logger.info(
                f"Admin updated booking status - ID: {booking_id}, "
                f"New Status: {new_status}"
            )
            
            return {
                "success": True,
                "message": "Booking status updated successfully",
                "data": updated_booking
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update booking status: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update booking: {str(e)}"
            )
