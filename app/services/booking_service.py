"""
Booking Service - Business Logic Layer
Handles booking CRUD, cancellations, completions, and email notifications
"""
import logging
import random
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import HTTPException, status

from app.core.database import get_db
from app.schemas import BookingCreate, BookingUpdate, BookingResponse
from app.schemas.request.booking import ServiceSummary, Totals, BookingForUpdate, BookingForCancellation
from app.services.email import email_service

logger = logging.getLogger(__name__)


class BookingService:
    """
    Service class for booking operations.
    Handles booking lifecycle, validations, and notifications.
    """
    
    def __init__(self, db_client):
        """Initialize service with database client"""
        self.db = db_client
    
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
                
                response = self.db.table("bookings").select("*").eq(
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
                
                response = self.db.table("bookings").select("*").eq(
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
            response = self.db.table("bookings").select(
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
    
    async def get_admin_bookings(
        self,
        page: int = 1,
        limit: int = 20,
        status_filter: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get all bookings for admin with pagination and filters.
        
        Args:
            page: Page number (1-indexed)
            limit: Results per page
            status_filter: Filter by booking status
            date_from: Filter bookings from this date
            date_to: Filter bookings to this date
            
        Returns:
            Dict with bookings list, pagination info, and total count
            
        Raises:
            HTTPException: If query fails
        """
        try:
            # Calculate offset
            offset = (page - 1) * limit
            
            # Build query with joins - Remove count="exact" to avoid timeout on large datasets
            # We'll count separately if needed
            query = self.db.table("bookings").select(
                "*, "
                "salons(id, business_name, city, address), "
                "profiles(id, full_name, email, phone)"
            )
            
            # Apply filters
            if status_filter:
                query = query.eq("status", status_filter)
            
            if date_from:
                query = query.gte("booking_date", date_from)
            
            if date_to:
                query = query.lte("booking_date", date_to)
            
            # Execute query with pagination - order and limit
            response = query.order("booking_date", desc=True).order(
                "created_at", desc=True
            ).range(offset, offset + limit - 1).execute()
            
            bookings = response.data or []
            # Use length of returned data as count (exact count can be slow)
            total_count = len(bookings)
            
            # DEBUG: Log first booking to see structure
            if bookings:
                logger.info(f"First booking structure: {bookings[0].keys()}")
                logger.info(f"Has 'salons' key: {'salons' in bookings[0]}")
                logger.info(f"Has 'profiles' key: {'profiles' in bookings[0]}")
                if 'salons' in bookings[0]:
                    logger.info(f"Salons data: {bookings[0]['salons']}")
                if 'profiles' in bookings[0]:
                    logger.info(f"Profiles data: {bookings[0]['profiles']}")
            
            # Calculate pagination info
            total_pages = max(1, page) if bookings else 0
            
            logger.info(f"Admin fetched {len(bookings)} bookings (page {page})")
            
            return {
                "data": bookings,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total_count,
                    "total_pages": total_pages,
                    "has_next": len(bookings) == limit,  # Has next if we got full page
                    "has_prev": page > 1
                }
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch admin bookings: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch bookings"
            )
    
    async def update_booking_status_admin(
        self,
        booking_id: str,
        new_status: str
    ) -> Dict[str, Any]:
        """
        Update booking status (admin function).
        
        Args:
            booking_id: Booking ID to update
            new_status: New status value
            
        Returns:
            Success response with updated booking
            
        Raises:
            HTTPException: If booking not found or update fails
        """
        try:
            # Validate status
            valid_statuses = ["pending", "confirmed", "completed", "cancelled", "no_show"]
            if new_status not in valid_statuses:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status. Must be one of: {valid_statuses}"
                )
            
            # Check booking exists
            check_response = self.db.table("bookings").select("id, status").eq(
                "id", booking_id
            ).single().execute()
            
            if not check_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found"
                )
            
            # Update status
            update_data = {"status": new_status}
            
            if new_status == "confirmed":
                update_data["confirmed_at"] = datetime.utcnow().isoformat()
            elif new_status == "completed":
                update_data["completed_at"] = datetime.utcnow().isoformat()
            elif new_status == "cancelled":
                update_data["cancelled_at"] = datetime.utcnow().isoformat()
            
            response = self.db.table("bookings").update(update_data).eq(
                "id", booking_id
            ).execute()
            
            logger.info(f"Admin updated booking {booking_id} status to {new_status}")
            
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
    # BOOKING CREATION
    # =====================================================
    
    async def create_booking(
        self,
        booking: BookingCreate,
        current_user_id: str
    ) -> Dict[str, Any]:
        """
        Create new booking with multiple services support.

        Args:
            booking: Booking creation data with services array
            current_user_id: Customer user ID

        Returns:
            Created booking data

        Raises:
            HTTPException: If validation fails or creation fails
        """
        try:
            # Validate services array
            if not booking.services or len(booking.services) == 0:
                from app.core.exceptions import ValidationError
                raise ValidationError("At least one service is required", "services")

            # Get customer details
            customer_data = await self._get_customer_profile(current_user_id)

            # Get salon details
            salon_data = await self._get_salon_details(booking.salon_id)

            # Extract all service IDs for batch query (fix N+1 problem)
            service_ids = []
            service_quantities = {}
            
            for service_item in booking.services:
                service_id = getattr(service_item, "service_id", None)
                quantity = getattr(service_item, "quantity", 1)

                if not service_id:
                    from app.core.exceptions import ValidationError
                    raise ValidationError("service_id is required for each service", "services")

                if quantity <= 0:
                    from app.core.exceptions import ValidationError
                    raise ValidationError("quantity must be greater than 0", "services")

                service_ids.append(service_id)
                service_quantities[service_id] = quantity

            # Batch fetch all service details in one query (N+1 fix)
            services_lookup = await self._get_services_batch(service_ids)

            # Process all services and calculate totals
            processed_services = []
            total_service_price = 0.0
            total_duration = 0

            for service_item in booking.services:
                service_id = getattr(service_item, "service_id", None)
                quantity = service_quantities.get(service_id, getattr(service_item, "quantity", 1))

                # Get service details from batch lookup
                service_details = services_lookup.get(service_id)
                if not service_details:
                    from app.core.exceptions import NotFoundError
                    raise NotFoundError("Service", service_id)

                # Calculate pricing
                unit_price = service_details.get("price", 0.0)
                line_total = unit_price * quantity
                line_duration = service_details.get("duration_minutes", 30) * quantity

                processed_services.append({
                    "service_id": service_id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "duration_minutes": line_duration,
                    "service_details": service_details
                })

                total_service_price += line_total
                total_duration += line_duration

            # Get convenience fee percentage from system config
            try:
                fee_config_response = self.db.table("system_config")\
                    .select("config_value")\
                    .eq("config_key", "convenience_fee_percentage")\
                    .eq("is_active", True)\
                    .single()\
                    .execute()
                
                convenience_fee_percentage = float(fee_config_response.data["config_value"]) if fee_config_response.data else 6.0
            except Exception:
                convenience_fee_percentage = 6.0  # Default fallback
            
            # Calculate convenience fee and totals
            totals = self._calculate_booking_totals_multi_service(
                total_service_price,
                convenience_fee_percentage
            )

            # Parse and format booking time
            db_time = self._parse_booking_time(booking.booking_time)

            # Generate unique booking number
            booking_number = self._generate_booking_number()

            # Prepare services jsonb data
            services_jsonb = []
            for svc in processed_services:
                service_data = {
                    "service_id": svc["service_id"],
                    "service_name": svc["service_details"].get("name", "Service"),
                    "quantity": svc["quantity"],
                    "unit_price": svc["unit_price"],
                    "line_total": svc["line_total"],
                    "duration_minutes": svc["duration_minutes"]
                }
                services_jsonb.append(service_data)
            
            # Prepare time slots (up to 3)
            time_slots = booking.time_slots if booking.time_slots else [booking.booking_time]
            if len(time_slots) > 3:
                from app.core.exceptions import ValidationError
                raise ValidationError("Maximum 3 time slots allowed", "time_slots")

            # Prepare database data
            db_booking_data = {
                "booking_number": booking_number,
                "customer_id": current_user_id,
                "salon_id": booking.salon_id,
                "services": services_jsonb,
                "booking_date": booking.booking_date,
                "booking_time": db_time,
                "time_slots": time_slots,  # Store time slots array
                "duration_minutes": total_duration,
                "status": "confirmed" if booking.payment_status == "paid" else "pending",
                "service_price": total_service_price,
                "convenience_fee": totals["convenience_fee"],
                "total_amount": totals["total_amount"],
                "notes": booking.notes,
                "customer_name": customer_data["full_name"],
                "customer_phone": customer_data.get("phone", ""),
                "customer_email": customer_data.get("email", ""),
                "created_by": current_user_id
            }

            # Create booking within transaction
            try:
                response = self.db.table("bookings").insert(db_booking_data).execute()
                created_booking = response.data[0] if response.data else None
            except Exception as insert_exc:
                # Log error and re-raise
                logger.error(f"Failed to insert booking: {insert_exc}")
                from app.core.exceptions import DatabaseError
                raise DatabaseError("insert", f"Failed to create booking: {str(insert_exc)}")
            
            if not created_booking:
                from app.core.exceptions import DatabaseError
                raise DatabaseError("insert", "Failed to create booking")
            
            # Create payment records in new unified payments table
            booking_id = created_booking["id"]
            
            # 1. Create convenience fee payment record (online payment)
            if booking.razorpay_order_id or booking.razorpay_payment_id:
                convenience_payment_data = {
                    "booking_id": booking_id,
                    "customer_id": current_user_id,
                    "payment_type": "convenience_fee",
                    "amount": totals["convenience_fee"],
                    "currency": "INR",
                    "razorpay_order_id": booking.razorpay_order_id,
                    "razorpay_payment_id": booking.razorpay_payment_id,
                    "razorpay_signature": booking.razorpay_signature,
                    "status": "success" if booking.razorpay_payment_id else "pending",
                    "payment_method": booking.payment_method or "razorpay",
                    "paid_at": datetime.utcnow().isoformat() if booking.razorpay_payment_id else None,
                    "created_by": current_user_id
                }
                
                try:
                    self.db.table("payments").insert(convenience_payment_data).execute()
                    logger.info(f"Created convenience_fee payment record for booking {booking_id}")
                except Exception as payment_exc:
                    logger.error(f"Failed to create convenience_fee payment: {payment_exc}")
                    # Don't fail booking creation, payment flags are set on booking
            
            # 2. Create service payment record (to be paid at salon)
            try:
                service_payment_data = {
                    "booking_id": booking_id,
                    "customer_id": current_user_id,
                    "payment_type": "service_payment",
                    "amount": total_service_price,
                    "currency": "INR",
                    "status": "pending",
                    "payment_method": None,
                    "notes": f"Service payment for {len(processed_services)} service(s)",
                    "created_by": current_user_id
                }
                
                self.db.table("payments").insert(service_payment_data).execute()
                logger.info(f"Created service_payment record for booking {booking_id} (pending)")
            except Exception as service_payment_exc:
                logger.error(f"Failed to create service_payment record: {service_payment_exc}")
                # Don't fail booking creation
            
            # Prepare typed service summaries and totals for notification
            service_summaries = [
                ServiceSummary(
                    service_id=svc["service_id"],
                    quantity=svc["quantity"],
                    unit_price=svc["unit_price"],
                    line_total=svc["line_total"],
                    duration_minutes=svc.get("duration_minutes")
                )
                for svc in processed_services
            ]
            totals_obj = Totals.model_validate(totals)

            # Send confirmation emails to customer and vendor
            try:
                # 1. Send confirmation to customer
                await email_service.send_booking_confirmation_to_customer(
                    customer_email=customer_data["email"],
                    customer_name=customer_data["full_name"],
                    salon_name=salon_data["business_name"],
                    booking_number=booking_number,
                    booking_date=str(booking.booking_date),
                    booking_time=booking.booking_time,
                    services=[{
                        "name": svc.get("service_details", {}).get("name", "Service"),
                        "price": svc["unit_price"]
                    } for svc in processed_services],
                    total_amount=totals["total_amount"],
                    convenience_fee=totals["convenience_fee"],
                    service_price=total_service_price
                )
                logger.info(f"Booking confirmation email sent to customer {customer_data['email']}")
                
                # 2. Send notification to vendor
                # Get vendor email from salon
                vendor_response = self.db.table("vendors")\
                    .select("profiles(email)")\
                    .eq("user_id", salon_data.get("vendor_id"))\
                    .single()\
                    .execute()
                
                if vendor_response.data and vendor_response.data.get("profiles"):
                    vendor_email = vendor_response.data["profiles"].get("email")
                    if vendor_email:
                        await email_service.send_new_booking_notification_to_vendor(
                            vendor_email=vendor_email,
                            salon_name=salon_data["business_name"],
                            customer_name=customer_data["full_name"],
                            customer_phone=customer_data.get("phone", "N/A"),
                            booking_number=booking_number,
                            booking_date=str(booking.booking_date),
                            booking_time=booking.booking_time,
                            services=[{
                                "name": svc.get("service_details", {}).get("name", "Service"),
                                "price": svc["unit_price"]
                            } for svc in processed_services],
                            total_amount=totals["total_amount"],
                            booking_id=created_booking.get("id", "")
                        )
                        logger.info(f"Booking notification email sent to vendor {vendor_email}")
                    else:
                        logger.warning(f"No vendor email found for salon {salon_data['id']}")
                else:
                    logger.warning(f"No vendor found for salon {salon_data['id']}")
                    
            except Exception as email_error:
                # Don't fail booking if email fails
                logger.error(f"Failed to send booking notification emails: {str(email_error)}")

            logger.info(f"Booking created: {booking_number} for customer {current_user_id} with {len(processed_services)} services")

            return created_booking

        except Exception as e:
            logger.error(f"Failed to create booking: {str(e)}")
            from app.core.exceptions import ValidationError, DatabaseError
            if isinstance(e, (ValidationError, DatabaseError)):
                raise
            raise DatabaseError("create", f"Failed to create booking: {str(e)}")
    
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
                update_data["customer_notes"] = updates.notes
            if updates.cancellation_reason:
                update_data["cancellation_reason"] = updates.cancellation_reason
                update_data["cancelled_at"] = datetime.utcnow().isoformat()
                update_data["cancelled_by"] = current_user_id
            update_data["updated_by"] = current_user_id
            
            # Update booking
            response = self.db.table("bookings").update(update_data).eq("id", booking_id).execute()
            
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
            booking_response = self.db.table("bookings").select(
                "*, profiles(email, full_name), services(name), salons(business_name)"
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
                "cancellation_reason": reason,
                "cancelled_at": datetime.utcnow().isoformat(),
                "cancelled_by": current_user_id,
                "updated_by": current_user_id
            }
            response = self.db.table("bookings").update(update_data).eq("id", booking_id).execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to cancel booking"
                )
            
            # Refund only covers online convenience fee for now
            refund_amount = booking_data.get("convenience_fee", 0.0)
            
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
            booking_check = self.db.table("bookings").select("salon_id, convenience_fee_paid, service_paid").eq("id", booking_id).single().execute()
            
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
            
            # Complete booking and mark offline payment as collected
            update_data = {
                "status": "completed",
                "service_paid": True,
                "updated_by": current_user_id
            }
            if booking_check.data.get("convenience_fee_paid"):
                update_data["payment_completed_at"] = datetime.utcnow().isoformat()
            response = self.db.table("bookings").update(update_data).eq("id", booking_id).execute()
            
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
        response = self.db.table("profiles").select("email, full_name, phone").eq(
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
        try:
            response = self.db.table("salons").select("id, business_name").eq(
                "id", salon_id
            ).execute()
            
            if not response.data or len(response.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Salon not found"
                )
            
            return response.data[0]
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching salon {salon_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch salon details"
            )
    
    def _calculate_booking_totals_multi_service(
        self,
        total_service_price: float,
        convenience_fee_percentage: float = 6.0
    ) -> Dict[str, Any]:
        """
        Calculate pricing for multi-service booking.

        Args:
            total_service_price: Sum of all service line totals
            convenience_fee_percentage: Convenience fee percentage (default 6%)

        Returns:
            Dict with calculated totals
        """
        convenience_fee = (total_service_price * convenience_fee_percentage) / 100
        total_amount = total_service_price + convenience_fee

        return {
            "service_price": total_service_price,
            "convenience_fee": convenience_fee,
            "total_amount": total_amount
        }

    async def _get_service_details(self, service_id: str) -> Dict[str, Any]:
        """
        Get service details by ID.

        Args:
            service_id: Service UUID

        Returns:
            Service data

        Raises:
            NotFoundError: If service not found
        """
        response = self.db.table("services").select("*").eq("id", service_id).single().execute()

        if not response.data:
            from app.core.exceptions import NotFoundError
            raise NotFoundError("Service", service_id)

        return response.data
    
    async def _get_services_batch(self, service_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Batch fetch multiple services by IDs in a single query.
        
        Args:
            service_ids: List of service UUIDs
            
        Returns:
            Dict mapping service_id to service data
            
        Raises:
            NotFoundError: If any service not found
        """
        if not service_ids:
            return {}
            
        response = self.db.table("services").select("*").in_("id", service_ids).execute()
        
        if not response.data:
            from app.core.exceptions import NotFoundError
            raise NotFoundError("Services", f"None of the requested services found: {service_ids}")
        
        # Create lookup dictionary
        services_lookup = {service["id"]: service for service in response.data}
        
        # Check if all requested services were found
        missing_services = set(service_ids) - set(services_lookup.keys())
        if missing_services:
            from app.core.exceptions import NotFoundError
            raise NotFoundError("Services", f"Services not found: {list(missing_services)}")
        
        return services_lookup
    
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
    
    async def _send_booking_confirmation(
        self,
        customer_email: str,
        customer_name: str,
        salon_name: str,
        booking: BookingCreate,
        services: List[ServiceSummary],
        totals: Totals,
        booking_id: str
    ) -> None:
        """
        Send booking confirmation email for multi-service booking.

        Args:
            customer_email: Customer email address
            customer_name: Customer full name
            salon_name: Salon business name
            booking: Original booking data
            services: List of processed services with details
            totals: Calculated totals
            booking_id: Booking ID
        """
        if not customer_email:
            return

        # Create service summary for email
        service_summary = []
        for svc in services:
            # `services` is now a list of ServiceSummary
            service_summary.append({
                "name": getattr(svc, "service_id", "Service"),
                "quantity": getattr(svc, "quantity", 1),
                "unit_price": getattr(svc, "unit_price", 0.0),
                "line_total": getattr(svc, "line_total", 0.0)
            })

        try:
            email_sent = await email_service.send_booking_confirmation_email(
                to_email=customer_email,
                customer_name=customer_name,
                salon_name=salon_name,
                services=service_summary,  # Pass services array instead of single service
                booking_date=booking.booking_date,
                booking_time=booking.booking_time,
                staff_name="Our Team",
                total_amount=totals.total_amount,
                booking_id=booking_id
            )

            if not email_sent:
                logger.warning(f"Failed to send booking confirmation email to {customer_email}")
        except Exception as e:
            logger.warning(f"Error sending booking confirmation email: {str(e)}")
    
    async def _send_cancellation_email(
        self,
        booking_data: BookingForCancellation,
        reason: Optional[str],
        refund_amount: float
    ) -> None:
        """Send cancellation email.

        Accepts either a validated `BookingResponse` model or a raw dict returned
        from the DB. Handles both shapes safely.
        """

        if not booking_data:
            return

        customer_email = booking_data.profiles.email if booking_data.profiles else None
        customer_name = booking_data.profiles.full_name if booking_data.profiles else "Customer"

        if not customer_email:
            return

        service_name = booking_data.services.name if booking_data.services else "Service"
        salon_name = booking_data.salons.business_name if booking_data.salons else "Salon"
        booking_date = booking_data.booking_date or "N/A"
        booking_time = booking_data.booking_time or "N/A"

        try:
            email_sent = await email_service.send_booking_cancellation_email(
                to_email=customer_email,
                customer_name=customer_name,
                salon_name=salon_name,
                service_name=service_name,
                booking_date=booking_date,
                booking_time=booking_time,
                refund_amount=refund_amount,
                cancellation_reason=reason
            )

            if not email_sent:
                logger.warning(f"Failed to send cancellation email to {customer_email}")
        except Exception as e:
            logger.warning(f"Error sending cancellation email: {str(e)}")
    
    async def _get_booking_for_update(self, booking_id: str) -> BookingForUpdate:
        """Get booking for update operations.

        Returns a lightweight `BookingForUpdate` model used for authorization
        checks and update operations.
        """
        response = self.db.table("bookings").select("id, customer_id, salon_id").eq(
            "id", booking_id
        ).single().execute()

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )

        return BookingForUpdate.model_validate(response.data)
    
    async def _verify_salon_ownership(self, salon_id: int, vendor_id: str) -> None:
        """Verify vendor owns the salon."""
        salon_check = self.db.table("salons").select("vendor_id").eq("id", salon_id).single().execute()
        
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
        """Get all bookings with filters (admin only)."""
        try:
            offset = (page - 1) * limit
            query = self.db.table("bookings").select("*", count="exact")
            
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
            response = self.db.table("bookings").update({
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
    
    # =====================================================
    # AUTHORIZATION VERIFICATION METHODS
    # =====================================================
    
    async def _verify_booking_access(
        self,
        booking: Dict[str, Any],
        current_user_id: str,
        current_user_role: str
    ) -> None:
        """
        Verify that current user has access to the booking.
        
        Args:
            booking: Booking data dictionary
            current_user_id: Current user ID
            current_user_role: Current user role
            
        Raises:
            HTTPException: If access is denied
        """
        # Admins can access all bookings
        if current_user_role == "admin":
            return
        
        # Customers can only access their own bookings
        if current_user_role == "customer":
            if booking.get("customer_id") != current_user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot access other customers' bookings"
                )
            return
        
        # Vendors can access bookings for salons they own
        if current_user_role == "vendor":
            await self._verify_salon_ownership(booking.get("salon_id"), current_user_id)
            return
        
        # Relationship managers can access bookings for salons in their region
        if current_user_role == "relationship_manager":
            await self._verify_rm_salon_access(booking.get("salon_id"), current_user_id)
            return
        
        # Deny access for unknown roles
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to access booking"
        )
    
    async def _verify_salon_ownership(
        self,
        salon_id: int,
        current_user_id: str
    ) -> None:
        """
        Verify that current user owns the salon.
        
        Args:
            salon_id: Salon ID to check
            current_user_id: Current user ID
            
        Raises:
            HTTPException: If user doesn't own the salon
        """
        try:
            response = self.db.table("salons").select("owner_id").eq("id", salon_id).single().execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Salon not found"
                )
            
            if response.data["owner_id"] != current_user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to access this salon"
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to verify salon ownership: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to verify salon access"
            )
    
    async def _verify_rm_salon_access(
        self,
        salon_id: int,
        current_user_id: str
    ) -> None:
        """
        Verify that RM has access to the salon (same city/region).
        
        Args:
            salon_id: Salon ID to check
            current_user_id: Current RM user ID
            
        Raises:
            HTTPException: If RM doesn't have access to the salon
        """
        try:
            # Get RM's assigned city/region
            rm_response = self.db.table("profiles").select("city, state").eq("id", current_user_id).single().execute()
            
            if not rm_response.data:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="RM profile not found"
                )
            
            rm_city = rm_response.data.get("city")
            rm_state = rm_response.data.get("state")
            
            # Get salon's city/region
            salon_response = self.db.table("salons").select("city, state").eq("id", salon_id).single().execute()
            
            if not salon_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Salon not found"
                )
            
            salon_city = salon_response.data.get("city")
            salon_state = salon_response.data.get("state")
            
            # Allow access if RM is assigned to same city/state
            if rm_city == salon_city and rm_state == salon_state:
                return
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access salons in this region"
            )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to verify RM salon access: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to verify regional access"
            )
