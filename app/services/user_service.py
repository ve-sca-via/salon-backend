"""
User Service - Business Logic Layer
Handles all admin user-management operations (creation, updates, deletion, listing).
Separated from the HTTP layer for testability and reuse.

Uses the injected Supabase service-role client for all access (DB tables + the
GoTrue admin auth API), consistent with the other service classes.
"""
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

from app.schemas.user import UserUpdate

logger = logging.getLogger(__name__)


@dataclass
class CreateUserRequest:
    """Data class for a user-creation request (already schema-validated upstream)."""
    email: str
    full_name: str
    user_role: str
    password: str
    phone: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None


@dataclass
class UserCreationResult:
    """Result of a user-creation operation."""
    success: bool
    user_id: Optional[str] = None
    profile_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    rm_profile_created: bool = False


class UserService:
    """Admin user-management operations. Takes a Supabase service-role client."""

    def __init__(self, db_client):
        """Initialize service with a Supabase client (service-role)."""
        self.db = db_client

    async def create_user(self, request: CreateUserRequest) -> UserCreationResult:
        """
        Create a new user with profile and optional RM profile.

        Returns a UserCreationResult; never raises for expected failures
        (duplicate email, auth/profile errors) — those are reported via `error`.
        """
        # Step 1: Reject duplicate email up front
        if await self._check_existing_user(request.email):
            return UserCreationResult(
                success=False,
                error=f"User with email {request.email} already exists",
            )

        # Step 2: Create the auth user
        try:
            auth_user_id = await self._create_auth_user(request)
        except Exception as e:
            logger.error(f"Failed to create auth user: {str(e)}")
            return UserCreationResult(success=False, error="Failed to create authentication account")

        # Step 3: Create the profile (rollback the auth user on failure)
        try:
            profile_data = await self._create_profile(auth_user_id, request)
        except Exception as e:
            logger.error(f"Failed to create profile: {str(e)}")
            await self._delete_auth_user(auth_user_id)
            return UserCreationResult(success=False, error="Failed to create user profile")

        # Step 4: Create the RM profile when needed (non-fatal on failure)
        rm_created = False
        if request.user_role == "relationship_manager":
            try:
                await self._create_rm_profile(auth_user_id, request)
                rm_created = True
            except Exception as e:
                logger.warning(f"Failed to create RM profile: {str(e)}")
                # Don't roll back — user and profile already exist.

        logger.info(f"User created successfully: {request.email} ({request.user_role})")
        return UserCreationResult(
            success=True,
            user_id=auth_user_id,
            profile_data=profile_data,
            rm_profile_created=rm_created,
        )

    async def _check_existing_user(self, email: str) -> bool:
        """Return True if a profile with this email already exists."""
        response = self.db.table("profiles").select("id").eq("email", email).execute()
        return bool(response.data)

    async def _create_auth_user(self, request: CreateUserRequest) -> str:
        """Create the Supabase auth user via the GoTrue admin API. Returns its id."""
        res = self.db.auth.admin.create_user({
            "email": request.email,
            "password": request.password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": request.full_name,
                "user_role": request.user_role,
            },
        })
        user_id = getattr(getattr(res, "user", None), "id", None)
        if not user_id:
            raise Exception("No user ID returned from auth API")
        logger.info(f"Auth user created: {user_id}")
        return user_id

    async def _create_profile(self, user_id: str, request: CreateUserRequest) -> Dict[str, Any]:
        """Insert the profile row. Returns the created profile."""
        profile_data = {
            "id": user_id,
            "email": request.email,
            "full_name": request.full_name,
            "phone": request.phone if request.phone else None,
            "user_role": request.user_role,
            "is_active": True,
            "age": request.age,
            "gender": request.gender,
        }
        response = self.db.table("profiles").insert(profile_data).execute()
        if not response.data:
            raise Exception("Failed to create profile - no data returned")
        created = response.data
        logger.info(f"Profile created for {request.email}")
        return created[0] if isinstance(created, list) else created

    async def _create_rm_profile(self, user_id: str, request: CreateUserRequest) -> Dict[str, Any]:
        """
        Create the RM profile (RM-specific data only; identity lives in profiles).
        Auto-generates employee_id in the RM0001, RM0002, ... format.
        """
        from datetime import datetime

        rm_profile_data = {
            "id": user_id,
            "assigned_territories": [],
            "performance_score": 0,
            "employee_id": await self._generate_next_employee_id(),
            "total_salons_added": 0,
            "total_approved_salons": 0,
            "joining_date": datetime.utcnow().date().isoformat(),
            "manager_notes": None,
        }
        response = self.db.table("rm_profiles").insert(rm_profile_data).execute()
        if not response.data:
            raise Exception("Failed to create RM profile - no data returned")
        created = response.data
        logger.info(f"RM profile created for {request.email}")
        return created[0] if isinstance(created, list) else created

    async def _generate_next_employee_id(self) -> str:
        """Generate the next sequential employee_id (RM0001, RM0002, ...)."""
        response = (
            self.db.table("rm_profiles")
            .select("employee_id")
            .not_.is_("employee_id", "null")
            .execute()
        )

        max_number = 0
        for row in response.data or []:
            emp_id = row.get("employee_id")
            if emp_id and emp_id.startswith("RM"):
                try:
                    max_number = max(max_number, int(emp_id[2:]))
                except (ValueError, IndexError):
                    continue

        next_employee_id = f"RM{max_number + 1:04d}"
        logger.info(f"Generated employee_id: {next_employee_id}")
        return next_employee_id

    async def _delete_auth_user(self, user_id: str) -> None:
        """Delete the auth user via the GoTrue admin API (404 is treated as success)."""
        try:
            self.db.auth.admin.delete_user(user_id)
            logger.info(f"Auth user deleted: {user_id}")
        except Exception as e:
            msg = str(e).lower()
            if "not found" in msg or "404" in msg:
                logger.warning(f"Auth user not found (may already be deleted): {user_id}")
                return
            logger.error(f"Failed to delete auth user {user_id}: {str(e)}")
            raise

    async def delete_user(self, user_id: str) -> bool:
        """
        Hard-delete a user from auth and (via CASCADE) the profiles table, freeing
        the email for reuse. Also deletes the RM profile for relationship managers.

        Raises ValueError if the user is missing, is an admin, or has blocking
        dependencies (active bookings/payments/reviews, or salons as a vendor).
        """
        existing = self.db.table("profiles").select("id, user_role, email").eq("id", user_id).execute()
        if not existing.data:
            raise ValueError(f"User {user_id} not found")

        user_data = existing.data[0]
        user_role = user_data.get("user_role")
        user_email = user_data.get("email")

        if user_role == "admin":
            raise ValueError("Cannot delete admin users")

        logger.info(f"Starting deletion process for user {user_id} ({user_email})")

        # Dependency checks (ON DELETE RESTRICT constraints)
        bookings_check = self.db.table("bookings").select("id", count="exact").eq("customer_id", user_id).is_("deleted_at", "null").execute()
        if bookings_check.count and bookings_check.count > 0:
            raise ValueError(f"Cannot delete user: Has {bookings_check.count} active booking(s). Please cancel or complete bookings first.")

        payments_check = self.db.table("booking_payments").select("id", count="exact").eq("customer_id", user_id).is_("deleted_at", "null").execute()
        if payments_check.count and payments_check.count > 0:
            raise ValueError(f"Cannot delete user: Has {payments_check.count} payment record(s). Please resolve payments first.")

        reviews_check = self.db.table("reviews").select("id", count="exact").eq("customer_id", user_id).is_("deleted_at", "null").execute()
        if reviews_check.count and reviews_check.count > 0:
            raise ValueError(f"Cannot delete user: Has {reviews_check.count} active review(s). Please delete reviews first.")

        if user_role in ["vendor", "regular_buyer"]:
            salons_check = self.db.table("salons").select("id", count="exact").eq("vendor_id", user_id).execute()
            if salons_check.count and salons_check.count > 0:
                raise ValueError(f"Cannot delete vendor: Has {salons_check.count} salon(s). Please delete or reassign salons first.")

        # Delete RM profile first (rm_profiles.id -> auth.users.id CASCADE)
        if user_role == "relationship_manager":
            try:
                self.db.table("rm_profiles").delete().eq("id", user_id).execute()
                logger.info(f"RM profile deleted for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to delete RM profile for {user_id}: {str(e)}")
                raise Exception(f"Failed to delete RM profile: {str(e)}")

        # Delete the auth user (CASCADE-deletes the profile)
        try:
            await self._delete_auth_user(user_id)
            logger.info(f"Auth user deleted for {user_id} (profile auto-deleted via CASCADE)")
        except Exception as e:
            logger.error(f"Failed to delete auth user {user_id}: {str(e)}")
            raise Exception(f"Failed to delete user from authentication system: {str(e)}")

        logger.info(f"User {user_id} ({user_email}) fully deleted and email is now available for reuse")
        return True

    # Fields an admin may update via the user-management screen.
    ALLOWED_UPDATE_FIELDS = {"full_name", "phone", "is_active"}

    async def update_user(self, user_id: str, updates: UserUpdate) -> Dict[str, Any]:
        """
        Update a user's profile (admin). Admin accounts cannot be modified.

        Raises ValueError if the user is missing, is an admin, or no valid fields
        are supplied.
        """
        existing = self.db.table("profiles").select("*").eq("id", user_id).execute()
        if not existing.data:
            raise ValueError(f"User {user_id} not found")

        current_role = existing.data[0].get("user_role")
        if current_role == "admin":
            raise ValueError("Cannot modify admin user accounts")

        updates_dict = updates.model_dump(exclude_none=True)
        filtered_updates = {k: v for k, v in updates_dict.items() if k in self.ALLOWED_UPDATE_FIELDS}
        if not filtered_updates:
            raise ValueError("No valid fields to update")

        try:
            response = self.db.table("profiles").update(filtered_updates).eq("id", user_id).execute()
            if not response.data:
                raise Exception("Update failed - no data returned")

            updated_user = response.data[0]

            # Deactivating an RM also deactivates their RM profile
            if filtered_updates.get("is_active") is False and current_role == "relationship_manager":
                try:
                    self.db.table("rm_profiles").update({"is_active": False}).eq("id", user_id).execute()
                    logger.info(f"RM profile also deactivated for user {user_id}")
                except Exception as e:
                    logger.warning(f"Failed to deactivate RM profile for {user_id}: {str(e)}")

            logger.info(f"User {user_id} updated: {list(filtered_updates.keys())}")
            return {"success": True, "message": "User updated successfully", "data": updated_user}

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to update user {user_id}: {str(e)}")
            raise Exception(f"Failed to update user: {str(e)}")

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a single user by id."""
        response = self.db.table("profiles").select("*").eq("id", user_id).execute()
        return response.data[0] if response.data else None

    async def list_users(
        self,
        page: int = 1,
        limit: int = 20,
        search: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        include_internal: bool = False,
    ) -> Dict[str, Any]:
        """
        List users with pagination and filters (admin).

        include_internal is False for client admins, so internal staff accounts
        do not appear in their user list. Those accounts show as ordinary
        admins otherwise, which invites questions about who published content
        the client did not publish themselves.
        """
        try:
            offset = (page - 1) * limit
            query = self.db.table("profiles").select("*", count="exact")

            if not include_internal:
                query = query.eq("is_internal", False)

            # Search: per-column .ilike() (or_() is unreliable in supabase-py URL encoding)
            if search and search.strip():
                pattern = f"%{search.strip()}%"
                matching_ids = set()
                for column in ("email", "full_name", "phone"):
                    try:
                        id_query = self.db.table("profiles").select("id").ilike(column, pattern)
                        if not include_internal:
                            # This lookup bypasses the query above, so it needs
                            # its own filter or search would surface staff.
                            id_query = id_query.eq("is_internal", False)
                        id_rows = id_query.execute()
                        for row in id_rows.data or []:
                            matching_ids.add(row["id"])
                    except Exception as col_err:
                        logger.warning("User search skipped column %s: %s", column, col_err)
                if not matching_ids:
                    return {"success": True, "data": [], "total": 0, "page": page, "limit": limit}
                query = query.in_("id", list(matching_ids))

            if role:
                query = query.eq("user_role", role)
            if is_active is not None:
                query = query.eq("is_active", is_active)

            response = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()

            logger.info(
                f"Admin users query - Page: {page}, Total: {response.count}, "
                f"Filters: search={search}, role={role}, is_active={is_active}"
            )
            return {
                "success": True,
                "data": response.data or [],
                "total": response.count or 0,
                "page": page,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Failed to list users: {str(e)}")
            raise Exception(f"Failed to fetch users: {str(e)}")
