"""
Authentication and Authorization Module
Handles JWT token verification and role-based access control
"""
from fastapi import HTTPException, Security, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
from supabase import create_client, Client
from app.core.config import settings
import logging
import uuid

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer()

# Initialize Supabase client with service role key
# Service role bypasses RLS automatically
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


# =====================================================
# PYDANTIC MODELS
# =====================================================

class TokenData(BaseModel):
    """Token payload data"""
    user_id: str
    email: str
    role: str
    jti: Optional[str] = None  # JWT ID for revocation (optional for backward compatibility)
    exp: Optional[datetime] = None


class TokenPayload(BaseModel):
    """JWT token payload"""
    sub: str  # user_id
    email: str
    role: str
    jti: str  # JWT ID for token revocation
    exp: int


# =====================================================
# JWT TOKEN FUNCTIONS
# =====================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT access token with JTI (JWT ID) for revocation support
    
    Args:
        data: Dictionary containing user data (user_id, email, role)
        expires_delta: Optional expiration time delta
    
    Returns:
        Encoded JWT token string with jti claim
    """
    to_encode = data.copy()
    
    # Generate unique JWT ID (jti) for token revocation
    jti = str(uuid.uuid4())
    to_encode.update({"jti": jti})
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """
    Create JWT refresh token with longer expiration and JTI for revocation
    
    Args:
        data: Dictionary containing user data
    
    Returns:
        Encoded JWT refresh token string with jti claim
    """
    to_encode = data.copy()
    
    # Generate unique JWT ID (jti) for token revocation
    jti = str(uuid.uuid4())
    to_encode.update({"jti": jti})
    
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    
    return encoded_jwt


def verify_token(token: str) -> TokenPayload:
    """
    Verify and decode JWT token, checking against blacklist
    
    Args:
        token: JWT token string
    
    Returns:
        TokenPayload with user data
    
    Raises:
        HTTPException: If token is invalid, expired, or blacklisted
    """
    logger.info(f"🔍 verify_token called")
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        role: str = payload.get("role")
        jti: str = payload.get("jti")
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user_id",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check if token is blacklisted (revoked)
        if jti:
            logger.info(f"Checking if token is blacklisted: {jti}")
            blacklist_check = supabase.table("token_blacklist").select("id").eq("token_jti", jti).execute()
            logger.info(f"Blacklist check result: {blacklist_check.data}")
            if blacklist_check.data:
                logger.warning(f"⚠️ BLOCKED: Attempt to use blacklisted token: {jti}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            logger.info(f"✓ Token not blacklisted: {jti}")
        
        return TokenPayload(sub=user_id, email=email, role=role, jti=jti, exp=payload.get("exp"))
    
    except JWTError as e:
        logger.error(f"JWT verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_refresh_token(token: str) -> dict:
    """
    Verify and decode JWT refresh token, checking against blacklist
    
    Args:
        token: JWT refresh token string
    
    Returns:
        Dictionary with token data
    
    Raises:
        HTTPException: If token is invalid, expired, or blacklisted
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        role: str = payload.get("role")
        jti: str = payload.get("jti")
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check if refresh token is blacklisted (revoked)
        if jti:
            blacklist_check = supabase.table("token_blacklist").select("id").eq("token_jti", jti).execute()
            if blacklist_check.data:
                logger.warning(f"Attempt to use blacklisted refresh token: {jti}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token has been revoked",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        
        return {
            "sub": user_id,
            "email": email,
            "role": role,
            "jti": jti
        }
    
    except JWTError as e:
        logger.error(f"Refresh token verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# =====================================================
# TOKEN REVOCATION FUNCTIONS
# =====================================================

def revoke_token(token_jti: str, user_id: str, token_type: str, expires_at: datetime, reason: str = "logout") -> bool:
    """
    Add token to blacklist to revoke it
    
    Args:
        token_jti: JWT ID (jti claim) of the token to revoke
        user_id: User ID who owns the token
        token_type: 'access' or 'refresh'
        expires_at: Token expiration timestamp
        reason: Reason for revocation (logout, security, etc.)
    
    Returns:
        True if successfully blacklisted
    
    Raises:
        HTTPException: If blacklist insertion fails
    """
    try:
        logger.info(f"Attempting to revoke token: {token_jti} for user {user_id}")
        logger.debug(f"Using Supabase URL: {settings.SUPABASE_URL}")
        logger.debug(f"Service role key present: {bool(settings.SUPABASE_SERVICE_ROLE_KEY)}")
        
        result = supabase.table("token_blacklist").insert({
            "token_jti": token_jti,
            "user_id": user_id,
            "token_type": token_type,
            "expires_at": expires_at.isoformat(),
            "reason": reason
        }).execute()
        
        if result.data:
            logger.info(f"✓ Token successfully revoked: {token_jti}")
            return True
        
        logger.warning(f"Token revocation returned no data: {token_jti}")
        return False
    except Exception as e:
        logger.error(f"Failed to revoke token: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception details: {repr(e)}")
        if hasattr(e, 'message'):
            logger.error(f"Exception message: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke token"
        )


def revoke_all_user_tokens(user_id: str, reason: str = "security") -> int:
    """
    Revoke all tokens for a specific user (useful for security incidents)
    
    Args:
        user_id: User ID whose tokens should be revoked
        reason: Reason for mass revocation
    
    Returns:
        Number of tokens revoked
    """
    try:
        # This is a placeholder - in reality you'd need to track all active tokens
        # For now, we log the action and return 0 (will be implemented with token tracking)
        logger.warning(f"Mass token revocation requested for user {user_id}, reason: {reason}")
        return 0
    except Exception as e:
        logger.error(f"Failed to revoke user tokens: {str(e)}")
        return 0


def cleanup_expired_tokens() -> int:
    """
    Remove expired tokens from blacklist (can be run as periodic job)
    
    Returns:
        Number of expired tokens removed
    """
    try:
        now = datetime.utcnow().isoformat()
        result = supabase.table("token_blacklist").delete().lt("expires_at", now).execute()
        count = len(result.data) if result.data else 0
        logger.info(f"Cleaned up {count} expired tokens from blacklist")
        return count
    except Exception as e:
        logger.error(f"Failed to cleanup expired tokens: {str(e)}")
        return 0


# =====================================================
# AUTHENTICATION DEPENDENCIES
# =====================================================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> TokenData:
    """
    Dependency to get current authenticated user from JWT token
    
    Args:
        credentials: Bearer token from Authorization header
    
    Returns:
        TokenData object with user information
    
    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials
    token_data = verify_token(token)
    
    # Verify user exists and is active
    try:
        user_response = supabase.table("profiles").select(
            "id, email, role, is_active"
        ).eq("id", token_data.sub).single().execute()
        
        if not user_response.data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user = user_response.data
        
        if not user.get("is_active", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive"
            )
        
        return TokenData(
            user_id=user["id"],
            email=user["email"],
            role=user["role"],
            jti=token_data.jti,
            exp=datetime.utcfromtimestamp(token_data.exp) if token_data.exp else None
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )


async def get_current_user_id(
    current_user: TokenData = Depends(get_current_user)
) -> str:
    """
    Dependency to get only the user ID
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        User ID string
    """
    return current_user.user_id


# =====================================================
# ROLE-BASED AUTHORIZATION
# =====================================================

class RoleChecker:
    """
    Dependency class to check if user has required role(s)
    
    Usage:
        @router.get("/admin-only", dependencies=[Depends(RoleChecker(["admin"]))])
        async def admin_endpoint():
            pass
    """
    
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles
    
    async def __call__(self, current_user: TokenData = Depends(get_current_user)):
        if current_user.role not in self.allowed_roles:
            logger.warning(
                f"User {current_user.user_id} with role '{current_user.role}' "
                f"attempted to access resource requiring roles: {self.allowed_roles}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {', '.join(self.allowed_roles)}"
            )
        return current_user


# =====================================================
# SPECIFIC ROLE DEPENDENCIES
# =====================================================

async def require_admin(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """
    Dependency to require admin role
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        TokenData if user is admin
    
    Raises:
        HTTPException: If user is not admin
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def require_rm(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """
    Dependency to require RM (Relationship Manager) role
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        TokenData if user is RM
    
    Raises:
        HTTPException: If user is not RM
    """
    if current_user.role != "relationship_manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Relationship Manager access required"
        )
    return current_user


async def require_vendor(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """
    Dependency to require vendor role
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        TokenData if user is vendor
    
    Raises:
        HTTPException: If user is not vendor
    """
    if current_user.role != "vendor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor access required"
        )
    return current_user


async def require_customer(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """
    Dependency to require customer role
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        TokenData if user is customer
    
    Raises:
        HTTPException: If user is not customer
    """
    if current_user.role != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer access required"
        )
    return current_user


# =====================================================
# SPECIAL TOKEN GENERATION
# =====================================================

def create_registration_token(request_id: str, salon_id: str, owner_email: str) -> str:
    """
    Create special JWT token for vendor registration link
    Shorter expiration time (7 days)
    
    Args:
        request_id: Vendor join request ID
        salon_id: Salon ID
        owner_email: Vendor owner email
    
    Returns:
        Encoded JWT token for registration
    """
    data = {
        "sub": "registration",
        "request_id": request_id,
        "salon_id": salon_id,
        "email": owner_email,
        "type": "registration"
    }
    
    expire = datetime.utcnow() + timedelta(days=7)
    data.update({"exp": expire})
    
    token = jwt.encode(
        data,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    
    return token


def verify_registration_token(token: str) -> dict:
    """
    Verify registration token and extract data
    
    Args:
        token: Registration JWT token
    
    Returns:
        Dictionary with request_id, salon_id, email
    
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        if payload.get("type") != "registration":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token type"
            )
        
        return {
            "request_id": payload.get("request_id"),
            "salon_id": payload.get("salon_id"),
            "email": payload.get("email")
        }
    
    except JWTError as e:
        logger.error(f"Registration token verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired registration token"
        )


# =====================================================
# UTILITY FUNCTIONS
# =====================================================

async def get_user_salon_id(user_id: str) -> Optional[str]:
    """
    Get salon ID for vendor user
    
    Args:
        user_id: User ID
    
    Returns:
        Salon ID if user is vendor owner, None otherwise
    """
    try:
        response = supabase.table("salons").select("id").eq(
            "owner_id", user_id
        ).eq("is_active", True).single().execute()
        
        return response.data.get("id") if response.data else None
    
    except Exception:
        return None


async def verify_salon_access(user: TokenData, salon_id: str) -> bool:
    """
    Verify if user has access to specific salon
    
    Args:
        user: Current user token data
        salon_id: Salon ID to check access
    
    Returns:
        True if user has access, False otherwise
    """
    # Admins have access to all salons
    if user.role == "admin":
        return True
    
    # Vendors can only access their own salon
    if user.role == "vendor":
        user_salon_id = await get_user_salon_id(user.user_id)
        return user_salon_id == salon_id
    
    return False
