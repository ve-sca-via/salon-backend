"""
User Service - Business Logic Layer
Handles all user-related operations (creation, updates, deletion)
Separated from HTTP layer for better testability and reusability
"""
import uuid
import logging
import requests
from typing import Optional, Dict, Any
from app.schemas.user import UserUpdate
from dataclasses import dataclass
from app.core.config import settings
from app.core.database import get_db

logger = logging.getLogger(__name__)


@dataclass
class CreateUserRequest:
    """Data class for user creation request"""
    email: str
    full_name: str
    user_role: str
    password: str
    phone: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    
    def validate(self) -> None:
        """Validate user creation request"""
        if not self.email or not self.full_name:
            raise ValueError("Email and full name are required")
        
        if self.user_role not in ["relationship_manager", "customer"]:
            raise ValueError("Invalid role. Must be 'relationship_manager' or 'customer'")
        
        if not self.email_is_valid():
            raise ValueError("Invalid email format")
    
    def email_is_valid(self) -> bool:
        """Basic email validation"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, self.email) is not None


@dataclass
class UserCreationResult:
    """Result of user creation operation"""
    success: bool
    user_id: Optional[str] = None
    profile_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    rm_profile_created: bool = False


class UserService:
    """
    Service class handling all user management operations.
    Follows Single Responsibility Principle - only handles user business logic.
    """
    
    def __init__(self):
        """Initialize service - uses centralized db client"""
        self.db_url = settings.SUPABASE_URL
        self.service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY
    
    async def create_user(self, request: CreateUserRequest) -> UserCreationResult:
        """
        Create a new user with profile and optional RM profile.
        
        Args:
            request: CreateUserRequest containing user details
            
        Returns:
            UserCreationResult with success status and created user data
            
        Raises:
            ValueError: If validation fails
            Exception: If creation fails after validation
        """
        # Step 1: Validate request
        try:
            request.validate()
        except ValueError as e:
            logger.error(f"Validation failed: {str(e)}")
            return UserCreationResult(success=False, error=str(e))
        
        # Step 2: Check if user already exists
        existing_user = await self._check_existing_user(request.email)
        if existing_user:
            return UserCreationResult(
                success=False,
                error=f"User with email {request.email} already exists"
            )
        
        # Step 3: Create auth user
        try:
            auth_user_id = await self._create_auth_user(request)
        except Exception as e:
            logger.error(f"Failed to create auth user: {str(e)}")
            return UserCreationResult(success=False, error=str(e))
        
        # Step 4: Create profile
        try:
            profile_data = await self._create_profile(auth_user_id, request)
        except Exception as e:
            logger.error(f"Failed to create profile: {str(e)}")
            # Rollback: delete auth user
            await self._delete_auth_user(auth_user_id)
            return UserCreationResult(success=False, error=str(e))
        
        # Step 5: Create RM profile if needed
        if request.user_role == "relationship_manager":
            try:
                rm_profile_data = await self._create_rm_profile(auth_user_id, request)
            except Exception as e:
                logger.warning(f"Failed to create RM profile: {str(e)}")
                # Don't rollback - user and profile are created
        
        logger.info(f"User created successfully: {request.email} ({request.user_role})")
        
        return UserCreationResult(
            success=True,
            user_id=auth_user_id,
            profile_data=profile_data
        )
    
    async def _check_existing_user(self, email: str) -> bool:
        """Check if user with email already exists"""
        db = get_db()
        response = db.table("profiles").select("id").eq("email", email).execute()
        return bool(response.data)
    
    async def _create_auth_user(self, request: CreateUserRequest) -> str:
        """
        Create Supabase auth user.
        
        Returns:
            str: User ID from Supabase Auth
            
        Raises:
            Exception: If auth user creation fails
        """
        headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json"
        }
        
        auth_payload = {
            "email": request.email,
            "password": request.password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": request.full_name,
                "user_role": request.user_role
            }
        }
        
        response = requests.post(
            f"{self.db_url}/auth/v1/admin/users",
            json=auth_payload,
            headers=headers
        )
        
        if response.status_code not in [200, 201]:
            error_msg = f"Auth API returned {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        auth_data = response.json()
        user_id = auth_data.get("id")
        
        if not user_id:
            raise Exception("No user ID returned from auth API")
        
        logger.info(f"Auth user created: {user_id}")
        return user_id
    
    async def _create_profile(
        self, 
        user_id: str, 
        request: CreateUserRequest
    ) -> Dict[str, Any]:
        """
        Create user profile in profiles table.
        
        Returns:
            Dict: Created profile data
            
        Raises:
            Exception: If profile creation fails
        """
        profile_data = {
            "id": user_id,
            "email": request.email,
            "full_name": request.full_name,
            "phone": request.phone if request.phone else None,  # Use None instead of empty string
            "user_role": request.user_role,
            "is_active": True,
            "age": request.age,
            "gender": request.gender
        }
        
        # Use direct HTTP request with service_role key to bypass RLS
        headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        
        response = requests.post(
            f"{self.db_url}/rest/v1/profiles",
            json=profile_data,
            headers=headers
        )
        
        if response.status_code not in [200, 201]:
            error_msg = response.json() if response.text else {}
            logger.error(f"Profile creation failed: {error_msg}")
            raise Exception(str(error_msg))
        
        created_profile = response.json()
        if not created_profile:
            raise Exception("Failed to create profile - no data returned")
        
        logger.info(f"Profile created for {request.email}")
        return created_profile[0] if isinstance(created_profile, list) else created_profile
    
    async def _create_rm_profile(self, user_id: str, request: CreateUserRequest) -> Dict[str, Any]:
        """
        Create RM profile with RM-specific data only.
        User data (name, email, phone) is stored in profiles table.
        Auto-generates employee_id in format RM0001, RM0002, etc.
        
        Returns:
            Dict: Created RM profile data
            
        Raises:
            Exception: If RM profile creation fails
        """
        from datetime import datetime
        
        # Generate next employee_id
        employee_id = await self._generate_next_employee_id()
        
        rm_profile_data = {
            "id": user_id,
            "assigned_territories": [],
            "performance_score": 0,
            "employee_id": employee_id,
            "total_salons_added": 0,
            "total_approved_salons": 0,
            "joining_date": datetime.utcnow().date().isoformat(),  # Set to current date
            "manager_notes": None
        }
        
        # Use direct HTTP request with service_role key to bypass RLS
        headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        
        response = requests.post(
            f"{self.db_url}/rest/v1/rm_profiles",
            json=rm_profile_data,
            headers=headers
        )
        
        if response.status_code not in [200, 201]:
            error_msg = response.json() if response.text else {}
            logger.error(f"RM profile creation failed: {error_msg}")
            raise Exception(str(error_msg))
        
        created_rm_profile = response.json()
        if not created_rm_profile:
            raise Exception("Failed to create RM profile - no data returned")
        
        logger.info(f"RM profile created for {request.email}")
        return created_rm_profile[0] if isinstance(created_rm_profile, list) else created_rm_profile
    
    async def _generate_next_employee_id(self) -> str:
        """
        Generate next sequential employee_id in format RM0001, RM0002, etc.
        
        Returns:
            str: Next employee ID (e.g., "RM0001", "RM0002")
        """
        db = get_db()
        
        # Get all existing employee_ids and find the highest number
        response = db.table("rm_profiles").select("employee_id").not_.is_("employee_id", "null").execute()
        
        max_number = 0
        if response.data:
            for row in response.data:
                emp_id = row.get("employee_id")
                if emp_id and emp_id.startswith("RM"):
                    try:
                        # Extract number part (e.g., "RM0001" -> 1)
                        number = int(emp_id[2:])
                        max_number = max(max_number, number)
                    except (ValueError, IndexError):
                        # Skip invalid formats
                        continue
        
        # Generate next ID
        next_number = max_number + 1
        next_employee_id = f"RM{next_number:04d}"  # Format with 4 digits: RM0001
        
        logger.info(f"Generated employee_id: {next_employee_id}")
        return next_employee_id
    
    async def _delete_auth_user(self, user_id: str) -> None:
        """Delete auth user from Supabase Auth"""
        try:
            headers = {
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
            }
            
            response = requests.delete(
                f"{self.db_url}/auth/v1/admin/users/{user_id}",
                headers=headers
            )
            
            if response.status_code in [200, 204]:
                logger.info(f"Auth user deleted: {user_id}")
            elif response.status_code == 404:
                logger.warning(f"Auth user not found (may already be deleted): {user_id}")
            else:
                logger.error(f"Failed to delete auth user {user_id}: {response.status_code} - {response.text}")
                raise Exception(f"Auth deletion failed with status {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to delete auth user {user_id}: {str(e)}")
            raise
    
    # NOTE: consolidated admin/general update into single implementation below
    
    async def delete_user(self, user_id: str) -> bool:
        """
        Hard delete user from auth and profiles table.
        This allows the email to be reused for new accounts.
        For relationship managers, also deletes their RM profile.
        
        Note: This will fail if user has:
        - Reviews (ON DELETE RESTRICT on reviews.customer_id)
        - Salons as vendor (ON DELETE RESTRICT on salons.vendor_id)
        
        Args:
            user_id: User ID to delete
            
        Returns:
            bool: True if successful
            
        Raises:
            ValueError: If user not found, user is admin, or has dependencies
        """
        # Check if user exists and get role
        db = get_db()
        existing = db.table("profiles").select("id, user_role, email").eq("id", user_id).execute()
        if not existing.data:
            raise ValueError(f"User {user_id} not found")
        
        user_data = existing.data[0]
        user_role = user_data.get("user_role")
        user_email = user_data.get("email")
        
        # Prevent deleting admin users
        if user_role == "admin":
            raise ValueError("Cannot delete admin users")
        
        logger.info(f"Starting deletion process for user {user_id} ({user_email})")
        
        # Check for dependencies that would prevent deletion (ON DELETE RESTRICT constraints)
        
        # 1. Check for bookings
        bookings_check = db.table("bookings").select("id", count="exact").eq("customer_id", user_id).is_("deleted_at", "null").execute()
        if bookings_check.count and bookings_check.count > 0:
            raise ValueError(f"Cannot delete user: Has {bookings_check.count} active booking(s). Please cancel or complete bookings first.")
        
        # 2. Check for booking payments
        payments_check = db.table("booking_payments").select("id", count="exact").eq("customer_id", user_id).is_("deleted_at", "null").execute()
        if payments_check.count and payments_check.count > 0:
            raise ValueError(f"Cannot delete user: Has {payments_check.count} payment record(s). Please resolve payments first.")
        
        # 3. Check for reviews
        reviews_check = db.table("reviews").select("id", count="exact").eq("customer_id", user_id).is_("deleted_at", "null").execute()
        if reviews_check.count and reviews_check.count > 0:
            raise ValueError(f"Cannot delete user: Has {reviews_check.count} active review(s). Please delete reviews first.")
        
        # 4. Check for salons (if vendor)
        if user_role == "vendor":
            salons_check = db.table("salons").select("id", count="exact").eq("vendor_id", user_id).execute()
            if salons_check.count and salons_check.count > 0:
                raise ValueError(f"Cannot delete vendor: Has {salons_check.count} salon(s). Please delete or reassign salons first.")
        
        # Step 1: Delete RM profile first if exists (due to foreign key constraint)
        # This must happen before auth deletion because rm_profiles.id -> auth.users.id (CASCADE)
        if user_role == "relationship_manager":
            try:
                db.table("rm_profiles").delete().eq("id", user_id).execute()
                logger.info(f"RM profile deleted for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to delete RM profile for {user_id}: {str(e)}")
                raise Exception(f"Failed to delete RM profile: {str(e)}")
        
        # Step 2: Delete from Supabase auth
        # This will CASCADE delete the profile due to profiles.id_fkey constraint
        try:
            await self._delete_auth_user(user_id)
            logger.info(f"Auth user deleted for {user_id} (profile auto-deleted via CASCADE)")
        except Exception as e:
            logger.error(f"Failed to delete auth user {user_id}: {str(e)}")
            raise Exception(f"Failed to delete user from authentication system: {str(e)}")
        
        logger.info(f"User {user_id} ({user_email}) fully deleted and email is now available for reuse")
        return True
    
    async def update_user(self, user_id: str, updates: UserUpdate) -> Dict[str, Any]:
        """
        Update user profile with authorization checks.
        
        Args:
            user_id: User ID to update
            updates: Fields to update
            
        Returns:
            Dict with success status and updated data
            
        Raises:
            ValueError: If user not found or invalid updates
            Exception: If update fails
        """
        # Check if user exists and get current data
        db = get_db()
        existing = db.table("profiles").select("*").eq("id", user_id).execute()
        if not existing.data:
            raise ValueError(f"User {user_id} not found")
        
        user_data = existing.data[0]
        current_role = user_data.get("user_role")
        
        # Prevent updating admin users (security measure)
        if current_role == "admin":
            raise ValueError("Cannot modify admin user accounts")
        
        # Validate updates (convert Pydantic model to dict excluding None)
        updates_dict = updates.model_dump(exclude_none=True)

        allowed_fields = {
            "full_name", "phone", "address", "city", "state", 
            "pincode", "profile_image_url", "is_active"
        }
        # Filter out invalid fields
        filtered_updates = {k: v for k, v in updates_dict.items() if k in allowed_fields}
        
        if not filtered_updates:
            raise ValueError("No valid fields to update")
        
        # Prevent deactivating admin users
        if "is_active" in filtered_updates and not filtered_updates["is_active"] and current_role == "admin":
            raise ValueError("Cannot deactivate admin user accounts")
        
        try:
            # Update profile
            response = db.table("profiles").update(filtered_updates).eq("id", user_id).execute()
            
            if not response.data:
                raise Exception("Update failed - no data returned")
            
            updated_user = response.data[0]
            
            # If deactivating RM, also deactivate RM profile
            if (filtered_updates.get("is_active") == False and current_role == "relationship_manager"):
                try:
                    db.table("rm_profiles").update({
                        "is_active": False
                    }).eq("id", user_id).execute()
                    logger.info(f"RM profile also deactivated for user {user_id}")
                except Exception as e:
                    logger.warning(f"Failed to deactivate RM profile for {user_id}: {str(e)}")
            
            logger.info(f"User {user_id} updated: {list(filtered_updates.keys())}")
            
            return {
                "success": True,
                "message": "User updated successfully",
                "data": updated_user
            }
        
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to update user {user_id}: {str(e)}")
            raise Exception(f"Failed to update user: {str(e)}")
    
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        db = get_db()
        response = db.table("profiles").select("*").eq("id", user_id).execute()
        return response.data[0] if response.data else None
    
    async def list_users(
        self, 
        page: int = 1, 
        limit: int = 20,
        search: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        List users with pagination and filters (admin).
        
        Args:
            page: Page number (1-indexed)
            limit: Results per page
            search: Search term for email or full_name
            role: Filter by role
            is_active: Filter by active status
            
        Returns:
            Dict with 'success', 'data', 'total', 'page', 'limit' keys
            
        Raises:
            Exception: If query fails
        """
        try:
            db = get_db()
            offset = (page - 1) * limit
            query = db.table("profiles").select("*", count="exact")
            
            # Apply search filter
            if search:
                query = query.or_(f"email.ilike.%{search}%,full_name.ilike.%{search}%")
            
            # Apply role filter
            if role:
                query = query.eq("user_role", role)
            
            # Apply active status filter
            if is_active is not None:
                query = query.eq("is_active", is_active)
            
            # Execute with pagination
            response = query.order("created_at", desc=True).range(
                offset, offset + limit - 1
            ).execute()
            
            logger.info(
                f"Admin users query - Page: {page}, Total: {response.count}, "
                f"Filters: search={search}, role={role}, is_active={is_active}"
            )
            
            return {
                "success": True,
                "data": response.data or [],
                "total": response.count or 0,
                "page": page,
                "limit": limit
            }
        
        except Exception as e:
            logger.error(f"Failed to list users: {str(e)}")
            raise Exception(f"Failed to fetch users: {str(e)}")
