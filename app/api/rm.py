"""
Relationship Manager (RM) API Endpoints
Handles salon submission, own requests viewing, and score tracking
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from supabase import create_client, Client
from app.core.config import settings
from app.core.auth import require_rm, TokenData, get_current_user_id
from app.schemas import (
    VendorJoinRequestCreate,
    VendorJoinRequestResponse,
    RMProfileResponse,
    RMScoreHistoryResponse,
    SuccessResponse
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rm", tags=["Relationship Manager"])

# Initialize Supabase client
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


# =====================================================
# VENDOR REQUEST SUBMISSION
# =====================================================

@router.post("/vendor-requests", response_model=VendorJoinRequestResponse)
async def create_vendor_request(
    request: VendorJoinRequestCreate,
    is_draft: bool = False,
    current_user: TokenData = Depends(require_rm)
):
    """
    Create new vendor join request
    - RM submits salon details to admin for approval
    - Can be saved as draft (is_draft=True) or submitted for approval (is_draft=False)
    """
    try:
        rm_id = current_user.user_id
        
        # Verify RM exists and is active
        rm_response = supabase.table("rm_profiles").select("is_active").eq("id", rm_id).single().execute()
        
        if not rm_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="RM profile not found"
            )
        
        if not rm_response.data.get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="RM account is inactive"
            )
        
        # Create vendor request
        request_data = request.model_dump()
        request_data["rm_id"] = rm_id
        request_data["status"] = "draft" if is_draft else "pending"
        
        response = supabase.table("vendor_join_requests").insert(request_data).execute()
        
        # Only update RM total salons added count if not a draft
        if not is_draft:
            rm_profile = supabase.table("rm_profiles").select("total_salons_added").eq("id", rm_id).single().execute()
            current_count = rm_profile.data.get("total_salons_added", 0) if rm_profile.data else 0
            
            supabase.table("rm_profiles").update({
                "total_salons_added": current_count + 1
            }).eq("id", rm_id).execute()
        
        status_label = "draft" if is_draft else "for approval"
        logger.info(f"RM {rm_id} submitted vendor request {status_label} for {request.business_name}")
        
        return response.data[0] if response.data else None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create vendor request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create vendor request"
        )


@router.put("/vendor-requests/{request_id}")
async def update_vendor_request(
    request_id: str,
    request: VendorJoinRequestCreate,
    submit_for_approval: bool = False,
    current_user: TokenData = Depends(require_rm)
):
    """
    Update a draft vendor request or submit it for approval
    - Can only update requests with 'draft' status
    - Set submit_for_approval=True to change status from 'draft' to 'pending'
    """
    try:
        rm_id = current_user.user_id
        
        # Check if request exists and belongs to this RM
        existing = supabase.table("vendor_join_requests").select("*").eq(
            "id", request_id
        ).eq("rm_id", rm_id).single().execute()
        
        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendor request not found or access denied"
            )
        
        # Can only update drafts
        if existing.data.get("status") != "draft":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only update draft requests"
            )
        
        # Update the request
        request_data = request.model_dump()
        request_data["status"] = "pending" if submit_for_approval else "draft"
        
        response = supabase.table("vendor_join_requests").update(
            request_data
        ).eq("id", request_id).execute()
        
        # Update RM total salons count if submitting for approval
        if submit_for_approval:
            rm_profile = supabase.table("rm_profiles").select("total_salons_added").eq("id", rm_id).single().execute()
            current_count = rm_profile.data.get("total_salons_added", 0) if rm_profile.data else 0
            
            supabase.table("rm_profiles").update({
                "total_salons_added": current_count + 1
            }).eq("id", rm_id).execute()
        
        logger.info(f"RM {rm_id} updated vendor request {request_id}")
        
        return response.data[0] if response.data else None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update vendor request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update vendor request"
        )


@router.delete("/vendor-requests/{request_id}")
async def delete_vendor_request(
    request_id: str,
    current_user: TokenData = Depends(require_rm)
):
    """
    Delete a draft vendor request
    - Only drafts can be deleted
    - RM can only delete their own requests
    """
    try:
        rm_id = current_user.user_id
        logger.info(f"RM {rm_id} attempting to delete request {request_id}")
        
        # First, fetch the request to verify ownership and status
        existing_response = supabase.table("vendor_join_requests").select("*").eq(
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
        
        # Delete associated images from storage if they exist
        documents = existing_request.get("documents", {})
        images_to_delete = []
        
        # Cover image
        if documents.get("cover_image"):
            images_to_delete.append(documents["cover_image"])
        
        # Gallery images
        if documents.get("images"):
            images_to_delete.extend(documents["images"])
        
        # License and registration images
        if documents.get("business_license"):
            images_to_delete.append(documents["business_license"])
        if documents.get("business_registration"):
            images_to_delete.append(documents["business_registration"])
        
        # Delete images from storage
        if images_to_delete:
            try:
                for image_path in images_to_delete:
                    # Extract the file path from the full URL
                    # Format: https://xxx.supabase.co/storage/v1/object/public/salon-images/path
                    if "salon-images/" in image_path:
                        file_path = image_path.split("salon-images/")[-1]
                        supabase.storage.from_("salon-images").remove([file_path])
                logger.info(f"Deleted {len(images_to_delete)} images from storage")
            except Exception as img_error:
                logger.warning(f"Failed to delete some images: {str(img_error)}")
                # Continue with deletion even if image cleanup fails
        
        # Delete the request
        delete_response = supabase.table("vendor_join_requests").delete().eq(
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


# =====================================================
# OWN REQUESTS VIEWING
# =====================================================

@router.get("/vendor-requests")
async def get_own_vendor_requests(
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(require_rm)
):
    """
    Get own vendor join requests
    - RM can only see requests they submitted
    """
    try:
        rm_id = current_user.user_id
        logger.info(f"Fetching vendor requests for RM: {rm_id}")
        
        query = supabase.table("vendor_join_requests").select("*").eq("rm_id", rm_id)
        
        if status_filter:
            query = query.eq("status", status_filter)
        
        response = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        
        logger.info(f"Found {len(response.data)} vendor requests")
        if response.data:
            logger.info(f"Sample request data: {response.data[0]}")
        
        return response.data
    
    except Exception as e:
        logger.error(f"Failed to fetch vendor requests: {str(e)}")
        logger.exception(e)  # This will log the full stack trace
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch vendor requests: {str(e)}"
        )


@router.get("/vendor-requests/{request_id}", response_model=VendorJoinRequestResponse)
async def get_vendor_request(
    request_id: str,
    current_user: TokenData = Depends(require_rm)
):
    """Get specific vendor request (own only)"""
    try:
        rm_id = current_user.user_id
        response = supabase.table("vendor_join_requests").select("*").eq(
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


# =====================================================
# SALONS VIEW (APPROVED)
# =====================================================

@router.get("/salons")
async def get_own_salons(
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(require_rm)
):
    """
    Get salons added by this RM
    - Only shows salons linked to this RM
    """
    try:
        rm_id = current_user.user_id
        response = supabase.table("salons").select(
            "*, vendor_join_requests(*)"
        ).eq("rm_id", rm_id).order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        
        return {
            "success": True,
            "data": response.data,
            "total": len(response.data) if response.data else 0
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch salons: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch salons"
        )


# =====================================================
# PROFILE & SCORE MANAGEMENT
# =====================================================

@router.get("/profile", response_model=RMProfileResponse)
async def get_own_profile(current_user: TokenData = Depends(require_rm)):
    """Get own RM profile with scores"""
    try:
        rm_id = current_user.user_id
        response = supabase.table("rm_profiles").select("*, profiles(*)").eq("id", rm_id).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="RM profile not found"
            )
        
        return response.data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch RM profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch RM profile"
        )


@router.put("/profile")
async def update_own_profile(
    profile_data: dict,
    current_user: TokenData = Depends(require_rm)
):
    """
    Update own RM profile
    - Can update: full_name, phone, address, city, state, pincode
    - Cannot update: email (read-only)
    """
    try:
        rm_id = current_user.user_id
        
        # Validate allowed fields
        allowed_fields = {"full_name", "phone", "address", "city", "state", "pincode"}
        update_data = {k: v for k, v in profile_data.items() if k in allowed_fields}
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid fields to update"
            )
        
        # Update profiles table (main user profile)
        profile_response = supabase.table("profiles").update(update_data).eq("id", rm_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        
        logger.info(f"RM {rm_id} updated profile: {list(update_data.keys())}")
        
        # Return updated profile with rm_profiles data
        response = supabase.table("rm_profiles").select("*, profiles(*)").eq("id", rm_id).single().execute()
        
        return {
            "success": True,
            "message": "Profile updated successfully",
            "data": response.data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update RM profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )


@router.get("/score-history", response_model=List[RMScoreHistoryResponse])
async def get_own_score_history(
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(require_rm)
):
    """Get own score history"""
    try:
        rm_id = current_user.user_id
        response = supabase.table("rm_score_history").select("*").eq(
            "rm_id", rm_id
        ).order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        
        return response.data
    
    except Exception as e:
        logger.error(f"Failed to fetch score history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch score history"
        )


# =====================================================
# DASHBOARD
# =====================================================

@router.get("/dashboard")
async def get_rm_dashboard(current_user: TokenData = Depends(require_rm)):
    """Get RM dashboard statistics"""
    try:
        rm_id = current_user.user_id
        
        # Get RM profile - use maybe_single() to handle 0 results
        profile_response = supabase.table("rm_profiles").select("*").eq("id", rm_id).execute()
        
        # If profile doesn't exist, create it
        if not profile_response.data or len(profile_response.data) == 0:
            logger.info(f"RM profile not found for {rm_id}, creating new profile")
            
            # Create new RM profile
            new_profile = {
                "id": rm_id,
                "employee_id": f"RM{rm_id[:8].upper()}",  # Generate employee ID
                "total_score": 0,
                "total_salons_added": 0,
                "total_approved_salons": 0,
                "is_active": True
            }
            
            create_response = supabase.table("rm_profiles").insert(new_profile).execute()
            profile = create_response.data[0] if create_response.data else new_profile
        else:
            profile = profile_response.data[0]
        
        # Get pending requests count
        pending_count = supabase.table("vendor_join_requests").select(
            "id", count="exact"
        ).eq("rm_id", rm_id).eq("status", "pending").execute()
        
        # Get approved requests count
        approved_count = supabase.table("vendor_join_requests").select(
            "id", count="exact"
        ).eq("rm_id", rm_id).eq("status", "approved").execute()
        
        # Get rejected requests count
        rejected_count = supabase.table("vendor_join_requests").select(
            "id", count="exact"
        ).eq("rm_id", rm_id).eq("status", "rejected").execute()
        
        # Get active salons count
        active_salons = supabase.table("salons").select(
            "id", count="exact"
        ).eq("rm_id", rm_id).eq("is_active", True).execute()
        
        # Get recent score changes
        recent_scores = supabase.table("rm_score_history").select("*").eq(
            "rm_id", rm_id
        ).order("created_at", desc=True).limit(5).execute()
        
        return {
            "profile": profile,
            "statistics": {
                "total_score": profile.get("total_score", 0),
                "total_salons_added": profile.get("total_salons_added", 0),
                "total_approved_salons": profile.get("total_approved_salons", 0),
                "pending_requests": pending_count.count if pending_count else 0,
                "approved_requests": approved_count.count if approved_count else 0,
                "rejected_requests": rejected_count.count if rejected_count else 0,
                "active_salons": active_salons.count if active_salons else 0
            },
            "recent_scores": recent_scores.data if recent_scores.data else []
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch RM dashboard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch RM dashboard"
        )


# =====================================================
# LEADERBOARD
# =====================================================

@router.get("/leaderboard")
async def get_rm_leaderboard(limit: int = 20):
    """
    Get RM leaderboard
    - Top RMs by score
    - Public information
    """
    try:
        response = supabase.table("rm_profiles").select(
            "id, employee_id, total_score, total_approved_salons, profiles(full_name)"
        ).eq("is_active", True).order("total_score", desc=True).limit(limit).execute()
        
        return {
            "success": True,
            "data": response.data,
            "total": len(response.data) if response.data else 0
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch leaderboard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch leaderboard"
        )

