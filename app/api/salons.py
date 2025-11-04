"""
Modern Salon API Endpoints using Supabase

These endpoints leverage:
- Row Level Security (automatic authorization)
- Supabase Storage for images
- PostGIS functions for efficient queries
- Auto-generated REST APIs
"""

from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from typing import Optional, List
from decimal import Decimal
from supabase import create_client, Client
from app.core.config import settings
from app.services.supabase_service import SupabaseService

router = APIRouter(prefix="/salons", tags=["salons"])

# Initialize Supabase client and service
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
supabase_service = SupabaseService()


# ========================================
# GET ENDPOINTS
# ========================================

@router.get("/public")
async def get_public_salons(
    city: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get all public salons (active, verified, and registration fee paid)
    
    This endpoint returns only salons that are:
    - is_active = true
    - is_verified = true  
    - registration_fee_paid = true
    """
    try:
        # Get paid and approved salons
        salons = supabase_service.get_public_salons(limit, offset)
        
        # Apply city filter if provided
        if city:
            salons = [s for s in salons if s.get('city', '').lower() == city.lower()]
        
        return {
            "salons": salons,
            "count": len(salons),
            "offset": offset,
            "limit": limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/")
async def get_salons(
    status: Optional[str] = Query(None, description="Filter by status"),
    city: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get all salons (respects RLS - only approved salons visible to public)
    
    RLS automatically enforces:
    - Public users can only see approved salons
    - Salon owners can see their own salons
    - Admins can see all salons
    """
    try:
        if status:
            if status == "approved":
                salons = supabase_service.get_approved_salons(limit, offset)
            elif status == "pending":
                # Only admins can access this (RLS enforced)
                salons = supabase_service.get_pending_salons(limit)
            else:
                raise HTTPException(status_code=400, detail="Invalid status")
        else:
            salons = supabase_service.get_approved_salons(limit, offset)
        
        return {
            "salons": salons,
            "count": len(salons),
            "offset": offset,
            "limit": limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{salon_id}")
async def get_salon(salon_id: str):
    """
    Get single salon by ID (UUID)
    
    Returns salon details if active, verified, and payment completed
    """
    try:
        salon = supabase_service.get_salon(salon_id)
        
        if not salon:
            raise HTTPException(status_code=404, detail="Salon not found")
        
        # Check if salon is publicly visible
        if not (salon.get('is_active') and salon.get('is_verified') and salon.get('registration_fee_paid')):
            raise HTTPException(status_code=404, detail="Salon not available")
        
        return salon
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{salon_id}/services")
async def get_salon_services(salon_id: str):
    """
    Get all services for a salon
    
    Returns services only for active, verified, paid salons
    """
    try:
        # First verify salon is public
        salon = supabase_service.get_salon(salon_id)
        if not salon or not (salon.get('is_active') and salon.get('is_verified') and salon.get('registration_fee_paid')):
            raise HTTPException(status_code=404, detail="Salon not found")
        
        services = supabase_service.get_salon_services(salon_id)
        return {"services": services, "count": len(services)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# NEARBY & SEARCH
# ========================================

@router.get("/search/nearby")
async def get_nearby_salons(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    radius: float = Query(10.0, ge=0.5, le=50, description="Radius in km"),
    limit: int = Query(50, ge=1, le=100)
):
    """
    Get nearby salons using PostGIS function
    
    This uses the database function for efficient distance calculation
    Much faster than calculating in Python!
    """
    try:
        salons = supabase_service.get_nearby_salons(lat, lon, radius, limit)
        
        return {
            "salons": salons,
            "count": len(salons),
            "query": {"lat": lat, "lon": lon, "radius_km": radius}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/query")
async def search_salons(
    q: str = Query(..., description="Search query"),
    city: Optional[str] = Query(None),
    min_rating: float = Query(0.0, ge=0.0, le=5.0),
    limit: int = Query(50, ge=1, le=100)
):
    """
    Search salons by name, description, or city
    
    Uses PostgreSQL full-text search function
    """
    try:
        salons = supabase_service.search_salons(q, city, min_rating, limit)
        
        return {
            "salons": salons,
            "count": len(salons),
            "query": q
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# CREATE & UPDATE (Admin Only - RLS Enforced)
# ========================================

@router.post("/")
async def create_salon(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    phone: str = Form(...),
    email: Optional[str] = Form(None),
    address_line1: str = Form(...),
    city: str = Form(...),
    state: str = Form(...),
    pincode: str = Form(...),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    cover_image: Optional[UploadFile] = File(None),
    owner_id: Optional[str] = Form(None),
    status: str = Form("pending")
):
    """
    Create new salon
    
    RLS ensures only admins/HMR agents can create salons
    If cover_image provided, uploads to Supabase Storage
    """
    try:
        # Prepare salon data
        salon_data = {
            "name": name,
            "description": description,
            "phone": phone,
            "email": email,
            "address_line1": address_line1,
            "city": city,
            "state": state,
            "pincode": pincode,
            "latitude": str(latitude) if latitude else None,
            "longitude": str(longitude) if longitude else None,
            "owner_id": owner_id,
            "status": status
        }
        
        # Create salon
        salon = supabase_service.create_salon(salon_data)
        
        if not salon:
            raise HTTPException(status_code=500, detail="Failed to create salon")
        
        # Upload cover image if provided
        if cover_image:
            try:
                image_data = await cover_image.read()
                cover_url = supabase_service.upload_salon_image(
                    salon_id=salon["id"],
                    image_data=image_data,
                    filename=f"cover.{cover_image.filename.split('.')[-1]}"
                )
                
                # Update salon with cover image URL
                salon = supabase_service.update_salon(salon["id"], {"cover_image": cover_url})
            except Exception as img_error:
                print(f"Warning: Failed to upload cover image: {img_error}")
                # Don't fail the entire request if image upload fails
        
        return salon
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{salon_id}")
async def update_salon(
    salon_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    phone: Optional[str] = None,
    # ... other optional fields
):
    """
    Update salon
    
    RLS ensures only salon owner or admin can update
    """
    try:
        updates = {}
        if name is not None:
            updates["name"] = name
        if description is not None:
            updates["description"] = description
        if phone is not None:
            updates["phone"] = phone
        
        salon = supabase_service.update_salon(salon_id, updates)
        
        if not salon:
            raise HTTPException(status_code=404, detail="Salon not found")
        
        return salon
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{salon_id}/approve")
async def approve_salon(
    salon_id: int,
    reviewed_by: str = Form(...),
    rejection_reason: Optional[str] = Form(None)
):
    """
    Approve or reject salon
    
    RLS ensures only admins can approve/reject
    """
    try:
        success = supabase_service.approve_salon(
            salon_id=salon_id,
            reviewed_by=reviewed_by,
            rejection_reason=rejection_reason
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to approve salon")
        
        return {"success": True, "message": "Salon approved" if not rejection_reason else "Salon rejected"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# IMAGE OPERATIONS
# ========================================

@router.post("/{salon_id}/images")
async def upload_salon_image(
    salon_id: int,
    image: UploadFile = File(...),
    image_type: str = Form("gallery")
):
    """
    Upload image for salon to Supabase Storage
    
    RLS ensures only salon owner or admin can upload
    """
    try:
        image_data = await image.read()
        
        # Upload to Supabase Storage
        url = supabase_service.upload_salon_image(
            salon_id=salon_id,
            image_data=image_data,
            filename=f"{image_type}_{image.filename}",
            content_type=image.content_type
        )
        
        return {"url": url, "message": "Image uploaded successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


