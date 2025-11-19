"""
Relationship Manager (RM) Service - Business Logic Layer
Handles RM profile management, scoring, and vendor request tracking
"""
import uuid
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.database import get_db
from app.schemas import VendorJoinRequestCreate
from app.schemas.request.rm import RMProfileUpdate

logger = logging.getLogger(__name__)


@dataclass
class RMScoreUpdate:
    """RM score update result"""
    success: bool
    new_total_score: int
    score_change: int
    error: Optional[str] = None


@dataclass
class VendorRequestStats:
    """Statistics for vendor requests by RM"""
    total_requests: int
    pending_requests: int
    approved_requests: int
    rejected_requests: int
    total_score: int


class RMService:
    """
    Service class for Relationship Manager operations.
    Handles RM profiles, scoring, and vendor request tracking.
    """
    
    def __init__(self, db_client):
        """Initialize service with database client"""
        self.db = db_client
    
    async def get_rm_profile(self, rm_id: str) -> Dict[str, Any]:
        """
        Get RM profile with associated user profile.
        
        Args:
            rm_id: RM profile ID
            
        Returns:
            RM profile data with user details
        """
        # Note: rm_profiles.id and profiles.id both reference auth.users.id
        # Since there's no direct FK between them, we fetch separately
        response = self.db.table("rm_profiles").select("*").eq("id", rm_id).single().execute()
        
        if not response.data:
            raise ValueError(f"RM profile {rm_id} not found")
        
        return response.data
    
    async def get_rm_stats(self, rm_id: str) -> VendorRequestStats:
        """
        Get comprehensive stats for RM's vendor requests.
        
        Args:
            rm_id: RM profile ID
            
        Returns:
            VendorRequestStats with all metrics
        """
        # Get RM profile for performance score
        rm_profile = await self.get_rm_profile(rm_id)
        
        # Get all requests created by this RM (via rm_id)
        requests_response = self.db.table("vendor_join_requests").select(
            "status"
        ).eq("rm_id", rm_id).execute()
        
        requests = requests_response.data or []
        
        # Count by status
        pending = sum(1 for r in requests if r["status"] == "pending")
        approved = sum(1 for r in requests if r["status"] == "approved")
        rejected = sum(1 for r in requests if r["status"] == "rejected")
        
        return VendorRequestStats(
            total_requests=len(requests),
            pending_requests=pending,
            approved_requests=approved,
            rejected_requests=rejected,
            total_score=rm_profile.get("performance_score", 0)
        )
    
    async def list_rm_profiles(
        self,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "performance_score",
        order_desc: bool = True
    ) -> List[Dict[str, Any]]:
        """
        List all RM profiles with pagination and sorting.
        
        Args:
            limit: Max results to return
            offset: Number of results to skip
            order_by: Field to sort by (performance_score, full_name, email)
            order_desc: Sort descending if True
            
        Returns:
            List of RM profiles with user details
        """
        query = self.db.table("rm_profiles").select(
            "*, profiles(id, full_name, email, phone, is_active)"
        )
        
        # Apply ordering
        if order_desc:
            query = query.order(order_by, desc=True)
        else:
            query = query.order(order_by, desc=False)
        
        # Apply pagination
        query = query.range(offset, offset + limit - 1)
        
        response = query.execute()
        
        return response.data or []
    
    async def update_rm_score(
        self,
        rm_id: str,
        score_change: int,
        reason: str,
        salon_id: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> RMScoreUpdate:
        """
        Update RM score with history tracking.
        
        Args:
            rm_id: RM profile ID
            score_change: Points to add (positive) or subtract (negative)
            reason: Explanation for score change
            salon_id: Optional related salon ID
            admin_id: Optional admin who made the change
            
        Returns:
            RMScoreUpdate with new total and change
        """
        try:
            # Get current score
            rm_response = self.db.table("rm_profiles").select(
                "performance_score"
            ).eq("id", rm_id).single().execute()
            
            if not rm_response.data:
                return RMScoreUpdate(
                    success=False,
                    new_total_score=0,
                    score_change=0,
                    error="RM profile not found"
                )
            
            current_score = rm_response.data.get("performance_score", 0)
            new_score = current_score + score_change
            
            # Ensure score doesn't go negative
            if new_score < 0:
                new_score = 0
                score_change = -current_score
            
            # Update score
            self.db.table("rm_profiles").update({
                "performance_score": new_score
            }).eq("id", rm_id).execute()
            
            # Add history entry (match actual schema: action, points, description)
            history_data = {
                "rm_id": rm_id,
                "action": reason[:100] if reason else "score_update",
                "points": score_change,
                "description": reason
            }
            
            self.db.table("rm_score_history").insert(history_data).execute()
            
            logger.info(f"📊 RM {rm_id} score updated: {current_score} → {new_score} ({score_change:+d})")
            
            return RMScoreUpdate(
                success=True,
                new_total_score=new_score,
                score_change=score_change
            )
            
        except Exception as e:
            logger.error(f"Failed to update RM score: {str(e)}")
            return RMScoreUpdate(
                success=False,
                new_total_score=0,
                score_change=0,
                error=str(e)
            )
    
    async def get_rm_score_history(
        self,
        rm_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get RM's score change history.
        
        Args:
            rm_id: RM profile ID
            limit: Max entries to return
            
        Returns:
            List of score history entries
        """
        response = self.db.table("rm_score_history").select(
            "*"
        ).eq("rm_id", rm_id).order("created_at", desc=True).limit(limit).execute()
        
        return response.data or []
    
    async def get_rm_vendor_requests(
        self,
        rm_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get vendor join requests submitted by RM.
        
        Args:
            rm_id: RM profile ID (user_id)
            status: Filter by status (pending, approved, rejected)
            limit: Max results
            offset: Pagination offset
            
        Returns:
            List of vendor requests
        """
        query = self.db.table("vendor_join_requests").select("*").eq("rm_id", rm_id)
        
        if status:
            query = query.eq("status", status)
        
        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
        
        response = query.execute()
        
        return response.data or []
    
    async def get_rm_salons(
        self,
        rm_id: str,
        include_inactive: bool = False,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get all salons associated with this RM.
        
        Args:
            rm_id: RM profile ID
            include_inactive: If True, include inactive salons
            limit: Max results
            
        Returns:
            List of salons
        """
        query = self.db.table("salons").select("*").eq("assigned_rm", rm_id)
        
        if not include_inactive:
            query = query.eq("is_active", True)
        
        query = query.order("created_at", desc=True).limit(limit)
        
        response = query.execute()
        
        return response.data or []
    
    async def update_rm_profile(
        self,
        rm_id: str,
        updates: "RMProfileUpdate"
    ) -> Dict[str, Any]:
        """
        Update RM profile fields (excluding protected fields).
        
        Args:
            rm_id: RM profile ID
            updates: Fields to update
            
        Returns:
            Updated RM profile
        """
        # Protected fields that cannot be updated directly
        protected_fields = {
            "id", "performance_score", "created_at"
        }
        
        # Convert Pydantic model to dict and filter out protected fields
        try:
            update_payload = updates.model_dump(exclude_none=True)
        except Exception:
            # Fall back to expecting a plain dict
            update_payload = dict(updates) if updates else {}

        safe_updates = {k: v for k, v in update_payload.items() if k not in protected_fields}
        
        if not safe_updates:
            raise ValueError("No valid fields to update")
        
        response = self.db.table("rm_profiles").update(
            safe_updates
        ).eq("id", rm_id).execute()
        
        if not response.data:
            raise ValueError("RM profile not found or update failed")
        
        logger.info(f"✏️ RM profile {rm_id} updated: {list(safe_updates.keys())}")
        
        return response.data[0]
    
    async def get_leaderboard(
        self,
        limit: int = 10,
        period: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get RM leaderboard by total score.
        
        Args:
            limit: Number of top RMs to return
            period: Optional time period filter (not implemented yet)
            
        Returns:
            List of top RMs with rankings
        """
        response = self.db.table("rm_profiles").select(
            "*, profiles(full_name, email)"
        ).order("performance_score", desc=True).limit(limit).execute()
        
        rms = response.data or []
        
        # Add rankings
        for idx, rm in enumerate(rms, start=1):
            rm["rank"] = idx
        
        return rms
    
    async def get_rm_by_email(self, email: str) -> Dict[str, Any]:
        """
        Get RM profile by email.
        
        Args:
            email: RM email address
            
        Returns:
            RM profile data
        """
        response = self.db.table("rm_profiles").select(
            "*, profiles(id, full_name, email, phone)"
        ).eq("email", email).single().execute()
        
        if not response.data:
            raise ValueError(f"RM with email {email} not found")
        
        return response.data
    
    # =====================================================
    # VENDOR REQUEST CRUD
    # =====================================================
    
    async def create_vendor_request(
        self,
        rm_id: str,
        request_data: VendorJoinRequestCreate,
        is_draft: bool = False
    ) -> Dict[str, Any]:
        """
        Create new vendor join request.
        
        Args:
            rm_id: RM profile ID
            request_data: Vendor request data
            is_draft: If True, save as draft; if False, submit for approval
            
        Returns:
            Created vendor request
            
        Raises:
            HTTPException: If RM is inactive or creation fails
        """
        try:
            # Verify RM exists and is active
            rm_response = self.db.table("rm_profiles").select("is_active").eq("id", rm_id).execute()
            
            if not rm_response.data or len(rm_response.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"RM profile not found for user {rm_id}. Please contact admin to create your RM profile."
                )
            
            if not rm_response.data[0].get("is_active"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="RM account is inactive"
                )
            
            # Prepare request data (mode='json' converts time objects to strings)
            db_data = request_data.model_dump(mode='json')
            db_data["rm_id"] = rm_id
            db_data["status"] = "draft" if is_draft else "pending"
            
            # Create request
            response = self.db.table("vendor_join_requests").insert(db_data).execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create vendor request"
                )
            
            status_label = "draft" if is_draft else "for approval"
            logger.info(f"RM {rm_id} submitted vendor request {status_label} for {request_data.business_name}")
            
            return response.data[0]
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create vendor request: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create vendor request"
            )
    
    async def update_vendor_request(
        self,
        request_id: str,
        rm_id: str,
        request_data: VendorJoinRequestCreate,
        submit_for_approval: bool = False
    ) -> Dict[str, Any]:
        """
        Update a draft vendor request or submit it for approval.
        
        Args:
            request_id: Vendor request ID
            rm_id: RM profile ID
            request_data: Updated request data
            submit_for_approval: If True, change status from draft to pending
            
        Returns:
            Updated vendor request
            
        Raises:
            HTTPException: If not found, not owned, or not a draft
        """
        try:
            # Verify ownership and draft status
            existing = self.db.table("vendor_join_requests").select("*").eq(
                "id", request_id
            ).eq("rm_id", rm_id).single().execute()
            
            if not existing.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Vendor request not found or access denied"
                )
            
            if existing.data.get("status") != "draft":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Only draft requests can be updated"
                )
            
            # Prepare update data
            update_data = request_data.model_dump()
            
            # Change status if submitting for approval
            if submit_for_approval:
                update_data["status"] = "pending"
            
            # Update request
            response = self.db.table("vendor_join_requests").update(
                update_data
            ).eq("id", request_id).execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Vendor request not found"
                )
            
            logger.info(f"RM {rm_id} updated vendor request {request_id}")
            
            return response.data[0]
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update vendor request: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update vendor request"
            )
    
    async def delete_vendor_request(
        self,
        request_id: str,
        rm_id: str
    ) -> Dict[str, Any]:
        """
        Delete a draft vendor request with image cleanup.
        
        Args:
            request_id: Vendor request ID
            rm_id: RM profile ID
            
        Returns:
            Success response
            
        Raises:
            HTTPException: If not found, not owned, or not a draft
        """
        try:
            # Verify ownership and draft status
            existing_response = self.db.table("vendor_join_requests").select("*").eq(
                "id", request_id
            ).eq("rm_id", rm_id).single().execute()
            
            if not existing_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Vendor request not found or access denied"
                )
            
            existing_request = existing_response.data
            
            # Only allow deletion of drafts
            if existing_request.get("status") != "draft":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Only draft requests can be deleted"
                )
            
            # Delete associated images from storage
            await self._cleanup_vendor_request_images(existing_request)
            
            # Delete the request
            delete_response = self.db.table("vendor_join_requests").delete().eq(
                "id", request_id
            ).execute()
            
            logger.info(f"Successfully deleted draft request {request_id}")
            
            return {
                "success": True,
                "message": "Draft deleted successfully"
            }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete vendor request: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete vendor request"
            )
    
    async def get_vendor_request(
        self,
        request_id: str,
        rm_id: str
    ) -> Dict[str, Any]:
        """
        Get single vendor request by ID.
        
        Args:
            request_id: Vendor request ID
            rm_id: RM profile ID
            
        Returns:
            Vendor request data
            
        Raises:
            HTTPException: If not found or access denied
        """
        try:
            response = self.db.table("vendor_join_requests").select("*").eq(
                "id", request_id
            ).eq("rm_id", rm_id).single().execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Vendor request not found or access denied"
                )
            
            return response.data
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch vendor request: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch vendor request"
            )
    
    async def get_service_categories(self) -> List[Dict[str, Any]]:
        """
        Get all active service categories.
        
        Returns:
            List of active service categories
        """
        try:
            response = self.db.table("service_categories").select(
                "id, name, description, icon_url, display_order"
            ).eq("is_active", True).order("display_order").execute()
            
            return response.data or []
        
        except Exception as e:
            logger.error(f"Failed to fetch service categories: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch service categories"
            )
    
    async def get_rm_dashboard(self, rm_id: str) -> Dict[str, Any]:
        """
        Get comprehensive dashboard statistics for RM.
        
        Args:
            rm_id: RM profile ID
            
        Returns:
            Dashboard data with profile, stats, and recent scores
            
        Raises:
            HTTPException: If RM profile not found
        """
        try:
            # Get RM profile
            profile = await self.get_rm_profile(rm_id)
            
            # Get stats
            stats = await self.get_rm_stats(rm_id)
            
            # Get active salons count
            salons = await self.get_rm_salons(rm_id, include_inactive=False)
            
            # Get recent score changes
            recent_scores = await self.get_rm_score_history(rm_id, limit=5)
            
            return {
                "profile": profile,
                "statistics": {
                    "total_score": stats.total_score,
                    "total_salons_added": stats.total_requests,
                    "total_approved_salons": stats.approved_requests,
                    "pending_requests": stats.pending_requests,
                    "approved_requests": stats.approved_requests,
                    "rejected_requests": stats.rejected_requests,
                    "active_salons": len(salons)
                },
                "recent_scores": recent_scores
            }
        
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        except Exception as e:
            logger.error(f"Failed to fetch RM dashboard: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch RM dashboard"
            )
    
    # =====================================================
    # HELPER METHODS
    # =====================================================
    
    async def _increment_rm_salons_count(self, rm_id: str) -> None:
        """Increment RM's total salons added count."""
        try:
            rm_profile = self.db.table("rm_profiles").select("total_salons_added").eq("id", rm_id).single().execute()
            current_count = rm_profile.data.get("total_salons_added", 0) if rm_profile.data else 0
            
            self.db.table("rm_profiles").update({
                "total_salons_added": current_count + 1
            }).eq("id", rm_id).execute()
        except Exception as e:
            logger.warning(f"Failed to increment RM salons count: {str(e)}")
    
    async def _cleanup_vendor_request_images(self, request: Dict[str, Any]) -> None:
        """Delete vendor request images from storage."""
        try:
            documents = request.get("documents", {})
            images_to_delete = []
            
            # Collect all image paths
            if documents.get("cover_image"):
                images_to_delete.append(documents["cover_image"])
            
            if documents.get("images"):
                images_to_delete.extend(documents["images"])
            
            if documents.get("business_license"):
                images_to_delete.append(documents["business_license"])
            
            if documents.get("business_registration"):
                images_to_delete.append(documents["business_registration"])
            
            # Delete images from storage
            if images_to_delete:
                for image_path in images_to_delete:
                    if "salon-images/" in image_path:
                        file_path = image_path.split("salon-images/")[-1]
                        db.storage.from_("salon-images").remove([file_path])
                
                logger.info(f"Deleted {len(images_to_delete)} images from storage")
        
        except Exception as e:
            logger.warning(f"Failed to delete some images: {str(e)}")
            # Don't raise - continue with deletion even if image cleanup fails
