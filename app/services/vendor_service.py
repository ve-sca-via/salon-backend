"""
Vendor Service - Business Logic Layer
Handles vendor salon management, services CRUD
"""
import logging
from datetime import date, datetime
from typing import Dict, Any, Optional, List
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException, status

from app.core.auth import (
    verify_registration_token,
    create_access_token,
    create_refresh_token
)
from app.schemas import (
    ServiceCreate,
    ServiceUpdate,
    SalonUpdate,
    SalonPromoApplyRequest,
)
from app.services.booking_service import BookingService
from app.services.activity_log_service import ActivityLogService
from app.services.config_service import ConfigService
from app.services.service_taxonomy import ServiceTaxonomyResolver

logger = logging.getLogger(__name__)


class VendorService:
    """
    Service class for vendor operations.
    Handles salon management, services CRUD, and bookings.
    """
    
    def __init__(self, db_client):
        """Initialize service with database client"""
        self.db = db_client
        self.config_service = ConfigService(db_client=db_client)
    
    # =====================================================
    # SALON OPERATIONS
    # =====================================================
    
    async def get_vendor_salon(self, vendor_id: str) -> Dict[str, Any]:
        """
        Get salon details for a vendor.
        
        Args:
            vendor_id: Vendor user ID
            
        Returns:
            Salon data with registration_fee_amount from system_config
            
        Raises:
            HTTPException: If salon not found
        """
        try:
            response = self.db.table("salons").select("*").eq("vendor_id", vendor_id).execute()
            
            if not response.data or len(response.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Salon not found"
                )
            
            salon_data = response.data[0]
            
            # Add registration fee amount from system config
            try:
                registration_fee_config = await self.config_service.get_config("registration_fee_amount")
                config_value = registration_fee_config.get("config_value")
                salon_data["registration_fee_amount"] = float(config_value)
            except Exception as e:
                logger.error(f"CRITICAL: Failed to fetch registration fee config from database: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to load system configuration. Please contact support."
                )
            
            return salon_data
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching salon for vendor {vendor_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch salon"
            )
    
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
            
            # Convert time objects to strings for JSON serialization
            if 'opening_time' in update_data and update_data['opening_time'] is not None:
                if hasattr(update_data['opening_time'], 'isoformat'):
                    update_data['opening_time'] = update_data['opening_time'].isoformat()
            if 'closing_time' in update_data and update_data['closing_time'] is not None:
                if hasattr(update_data['closing_time'], 'isoformat'):
                    update_data['closing_time'] = update_data['closing_time'].isoformat()
            
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
    
    async def get_vendor_salon_id(self, vendor_id: str) -> str:
        """
        Get salon ID for a vendor.
        
        Args:
            vendor_id: Vendor user ID
            
        Returns:
            Salon ID (UUID string)
            
        Raises:
            HTTPException: If salon not found
        """
        try:
            response = self.db.table("salons").select("id").eq("vendor_id", vendor_id).execute()
            
            if not response.data or len(response.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Salon not found. Please create a salon first."
                )
            
            return str(response.data[0]["id"])
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching salon ID for vendor {vendor_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch salon ID"
            )
    
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
            await self._sync_promotions_if_needed(salon_id)

            # Get services with category and subcategory details
            response = self.db.table("services").select(
                "*, service_categories(*), service_subcategories(*)"
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
            
            category_id, subcategory_id = await self._resolve_service_category_fields(
                category_id=service.category_id,
                subcategory_id=service.subcategory_id,
                sub_subcategory_id=service.sub_subcategory_id,
                category_name=service.category_name,
                subcategory_name=service.subcategory_name,
                sub_subcategory_name=service.sub_subcategory_name,
            )

            # A service must belong to a category (services.category_id is NOT NULL).
            # Fail with a clear 400 rather than letting the DB raise on insert.
            if not category_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A service category is required",
                )

            await self._validate_service_category(category_id)

            if subcategory_id:
                await self._validate_service_subcategory(subcategory_id, category_id)

            # Create service with auto-assigned salon_id.
            # subcategory_id holds the DEEPEST taxonomy node; sub_subcategory_* are
            # resolver inputs only and are not columns on the services table.
            service_data = service.model_dump(
                exclude={
                    'salon_id', 'category_name', 'subcategory_name',
                    'sub_subcategory_id', 'sub_subcategory_name',
                }
            )
            service_data['category_id'] = category_id
            service_data['subcategory_id'] = subcategory_id
            service_data['salon_id'] = salon_id  # Auto-assign from authenticated vendor
            service_data = self._apply_discount_fields(service_data)
            
            response = self.db.table("services").insert(service_data).execute()
            
            created_service = response.data[0] if response.data else None
            
            logger.info(
                f"Vendor {vendor_id} created service: {service.name} "
                f"(category: {service.category_id or 'none'}, subcategory: {service.subcategory_id or 'none'})"
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
            
            update_data = update.model_dump(
                exclude_unset=True,
                exclude={
                    'category_name', 'subcategory_name',
                    'sub_subcategory_id', 'sub_subcategory_name',
                },
            )

            taxonomy_touched = (
                update.category_id is not None
                or update.subcategory_id is not None
                or update.sub_subcategory_id is not None
                or update.category_name is not None
                or update.subcategory_name is not None
                or update.sub_subcategory_name is not None
            )
            if taxonomy_touched:
                resolved_category_id, resolved_subcategory_id = await self._resolve_service_category_fields(
                    category_id=update.category_id,
                    subcategory_id=update.subcategory_id,
                    sub_subcategory_id=update.sub_subcategory_id,
                    category_name=update.category_name,
                    subcategory_name=update.subcategory_name,
                    sub_subcategory_name=update.sub_subcategory_name,
                )
                if update.category_id is not None or update.category_name is not None:
                    update_data['category_id'] = resolved_category_id
                # The deepest selected node becomes the stored leaf reference.
                if (
                    update.subcategory_id is not None
                    or update.subcategory_name is not None
                    or update.sub_subcategory_id is not None
                    or update.sub_subcategory_name is not None
                ):
                    update_data['subcategory_id'] = resolved_subcategory_id

            if update_data.get('category_id'):
                await self._validate_service_category(update_data['category_id'])

            if update_data.get('subcategory_id'):
                await self._validate_service_subcategory(
                    update_data['subcategory_id'],
                    update_data.get('category_id'),
                )
            
            if not update_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No fields provided for update"
                )

            # Recalculate discounted_price when price or discount_percentage changes
            if "price" in update_data or "discount_percentage" in update_data:
                existing_service_response = self.db.table("services").select(
                    "price, discount_percentage"
                ).eq("id", service_id).single().execute()

                if not existing_service_response.data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Service not found"
                    )

                existing_service = existing_service_response.data
                effective_data = {
                    "price": update_data.get("price", existing_service.get("price", 0)),
                    "discount_percentage": update_data.get("discount_percentage", existing_service.get("discount_percentage"))
                }

                update_data.update(self._apply_discount_fields(effective_data))
            
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
            logger.info(f"Fetching bookings for salon_id: {salon_id} (type: {type(salon_id).__name__})")
            
            # Use bookings_with_payments view which has customer data pre-joined
            query = self.db.from_("bookings_with_payments").select("*").eq("salon_id", salon_id).is_("deleted_at", "null")
            
            if status_filter:
                query = query.eq("status", status_filter)
            
            if date_from:
                query = query.gte("booking_date", date_from)
            
            if date_to:
                query = query.lte("booking_date", date_to)
            
            response = query.order("booking_date", desc=True).order(
                "created_at", desc=True
            ).range(offset, offset + limit).execute()
            
            bookings = response.data or []
            logger.info(f"Query returned {len(bookings)} bookings from bookings_with_payments view")
            
            # DEBUG: Log first booking to verify customer data
            if bookings:
                first_booking = bookings[0]
                logger.debug(f"First booking customer_name: {first_booking.get('customer_name')}")
                logger.debug(f"First booking customer_phone: {first_booking.get('customer_phone')}")
            
            # Enrich booking data with service names
            enriched_bookings = []
            for booking in bookings:
                # Extract service names from services JSON
                services = booking.get("services", [])
                service_names = [s.get("name", "Unknown Service") for s in services] if services else []
                
                enriched_bookings.append({
                    **booking,
                    "service_names": service_names,
                    "service_names_str": ", ".join(service_names) if service_names else "No services"
                })
            
            logger.info(f"Returning {len(enriched_bookings)} enriched bookings")
            return enriched_bookings
        
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
            
            response = self.db.table("bookings").update(update_data).eq("id", booking_id).execute()
            
            logger.info(f"Vendor {vendor_id} updated booking {booking_id} status to {new_status}")
            
            # Send review request email if booking was marked completed
            if new_status == "completed":
                try:
                    booking_service = BookingService(db_client=self.db)
                    await booking_service._send_review_request_email(booking_id)
                except Exception as email_error:
                    logger.error(f"Failed to send review request email for booking {booking_id}: {email_error}")
                    # Don't fail the request, just log the error
            
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
            
            # Check if regular_buyer
            is_regular_buyer = salon.get("salon_type") == "regular_buyer"
            
            # Get product order stats
            orders_response = self.db.table("product_orders").select("id, total_amount", count="exact").eq("user_id", vendor_id).execute()
            pending_orders_response = self.db.table("product_orders").select("id", count="exact").eq("user_id", vendor_id).eq("status", "pending").execute()
            completed_orders = self.db.table("product_orders").select("total_amount").eq("user_id", vendor_id).eq("payment_status", "completed").execute()
            total_spending = sum([o.get("total_amount", 0) for o in completed_orders.data]) if completed_orders.data else 0

            if is_regular_buyer:
                return {
                    "total_bookings": 0,
                    "total_revenue": 0.0,
                    "active_services": 0,
                    "average_rating": 0.0,
                    "pending_bookings": 0,
                    "total_product_orders": orders_response.count if orders_response else 0,
                    "pending_product_orders": pending_orders_response.count if pending_orders_response else 0,
                    "total_product_spending": total_spending
                }
            
            # Original salon logic
            # Get counts
            services_response = self.db.table("services").select("id", count="exact").eq("salon_id", salon_id).eq("is_active", True).execute()
            bookings_response = self.db.table("bookings").select("id, total_amount", count="exact").eq("salon_id", salon_id).execute()
            pending_response = self.db.table("bookings").select("id", count="exact").eq("salon_id", salon_id).eq("status", "pending").execute()
            
            # Calculate total revenue from completed bookings
            completed_bookings = self.db.table("bookings").select("total_amount").eq("salon_id", salon_id).eq("status", "completed").execute()
            total_revenue = sum([b.get("total_amount", 0) for b in completed_bookings.data]) if completed_bookings.data else 0
            
            return {
                "total_bookings": bookings_response.count if bookings_response else 0,
                "total_revenue": total_revenue,
                "active_services": services_response.count if services_response else 0,
                "average_rating": salon.get("average_rating", 0.0),
                "pending_bookings": pending_response.count if pending_response else 0,
                "total_product_orders": orders_response.count if orders_response else 0,
                "pending_product_orders": pending_orders_response.count if pending_orders_response else 0,
                "total_product_spending": total_spending
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
    
    def _taxonomy(self) -> ServiceTaxonomyResolver:
        """Shared category/subcategory/sub-subcategory resolver."""
        return ServiceTaxonomyResolver(self.db)

    async def _resolve_service_category_fields(
        self,
        category_id: Optional[str] = None,
        subcategory_id: Optional[str] = None,
        sub_subcategory_id: Optional[str] = None,
        category_name: Optional[str] = None,
        subcategory_name: Optional[str] = None,
        sub_subcategory_name: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        return await self._taxonomy().resolve_fields(
            category_id=category_id,
            subcategory_id=subcategory_id,
            sub_subcategory_id=sub_subcategory_id,
            category_name=category_name,
            subcategory_name=subcategory_name,
            sub_subcategory_name=sub_subcategory_name,
        )

    async def _validate_service_category(self, category_id: str) -> None:
        await self._taxonomy().validate_category(category_id)

    async def _validate_service_subcategory(self, subcategory_id: str, category_id: str = None) -> None:
        await self._taxonomy().validate_subcategory(subcategory_id, category_id)
    
    async def _verify_service_ownership(self, service_id: str, salon_id: str) -> None:
        """
        Verify that service belongs to the vendor's salon.
        
        Args:
            service_id: Service ID to verify
            salon_id: Vendor's salon ID (UUID string)
            
        Raises:
            HTTPException: If service not found or doesn't belong to salon
        """
        service_check = self.db.table("services").select("salon_id").eq("id", service_id).single().execute()
        
        if not service_check.data or str(service_check.data["salon_id"]) != salon_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found or access denied"
            )
    
    async def _verify_booking_ownership(self, booking_id: str, salon_id: str) -> None:
        """
        Verify that booking belongs to the vendor's salon.
        
        Args:
            booking_id: Booking ID to verify
            salon_id: Vendor's salon ID (UUID string)
            
        Raises:
            HTTPException: If booking not found or doesn't belong to salon
        """
        booking_check = self.db.table("bookings").select("salon_id, status").eq("id", booking_id).single().execute()
        
        if not booking_check.data or str(booking_check.data["salon_id"]) != salon_id:
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
        full_name: str,
        age: int,
        gender: str,
        user_role: str = "vendor"
    ) -> Dict[str, Any]:
        """
        Create vendor profile in profiles table.
        
        Args:
            user_id: User ID from Supabase auth
            email: Vendor email
            full_name: Vendor full name
            age: Vendor age (18-120)
            gender: Vendor gender (male, female, other)
            
        Returns:
            Created profile data
        """
        # Validate gender
        if gender.lower() not in ['male', 'female', 'other']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid gender. Must be 'male', 'female', or 'other'."
            )
        
        profile_data = {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "age": age,
            "gender": gender.lower(),
            "user_role": user_role,
            "is_active": True
        }
        
        response = self.db.table("profiles").insert(profile_data).execute()
        
        logger.info(f"Vendor profile created for {email}")
        
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
        
        logger.info(f"Vendor {user_id} linked to salon {salon_id}")
        logger.info("Salon automatically verified upon vendor registration")
        
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
        
        # Get vendor's salon (also attaches registration_fee_amount from system_config)
        salon = await self.get_vendor_salon(vendor_id)
        salon_id = salon["id"]
        business_name = salon.get("business_name", "Salon")
        registration_fee_amount = float(salon.get("registration_fee_amount") or 0)

        logger.info(f"Processing payment for vendor: {vendor_id}, salon: {business_name}")
        
        # Prepare payment data (match actual schema - no subscription fields in salons table)
        payment_data = {
            "registration_fee_paid": True,
            "is_active": True,  # Activate salon after successful payment
            "is_verified": True
        }
        
        # Update salon with payment info
        self.db.table("salons").update(payment_data).eq("id", salon_id).execute()
        
        logger.info(f"Payment processed successfully for salon: {business_name}")
        
        return {
            "payment_status": "success",
            "payment_amount": registration_fee_amount,
            "salon_name": business_name,
            "salon_id": salon_id
        }
    
    async def complete_registration(
        self,
        token: str,
        full_name: str,
        password: str,
        confirm_password: str,
        age: int,
        gender: str
    ) -> Dict[str, Any]:
        """
        Complete vendor registration after admin approval.
        
        Args:
            token: JWT registration token
            full_name: Vendor's full name
            password: Password for the account
            confirm_password: Password confirmation
            age: Vendor's age (18-120)
            gender: Vendor's gender (male, female, other)
            
        Returns:
            Registration completion data with tokens
            
        Raises:
            HTTPException: If registration fails
        """
        logger.info("Starting vendor registration completion...")
        
        # Verify JWT registration token
        token_data = verify_registration_token(token)
        salon_id = token_data["salon_id"]
        request_id = token_data["request_id"]
        vendor_email = token_data["email"]
        
        logger.info(f"Token verified for {vendor_email}, salon_id: {salon_id}")
        
        # Fetch salon to verify existence
        salon_response = self.db.table("salons").select("id").eq("id", salon_id).single().execute()
        if not salon_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        # Determine salon type (salon vs regular_buyer)
        salon_type = salon_response.data.get("salon_type")
        
        # Fallback: check the original join request if salon_type is missing from salon record
        if not salon_type:
            try:
                request_response = self.db.table("vendor_join_requests").select("request_type").eq("id", request_id).single().execute()
                if request_response.data:
                    salon_type = request_response.data.get("request_type")
            except Exception as e:
                logger.warning(f"Could not fetch request_type for fallback: {e}")
        
        # Final fallback
        if not salon_type:
            salon_type = "salon"
            
        user_role = "regular_buyer" if salon_type == "regular_buyer" else "vendor"
        logger.info(f"Determined user role: {user_role} (from salon_type: {salon_type})")

        # Use full_name from registration request (provided by vendor)
        vendor_full_name = full_name.strip()
        
        logger.info(f"Vendor name: {vendor_full_name}")
        
        if password != confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )
        
        logger.info(f"Creating db auth user for {vendor_email}...")
        
        # Create db auth user using admin API
        auth_user_created = False
        try:
            auth_response = self.db.auth.admin.create_user({
                "email": vendor_email,
                "password": password,
                "email_confirm": True,  # Auto-confirm email
                "user_metadata": {
                    "role": user_role,
                    "full_name": vendor_full_name
                }
            })
            auth_user_created = True
            logger.info("Auth user created successfully")
        except Exception as auth_error:
            logger.error(f"Auth user creation failed: {str(auth_error)}")
            # Try alternative approach: sign up the user
            logger.info("Attempting alternative signup method...")
            try:
                auth_response = self.db.auth.sign_up({
                    "email": vendor_email,
                    "password": password,
                    "options": {
                        "data": {
                            "role": user_role,
                            "full_name": vendor_full_name
                        }
                    }
                })
                auth_user_created = True
                logger.info("User signed up successfully")
            except Exception as signup_error:
                logger.error(f"User signup also failed: {str(signup_error)}")
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
        
        logger.info(f"User ID: {user_id}")
        
        # Create vendor profile using service
        try:
            await self.create_vendor_profile(
                user_id=user_id,
                email=vendor_email,
                full_name=vendor_full_name,
                age=age,
                gender=gender,
                user_role=user_role
            )
            logger.info("Vendor profile created successfully")
        except Exception as profile_error:
            logger.error(f"Vendor profile creation failed: {str(profile_error)}")
            # Cleanup: Delete the auth user if profile creation failed
            if auth_user_created:
                try:
                    self.db.auth.admin.delete_user(user_id)
                    logger.info("Cleaned up auth user after profile creation failure")
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup auth user: {str(cleanup_error)}")
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
            logger.info("Vendor linked to salon successfully")
        except Exception as link_error:
            logger.error(f"Vendor-salon linking failed: {str(link_error)}")
            # Cleanup: Delete the auth user and profile if linking failed
            if auth_user_created:
                try:
                    self.db.auth.admin.delete_user(user_id)
                    logger.info("Cleaned up auth user after salon linking failure")
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup auth user: {str(cleanup_error)}")
            # Try to delete vendor profile as well
            try:
                self.db.table("profiles").delete().eq("id", user_id).execute()
                logger.info("Cleaned up vendor profile after salon linking failure")
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup vendor profile: {str(cleanup_error)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to link vendor to salon"
            )
        
        # Generate access and refresh tokens
        token_data = {
            "sub": user_id,
            "email": vendor_email,
            "user_role": user_role
        }
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        logger.info(f"Vendor registration completed successfully for {vendor_email}")
        
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
                    "role": user_role
                }
            }
        }
    
    async def get_service_categories(self) -> List[Dict[str, Any]]:
        """
        Get all active service categories with their subcategories nested as a
        3-level taxonomy tree. Tree assembly is shared via ServiceTaxonomyResolver.
        """
        return await self._taxonomy().build_category_tree()


    def _apply_discount_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute discounted_price from price and discount_percentage.

        Business rules:
        - discount_percentage is optional
        - if discount_percentage is None or 0, remove discount fields
        - if price is 0, discount cannot be applied
        """
        price_raw = data.get("price", 0)
        discount_raw = data.get("discount_percentage")

        try:
            price = Decimal(str(price_raw or 0))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid price value"
            )

        if discount_raw is None:
            data["discount_percentage"] = None
            data["discounted_price"] = None
            return data

        try:
            discount_percentage = Decimal(str(discount_raw))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid discount percentage"
            )

        if discount_percentage < 0 or discount_percentage > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Discount percentage must be between 0 and 100"
            )

        if discount_percentage == 0:
            data["discount_percentage"] = None
            data["discounted_price"] = None
            return data

        if price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Discount can only be applied to services with price greater than 0"
            )

        discounted_price = (price * (Decimal("100") - discount_percentage) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        normalized_discount = discount_percentage.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        data["discount_percentage"] = float(normalized_discount)
        data["discounted_price"] = float(discounted_price)
        return data

    # =====================================================
    # SALON-WIDE DISCOUNT PROMOTIONS
    # =====================================================

    def _parse_promo_date(self, value: str, field_name: str) -> date:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid {field_name}. Use YYYY-MM-DD format.",
            ) from exc

    def _promo_status(self, promo: Dict[str, Any], today: date) -> str:
        start = promo.get("start_date")
        end = promo.get("end_date")
        if isinstance(start, str):
            start = datetime.strptime(start, "%Y-%m-%d").date()
        if end and isinstance(end, str):
            end = datetime.strptime(end, "%Y-%m-%d").date()

        if not promo.get("is_active"):
            return "inactive"
        if start and today < start:
            return "scheduled"
        if end and today > end:
            return "expired"
        return "active"

    def _serialize_promo(self, promo: Dict[str, Any], today: date, services_updated: int = 0) -> Dict[str, Any]:
        start = promo.get("start_date")
        end = promo.get("end_date")
        if hasattr(start, "isoformat"):
            start = start.isoformat()
        if end and hasattr(end, "isoformat"):
            end = end.isoformat()

        return {
            **promo,
            "start_date": start,
            "end_date": end,
            "status": self._promo_status(promo, today),
            "services_updated": services_updated,
        }

    async def _clear_salon_service_discounts(self, salon_id: str) -> None:
        services = self.db.table("services").select("id, price").eq(
            "salon_id", salon_id
        ).is_("deleted_at", "null").execute()
        for svc in services.data or []:
            payload = self._apply_discount_fields({
                "price": svc.get("price", 0),
                "discount_percentage": None,
            })
            self.db.table("services").update(payload).eq("id", svc["id"]).execute()

    def _discount_percentage_for_service(
        self,
        price: float,
        discount_type: str,
        discount_value: float,
    ) -> Optional[float]:
        if price <= 0:
            return None
        if discount_type == "percentage":
            return min(float(discount_value), 100.0)
        flat = float(discount_value)
        pct = (flat / float(price)) * 100
        return min(round(pct, 2), 100.0)

    async def _apply_promo_to_all_services(
        self,
        salon_id: str,
        discount_type: str,
        discount_value: float,
    ) -> int:
        services = self.db.table("services").select("id, price").eq(
            "salon_id", salon_id
        ).is_("deleted_at", "null").execute()
        updated = 0
        for svc in services.data or []:
            pct = self._discount_percentage_for_service(
                float(svc.get("price") or 0),
                discount_type,
                discount_value,
            )
            if pct is None or pct <= 0:
                continue
            payload = self._apply_discount_fields({
                "price": svc.get("price", 0),
                "discount_percentage": pct,
            })
            self.db.table("services").update(payload).eq("id", svc["id"]).execute()
            updated += 1
        return updated

    async def _sync_promotions_if_needed(self, salon_id: str) -> None:
        today = date.today()
        promos = self.db.table("salon_discount_promotions").select("*").eq(
            "salon_id", salon_id
        ).eq("is_active", True).order("created_at", desc=True).execute()

        expired_any = False
        for promo in promos.data or []:
            if self._promo_status(promo, today) == "expired":
                self.db.table("salon_discount_promotions").update(
                    {"is_active": False}
                ).eq("id", promo["id"]).execute()
                expired_any = True

        if expired_any:
            await self._clear_salon_service_discounts(salon_id)

        latest_resp = self.db.table("salon_discount_promotions").select("*").eq(
            "salon_id", salon_id
        ).eq("is_active", True).order("created_at", desc=True).limit(1).execute()

        latest = latest_resp.data[0] if latest_resp.data else None
        if not latest:
            return

        start = latest.get("start_date")
        if isinstance(start, str):
            start = datetime.strptime(start, "%Y-%m-%d").date()

        status_label = self._promo_status(latest, today)
        if status_label in ("active", "scheduled") and start and today >= start:
            await self._apply_promo_to_all_services(
                salon_id,
                latest["discount_type"],
                float(latest["discount_value"]),
            )

    async def apply_salon_promotion(
        self,
        vendor_id: str,
        promo: SalonPromoApplyRequest,
    ) -> Dict[str, Any]:
        salon_id = await self.get_vendor_salon_id(vendor_id)
        today = date.today()
        start = self._parse_promo_date(promo.start_date, "start_date")
        end = self._parse_promo_date(promo.end_date, "end_date") if promo.end_date else None

        if end and end < start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="End date must be on or after start date",
            )
        if end and end < today:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="End date cannot be in the past",
            )
        if promo.discount_type == "percentage" and promo.discount_value > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Percentage discount cannot exceed 100",
            )
        if promo.min_booking_amount is not None and promo.max_discount_limit is not None:
            if promo.max_discount_limit < promo.min_booking_amount:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Max discount limit should be greater than or equal to minimum booking amount",
                )

        await self._sync_promotions_if_needed(salon_id)

        self.db.table("salon_discount_promotions").update(
            {"is_active": False}
        ).eq("salon_id", salon_id).eq("is_active", True).execute()

        insert_data = {
            "salon_id": salon_id,
            "title": promo.title.strip(),
            "discount_type": promo.discount_type,
            "discount_value": promo.discount_value,
            "min_booking_amount": promo.min_booking_amount,
            "max_discount_limit": promo.max_discount_limit,
            "start_date": start.isoformat(),
            "end_date": end.isoformat() if end else None,
            "is_active": True,
        }
        created = self.db.table("salon_discount_promotions").insert(insert_data).execute()
        record = created.data[0] if created.data else None
        if not record:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create promotion",
            )

        services_updated = 0
        if today >= start and (end is None or today <= end):
            services_updated = await self._apply_promo_to_all_services(
                salon_id,
                promo.discount_type,
                promo.discount_value,
            )
        else:
            await self._clear_salon_service_discounts(salon_id)

        logger.info(
            f"Vendor {vendor_id} applied salon promo '{promo.title}' "
            f"({promo.discount_type}={promo.discount_value}), services_updated={services_updated}"
        )
        return self._serialize_promo(record, today, services_updated)

    async def get_active_salon_promotion(self, vendor_id: str) -> Optional[Dict[str, Any]]:
        salon_id = await self.get_vendor_salon_id(vendor_id)
        await self._sync_promotions_if_needed(salon_id)
        today = date.today()

        response = self.db.table("salon_discount_promotions").select("*").eq(
            "salon_id", salon_id
        ).eq("is_active", True).order("created_at", desc=True).limit(1).execute()

        if not response.data:
            return None

        promo = response.data[0]
        return self._serialize_promo(promo, today)

    # =====================================================
    # VENDOR COUPONS (code-based discounts, scoped to this salon)
    # =====================================================
    async def create_vendor_coupon(self, vendor_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        from app.services.coupon_service import CouponService
        # Defense in depth: the convenience fee is platform revenue, so vendors
        # may never waive it (also enforced in VendorCouponCreate schema).
        if data.get("applies_to") == "convenience_fee":
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vendors can only create service-discount coupons.",
            )
        salon_id = await self.get_vendor_salon_id(vendor_id)
        payload = {
            **data,
            "scope": "vendor",
            "salon_id": salon_id,
            "funded_by": "vendor",       # vendor sales come out of the vendor's take
            "created_by": vendor_id,
        }
        return await CouponService(self.db).create_coupon(payload)

    async def list_vendor_coupons(self, vendor_id: str) -> List[Dict[str, Any]]:
        from app.services.coupon_service import CouponService
        salon_id = await self.get_vendor_salon_id(vendor_id)
        return await CouponService(self.db).list_coupons(scope="vendor", salon_id=salon_id)

    async def update_vendor_coupon(
        self, vendor_id: str, coupon_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        from app.services.coupon_service import CouponService
        salon_id = await self.get_vendor_salon_id(vendor_id)
        return await CouponService(self.db).update_coupon(coupon_id, updates, salon_id=salon_id)

    async def deactivate_vendor_coupon(self, vendor_id: str, coupon_id: str) -> Dict[str, Any]:
        from app.services.coupon_service import CouponService
        salon_id = await self.get_vendor_salon_id(vendor_id)
        return await CouponService(self.db).deactivate_coupon(coupon_id, salon_id=salon_id)
