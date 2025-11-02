"""
Admin API Endpoints
Handles vendor request approvals, system configuration, and RM management
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from supabase import create_client, Client
from app.core.config import settings
from app.core.auth import require_admin, TokenData, create_registration_token
from app.schemas import (
    VendorJoinRequestResponse,
    VendorJoinRequestUpdate,
    SystemConfigResponse,
    SystemConfigUpdate,
    RMProfileResponse,
    RMScoreHistoryResponse,
    SuccessResponse
)
from app.services.email import email_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

# Initialize Supabase client
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


# =====================================================
# VENDOR REQUEST MANAGEMENT
# =====================================================

@router.get("/vendor-requests", response_model=List[VendorJoinRequestResponse])
async def get_vendor_requests(
    status_filter: Optional[str] = "pending",
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(require_admin)
):
    """
    Get vendor join requests
    - Admin only
    - Filter by status: pending, approved, rejected
    """
    try:
        # Fetch vendor requests with RM profile information
        query = supabase.table("vendor_join_requests").select(
            "*"
        )
        
        if status_filter:
            query = query.eq("status", status_filter)
        
        response = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        
        # Manually fetch RM profile data for each request
        for request in response.data:
            rm_id = request.get('rm_id')
            
            if rm_id:
                try:
                    # Fetch RM profile
                    rm_response = supabase.table("rm_profiles").select("*").eq("id", rm_id).execute()
                    
                    if rm_response.data and len(rm_response.data) > 0:
                        rm_data = rm_response.data[0]
                        
                        # Fetch user profile
                        profile_response = supabase.table("profiles").select("*").eq("id", rm_id).execute()
                        
                        # Combine data - use 'profiles' (plural) to match frontend expectation
                        profile_data = profile_response.data[0] if profile_response.data and len(profile_response.data) > 0 else None
                        
                        request['rm_profile'] = {
                            **rm_data,
                            'profiles': profile_data
                        }
                    else:
                        request['rm_profile'] = None
                except Exception as e:
                    logger.error(f"Failed to fetch RM profile for {rm_id}: {str(e)}")
                    request['rm_profile'] = None
        
        return response.data
    
    except Exception as e:
        logger.error(f"Failed to fetch vendor requests: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch vendor requests: {str(e)}"
        )


@router.get("/vendor-requests/{request_id}", response_model=VendorJoinRequestResponse)
async def get_vendor_request(
    request_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Get specific vendor request details"""
    try:
        response = supabase.table("vendor_join_requests").select(
            "*, rm_profiles(*, profiles(*))"
        ).eq("id", request_id).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendor request not found"
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


@router.post("/vendor-requests/{request_id}/approve")
async def approve_vendor_request(
    request_id: str,
    admin_notes: Optional[str] = None,
    current_user: TokenData = Depends(require_admin)
):
    """
    Approve vendor join request
    - Creates salon entry
    - Updates RM score
    - Sends email to vendor with registration link
    """
    try:
        # Get request details
        request_response = supabase.table("vendor_join_requests").select("*").eq("id", request_id).single().execute()
        
        if not request_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Request not found"
            )
        
        request_data = request_response.data
        
        if request_data.get("status") != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Request already {request_data.get('status')}"
            )
        
        # Get RM score configuration
        config_response = supabase.table("system_config").select("config_value").eq(
            "config_key", "rm_score_per_approval"
        ).eq("is_active", True).single().execute()
        
        rm_score = int(config_response.data.get("config_value", 10)) if config_response.data else 10
        
        # Get registration fee
        fee_response = supabase.table("system_config").select("config_value").eq(
            "config_key", "registration_fee_amount"
        ).eq("is_active", True).single().execute()
        
        registration_fee = float(fee_response.data.get("config_value", 5000)) if fee_response.data else 5000.0
        
        # Update request status
        supabase.table("vendor_join_requests").update({
            "status": "approved",
            "admin_notes": admin_notes,
            "reviewed_at": "now()"
        }).eq("id", request_id).execute()
        
        # Create salon entry
        salon_data = {
            "rm_id": request_data["rm_id"],
            "join_request_id": request_id,
            "business_name": request_data["business_name"],
            "business_type": request_data["business_type"],
            "description": None,
            "phone": request_data["owner_phone"],
            "email": request_data["owner_email"],
            "address": request_data["business_address"],
            "city": request_data["city"],
            "state": request_data["state"],
            "pincode": request_data["pincode"],
            "latitude": request_data.get("latitude") or 0.0,
            "longitude": request_data.get("longitude") or 0.0,
            "gst_number": request_data.get("gst_number"),
            "business_license": request_data.get("business_license"),
            "registration_fee_amount": registration_fee,
            "registration_fee_paid": False,
            "is_active": False,  # Activated after payment
            "approved_at": "now()"
        }
        
        salon_response = supabase.table("salons").insert(salon_data).execute()
        salon_id = salon_response.data[0]["id"] if salon_response.data else None
        
        # Update RM score - Get current values first
        rm_profile_response = supabase.table("rm_profiles").select(
            "total_score, total_approved_salons"
        ).eq("id", request_data["rm_id"]).single().execute()
        
        current_score = rm_profile_response.data.get("total_score", 0) if rm_profile_response.data else 0
        current_approved = rm_profile_response.data.get("total_approved_salons", 0) if rm_profile_response.data else 0
        
        supabase.table("rm_profiles").update({
            "total_score": current_score + rm_score,
            "total_approved_salons": current_approved + 1
        }).eq("id", request_data["rm_id"]).execute()
        
        # Add score history
        supabase.table("rm_score_history").insert({
            "rm_id": request_data["rm_id"],
            "salon_id": salon_id,
            "score_change": rm_score,
            "reason": f"Salon approved: {request_data['business_name']}"
        }).execute()
        
        # Generate secure JWT registration token
        registration_token = create_registration_token(
            request_id=request_id,
            salon_id=salon_id,
            owner_email=request_data["owner_email"]
        )
        
        # Send approval email to vendor (non-blocking)
        try:
            email_sent = email_service.send_vendor_approval_email(
                to_email=request_data["owner_email"],
                owner_name=request_data["owner_name"],
                salon_name=request_data["business_name"],
                registration_token=registration_token,
                registration_fee=registration_fee
            )
            
            if not email_sent:
                logger.warning(f"Failed to send approval email to {request_data['owner_email']}")
        except Exception as email_error:
            logger.error(f"Email service error: {str(email_error)}")
            # Continue with approval even if email fails
        
        logger.info(f"Vendor request {request_id} approved. Salon created: {salon_id}")
        
        return {
            "success": True,
            "message": "Vendor request approved successfully",
            "data": {
                "salon_id": salon_id,
                "rm_score_awarded": rm_score
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve vendor request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve vendor request"
        )


@router.post("/vendor-requests/{request_id}/reject")
async def reject_vendor_request(
    request_id: str,
    admin_notes: str,
    current_user: TokenData = Depends(require_admin)
):
    """
    Reject vendor join request
    - Updates status
    - Sends rejection email
    """
    try:
        # Get request details
        request_response = supabase.table("vendor_join_requests").select("*").eq("id", request_id).single().execute()
        
        if not request_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Request not found"
            )
        
        request_data = request_response.data
        
        if request_data.get("status") != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Request already {request_data.get('status')}"
            )
        
        # Update request status
        supabase.table("vendor_join_requests").update({
            "status": "rejected",
            "admin_notes": admin_notes,
            "reviewed_at": "now()"
        }).eq("id", request_id).execute()
        
        # Get RM details for email notification
        rm_response = supabase.table("rm_profiles").select(
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
                logger.warning(f"Failed to send rejection email to RM {rm_email}")
        
        logger.info(f"Vendor request {request_id} rejected")
        
        return {
            "success": True,
            "message": "Vendor request rejected"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject vendor request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject vendor request"
        )


# =====================================================
# SYSTEM CONFIGURATION MANAGEMENT
# =====================================================

@router.get("/config", response_model=List[SystemConfigResponse])
async def get_all_configs(current_user: TokenData = Depends(require_admin)):
    """Get all system configurations"""
    try:
        response = supabase.table("system_config").select("*").order("config_key").execute()
        return response.data
    
    except Exception as e:
        logger.error(f"Failed to fetch configs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch configurations"
        )


@router.get("/config/{config_key}", response_model=SystemConfigResponse)
async def get_config(
    config_key: str,
    current_user: TokenData = Depends(require_admin)
):
    """Get specific configuration"""
    try:
        response = supabase.table("system_config").select("*").eq("config_key", config_key).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Configuration not found"
            )
        
        return response.data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch config: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch configuration"
        )


@router.put("/config/{config_key}")
async def update_config(
    config_key: str,
    update: SystemConfigUpdate,
    current_user: TokenData = Depends(require_admin)
):
    """Update system configuration"""
    try:
        # Verify config exists
        check_response = supabase.table("system_config").select("id").eq("config_key", config_key).single().execute()
        
        if not check_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Configuration not found"
            )
        
        # Update config
        update_data = update.model_dump(exclude_unset=True)
        
        response = supabase.table("system_config").update(update_data).eq("config_key", config_key).execute()
        
        logger.info(f"System config updated: {config_key} = {update.config_value}")
        
        return {
            "success": True,
            "message": "Configuration updated successfully",
            "data": response.data[0] if response.data else None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update config: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update configuration"
        )


# =====================================================
# RM MANAGEMENT
# =====================================================

@router.get("/rms", response_model=List[RMProfileResponse])
async def get_all_rms(
    is_active: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(require_admin)
):
    """Get all Relationship Managers"""
    try:
        query = supabase.table("rm_profiles").select("*, profiles(*)")
        
        if is_active is not None:
            query = query.eq("is_active", is_active)
        
        response = query.order("total_score", desc=True).range(offset, offset + limit - 1).execute()
        
        return response.data
    
    except Exception as e:
        logger.error(f"Failed to fetch RMs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch RM profiles"
        )


@router.get("/rms/{rm_id}", response_model=RMProfileResponse)
async def get_rm_profile(
    rm_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Get specific RM profile"""
    try:
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


@router.get("/rms/{rm_id}/score-history", response_model=List[RMScoreHistoryResponse])
async def get_rm_score_history(
    rm_id: str,
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(require_admin)
):
    """Get RM score history"""
    try:
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
# DASHBOARD & ANALYTICS
# =====================================================

@router.get("/dashboard/stats")
async def get_dashboard_stats(current_user: TokenData = Depends(require_admin)):
    """Get admin dashboard statistics"""
    try:
        # Get pending requests count
        pending_requests = supabase.table("vendor_join_requests").select(
            "id", count="exact"
        ).eq("status", "pending").execute()
        
        # Get total salons
        total_salons = supabase.table("salons").select("id", count="exact").execute()
        
        # Get active salons
        active_salons = supabase.table("salons").select(
            "id", count="exact"
        ).eq("is_active", True).execute()
        
        # Get total bookings today
        today_bookings = supabase.table("bookings").select(
            "id", count="exact"
        ).gte("created_at", "today").execute()
        
        # Get total RMs
        total_rms = supabase.table("rm_profiles").select("id", count="exact").execute()
        
        # Get payment stats
        total_revenue = supabase.table("vendor_payments").select("amount").eq(
            "status", "success"
        ).execute()
        
        revenue_sum = sum(float(p["amount"]) for p in total_revenue.data) if total_revenue.data else 0
        
        return {
            "pending_requests": pending_requests.count if pending_requests else 0,
            "total_salons": total_salons.count if total_salons else 0,
            "active_salons": active_salons.count if active_salons else 0,
            "today_bookings": today_bookings.count if today_bookings else 0,
            "total_rms": total_rms.count if total_rms else 0,
            "total_revenue": revenue_sum
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch dashboard stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch dashboard statistics"
        )


# =====================================================
# USER MANAGEMENT
# =====================================================

@router.get("/users")
async def get_all_users(
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
    role: Optional[str] = None,
    current_user: TokenData = Depends(require_admin)
):
    """Get all users with pagination and filters"""
    try:
        offset = (page - 1) * limit
        query = supabase.table("profiles").select("*", count="exact")
        
        if search:
            query = query.or_(f"email.ilike.%{search}%,full_name.ilike.%{search}%")
        
        if role:
            query = query.eq("role", role)
        
        response = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        
        return {
            "success": True,
            "data": response.data,
            "total": response.count,
            "page": page,
            "limit": limit
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch users"
        )


@router.post("/users")
async def create_user(
    user_data: dict,
    current_user: TokenData = Depends(require_admin)
):
    """Create a new user (Relationship Manager or Customer only)"""
    try:
        email = user_data.get("email")
        password = user_data.get("password", "defaultPass123")  # Default password if not provided
        full_name = user_data.get("full_name")
        phone = user_data.get("phone", "")
        role = user_data.get("role", "customer")
        
        # Validation
        if not email or not full_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email and full name are required"
            )
        
        # Prevent creating admin users
        if role not in ["relationship_manager", "customer"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only create Relationship Manager or Customer accounts"
            )
        
        # Check if email already exists
        existing_profile = supabase.table("profiles").select("id").eq("email", email).execute()
        if existing_profile.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Create auth user using Supabase Management API
        import requests
        import os
        
        supabase_url = settings.SUPABASE_URL
        service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY
        
        # Call Supabase Admin API directly
        headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json"
        }
        
        auth_payload = {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": full_name,
                "role": role
            }
        }
        
        auth_response = requests.post(
            f"{supabase_url}/auth/v1/admin/users",
            json=auth_payload,
            headers=headers
        )
        
        if auth_response.status_code not in [200, 201]:
            logger.error(f"Auth creation failed: {auth_response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create auth user: {auth_response.text}"
            )
        
        auth_data = auth_response.json()
        user_id = auth_data.get("id")
        
        # Create profile entry
        profile_data = {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "phone": phone,
            "role": role,
            "is_active": True,
            "email_verified": True
        }
        
        profile_response = supabase.table("profiles").insert(profile_data).execute()
        
        if not profile_response.data:
            # Rollback: try to delete the auth user
            try:
                requests.delete(
                    f"{supabase_url}/auth/v1/admin/users/{user_id}",
                    headers=headers
                )
            except:
                pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user profile"
            )
        
        # If creating a Relationship Manager, also create rm_profile entry
        if role == "relationship_manager":
            try:
                # Generate employee ID (RM-<random 5 digits>)
                import random
                employee_id = f"RM-{random.randint(10000, 99999)}"
                
                rm_profile_data = {
                    "id": user_id,
                    "employee_id": employee_id,
                    "total_score": 0,
                    "total_salons_added": 0,
                    "total_approved_salons": 0,
                    "is_active": True
                }
                
                rm_profile_response = supabase.table("rm_profiles").insert(rm_profile_data).execute()
                
                if not rm_profile_response.data:
                    logger.warning(f"Failed to create RM profile for {email}, but user created")
                else:
                    logger.info(f"RM profile created for {email} with employee_id {employee_id}")
            except Exception as rm_error:
                logger.error(f"Failed to create RM profile: {str(rm_error)}")
                # Don't fail the whole operation, just log it
        
        logger.info(f"User created successfully: {email} ({role})")
        
        return {
            "success": True,
            "message": f"{role.replace('_', ' ').title()} created successfully!",
            "data": profile_response.data[0]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user: {str(e)}"
        )


@router.post("/fix-rm-profiles")
async def fix_rm_profiles(current_user: TokenData = Depends(require_admin)):
    """Create missing rm_profiles for existing relationship_manager users"""
    try:
        import requests
        import random
        
        # Find all users with role 'relationship_manager'
        profiles_response = supabase.table("profiles").select("id, email, full_name").eq("role", "relationship_manager").execute()
        
        if not profiles_response.data:
            return {
                "success": True,
                "message": "No relationship managers found",
                "created": 0
            }
        
        created_count = 0
        errors = []
        
        # Use Supabase REST API directly to bypass RLS
        headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        
        for profile in profiles_response.data:
            user_id = profile["id"]
            
            # Check if rm_profile already exists
            existing_rm = supabase.table("rm_profiles").select("id").eq("id", user_id).execute()
            
            if existing_rm.data:
                logger.info(f"RM profile already exists for {profile['email']}")
                continue
            
            # Create rm_profile using direct REST API call
            try:
                employee_id = f"RM-{random.randint(10000, 99999)}"
                
                rm_profile_data = {
                    "id": user_id,
                    "employee_id": employee_id,
                    "total_score": 0,
                    "total_salons_added": 0,
                    "total_approved_salons": 0,
                    "is_active": True
                }
                
                # Direct REST API call
                response = requests.post(
                    f"{settings.SUPABASE_URL}/rest/v1/rm_profiles",
                    headers=headers,
                    json=rm_profile_data
                )
                
                if response.status_code in [200, 201]:
                    created_count += 1
                    logger.info(f"Created RM profile for {profile['email']} with employee_id {employee_id}")
                else:
                    error_msg = f"Failed for {profile['email']}: {response.text}"
                    errors.append(error_msg)
                    logger.error(error_msg)
                    
            except Exception as e:
                errors.append(f"Error creating profile for {profile['email']}: {str(e)}")
                logger.error(f"Error creating RM profile: {str(e)}")
        
        return {
            "success": True,
            "message": f"Created {created_count} RM profiles",
            "created": created_count,
            "errors": errors if errors else None
        }
    
    except Exception as e:
        logger.error(f"Failed to fix RM profiles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fix RM profiles: {str(e)}"
        )


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    updates: dict,
    current_user: TokenData = Depends(require_admin)
):
    """Update user profile"""
    try:
        response = supabase.table("profiles").update(updates).eq("id", user_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return {
            "success": True,
            "message": "User updated successfully",
            "data": response.data[0]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user"
        )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Delete user (soft delete by setting is_active=false)"""
    try:
        # Soft delete by deactivating
        response = supabase.table("profiles").update({
            "is_active": False
        }).eq("id", user_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return {
            "success": True,
            "message": "User deleted successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )


# =====================================================
# SALON MANAGEMENT
# =====================================================

@router.get("/salons")
async def get_all_salons_admin(
    current_user: TokenData = Depends(require_admin)
):
    """Get all salons (including inactive)"""
    try:
        response = supabase.table("salons").select("*").order("created_at", desc=True).execute()
        
        return {
            "success": True,
            "data": response.data
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch salons: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch salons"
        )


@router.put("/salons/{salon_id}")
async def update_salon(
    salon_id: str,
    updates: dict,
    current_user: TokenData = Depends(require_admin)
):
    """Update salon"""
    try:
        response = supabase.table("salons").update(updates).eq("id", salon_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salon not found"
            )
        
        return {
            "success": True,
            "message": "Salon updated successfully",
            "data": response.data[0]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update salon: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update salon"
        )


@router.delete("/salons/{salon_id}")
async def delete_salon(
    salon_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Delete salon"""
    try:
        response = supabase.table("salons").delete().eq("id", salon_id).execute()
        
        return {
            "success": True,
            "message": "Salon deleted successfully"
        }
    
    except Exception as e:
        logger.error(f"Failed to delete salon: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete salon"
        )


# =====================================================
# BOOKINGS/APPOINTMENTS MANAGEMENT
# =====================================================

@router.get("/bookings")
async def get_all_bookings_admin(
    page: int = 1,
    limit: int = 20,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: TokenData = Depends(require_admin)
):
    """Get all bookings with filters"""
    try:
        offset = (page - 1) * limit
        query = supabase.table("bookings").select("*", count="exact")
        
        if status:
            query = query.eq("status", status)
        
        if date_from:
            query = query.gte("booking_date", date_from)
        
        if date_to:
            query = query.lte("booking_date", date_to)
        
        response = query.order("booking_date", desc=True).range(offset, offset + limit - 1).execute()
        
        return {
            "success": True,
            "data": response.data,
            "total": response.count,
            "page": page,
            "limit": limit
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch bookings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch bookings"
        )


@router.put("/bookings/{booking_id}/status")
async def update_booking_status(
    booking_id: str,
    status: str,
    current_user: TokenData = Depends(require_admin)
):
    """Update booking status"""
    try:
        response = supabase.table("bookings").update({
            "status": status
        }).eq("id", booking_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )
        
        return {
            "success": True,
            "message": "Booking status updated",
            "data": response.data[0]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update booking: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update booking"
        )


# =====================================================
# SERVICES MANAGEMENT
# =====================================================

@router.get("/services")
async def get_all_services_admin(
    current_user: TokenData = Depends(require_admin)
):
    """Get all services"""
    try:
        response = supabase.table("services").select("*").order("name").execute()
        
        return {
            "success": True,
            "data": response.data
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch services: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch services"
        )


@router.post("/services")
async def create_service(
    service_data: dict,
    current_user: TokenData = Depends(require_admin)
):
    """Create new service"""
    try:
        response = supabase.table("services").insert(service_data).execute()
        
        return {
            "success": True,
            "message": "Service created successfully",
            "data": response.data[0]
        }
    
    except Exception as e:
        logger.error(f"Failed to create service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create service"
        )


@router.put("/services/{service_id}")
async def update_service(
    service_id: str,
    updates: dict,
    current_user: TokenData = Depends(require_admin)
):
    """Update service"""
    try:
        response = supabase.table("services").update(updates).eq("id", service_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found"
            )
        
        return {
            "success": True,
            "message": "Service updated successfully",
            "data": response.data[0]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update service"
        )


@router.delete("/services/{service_id}")
async def delete_service(
    service_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Delete service"""
    try:
        response = supabase.table("services").delete().eq("id", service_id).execute()
        
        return {
            "success": True,
            "message": "Service deleted successfully"
        }
    
    except Exception as e:
        logger.error(f"Failed to delete service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete service"
        )


# =====================================================
# STAFF MANAGEMENT
# =====================================================

@router.get("/staff")
async def get_all_staff(
    current_user: TokenData = Depends(require_admin)
):
    """Get all staff members"""
    try:
        response = supabase.table("profiles").select("*").eq("role", "staff").order("full_name").execute()
        
        return {
            "success": True,
            "data": response.data
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch staff: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch staff"
        )


@router.put("/staff/{staff_id}")
async def update_staff(
    staff_id: str,
    updates: dict,
    current_user: TokenData = Depends(require_admin)
):
    """Update staff member"""
    try:
        response = supabase.table("profiles").update(updates).eq("id", staff_id).eq("role", "staff").execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Staff member not found"
            )
        
        return {
            "success": True,
            "message": "Staff updated successfully",
            "data": response.data[0]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update staff: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update staff"
        )


@router.delete("/staff/{staff_id}")
async def delete_staff(
    staff_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Delete staff member (soft delete)"""
    try:
        response = supabase.table("profiles").update({
            "is_active": False
        }).eq("id", staff_id).eq("role", "staff").execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Staff member not found"
            )
        
        return {
            "success": True,
            "message": "Staff deleted successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete staff: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete staff"
        )

