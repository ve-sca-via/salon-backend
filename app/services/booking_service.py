"""
Booking Service - Business Logic Layer
Handles booking CRUD, cancellations, completions, and email notifications
"""
import logging
import random
from typing import Dict, Any, Optional, List
from datetime import datetime, date
from fastapi import HTTPException, status

from app.core.auth import create_review_feedback_token
from app.core.config import settings
from app.schemas import BookingCreate
from app.schemas.request.booking import ServiceSummary, Totals, BookingForCancellation
from app.services.email import email_service
from app.services.activity_log_service import ActivityLogService

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
            
            # Use bookings_with_payments view which has customer data pre-joined
            query = self.db.from_("bookings_with_payments").select(
                "*, "
                "salons(id, business_name, city, address)"
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
            
            # Enrich bookings with profiles object for compatibility with frontend
            enriched_bookings = []
            for booking in bookings:
                # Create profiles object from customer data in view
                profiles_obj = None
                if booking.get("customer_name") or booking.get("customer_email") or booking.get("customer_phone"):
                    profiles_obj = {
                        "full_name": booking.get("customer_name"),
                        "email": booking.get("customer_email"),
                        "phone": booking.get("customer_phone")
                    }
                
                enriched_booking = {
                    **booking,
                    "profiles": profiles_obj  # Add profiles object for frontend compatibility
                }
                enriched_bookings.append(enriched_booking)
            
            # Use length of returned data as count (exact count can be slow)
            total_count = len(enriched_bookings)
            
            # DEBUG: Log first booking to see structure
            if enriched_bookings:
                logger.info(f"First booking structure: {enriched_bookings[0].keys()}")
                logger.info(f"Has 'salons' key: {'salons' in enriched_bookings[0]}")
                logger.info(f"Has 'profiles' key: {'profiles' in enriched_bookings[0]}")
                if 'salons' in enriched_bookings[0]:
                    logger.info(f"Salons data: {enriched_bookings[0]['salons']}")
                if 'profiles' in enriched_bookings[0]:
                    logger.info(f"Profiles data: {enriched_bookings[0]['profiles']}")
            
            # Calculate pagination info
            total_pages = max(1, page) if enriched_bookings else 0
            
            logger.info(f"Admin fetched {len(enriched_bookings)} bookings (page {page})")
            
            return {
                "data": enriched_bookings,
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
            # IDEMPOTENCY CHECK: Check if payment already used for a booking
            if booking.razorpay_payment_id:
                existing_booking = self.db.table("bookings").select(
                    "id, booking_number, status, booking_date, time_slots, total_amount, salon_id, salons(business_name)"
                ).eq("razorpay_payment_id", booking.razorpay_payment_id).execute()
                
                if existing_booking.data:
                    logger.warning(f"Payment {booking.razorpay_payment_id} already used for booking. Returning existing booking (idempotent).")
                    return existing_booking.data[0]
            
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
            original_service_price = 0.0
            total_duration = 0

            for service_item in booking.services:
                service_id = getattr(service_item, "service_id", None)
                quantity = service_quantities.get(service_id, getattr(service_item, "quantity", 1))

                # Get service details from batch lookup
                service_details = services_lookup.get(service_id)
                if not service_details:
                    from app.core.exceptions import NotFoundError
                    raise NotFoundError("Service", service_id)

                # Effective price (discounted when available) — amount due at salon
                unit_price = service_details.get("discounted_price")
                if unit_price is None:
                    unit_price = service_details.get("price", 0.0)
                unit_price = float(unit_price)

                original_unit_price = float(service_details.get("price", 0.0))
                line_total = unit_price * quantity
                original_line_total = original_unit_price * quantity
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
                original_service_price += original_line_total
                total_duration += line_duration

            # Get convenience fee percentage from system config (admin-managed; required, no silent default)
            try:
                fee_config_response = self.db.table("system_config")\
                    .select("config_value")\
                    .eq("config_key", "convenience_fee_percentage")\
                    .eq("is_active", True)\
                    .single()\
                    .execute()
                convenience_fee_percentage = float(fee_config_response.data["config_value"])
            except Exception as e:
                logger.error(f"convenience_fee_percentage config missing or invalid: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Payment configuration not available. Please contact support."
                )
            
            # Calculate convenience fee and totals
            totals = self._calculate_booking_totals_multi_service(
                total_service_price,
                original_service_price,
                convenience_fee_percentage
            )

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
                    "original_price": svc["service_details"].get("price", 0.0),
                    "discounted_price": svc["service_details"].get("discounted_price"),
                    "discount_percentage": svc["service_details"].get("discount_percentage"),
                    "line_total": svc["line_total"],
                    "duration_minutes": svc["duration_minutes"]
                }
                services_jsonb.append(service_data)
            
            # Prepare time slots (up to 3)
            time_slots = booking.time_slots if booking.time_slots else []
            if not time_slots:
                from app.core.exceptions import ValidationError
                raise ValidationError("time_slots is required", "time_slots")
            if len(time_slots) > 3:
                from app.core.exceptions import ValidationError
                raise ValidationError("Maximum 3 time slots allowed", "time_slots")

            # Prepare database data (customer info fetched via JOIN, not stored redundantly)
            db_booking_data = {
                "booking_number": booking_number,
                "customer_id": current_user_id,
                "salon_id": booking.salon_id,
                "services": services_jsonb,
                "booking_date": booking.booking_date,
                "time_slots": time_slots,  # Store time slots array (1-3 appointment times)
                "duration_minutes": total_duration,
                "status": "confirmed" if booking.payment_status == "paid" else "pending",
                "service_price": total_service_price,
                "convenience_fee": totals["convenience_fee"],
                "total_amount": totals["total_amount"],
                "notes": booking.notes,
                "created_by": current_user_id,
                "razorpay_payment_id": booking.razorpay_payment_id  # Store for idempotency checks
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
            
            # Send confirmation emails to customer and vendor
            try:
                # 1. Send confirmation to customer
                await email_service.send_booking_confirmation_to_customer(
                    customer_email=customer_data["email"],
                    customer_name=customer_data["full_name"],
                    salon_name=salon_data["business_name"],
                    booking_number=booking_number,
                    booking_date=str(booking.booking_date),
                    booking_time=booking.time_slots[0] if booking.time_slots else "N/A",
                    services=[{
                        "name": svc.get("service_details", {}).get("name", "Service"),
                        "price": svc["unit_price"],
                        "quantity": svc["quantity"],
                    } for svc in processed_services],
                    total_amount=totals["total_amount"],
                    convenience_fee=totals["convenience_fee"],
                    service_price=total_service_price
                )
                logger.info(f"Booking confirmation email sent to customer {customer_data['email']}")
                
                # 2. Send notification to vendor
                # Use vendor email from salon_data (already fetched with salon)
                vendor_email = salon_data.get("vendor_email")
                if vendor_email:
                    await email_service.send_new_booking_notification_to_vendor(
                            vendor_email=vendor_email,
                            salon_name=salon_data["business_name"],
                            customer_name=customer_data["full_name"],
                            customer_phone=customer_data.get("phone", "N/A"),
                            booking_number=booking_number,
                            booking_date=str(booking.booking_date),
                            booking_time=booking.time_slots[0] if booking.time_slots else "N/A",
                            services=[{
                                "name": svc.get("service_details", {}).get("name", "Service"),
                                "price": svc["unit_price"],
                                "quantity": svc["quantity"],
                            } for svc in processed_services],
                            service_price=total_service_price,
                            booking_id=created_booking.get("id", "")
                        )
                    logger.info(f"Booking notification email sent to vendor {vendor_email}")
                else:
                    logger.warning(f"Vendor email not found for salon {booking.salon_id}")
                    
            except Exception as email_error:
                # Don't fail booking if email fails
                logger.error(f"Failed to send booking notification emails: {str(email_error)}")

            logger.info(f"Booking created: {booking_number} for customer {current_user_id} with {len(processed_services)} services")

            return created_booking

        except Exception as e:
            logger.error(f"Failed to create booking: {str(e)}")
            from app.core.exceptions import ValidationError, DatabaseError
            if isinstance(e, (HTTPException, ValidationError, DatabaseError)):
                raise
            raise DatabaseError("create", f"Failed to create booking: {str(e)}")
    
    # =====================================================
    # BOOKING UPDATES
    # =====================================================
    
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
            booking_response = self.db.table("bookings").select("*").eq("id", booking_id).single().execute()
            
            if not booking_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found"
                )
            
            booking_data = booking_response.data

            if booking_data.get("status") in ("completed", "cancelled"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot cancel {booking_data['status']} booking"
                )

            booking_date_raw = booking_data.get("booking_date")
            if booking_date_raw:
                if isinstance(booking_date_raw, str):
                    appointment_date = date.fromisoformat(booking_date_raw[:10])
                else:
                    appointment_date = booking_date_raw
                if appointment_date < date.today():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cancellation is only allowed for upcoming appointments."
                    )
            
            # Verify ownership (only customer or admin can cancel)
            if current_user_role != "admin" and str(booking_data.get("customer_id")) != str(current_user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot cancel other users' bookings"
                )

            # Load related profile and salon for notification emails
            try:
                profile_response = self.db.table("profiles").select(
                    "email, full_name, phone"
                ).eq("id", booking_data["customer_id"]).single().execute()
                booking_data["profiles"] = profile_response.data or {}
            except Exception as profile_error:
                logger.warning(f"Could not load customer profile for booking {booking_id}: {profile_error}")
                booking_data["profiles"] = {}

            try:
                salon_response = self.db.table("salons").select(
                    "id, business_name, vendor_id"
                ).eq("id", booking_data["salon_id"]).single().execute()
                booking_data["salons"] = salon_response.data or {}
            except Exception as salon_error:
                logger.warning(f"Could not load salon for booking {booking_id}: {salon_error}")
                booking_data["salons"] = {}
            
            # Cancel booking (cancelled_by is tracked via updated_by — no cancelled_by column)
            update_data = {
                "status": "cancelled",
                "cancellation_reason": reason,
                "cancelled_at": datetime.utcnow().isoformat(),
                "updated_by": current_user_id,
            }
            response = (
                self.db.table("bookings")
                .update(update_data)
                .eq("id", booking_id)
                .execute()
            )
            
            cancelled_booking = response.data[0] if response.data else None
            if not cancelled_booking:
                # Re-fetch in case client returned no rows (should not happen with service role)
                refetch = self.db.table("bookings").select("*").eq("id", booking_id).single().execute()
                cancelled_booking = refetch.data
                if not cancelled_booking or cancelled_booking.get("status") != "cancelled":
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to cancel booking"
                    )
            
            # Send cancellation emails to customer and vendor
            await self._send_cancellation_emails(booking_data, reason)

            try:
                profile = booking_data.get("profiles") or {}
                salon = booking_data.get("salons") or {}
                await ActivityLogService.log(
                    user_id=current_user_id,
                    action="booking_cancelled",
                    entity_type="booking",
                    entity_id=booking_id,
                    details={
                        "booking_number": booking_data.get("booking_number"),
                        "salon_name": salon.get("business_name"),
                        "customer_name": profile.get("full_name"),
                        "cancelled_by_role": current_user_role,
                        "reason": reason,
                    },
                )
            except Exception as log_error:
                logger.warning(f"Failed to log booking cancellation activity: {log_error}")
            
            logger.info(f"Booking {booking_id} cancelled by user {current_user_id}")
            
            return {
                "success": True,
                "message": "Booking cancelled successfully",
                "booking": cancelled_booking,
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to cancel booking: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to cancel booking"
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

    async def _send_review_request_email(self, booking_id: str) -> None:
        """Send a review invitation email for a completed booking."""
        booking_response = self.db.table("bookings").select(
            "id, booking_number, booking_date, customer_id, salon_id, "
            "profiles!customer_id(full_name, email), salons(business_name)"
        ).eq("id", booking_id).single().execute()

        booking = booking_response.data
        if not booking:
            logger.warning(f"Review request email skipped: booking {booking_id} not found")
            return

        customer = booking.get("profiles") or {}
        salon = booking.get("salons") or {}
        customer_email = customer.get("email")
        if not customer_email:
            logger.warning(f"Review request email skipped: booking {booking_id} has no customer email")
            return

        token = create_review_feedback_token(
            booking_id=booking["id"],
            salon_id=booking["salon_id"],
            customer_id=booking["customer_id"],
            customer_email=customer_email
        )
        feedback_url = f"{settings.FRONTEND_URL.rstrip('/')}/salons/{booking['salon_id']}/feedback?token={token}"

        await email_service.send_review_request_email(
            customer_email=customer_email,
            customer_name=customer.get("full_name") or "Customer",
            salon_name=salon.get("business_name") or "your salon",
            booking_number=booking.get("booking_number") or booking["id"],
            booking_date=str(booking.get("booking_date") or ""),
            feedback_url=feedback_url,
            booking_id=booking["id"]
        )
    
    async def _get_salon_details(self, salon_id: int) -> Dict[str, Any]:
        """Get salon details with vendor email."""
        try:
            # Get salon details first
            response = self.db.table("salons").select(
                "id, business_name, vendor_id"
            ).eq("id", salon_id).execute()
            
            if not response.data or len(response.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Salon not found"
                )
            
            salon = response.data[0]
            
            # Get vendor email separately if vendor_id exists
            vendor_email = None
            if salon.get("vendor_id"):
                try:
                    vendor_response = self.db.table("profiles").select(
                        "email"
                    ).eq("id", salon["vendor_id"]).execute()
                    
                    if vendor_response.data and len(vendor_response.data) > 0:
                        vendor_email = vendor_response.data[0].get("email")
                except Exception as vendor_error:
                    logger.warning(f"Could not fetch vendor email for salon {salon_id}: {vendor_error}")
            
            salon["vendor_email"] = vendor_email
            
            return salon
            
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
        discounted_service_price: float,
        original_service_price: float,
        convenience_fee_percentage: float = 6.0
    ) -> Dict[str, Any]:
        """
        Calculate pricing for multi-service booking.

        Convenience fee is charged on the original (pre-discount) service total,
        matching checkout UI and Razorpay payment. Service amount due at salon
        uses discounted prices when available.

        Args:
            discounted_service_price: Sum of discounted service line totals (pay at salon)
            original_service_price: Sum of original service line totals (fee base)
            convenience_fee_percentage: Convenience fee percentage (default 6%)

        Returns:
            Dict with calculated totals
        """
        convenience_fee = round(
            (original_service_price * convenience_fee_percentage) / 100,
            2
        )
        total_amount = round(discounted_service_price + convenience_fee, 2)

        return {
            "service_price": round(discounted_service_price, 2),
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
            # Format time_slots for email display (use first slot)
            booking_time_display = booking.time_slots[0] if booking.time_slots else "N/A"
            
            email_sent = await email_service.send_booking_confirmation_email(
                to_email=customer_email,
                customer_name=customer_name,
                salon_name=salon_name,
                services=service_summary,  # Pass services array instead of single service
                booking_date=booking.booking_date,
                booking_time=booking_time_display,
                total_amount=totals.total_amount,
                booking_id=booking_id
            )

            if not email_sent:
                logger.warning(f"Failed to send booking confirmation email to {customer_email}")
        except Exception as e:
            logger.warning(f"Error sending booking confirmation email: {str(e)}")
    
    def _extract_booking_services(self, booking_data: Dict[str, Any]) -> tuple[str, List[Dict[str, Any]]]:
        """Extract service summary from booking JSONB services field."""
        services = booking_data.get("services") or []
        if not isinstance(services, list) or not services:
            return "Service", [{"name": "Service", "price": 0, "quantity": 1}]

        names: List[str] = []
        service_list: List[Dict[str, Any]] = []
        for service in services:
            if not isinstance(service, dict):
                continue
            name = (
                service.get("name")
                or service.get("service_name")
                or (service.get("service_details") or {}).get("name")
                or "Service"
            )
            names.append(name)
            service_list.append({
                "name": name,
                "price": float(service.get("unit_price") or service.get("price") or 0),
                "quantity": int(service.get("quantity") or 1),
            })

        if not names:
            return "Service", [{"name": "Service", "price": 0, "quantity": 1}]

        return ", ".join(names), service_list

    async def _send_cancellation_emails(
        self,
        booking_data: Dict[str, Any],
        reason: Optional[str],
    ) -> None:
        """Send cancellation emails to customer and vendor/salon."""
        if not booking_data:
            return

        profile = booking_data.get("profiles") or {}
        salon = booking_data.get("salons") or {}
        customer_email = profile.get("email")
        customer_name = profile.get("full_name") or "Customer"
        customer_phone = profile.get("phone") or "N/A"
        salon_name = salon.get("business_name") or "Salon"
        booking_id = booking_data.get("id")
        booking_number = booking_data.get("booking_number") or booking_id
        booking_date = booking_data.get("booking_date") or "N/A"
        time_slots = booking_data.get("time_slots") or []
        booking_time = time_slots[0] if isinstance(time_slots, list) and time_slots else "N/A"
        service_name, services = self._extract_booking_services(booking_data)

        if customer_email:
            try:
                email_sent = await email_service.send_booking_cancellation_email(
                    to_email=customer_email,
                    customer_name=customer_name,
                    salon_name=salon_name,
                    service_name=service_name,
                    booking_date=str(booking_date),
                    booking_time=booking_time,
                    cancellation_reason=reason,
                    booking_id=booking_id,
                    booking_number=booking_number,
                )
                if not email_sent:
                    logger.warning(f"Failed to send cancellation email to {customer_email}")
            except Exception as e:
                logger.warning(f"Error sending customer cancellation email: {e}")

        vendor_email = None
        vendor_id = salon.get("vendor_id")
        if vendor_id:
            try:
                vendor_response = self.db.table("profiles").select("email").eq("id", vendor_id).execute()
                if vendor_response.data:
                    vendor_email = vendor_response.data[0].get("email")
            except Exception as vendor_error:
                logger.warning(f"Could not fetch vendor email for booking {booking_id}: {vendor_error}")

        if vendor_email:
            try:
                vendor_sent = await email_service.send_booking_cancellation_notification_to_vendor(
                    vendor_email=vendor_email,
                    salon_name=salon_name,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    booking_number=booking_number,
                    booking_date=str(booking_date),
                    booking_time=booking_time,
                    services=services,
                    cancellation_reason=reason,
                    booking_id=booking_id,
                )
                if not vendor_sent:
                    logger.warning(f"Failed to send cancellation email to vendor {vendor_email}")
            except Exception as e:
                logger.warning(f"Error sending vendor cancellation email: {e}")
        else:
            logger.warning(f"Vendor email not found for cancelled booking {booking_id}")

    async def _send_cancellation_email(
        self,
        booking_data: BookingForCancellation,
        reason: Optional[str],
        refund_amount: float
    ) -> None:
        """Backward-compatible wrapper for cancellation emails."""
        if isinstance(booking_data, dict):
            await self._send_cancellation_emails(booking_data, reason)
            return

        if not booking_data:
            return

        customer_email = booking_data.profiles.email if booking_data.profiles else None
        customer_name = booking_data.profiles.full_name if booking_data.profiles else "Customer"

        if not customer_email:
            return

        service_name = booking_data.services.name if booking_data.services else "Service"
        salon_name = booking_data.salons.business_name if booking_data.salons else "Salon"
        booking_date = booking_data.booking_date or "N/A"
        booking_time = booking_data.time_slots[0] if booking_data.time_slots else "N/A"

        try:
            email_sent = await email_service.send_booking_cancellation_email(
                to_email=customer_email,
                customer_name=customer_name,
                salon_name=salon_name,
                service_name=service_name,
                booking_date=booking_date,
                booking_time=booking_time,
                cancellation_reason=reason,
                booking_id=getattr(booking_data, "id", None),
            )

            if not email_sent:
                logger.warning(f"Failed to send cancellation email to {customer_email}")
        except Exception as e:
            logger.warning(f"Error sending cancellation email: {str(e)}")
