"""
Vendor Approval Service - Business Logic Layer
Handles vendor join request approval workflow
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from app.services.geocoding import geocoding_service
from app.services.email import email_service
from app.core.auth import create_registration_token
from app.schemas.response.vendor import VendorJoinRequestResponse
from app.utils.location_text import normalize_city_name

logger = logging.getLogger(__name__)


@dataclass
class ApprovalResult:
    """Result of vendor approval operation"""
    success: bool
    salon_id: Optional[str] = None
    salon_name: Optional[str] = None
    rm_score_awarded: Optional[int] = None
    rm_new_score: Optional[int] = None
    error: Optional[str] = None
    # Machine-readable reason so the API can map to 404/409 instead of a blanket 500
    error_code: Optional[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class RequestNotFoundError(ValueError):
    """Vendor join request does not exist"""


class RequestAlreadyReviewedError(ValueError):
    """Vendor join request has already been approved or rejected"""


class VendorApprovalService:
    """
    Service class handling vendor join request approval workflow.
    Follows Single Responsibility Principle.
    """
    
    def __init__(self, db_client):
        """Initialize service - uses centralized db client"""
        self.db = db_client

    @staticmethod
    def _ensure_request_pending(request_data: Dict[str, Any]) -> None:
        """Raise ValueError if the vendor request is not in 'pending' state."""
        current_status = request_data.get("status")
        if current_status != "pending":
            raise RequestAlreadyReviewedError(f"Request already {current_status}")

    async def approve_vendor_request(
        self,
        request_id: str,
        admin_notes: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> ApprovalResult:
        """
        Approve vendor join request - claims the request, creates the salon and
        updates the RM score.

        Emails are NOT sent here: notification delivery is slow and unreliable
        compared to the database work, and used to keep the admin's HTTP request
        open long enough to time out (leaving the UI showing a failure for an
        approval that had actually succeeded). Callers should schedule
        ``send_approval_notifications`` as a background task afterwards.

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
        except RequestNotFoundError as e:
            return ApprovalResult(success=False, error=str(e), error_code="not_found")
        except RequestAlreadyReviewedError as e:
            return ApprovalResult(success=False, error=str(e), error_code="already_reviewed")

        # Step 2: Get system config (RM score, registration fee)
        config = await self._get_approval_config()

        warnings = []

        # Step 3: Claim the request (atomic pending -> approved). Doing this first
        # means a double-clicked Approve button can't create two salons; the second
        # call finds no pending row and stops here.
        try:
            claimed = await self._claim_request(request_id, admin_notes, admin_id)
        except Exception as e:
            return ApprovalResult(success=False, error=f"Failed to update request: {str(e)}")

        if not claimed:
            return ApprovalResult(
                success=False,
                error="Request has already been reviewed",
                error_code="already_reviewed"
            )

        # Step 4: Geocode address if needed
        coordinates = await self._geocode_salon_address(request_data)
        if coordinates['latitude'] == 0.0:
            warnings.append("Geocoding failed - coordinates set to 0.0")

        # Step 5: Create salon. If this fails the request must go back to pending,
        # otherwise it is stuck as "approved" with no salon and no way to retry.
        try:
            salon_id = await self._create_salon(request_id, request_data, coordinates, config)
        except Exception as e:
            logger.error(f"Failed to create salon: {str(e)}")
            await self._release_request(request_id)
            return ApprovalResult(success=False, error=str(e))

        # Services are no longer created at approval time — vendors add their own
        # services (category / subcategory / sub-subcategory) after onboarding.

        # Step 6: Update RM score and get new total
        rm_new_score = None
        try:
            rm_new_score = await self._update_rm_score(request_data.rm_id, config['rm_score'], salon_id, request_data.business_name)
        except Exception as e:
            warnings.append(f"Failed to update RM score: {str(e)}")

        logger.info(f"Vendor request {request_id} approved. Salon: {salon_id}")

        return ApprovalResult(
            success=True,
            salon_id=salon_id,
            salon_name=request_data.business_name,
            rm_score_awarded=config['rm_score'],
            rm_new_score=rm_new_score,
            warnings=warnings if warnings else None
        )

    async def send_approval_notifications(
        self,
        request_id: str,
        salon_id: str,
        rm_new_score: Optional[int] = None,
        vendor_only: bool = False,
        force_vendor_email: bool = False
    ) -> Dict[str, Any]:
        """
        Send the vendor registration email and the RM notification for an already
        approved request.

        Re-reads the request so it is safe to run detached from the approval call
        (background task) and safe to re-run from the admin "resend" action.

        Args:
            request_id: Vendor join request ID
            salon_id: Salon created for this request
            rm_new_score: RM total after approval (falls back to their current score)
            vendor_only: Skip the RM notification (used by the admin resend action)
            force_vendor_email: Send to the owner even when they are also the RM

        Returns:
            Dict with per-recipient delivery status and any errors.
        """
        result: Dict[str, Any] = {
            "vendor_email_sent": False,
            "rm_email_sent": False,
            "errors": []
        }

        try:
            request_data = await self._get_vendor_request(request_id, require_pending=False)
            config = await self._get_approval_config()
        except Exception as e:
            logger.error(f"Cannot send approval notifications for {request_id}: {e}")
            result["errors"].append(str(e))
            return result

        # RM details are needed both for the RM email and for the "owner is the RM"
        # check below, but a missing RM profile must not block the vendor email.
        rm_email = None
        rm_name = None
        try:
            rm_details = await self._get_rm_details(request_data.rm_id)
            rm_email = rm_details.get("email")
            rm_name = rm_details.get("name", "RM")
            if rm_new_score is None:
                rm_new_score = rm_details.get("performance_score")
        except Exception as e:
            result["errors"].append(f"Failed to get RM details: {str(e)}")

        try:
            result["vendor_email_sent"] = await self._send_approval_email(
                request_id, salon_id, request_data, config,
                rm_email=None if force_vendor_email else rm_email
            )
        except Exception as e:
            logger.error(f"Failed to send vendor approval email for {request_id}: {e}", exc_info=True)
            result["errors"].append(f"Failed to send vendor email: {str(e)}")

        if vendor_only:
            return result

        try:
            if rm_email and rm_name:
                result["rm_email_sent"] = await self._send_rm_notification_email(
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
                result["errors"].append("Could not send RM notification - RM details not found")
        except Exception as e:
            logger.error(f"Failed to send RM notification for {request_id}: {e}", exc_info=True)
            result["errors"].append(f"Failed to send RM notification: {str(e)}")

        return result

    async def _get_vendor_request(
        self,
        request_id: str,
        require_pending: bool = True
    ) -> VendorJoinRequestResponse:
        """Get vendor request and return a typed response model"""
        response = self.db.table("vendor_join_requests").select("*").eq("id", request_id).maybe_single().execute()

        if not response or not response.data:
            raise RequestNotFoundError(f"Request {request_id} not found")

        request_data = response.data

        if require_pending:
            self._ensure_request_pending(request_data)

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
                "config_key", "rm_rejection_penalty"
            ).eq("is_active", True).maybe_single().execute()
            
            rm_penalty = abs(int(penalty_response.data.get("config_value", 5))) if penalty_response.data else 5
        except Exception:
            rm_penalty = 5  # Default fallback
        
        # Get registration fee (no fallback - must exist in database)
        try:
            fee_response = self.db.table("system_config").select("config_value").eq(
                "config_key", "registration_fee_amount"
            ).eq("is_active", True).maybe_single().execute()
            
            if not fee_response.data:
                logger.error("CRITICAL: registration_fee_amount not found in system_config")
                raise ValueError("Registration fee configuration missing")
            
            registration_fee = float(fee_response.data.get("config_value"))
        except Exception as e:
            logger.error(f"Failed to fetch registration fee config: {e}")
            raise
        
        return {
            "rm_score": rm_score,
            "rm_rejection_penalty": rm_penalty,
            "registration_fee": registration_fee
        }
    
    async def _claim_request(
        self,
        request_id: str,
        admin_notes: Optional[str],
        admin_id: Optional[str] = None
    ) -> bool:
        """
        Flip the request from 'pending' to 'approved', but only if it is still
        pending. The extra ``status = pending`` filter makes this a compare-and-swap:
        two concurrent approvals (double-clicked button, retried request) race on
        the database, and only one of them gets rows back.

        Returns:
            True if this call claimed the request, False if someone else already did.
        """
        update_data = {
            "status": "approved",
            "admin_notes": admin_notes,
            "reviewed_at": datetime.utcnow().isoformat()
        }

        if admin_id:
            update_data["reviewed_by"] = admin_id

        response = self.db.table("vendor_join_requests").update(update_data).eq(
            "id", request_id
        ).eq("status", "pending").execute()

        return bool(response.data)

    async def _release_request(self, request_id: str) -> None:
        """
        Put a claimed request back to 'pending' after a failed approval, so the
        admin can simply press Approve again instead of being told it was
        'already approved' for a salon that was never created.
        """
        try:
            self.db.table("vendor_join_requests").update({
                "status": "pending",
                "reviewed_at": None,
                "reviewed_by": None
            }).eq("id", request_id).eq("status", "approved").execute()
            logger.info(f"Rolled request {request_id} back to pending after failed approval")
        except Exception as e:
            logger.error(f"Failed to roll back request {request_id} to pending: {e}")


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
            logger.warning("Full address geocoding failed, trying city...")
            city_coords = await geocoding_service.geocode_address(
                f"{request_data.city}, {request_data.state}"
            )
            
            if city_coords:
                # geocode_address returns tuple (latitude, longitude)
                latitude, longitude = city_coords
                logger.info(f"City geocoded to: {latitude}, {longitude}")
                return {"latitude": latitude, "longitude": longitude}
            
            # Final fallback
            logger.error("All geocoding failed")
            return {"latitude": 0.0, "longitude": 0.0}
            
        except Exception as e:
            logger.error(f"Geocoding error: {str(e)}")
            return {"latitude": 0.0, "longitude": 0.0}
    
    async def _create_salon(
        self,
        request_id: str,
        request_data: VendorJoinRequestResponse,
        coordinates: Dict[str, float],
        config: Dict[str, Any]
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
        
        # Extract business hours from documents (primary source now)
        # Format in documents.business_hours: {"monday": "9:00 AM - 6:00 PM", ...}
        business_hours = documents.get("business_hours", {})
        opening_time = None
        closing_time = None
        working_days = []
        
        if business_hours and isinstance(business_hours, dict):
            opening_times = []
            closing_times = []
            
            # Map day names to ensure consistent order if needed, but here we just need all times
            for day, hours_str in business_hours.items():
                if hours_str and hours_str != 'Closed' and ' - ' in hours_str:
                    try:
                        working_days.append(day.capitalize())
                        open_str, close_str = hours_str.split(' - ')
                        
                        # Parse "9:00 AM" to time object
                        open_dt = datetime.strptime(open_str.strip(), '%I:%M %p')
                        close_dt = datetime.strptime(close_str.strip(), '%I:%M %p')
                        
                        opening_times.append(open_dt.time())
                        closing_times.append(close_dt.time())
                    except (ValueError, AttributeError) as e:
                        logger.warning(f"Failed to parse hours for {day}: {hours_str}. Error: {e}")
            
            if opening_times:
                opening_time = min(opening_times).strftime('%H:%M:%S')
            if closing_times:
                closing_time = max(closing_times).strftime('%H:%M:%S')
        
        # Fallback to direct columns if documents parsing failed or returned nothing
        if not opening_time:
            opening_time = getattr(request_data, "opening_time", None)
            if opening_time and hasattr(opening_time, 'strftime'):
                opening_time = opening_time.strftime('%H:%M:%S')
                
        if not closing_time:
            closing_time = getattr(request_data, "closing_time", None)
            if closing_time and hasattr(closing_time, 'strftime'):
                closing_time = closing_time.strftime('%H:%M:%S')
                
        if not working_days:
            working_days = getattr(request_data, "working_days", [])
        
        # Note: vendor_id will be set when vendor completes registration
        # assigned_rm should be the RM user_id from request (not rm_id column)
        salon_data = {
            "vendor_id": getattr(request_data, "user_id", None),  # Will be set after vendor registers
            "assigned_rm": request_data.rm_id,  # RM who submitted this
            "join_request_id": request_id,  # Link salon to original vendor request
            "business_name": request_data.business_name,
            "description": documents.get("description"),
            "outlet": getattr(request_data, "outlet", None) or documents.get("outlet", None),
            "phone": request_data.owner_phone,
            "email": request_data.owner_email,
            "address": request_data.business_address,
            "city": normalize_city_name(request_data.city),
            "state": request_data.state,
            "pincode": request_data.pincode,
            "latitude": coordinates["latitude"],
            "longitude": coordinates["longitude"],
            "gst_number": getattr(request_data, "gst_number", None),
            "is_gst": getattr(request_data, "is_gst", False) or documents.get("is_gst", False),
            "pan_number": getattr(request_data, "pan_number", None),
            "logo_url": logo_url,
            "cover_images": cover_images_array if cover_images_array else [],
            "agreement_document_url": getattr(request_data, "registration_certificate", None),  # Agreement document
            "opening_time": opening_time,
            "closing_time": closing_time,
            "working_days": working_days if isinstance(working_days, list) else [],
            "business_hours": business_hours,
            "facilities": getattr(request_data, "facilities", None) or documents.get("facilities", None),
            "salon_type": getattr(request_data, "request_type", "salon"),
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
    
    async def _send_approval_email(
        self,
        request_id: str,
        salon_id: str,
        request_data: VendorJoinRequestResponse,
        config: Dict[str, Any],
        rm_email: Optional[str] = None
    ) -> bool:
        """Send approval email to vendor with registration link"""
        if not request_data.owner_email:
            logger.error(f"Request {request_id} has no owner email - cannot send approval email")
            return False

        # Skip if owner email is same as RM email (testing scenario). NOTE: the RM
        # notification does not carry the registration link, so an RM who submits a
        # salon under their own email gets no registration link at all - use the
        # resend-approval-email admin action for that case.
        if rm_email and request_data.owner_email.lower() == rm_email.lower():
            logger.info(f"Skipping vendor email - owner is the RM ({request_data.owner_email})")
            return True

        # Generate registration token
        registration_token = create_registration_token(
            request_id=request_id,
            salon_id=salon_id,
            owner_email=request_data.owner_email,
            request_type=getattr(request_data, "request_type", "salon")
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
            logger.error(
                f"Failed to send approval email to {request_data.owner_email} "
                f"(request {request_id}, salon {salon_id}) - vendor has no registration link"
            )

        return email_sent


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
    ) -> bool:
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

            return email_sent

        except Exception as e:
            logger.error(f"Error sending RM notification: {str(e)}")
            raise
    
    async def _get_rm_details(self, rm_id: str) -> Dict[str, Any]:
        """Get RM email, name and current score from database"""
        from fastapi import HTTPException, status

        rm_response = self.db.table("rm_profiles").select(
            "performance_score, profiles(email, full_name)"
        ).eq("id", rm_id).execute()

        if not rm_response.data or len(rm_response.data) == 0 or not rm_response.data[0].get("profiles"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"RM profile not found for {rm_id}"
            )

        row = rm_response.data[0]

        return {
            "email": row["profiles"]["email"],
            "name": row["profiles"]["full_name"] or "RM",
            "performance_score": row.get("performance_score")
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
        request_response = self.db.table("vendor_join_requests").select("*").eq("id", request_id).maybe_single().execute()

        if not request_response or not request_response.data:
            raise RequestNotFoundError(f"Request {request_id} not found")

        request_data = request_response.data

        self._ensure_request_pending(request_data)

        # Update status
        update_data = {
            "status": "rejected",
            "admin_notes": admin_notes,
            "reviewed_at": datetime.utcnow().isoformat()
        }
        
        if admin_id:
            update_data["reviewed_by"] = admin_id
            
        self.db.table("vendor_join_requests").update(update_data).eq("id", request_id).execute()
        
        # Penalize RM score for rejection
        try:
            config = await self._get_approval_config()
            score_penalty = config.get("rm_rejection_penalty", 5)  # Default 5 points penalty
            await self._penalize_rm_score(
                rm_id=request_data["rm_id"],
                score_penalty=score_penalty,
                request_id=request_id,
                salon_name=request_data["business_name"]
            )
        except Exception as e:
            logger.error(f"Failed to penalize RM score: {str(e)}", exc_info=True)
        
        # Get RM details and send rejection email (reuse shared fetch helper).
        # A missing RM profile is non-fatal: the request is still rejected and we
        # simply skip the notification email (preserves prior behavior).
        try:
            rm_details = await self._get_rm_details(request_data["rm_id"])
            rm_email = rm_details["email"]
            rm_name = rm_details["name"]

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
        except Exception as e:
            logger.warning(f"Could not send RM rejection notification: {str(e)}")
        
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
