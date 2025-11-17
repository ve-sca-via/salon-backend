"""
Vendor Approval Service - Business Logic Layer
Handles vendor join request approval workflow
"""
import uuid
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from app.core.database import get_db
from app.services.geocoding import geocoding_service
from app.services.email import email_service
from app.core.auth import create_registration_token
from app.schemas.response.vendor import VendorJoinRequestResponse
from app.schemas.request.vendor import Coordinates, ApprovalConfig

logger = logging.getLogger(__name__)


@dataclass
class ApprovalResult:
    """Result of vendor approval operation"""
    success: bool
    salon_id: Optional[str] = None
    rm_score_awarded: Optional[int] = None
    error: Optional[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class VendorApprovalService:
    """
    Service class handling vendor join request approval workflow.
    Follows Single Responsibility Principle.
    """
    
    def __init__(self, db_client):
        """Initialize service - uses centralized db client"""
        self.db = db_client
    
    async def approve_vendor_request(
        self,
        request_id: str,
        admin_notes: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> ApprovalResult:
        """
        Approve vendor join request - creates salon, updates RM score, sends email.
        
        Args:
            request_id: Vendor join request ID
            admin_notes: Optional notes from admin
            admin_id: ID of the admin who approved the request
            
        Returns:
            ApprovalResult with success status and salon details
        """
        logger.info(f"🔍 Starting approval for request: {request_id}")
        
        # Step 1: Get and validate request
        try:
            request_data = await self._get_vendor_request(request_id)
        except ValueError as e:
            return ApprovalResult(success=False, error=str(e))
        
        # Step 2: Get system config (RM score, registration fee)
        config = await self._get_approval_config()
        
        # Use transaction for multi-step operations
        async with self.db.transaction():
            # Step 3: Update request status
            try:
                await self._update_request_status(request_id, admin_notes, admin_id)
            except Exception as e:
                return ApprovalResult(success=False, error=f"Failed to update request: {str(e)}")
            
            # Step 4: Geocode address if needed
            coordinates = await self._geocode_salon_address(request_data)
            warnings = []
            if coordinates['latitude'] == 0.0:
                warnings.append("Geocoding failed - coordinates set to 0.0")
            
            # Step 5: Create salon
            try:
                salon_id = await self._create_salon(request_id, request_data, coordinates, config)
            except Exception as e:
                logger.error(f"Failed to create salon: {str(e)}")
                return ApprovalResult(success=False, error=str(e))
            
            # Step 6: Insert services if provided
            services_created = await self._create_salon_services(salon_id, request_data)
            if services_created:
                logger.info(f"✅ Created {services_created} services")
            
            # Step 7: Update RM score
            try:
                await self._update_rm_score(request_data.rm_id, config['rm_score'], salon_id, request_data.business_name)
            except Exception as e:
                warnings.append(f"Failed to update RM score: {str(e)}")
            
            # Step 8: Send approval email (within transaction context)
            try:
                await self._send_approval_email(request_id, salon_id, request_data, config)
            except Exception as e:
                warnings.append(f"Failed to send email: {str(e)}")
        
        logger.info(f"✅ Vendor request {request_id} approved. Salon: {salon_id}")
        
        return ApprovalResult(
            success=True,
            salon_id=salon_id,
            rm_score_awarded=config['rm_score'],
            warnings=warnings if warnings else None
        )
    
    async def _get_vendor_request(self, request_id: str) -> VendorJoinRequestResponse:
        """Get and validate vendor request and return a typed response model"""
        response = self.db.table("vendor_join_requests").select("*").eq("id", request_id).single().execute()

        if not response.data:
            raise ValueError(f"Request {request_id} not found")

        request_data = response.data

        if request_data.get("status") != "pending":
            raise ValueError(f"Request already {request_data.get('status')}")

        # Convert to response model for typed access, allow extra DB fields
        try:
            model = VendorJoinRequestResponse(**request_data)
        except Exception:
            # Fallback: create a minimal model using only known fields
            model = VendorJoinRequestResponse.parse_obj(request_data)

        return model
    
    async def _get_approval_config(self) -> Dict[str, Any]:
        """Get RM score and registration fee from system config"""
        # Get RM score
        rm_score_response = self.db.table("system_config").select("config_value").eq(
            "config_key", "rm_score_per_approval"
        ).eq("is_active", True).single().execute()
        
        rm_score = int(rm_score_response.data.get("config_value", 10)) if rm_score_response.data else 10
        
        # Get registration fee
        fee_response = self.db.table("system_config").select("config_value").eq(
            "config_key", "registration_fee_amount"
        ).eq("is_active", True).single().execute()
        
        registration_fee = float(fee_response.data.get("config_value", 5000)) if fee_response.data else 5000.0
        
        return {
            "rm_score": rm_score,
            "registration_fee": registration_fee
        }
    
    async def _update_request_status(self, request_id: str, admin_notes: Optional[str], admin_id: Optional[str] = None) -> None:
        """Update vendor request status to approved"""
        update_data = {
            "status": "approved",
            "admin_notes": admin_notes,
            "reviewed_at": "now()"
        }
        
        if admin_id:
            update_data["reviewed_by"] = admin_id
            
        self.db.table("vendor_join_requests").update(update_data).eq("id", request_id).execute()
    
    async def _geocode_salon_address(self, request_data: VendorJoinRequestResponse) -> Dict[str, float]:
        """
        Geocode salon address using geocoding service.
        Returns coordinates with fallback to 0.0 if failed.
        """
        latitude = getattr(request_data, "latitude", None)
        longitude = getattr(request_data, "longitude", None)
        
        # If coordinates already provided and valid, use them
        if latitude and longitude and latitude != 0.0 and longitude != 0.0:
            logger.info(f"✅ Using provided coordinates: {latitude}, {longitude}")
            return {"latitude": latitude, "longitude": longitude}
        
        # Try geocoding full address
        logger.info(f"🗺️ Geocoding address for {request_data.business_name}...")

        full_address = f"{request_data.business_address}, {request_data.city}, {request_data.state}, {request_data.pincode}"
        
        try:
            coords = await geocoding_service.geocode_address(full_address)
            
            if coords:
                # geocode_address returns tuple (latitude, longitude)
                latitude, longitude = coords
                logger.info(f"✅ Geocoded to: {latitude}, {longitude}")
                return {"latitude": latitude, "longitude": longitude}
            
            # Fallback to city-level geocoding
            logger.warning(f"⚠️ Full address geocoding failed, trying city...")
            city_coords = await geocoding_service.geocode_address(
                f"{request_data['city']}, {request_data['state']}"
            )
            
            if city_coords:
                # geocode_address returns tuple (latitude, longitude)
                latitude, longitude = city_coords
                logger.info(f"✅ City geocoded to: {latitude}, {longitude}")
                return {"latitude": latitude, "longitude": longitude}
            
            # Final fallback
            logger.error(f"❌ All geocoding failed")
            return {"latitude": 0.0, "longitude": 0.0}
            
        except Exception as e:
            logger.error(f"❌ Geocoding error: {str(e)}")
            return {"latitude": 0.0, "longitude": 0.0}
    
    async def _create_salon(
        self,
        request_id: str,
        request_data: VendorJoinRequestResponse,
        coordinates: Dict[str, float],
        config: ApprovalConfig
    ) -> str:
        """Create salon entry in database"""
        # Extract documents JSON
        documents = request_data.documents or {}
        if isinstance(documents, str):
            import json
            documents = json.loads(documents)
        
        # Extract cover images - convert single image to array
        cover_images_data = documents.get("cover_image") or documents.get("cover_images", [])
        if isinstance(cover_images_data, str):
            cover_images = [cover_images_data] if cover_images_data else []
        else:
            cover_images = cover_images_data if isinstance(cover_images_data, list) else []
        
        # Note: vendor_id will be set when vendor completes registration
        # assigned_rm should be the RM user_id from request (not rm_id column)
        salon_data = {
            "vendor_id": getattr(request_data, "user_id", None),  # Will be set after vendor registers
            "assigned_rm": getattr(request_data, "user_id", None),  # RM who submitted this
            "business_name": request_data.business_name,
            "description": documents.get("description"),
            "phone": request_data.owner_phone,
            "email": request_data.owner_email,
            "address": request_data.business_address,
            "city": request_data.city,
            "state": request_data.state,
            "pincode": request_data.pincode,
            "latitude": coordinates["latitude"],
            "longitude": coordinates["longitude"],
            "gst_number": getattr(request_data, "gst_number", None),
            "pan_number": getattr(request_data, "pan_number", None),
            "logo_url": documents.get("logo"),
            "cover_images": cover_images,
            "opening_time": documents.get("opening_time"),
            "closing_time": documents.get("closing_time"),
            "working_days": documents.get("working_days", []),
            "registration_fee_paid": False,
            "is_active": False,
            "is_verified": False
        }
        
        response = self.db.table("salons").insert(salon_data).execute()
        
        if not response.data:
            raise Exception("Failed to create salon - no data returned")
        
        salon_id = response.data[0]["id"]
        logger.info(f"✅ Salon created: {salon_id}")
        
        return salon_id
    
    async def _create_salon_services(
        self,
        salon_id: str,
        request_data: VendorJoinRequestResponse
    ) -> int:
        """
        Create pre-filled services from RM submission.
        
        IMPORTANT: Maps service names to category_id using service_categories table.
        If no match found, service is created with category_id = NULL (vendor must set later).
        """
        documents = request_data.documents or {}
        if isinstance(documents, str):
            import json
            documents = json.loads(documents)
        
        services_data = documents.get("services", [])
        
        if not services_data or not isinstance(services_data, list):
            return 0
        
        try:
            services_to_insert = []
            
            for service in services_data:
                # RM must provide category_id via dropdown selection
                category_id = service.get("category_id")
                
                if not category_id:
                    logger.warning(f"⚠️ Service '{service.get('name')}' missing category_id - skipping")
                    continue
                
                service_entry = {
                    "salon_id": salon_id,
                    "name": service.get("name", ""),
                    "description": service.get("description", ""),
                    "price": float(service.get("price", 0)),
                    "duration_minutes": int(service.get("duration_minutes", 30)),
                    "category_id": category_id,
                    "is_active": True,
                    "available_for_booking": True
                }
                
                services_to_insert.append(service_entry)
            
            if services_to_insert:
                logger.info(f"📝 Inserting {len(services_to_insert)} services for salon {salon_id}")
                logger.debug(f"Services data: {services_to_insert}")
                
                response = self.db.table("services").insert(services_to_insert).execute()
                
                if response.data:
                    logger.info(f"✅ Successfully created {len(response.data)} services")
                    return len(response.data)
                else:
                    logger.warning("⚠️ Services insert returned no data")
                    return 0
            
        except Exception as e:
            logger.error(f"❌ Failed to create services: {str(e)}")
            logger.exception("Full traceback:")
        
        return 0
    
    async def _update_rm_score(
        self,
        rm_id: str,
        score_change: int,
        salon_id: str,
        salon_name: str
    ) -> None:
        """Update RM score and create history entry"""
        # Get current RM performance_score
        rm_response = self.db.table("rm_profiles").select(
            "performance_score"
        ).eq("id", rm_id).single().execute()
        
        current_score = rm_response.data.get("performance_score", 0) if rm_response.data else 0
        
        # Update RM profile
        self.db.table("rm_profiles").update({
            "performance_score": current_score + score_change
        }).eq("id", rm_id).execute()
        
        logger.info(f"📊 RM score updated: +{score_change} points (Total: {current_score + score_change})")
        
        # Add score history (match schema: action, points, description)
        self.db.table("rm_score_history").insert({
            "rm_id": rm_id,
            "action": "salon_approved",
            "points": score_change,
            "description": f"Salon approved: {salon_name}"
        }).execute()
    
    async def _send_approval_email(
        self,
        request_id: str,
        salon_id: str,
        request_data: VendorJoinRequestResponse,
        config: ApprovalConfig
    ) -> None:
        """Send approval email to vendor with registration link"""
        # Generate registration token
        registration_token = create_registration_token(
            request_id=request_id,
            salon_id=salon_id,
            owner_email=request_data.owner_email
        )
        
        logger.info(f"🔐 Registration token generated for {request_data.owner_email}")
        
        # Send email
        email_sent = await email_service.send_vendor_approval_email(
            to_email=request_data.owner_email,
            owner_name=request_data.owner_name,
            salon_name=request_data.business_name,
            registration_token=registration_token,
            registration_fee=config.registration_fee
        )
        
        if email_sent:
            logger.info(f"✉️ Approval email sent to {request_data.owner_email}")
        else:
            logger.warning(f"⚠️ Failed to send approval email to {request_data.owner_email}")
    
    async def reject_vendor_request(
        self,
        request_id: str,
        admin_notes: str,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reject vendor join request and notify RM.
        
        Returns:
            Dict with success status and message
        """
        # Get request
        request_response = self.db.table("vendor_join_requests").select("*").eq("id", request_id).single().execute()
        
        if not request_response.data:
            raise ValueError("Request not found")
        
        request_data = request_response.data
        
        if request_data.get("status") != "pending":
            raise ValueError(f"Request already {request_data.get('status')}")
        
        # Update status
        update_data = {
            "status": "rejected",
            "admin_notes": admin_notes,
            "reviewed_at": "now()"
        }
        
        if admin_id:
            update_data["reviewed_by"] = admin_id
            
        self.db.table("vendor_join_requests").update(update_data).eq("id", request_id).execute()
        
        # Get RM details and send email
        rm_response = self.db.table("rm_profiles").select(
            "*, profiles(email, full_name)"
        ).eq("id", request_data["rm_id"]).single().execute()
        
        if rm_response.data and rm_response.data.get("profiles"):
            rm_email = rm_response.data["profiles"]["email"]
            rm_name = rm_response.data["profiles"]["full_name"]
            
            # Send rejection email to RM
            email_sent = await email_service.send_vendor_rejection_email(
                to_email=rm_email,
                rm_name=rm_name,
                salon_name=request_data["business_name"],
                owner_name=request_data["owner_name"],
                rejection_reason=admin_notes
            )
            
            if not email_sent:
                logger.warning(f"Failed to send rejection email to {rm_email}")
        
        logger.info(f"❌ Vendor request {request_id} rejected")
        
        return {
            "success": True,
            "message": "Vendor request rejected"
        }
