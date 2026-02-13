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
    salon_name: Optional[str] = None
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
        logger.info(f"Starting approval for request: {request_id}")
        
        # Step 1: Get and validate request
        try:
            request_data = await self._get_vendor_request(request_id)
        except ValueError as e:
            return ApprovalResult(success=False, error=str(e))
        
        # Step 2: Get system config (RM score, registration fee)
        config = await self._get_approval_config()
        
        warnings = []
        
        # Step 3: Update request status
        try:
            await self._update_request_status(request_id, admin_notes, admin_id)
        except Exception as e:
            return ApprovalResult(success=False, error=f"Failed to update request: {str(e)}")
        
        # Step 4: Geocode address if needed
        coordinates = await self._geocode_salon_address(request_data)
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
            logger.info(f"Created {services_created} services")
        
        # Step 7: Update RM score and get new total
        rm_new_score = None
        try:
            rm_new_score = await self._update_rm_score(request_data.rm_id, config['rm_score'], salon_id, request_data.business_name)
        except Exception as e:
            warnings.append(f"Failed to update RM score: {str(e)}")
        
        # Step 8: Get RM details for email notifications
        rm_email = None
        rm_name = None
        try:
            rm_details = await self._get_rm_details(request_data.rm_id)
            rm_email = rm_details.get("email")
            rm_name = rm_details.get("name", "RM")
        except Exception as e:
            warnings.append(f"Failed to get RM details: {str(e)}")
        
        # Step 9: Send approval email to vendor (skip if vendor email same as RM)
        try:
            await self._send_approval_email(request_id, salon_id, request_data, config, rm_email)
        except Exception as e:
            warnings.append(f"Failed to send vendor email: {str(e)}")
        
        # Step 10: Send notification email to RM
        try:
            if rm_email and rm_name:
                await self._send_rm_notification_email(
                    rm_email,
                    rm_name,
                    request_data.business_name, 
                    request_data.owner_name,
                    request_data.owner_email,
                    config['rm_score'],
                    rm_new_score,
                    config['registration_fee'],
                    salon_id
                )
            else:
                warnings.append("Could not send RM notification - RM details not found")
        except Exception as e:
            warnings.append(f"Failed to send RM notification: {str(e)}")
        except Exception as e:
            warnings.append(f"Failed to send RM notification: {str(e)}")
        
        logger.info(f"Vendor request {request_id} approved. Salon: {salon_id}")
        
        return ApprovalResult(
            success=True,
            salon_id=salon_id,
            salon_name=request_data.business_name,
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
        """Get RM score, penalty, and registration fee from system config"""
        # Get RM score for approval (with fallback)
        try:
            rm_score_response = self.db.table("system_config").select("config_value").eq(
                "config_key", "rm_score_per_approval"
            ).eq("is_active", True).maybe_single().execute()
            
            rm_score = int(rm_score_response.data.get("config_value", 10)) if rm_score_response.data else 10
        except Exception:
            rm_score = 10  # Default fallback
        
        # Get RM penalty for rejection (with fallback)
        try:
            penalty_response = self.db.table("system_config").select("config_value").eq(
                "config_key", "rm_score_penalty_rejection"
            ).eq("is_active", True).maybe_single().execute()
            
            rm_penalty = abs(int(penalty_response.data.get("config_value", 5))) if penalty_response.data else 5
        except Exception:
            rm_penalty = 5  # Default fallback
        
        # Get registration fee (with fallback)
        try:
            fee_response = self.db.table("system_config").select("config_value").eq(
                "config_key", "registration_fee_amount"
            ).eq("is_active", True).maybe_single().execute()
            
            registration_fee = float(fee_response.data.get("config_value", 5000)) if fee_response.data else 5000.0
        except Exception:
            registration_fee = 5000.0  # Default fallback
        
        return {
            "rm_score": rm_score,
            "rm_score_penalty_rejection": rm_penalty,
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
            logger.info(f"Using provided coordinates: {latitude}, {longitude}")
            return {"latitude": latitude, "longitude": longitude}
        
        # Try geocoding full address
        logger.info(f"Geocoding address for {request_data.business_name}...")
        full_address = f"{request_data.business_address}, {request_data.city}, {request_data.state}, {request_data.pincode}"
        
        try:
            coords = await geocoding_service.geocode_address(full_address)
            
            if coords:
                # geocode_address returns tuple (latitude, longitude)
                latitude, longitude = coords
                logger.info(f"Geocoded to: {latitude}, {longitude}")
                return {"latitude": latitude, "longitude": longitude}
            
            # Fallback to city-level geocoding
            logger.warning(f"Full address geocoding failed, trying city...")
            city_coords = await geocoding_service.geocode_address(
                f"{request_data.city}, {request_data.state}"
            )
            
            if city_coords:
                # geocode_address returns tuple (latitude, longitude)
                latitude, longitude = city_coords
                logger.info(f"City geocoded to: {latitude}, {longitude}")
                return {"latitude": latitude, "longitude": longitude}
            
            # Final fallback
            logger.error(f"All geocoding failed")
            return {"latitude": 0.0, "longitude": 0.0}
            
        except Exception as e:
            logger.error(f"Geocoding error: {str(e)}")
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
        
        # Extract cover_image_url from direct column (primary source)
        # Fallback to documents.cover_image for backward compatibility
        cover_image_url = getattr(request_data, "cover_image_url", None) or documents.get("cover_image")
        
        # Extract gallery_images from direct column (primary source)
        # Fallback to documents.cover_images for backward compatibility
        gallery_images_data = getattr(request_data, "gallery_images", None) or documents.get("cover_images", [])
        if isinstance(gallery_images_data, str):
            gallery_images = [gallery_images_data] if gallery_images_data else []
        else:
            gallery_images = gallery_images_data if isinstance(gallery_images_data, list) else []
        
        # Combine cover + gallery into cover_images array for database
        # Database uses cover_images (JSONB array) not cover_image_url
        cover_images_array = []
        if cover_image_url:
            cover_images_array.append(cover_image_url)
        cover_images_array.extend(gallery_images)
        
        # Extract logo from documents
        logo_url = documents.get("logo")
        
        # Extract business hours from direct columns (primary) or documents (fallback)
        opening_time = getattr(request_data, "opening_time", None) or documents.get("opening_time")
        closing_time = getattr(request_data, "closing_time", None) or documents.get("closing_time")
        working_days = getattr(request_data, "working_days", None) or documents.get("working_days", [])
        
        # Convert time objects to strings if needed (fix JSON serialization)
        if opening_time and hasattr(opening_time, 'strftime'):
            opening_time = opening_time.strftime('%H:%M:%S')
        if closing_time and hasattr(closing_time, 'strftime'):
            closing_time = closing_time.strftime('%H:%M:%S')
        
        # Note: vendor_id will be set when vendor completes registration
        # assigned_rm should be the RM user_id from request (not rm_id column)
        salon_data = {
            "vendor_id": getattr(request_data, "user_id", None),  # Will be set after vendor registers
            "assigned_rm": getattr(request_data, "user_id", None),  # RM who submitted this
            "join_request_id": request_id,  # Link salon to original vendor request
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
            "logo_url": logo_url,
            "cover_images": cover_images_array if cover_images_array else [],
            "opening_time": opening_time,
            "closing_time": closing_time,
            "working_days": working_days if isinstance(working_days, list) else [],
            "registration_fee_paid": False,
            "is_active": False,
            "is_verified": False
        }
        
        response = self.db.table("salons").insert(salon_data).execute()
        
        if not response.data:
            raise Exception("Failed to create salon - no data returned")
        
        salon_id = response.data[0]["id"]
        logger.info(f"Salon created: {salon_id}")
        
        return salon_id
    
    async def _create_salon_services(
        self,
        salon_id: str,
        request_data: VendorJoinRequestResponse
    ) -> int:
        """
        Create pre-filled services from RM submission.
        
        IMPORTANT: Services must have category_id to be inserted.
        This method now checks multiple data sources and provides detailed logging.
        """
        documents = request_data.documents or {}
        if isinstance(documents, str):
            import json
            documents = json.loads(documents)
        
        services_data = documents.get("services", [])
        
        # FIX: Also check services_offered if documents.services is empty or invalid
        if not services_data or not isinstance(services_data, list):
            logger.info(f"No services found in documents.services for salon {salon_id}")
            
            # Try to get services from services_offered column
            services_offered = getattr(request_data, "services_offered", None)
            if services_offered and isinstance(services_offered, dict):
                logger.info(f"Attempting to extract services from services_offered...")
                services_data = []
                
                # Get all service categories from database for mapping
                categories_response = self.db.table("service_categories").select("id, name").execute()
                category_map = {cat["name"]: cat["id"] for cat in (categories_response.data or [])}
                
                # Extract services from services_offered (grouped by category name)
                for category_name, service_list in services_offered.items():
                    category_id = category_map.get(category_name)
                    
                    if isinstance(service_list, list):
                        for svc in service_list:
                            if isinstance(svc, dict) and svc.get("name"):
                                services_data.append({
                                    "name": svc.get("name"),
                                    "category_id": category_id,
                                    "price": svc.get("price", 0),
                                    "duration_minutes": svc.get("duration_minutes", 30),
                                    "description": svc.get("description", "")
                                })
                
                if services_data:
                    logger.info(f"Extracted {len(services_data)} services from services_offered")
        
        if not services_data or not isinstance(services_data, list):
            logger.warning(f"No valid services data found for salon {salon_id}")
            return 0
        
        logger.info(f"Processing {len(services_data)} services for salon {salon_id}")
        
        try:
            services_to_insert = []
            skipped_services = []
            
            for service in services_data:
                service_name = service.get("name", "Unnamed Service")
                category_id = service.get("category_id")
                
                # FIX: Log detailed information about each service
                logger.debug(f"Processing service: {service_name}, category_id: {category_id}")
                
                if not category_id:
                    skipped_services.append(service_name)
                    logger.warning(f"Service '{service_name}' missing category_id - SKIPPING. "
                                 f"Raw service data: {service}")
                    continue
                
                # Validate required fields
                if not service_name or service_name == "Unnamed Service":
                    skipped_services.append(service_name)
                    logger.warning(f"Service missing name - SKIPPING. Raw data: {service}")
                    continue
                
                service_entry = {
                    "salon_id": salon_id,
                    "name": service_name,
                    "description": service.get("description", ""),
                    "price": float(service.get("price", 0)),
                    "duration_minutes": int(service.get("duration_minutes", 30)),
                    "category_id": category_id,
                    "is_active": True,
                    "is_featured": False
                }
                
                services_to_insert.append(service_entry)
            
            # FIX: Provide detailed summary
            if skipped_services:
                logger.error(
                    f"IMPORTANT: {len(skipped_services)} services were SKIPPED during migration: "
                    f"{', '.join(skipped_services)}. "
                    f"These services are missing category_id. Total services processed: {len(services_data)}, "
                    f"Valid services: {len(services_to_insert)}"
                )
            
            if services_to_insert:
                logger.info(f"Inserting {len(services_to_insert)} valid services for salon {salon_id}")
                logger.info(f"Service names: {[s['name'] for s in services_to_insert]}")
                
                response = self.db.table("services").insert(services_to_insert).execute()
                
                if response.data:
                    created_count = len(response.data)
                    logger.info(f"✅ Successfully created {created_count} services for salon {salon_id}")
                    
                    # FIX: Verify services were created correctly
                    verify_response = self.db.table("services").select("id, name").eq(
                        "salon_id", salon_id
                    ).execute()
                    if verify_response.data:
                        logger.info(f"Verification: Found {len(verify_response.data)} services in database for salon {salon_id}")
                    
                    return created_count
                else:
                    logger.error(f"❌ Services insert returned no data for salon {salon_id}")
                    return 0
            else:
                logger.error(
                    f"❌ NO SERVICES CREATED for salon {salon_id}! "
                    f"All {len(services_data)} services were skipped (missing category_id or name). "
                    f"Vendor will have NO services when they log in. "
                    f"Raw services data: {services_data}"
                )
                return 0
            
        except Exception as e:
            logger.error(f"❌ Failed to create services for salon {salon_id}: {str(e)}")
            logger.exception("Full traceback:")
            return 0
    
    async def _penalize_rm_for_rejection(
        self,
        rm_id: str,
        salon_name: str,
        rejection_reason: str
    ) -> None:
        """Deduct RM score for rejected vendor request (quality incentive)"""
        # Get penalty from system config (default -5 points)
        config_response = self.db.table("system_config").select("value").eq(
            "key", "rm_rejection_penalty"
        ).single().execute()
        
        penalty = int(config_response.data.get("value", -5)) if config_response.data else -5
        
        # Get current RM performance_score
        rm_response = self.db.table("rm_profiles").select(
            "performance_score"
        ).eq("id", rm_id).single().execute()
        
        current_score = rm_response.data.get("performance_score", 0) if rm_response.data else 0
        new_score = max(0, current_score + penalty)  # Don't go below 0
        
        # Update RM profile
        self.db.table("rm_profiles").update({
            "performance_score": new_score
        }).eq("id", rm_id).execute()
        
        logger.info(f"RM score penalized: {penalty} points (Total: {new_score})")
        
        # Add score history
        self.db.table("rm_score_history").insert({
            "rm_id": rm_id,
            "action": "salon_rejected",
            "points": penalty,
            "description": f"Salon rejected: {salon_name} - {rejection_reason[:100]}"
        }).execute()
    
    async def _send_approval_email(
        self,
        request_id: str,
        salon_id: str,
        request_data: VendorJoinRequestResponse,
        config: ApprovalConfig,
        rm_email: Optional[str] = None
    ) -> None:
        """Send approval email to vendor with registration link"""
        # Skip if owner email is same as RM email (testing scenario)
        if rm_email and request_data.owner_email.lower() == rm_email.lower():
            logger.info(f"Skipping vendor email - owner is the RM ({request_data.owner_email})")
            return
        
        # Generate registration token
        registration_token = create_registration_token(
            request_id=request_id,
            salon_id=salon_id,
            owner_email=request_data.owner_email
        )
        
        logger.info(f"Registration token generated for {request_data.owner_email}")
        
        # Send email
        email_sent = await email_service.send_vendor_approval_email(
            to_email=request_data.owner_email,
            owner_name=request_data.owner_name,
            salon_name=request_data.business_name,
            registration_token=registration_token,
            registration_fee=config["registration_fee"],
            salon_id=salon_id
        )
        
        if email_sent:
            logger.info(f"Approval email sent to {request_data.owner_email}")
        else:
            logger.warning(f"Failed to send approval email to {request_data.owner_email}")
    
    async def _send_rm_notification_email(
        self,
        rm_email: str,
        rm_name: str,
        salon_name: str,
        owner_name: str,
        owner_email: str,
        points_awarded: int,
        new_total_score: Optional[int],
        registration_fee: float,
        salon_id: Optional[str] = None
    ) -> None:
        """Send notification email to RM about salon approval"""
        try:
            # Send RM notification email
            email_sent = await email_service.send_rm_salon_approved_email(
                to_email=rm_email,
                rm_name=rm_name,
                salon_name=salon_name,
                owner_name=owner_name,
                owner_email=owner_email,
                points_awarded=points_awarded,
                new_total_score=new_total_score or 0,
                registration_fee=registration_fee,
                salon_id=salon_id
            )
            
            if email_sent:
                logger.info(f"RM notification sent to {rm_email}")
            else:
                logger.warning(f"Failed to send RM notification to {rm_email}")
                
        except Exception as e:
            logger.error(f"Error sending RM notification: {str(e)}")
            raise
    
    async def _get_rm_details(self, rm_id: str) -> Dict[str, str]:
        """Get RM email and name from database"""
        from fastapi import HTTPException, status
        
        rm_response = self.db.table("rm_profiles").select(
            "profiles(email, full_name)"
        ).eq("id", rm_id).execute()
        
        if not rm_response.data or len(rm_response.data) == 0 or not rm_response.data[0].get("profiles"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"RM profile not found for {rm_id}"
            )
        
        return {
            "email": rm_response.data[0]["profiles"]["email"],
            "name": rm_response.data[0]["profiles"]["full_name"] or "RM"
        }
    
    async def _update_rm_score(
        self, 
        rm_id: str, 
        score_points: int, 
        salon_id: str, 
        salon_name: str
    ) -> Optional[int]:
        """
        Update RM's performance score after successful salon approval.
        Uses RMService's update_rm_score method for consistency.
        Returns the new total score.
        """
        from app.services.rm_service import RMService
        
        rm_service = RMService(db_client=self.db)
        
        result = await rm_service.update_rm_score(
            rm_id=rm_id,
            score_change=score_points,
            reason=f"Salon '{salon_name}' approved and created",
            salon_id=salon_id,
            admin_id=None  # System-generated, not admin action
        )
        
        if result.success:
            logger.info(f"RM {rm_id} awarded {score_points} points (new total: {result.new_total_score})")
            return result.new_total_score
        else:
            logger.error(f"Failed to update RM score: {result.error}")
            raise Exception(result.error or "Failed to update RM score")
    
    async def _penalize_rm_for_rejection(
        self,
        rm_id: str,
        salon_name: str,
        rejection_reason: str
    ) -> None:
        """
        Deduct points from RM when their vendor request is rejected.
        Encourages quality submissions.
        """
        from app.services.rm_service import RMService
        
        # Get penalty from config (default -5 points)
        config_response = self.db.table("system_config").select(
            "rejection_penalty"
        ).eq("id", 1).single().execute()
        
        penalty = -5  # Default
        if config_response.data and "rejection_penalty" in config_response.data:
            penalty = -abs(config_response.data["rejection_penalty"])  # Ensure negative
        
        rm_service = RMService(db_client=self.db)
        
        result = await rm_service.update_rm_score(
            rm_id=rm_id,
            score_change=penalty,
            reason=f"Vendor request rejected: '{salon_name}' - {rejection_reason[:50]}",
            salon_id=None,
            admin_id=None
        )
        
        if result.success:
            logger.info(f"RM {rm_id} penalized {penalty} points (new total: {result.new_total_score})")
        else:
            logger.warning(f"Failed to penalize RM: {result.error}")
    
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
        
        # Penalize RM score for rejection
        try:
            config = await self._get_approval_config()
            score_penalty = config.get("rm_score_penalty_rejection", 5)  # Default 5 points penalty
            await self._penalize_rm_score(
                rm_id=request_data["rm_id"],
                score_penalty=score_penalty,
                request_id=request_id,
                salon_name=request_data["business_name"]
            )
        except Exception as e:
            logger.error(f"Failed to penalize RM score: {str(e)}", exc_info=True)
        
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
                rejection_reason=admin_notes,
                request_id=request_id
            )
            
            if not email_sent:
                logger.warning(f"Failed to send rejection email to {rm_email}")
        
        logger.info(f"Vendor request {request_id} rejected")
        
        return {
            "success": True,
            "message": "Vendor request rejected",
            "salon_id": request_id,
            "salon_name": request_data.get("business_name", "Unknown")
        }
    
    async def _penalize_rm_score(
        self,
        rm_id: str,
        score_penalty: int,
        request_id: str,
        salon_name: str
    ) -> None:
        """Penalize RM score for rejected request"""
        from app.services.rm_service import RMService
        
        rm_service = RMService(db_client=self.db)
        
        reason = f"Salon '{salon_name}' rejected"
        
        await rm_service.update_rm_score(
            rm_id=rm_id,
            score_change=-score_penalty,  # Negative for penalty
            reason=reason,
            salon_id=None
        )
        
        logger.info(f"RM {rm_id} penalized {score_penalty} points for rejection")
