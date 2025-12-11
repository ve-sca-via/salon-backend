# Authentication & Authorization Architecture

**Last Updated:** December 11, 2025  
**Architecture:** Backend-Only JWT + Service Role + Rate Limiting

---

## Overview

This backend uses **FastAPI + Supabase** in a **backend-only architecture** where:
- FastAPI handles ALL authentication and authorization
- Supabase is used as a database only (not as an auth provider for clients)
- Custom JWT tokens are issued and validated by FastAPI
- Service role key bypasses Row Level Security (RLS)
- **Rate limiting** via SlowAPI prevents brute force attacks
- **Background task** cleans expired tokens every 6 hours
- **Token blacklist** stored in `blacklisted_tokens` table

---

## Architecture Decision: Why Service Role?

### ✅ What We Do (Service Role Mode)

```
Frontend → FastAPI (JWT validation + role checks) → Supabase (service_role)
```

**Flow:**
1. User logs in via `/api/v1/auth/login`
2. FastAPI validates credentials with Supabase Auth
3. FastAPI creates **custom JWT** (HS256, signed with `JWT_SECRET_KEY`)
4. Frontend stores JWT and includes it in `Authorization: Bearer <token>`
5. FastAPI validates JWT on every protected endpoint
6. FastAPI uses **service_role key** for all database operations
7. Authorization logic is explicit in Python code

**Benefits:**
- ✅ Simple and straightforward
- ✅ All auth logic in one place (Python code)
- ✅ Easier to debug (no cryptic RLS errors)
- ✅ More flexible (custom JWT claims, expiration, refresh logic)
- ✅ Standard pattern for backend-driven apps
- ✅ Frontend never directly accesses database

### ❌ What We Don't Do (RLS Mode)

```
Frontend → FastAPI → Supabase (anon key + user JWT)
```

This would require:
- Using Supabase JWT tokens (not custom FastAPI JWT)
- Passing user's `access_token` to Supabase client
- Using `ANON` key instead of `SERVICE_ROLE` key
- Writing and maintaining RLS policies for every table
- Dealing with `auth.uid()` returning user ID from JWT

**Why we avoid this:**
- ❌ More complex (two JWT systems)
- ❌ Less flexible (limited by Supabase JWT structure)
- ❌ Harder to debug (RLS failures are cryptic)
- ❌ Unnecessary for backend-only architecture

---

## Authentication Flow

### User Login

```python
# POST /api/v1/auth/login
{
  "email": "user@example.com",
  "password": "password123"
}

# Backend process:
1. Validate credentials with Supabase Auth (auth_client.sign_in_with_password)
2. Fetch user profile from profiles table (using service_role db client)
3. Check if user is active
4. Create custom JWT token with:
   - sub: user_id (UUID)
   - email: user email
   - user_role: admin|relationship_manager|vendor|customer
   - jti: unique token ID (for blacklist/revocation)
   - exp: expiration timestamp
5. Sign token with JWT_SECRET_KEY (HS256)
6. Return tokens + user data to frontend

# Response:
{
  "success": true,
  "access_token": "eyJhbGc...",  # Custom FastAPI JWT
  "refresh_token": "eyJhbGc...",  # Custom FastAPI JWT
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "user_role": "customer",
    "full_name": "John Doe"
  }
}
```

### Protected Endpoint Access

```python
# GET /api/v1/bookings
# Headers: Authorization: Bearer eyJhbGc...

# Backend process:
1. Extract JWT from Authorization header (HTTPBearer)
2. Verify JWT signature with JWT_SECRET_KEY
3. Check expiration
4. Check if token is blacklisted (token_blacklist table)
5. Fetch user from profiles table to verify still active
6. Extract user_role from JWT
7. Apply authorization logic (role checks, ownership checks)
8. Execute database query with service_role client
9. Return filtered/authorized data

# Authorization examples:
- Customer: Can only see their own bookings
- Vendor: Can see bookings for their salon
- Admin: Can see all bookings
```

---

## Security Model

### JWT Token Structure

```json
{
  "sub": "user-uuid-here",           // User ID
  "email": "user@example.com",       // User email
  "user_role": "customer",           // Role for authorization
  "jti": "unique-token-id",          // For revocation
  "exp": 1700000000                  // Expiration timestamp
}
```

**Signed with:** `JWT_SECRET_KEY` (HS256 algorithm)  
**Expiration:** 30 minutes (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`)

### Authorization Patterns

#### Pattern 1: JWT Validation Only
```python
@router.get("/profile")
async def get_profile(current_user: TokenData = Depends(get_current_user)):
    # current_user.user_id, current_user.email, current_user.user_role available
    return {"user": current_user}
```

#### Pattern 2: Role-Based Access
```python
@router.get("/admin/users")
async def list_users(admin: TokenData = Depends(require_admin)):
    # Only users with user_role='admin' can access
    return db.table("profiles").select("*").execute()
```

#### Pattern 3: Resource Ownership
```python
@router.get("/bookings/{booking_id}")
async def get_booking(
    booking_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Client = Depends(get_db_client)
):
    booking = db.table("bookings").select("*").eq("id", booking_id).single().execute()
    
    # Authorization check: User can only access their own booking (unless admin)
    if booking.data["customer_id"] != current_user.user_id and current_user.user_role != "admin":
        raise HTTPException(403, "Forbidden")
    
    return booking.data
```

#### Pattern 4: Multi-Role Access
```python
@router.get("/salons/{salon_id}/bookings")
async def get_salon_bookings(
    salon_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Client = Depends(get_db_client)
):
    # Different logic based on role
    if current_user.user_role == "vendor":
        # Verify vendor owns this salon
        salon = db.table("salons").select("vendor_id").eq("id", salon_id).single().execute()
        if salon.data["vendor_id"] != current_user.user_id:
            raise HTTPException(403, "Forbidden")
    elif current_user.user_role == "admin":
        # Admins can access any salon
        pass
    else:
        raise HTTPException(403, "Forbidden")
    
    return db.table("bookings").select("*").eq("salon_id", salon_id).execute()
```

---

## Row Level Security (RLS)

### Current Status: **DISABLED**

RLS is disabled on all tables via migration `20251123000000_disable_rls_for_service_role_architecture.sql`

### Why RLS is Disabled

1. **Service role bypasses RLS anyway**
   - Using `SUPABASE_SERVICE_ROLE_KEY` means RLS policies are ignored
   - Having policies creates confusion without providing security

2. **Custom JWT tokens don't work with RLS**
   - RLS policies use `auth.uid()` which expects Supabase JWT
   - Our custom FastAPI JWT tokens aren't recognized by Supabase
   - `auth.uid()` returns `NULL` with service_role → policies fail

3. **Backend-only architecture doesn't need RLS**
   - RLS is designed for client-side database access
   - We control all database access through FastAPI endpoints
   - Authorization is explicit in Python code

### If You Wanted to Enable RLS (Not Recommended)

You would need to:

1. **Stop using custom JWT tokens**
   ```python
   # Don't do this:
   access_token = create_access_token(token_data)
   
   # Do this instead:
   return session.access_token  # Use Supabase's JWT
   ```

2. **Use ANON key with user JWT**
   ```python
   def get_user_db_client(token: str) -> Client:
       client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
       client.postgrest.auth(token)  # Inject user's Supabase JWT
       return client
   ```

3. **Write RLS policies for every table**
   ```sql
   CREATE POLICY "users_select_own" ON profiles
   FOR SELECT USING (auth.uid() = id);
   ```

4. **Give up custom JWT features**
   - No custom claims (JTI for blacklist)
   - Limited control over expiration
   - Can't add custom authorization metadata

**Bottom line:** Not worth it for backend-only apps.

---

## Security Checklist

### ✅ What We Do Right

- [x] Service role key only in backend `.env` (never exposed to frontend)
- [x] JWT validation on all protected endpoints via `Depends(get_current_user)`
- [x] Role-based authorization helpers (`require_admin`, `require_vendor`, etc.)
- [x] Token blacklist for logout/revocation
- [x] Password hashing via Supabase Auth
- [x] Input validation via Pydantic schemas
- [x] XSS protection via `html.escape()` on user-generated content
- [x] CORS configuration restricted to known origins
- [x] Audit logging for sensitive operations

### ⚠️ Must Maintain

1. **Never expose service_role key**
   ```bash
   # ❌ NEVER do this
   VITE_SUPABASE_SERVICE_ROLE_KEY=... # in frontend .env
   
   # ✅ Only in backend .env
   SUPABASE_SERVICE_ROLE_KEY=... # backend only
   ```

2. **Every endpoint must have auth**
   ```python
   # ❌ BAD: No authorization
   @router.get("/users/{user_id}")
   async def get_user(user_id: str):
       return db.table("profiles").select("*").eq("id", user_id).single().execute()
   
   # ✅ GOOD: JWT validation + authorization
   @router.get("/users/{user_id}")
   async def get_user(
       user_id: str,
       current_user: TokenData = Depends(get_current_user)
   ):
       if current_user.user_id != user_id and current_user.user_role != "admin":
           raise HTTPException(403, "Forbidden")
       return db.table("profiles").select("*").eq("id", user_id).single().execute()
   ```

3. **Never trust client-provided IDs**
   ```python
   # ❌ BAD: Client can fake user_id
   @router.get("/bookings")
   async def get_bookings(user_id: str):  # From query param
       return db.table("bookings").eq("user_id", user_id).execute()
   
   # ✅ GOOD: Use JWT claims
   @router.get("/bookings")
   async def get_bookings(current_user: TokenData = Depends(get_current_user)):
       return db.table("bookings").eq("user_id", current_user.user_id).execute()
   ```

4. **Rate limit auth endpoints**
   ```python
   # ✅ ALREADY IMPLEMENTED
   from app.core.rate_limit import limiter, RateLimits
   
   @router.post("/auth/login")
   @limiter.limit(RateLimits.AUTH_LOGIN)  # 5/minute
   async def login(request: Request, ...):
       pass
   ```

---

## Token Management

### Token Lifecycle

```
1. Login → Create access_token (30min) + refresh_token (7 days)
2. Access protected endpoints → Validate access_token
3. Token expires → Use refresh_token to get new access_token
4. Logout → Add token JTI to blacklist
5. Blacklisted tokens → Rejected even if not expired
```

### Token Blacklist

```python
# On logout, token is added to token_blacklist table
{
  "token_jti": "unique-token-id",
  "user_id": "user-uuid",
  "expires_at": "2025-11-23T12:00:00Z"
}

# On every request, we check:
blacklist_check = db.table("token_blacklist").select("id").eq("token_jti", jti).execute()
if blacklist_check.data:
    raise HTTPException(401, "Token has been revoked")
```

### Refresh Token Flow

```python
# POST /api/v1/auth/refresh
{
  "refresh_token": "eyJhbGc..."
}

# Backend process:
1. Verify refresh_token signature
2. Check if refresh_token is blacklisted
3. Fetch latest user data from database
4. Create new access_token + new refresh_token
5. Return new tokens

# Response:
{
  "access_token": "new-token",
  "refresh_token": "new-refresh-token"
}
```

---

## User Roles

| Role | Code | Permissions |
|------|------|-------------|
| **Admin** | `admin` | Full system access, manage all resources, approve salons, manage RMs |
| **Relationship Manager** | `relationship_manager` | Manage assigned salons, verify vendors, view reports |
| **Vendor** | `vendor` | Manage own salon, services, staff, bookings |
| **Customer** | `customer` | Browse salons, create bookings, write reviews |

### Role Hierarchy

```
admin (highest authority)
  ├── Can access all endpoints
  ├── Can impersonate other roles
  └── Can modify system configuration

relationship_manager
  ├── Can manage assigned salons
  ├── Can approve/reject vendor requests
  └── Limited to assigned territory

vendor
  ├── Can manage own salon only
  ├── Can view own salon's bookings/payments
  └── Cannot access other vendor data

customer (lowest privilege)
  ├── Can create bookings
  ├── Can view own data only
  └── Public read access to salons/services
```

---

## Common Patterns

### Public Endpoints (No Auth Required)

```python
@router.get("/salons/public")
async def get_public_salons():
    # Anyone can access
    return db.table("salons").select("*").eq("is_verified", True).execute()
```

### Authenticated Endpoints

```python
@router.get("/profile")
async def get_profile(current_user: TokenData = Depends(get_current_user)):
    # Must be logged in
    return db.table("profiles").select("*").eq("id", current_user.user_id).single().execute()
```

### Admin-Only Endpoints

```python
@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    admin: TokenData = Depends(require_admin)
):
    # Only admins can access
    return db.table("profiles").delete().eq("id", user_id).execute()
```

### Multi-Role Endpoints

```python
@router.get("/bookings")
async def get_bookings(
    current_user: TokenData = Depends(get_current_user),
    db: Client = Depends(get_db_client)
):
    if current_user.user_role == "customer":
        # Customers see only their bookings
        bookings = db.table("bookings").select("*").eq("customer_id", current_user.user_id).execute()
    elif current_user.user_role == "vendor":
        # Vendors see bookings for their salon
        salon = db.table("salons").select("id").eq("vendor_id", current_user.user_id).single().execute()
        bookings = db.table("bookings").select("*").eq("salon_id", salon.data["id"]).execute()
    elif current_user.user_role == "admin":
        # Admins see all bookings
        bookings = db.table("bookings").select("*").execute()
    else:
        raise HTTPException(403, "Forbidden")
    
    return bookings.data
```

---

## Environment Variables

### Required Auth Variables

```bash
# JWT Configuration (Backend only)
JWT_SECRET_KEY="your-super-secret-jwt-key-min-32-chars"  # CRITICAL: Never commit to git
JWT_ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Supabase Configuration
SUPABASE_URL="https://your-project.supabase.co"
SUPABASE_ANON_KEY="eyJhbGc..."           # For auth operations (sign_in, sign_up)
SUPABASE_SERVICE_ROLE_KEY="eyJhbGc..."  # For database operations (CRITICAL: Never expose)

# Database
DATABASE_URL="postgresql://postgres:password@..."  # Direct connection (optional)
```

### Frontend Variables

```bash
# Frontend .env (safe to expose)
VITE_SUPABASE_URL="https://your-project.supabase.co"
VITE_SUPABASE_ANON_KEY="eyJhbGc..."  # ✅ Safe to expose (limited permissions)
VITE_API_URL="http://localhost:8000"

# ❌ NEVER put these in frontend
# SUPABASE_SERVICE_ROLE_KEY  # Would give god-mode access
# JWT_SECRET_KEY              # Would allow forging tokens
```

---

## Testing

### Mock Authentication in Tests

```python
# tests/conftest.py
@pytest.fixture
def mock_admin_user():
    return TokenData(
        user_id="admin-uuid",
        email="admin@example.com",
        user_role="admin",
        jti="test-jti",
        exp=datetime.utcnow() + timedelta(hours=1)
    )

# Override dependency
def test_admin_endpoint(client, mock_admin_user):
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    response = client.get("/api/v1/admin/users")
    assert response.status_code == 200
```

---

## Migration Guide

### From RLS Mode to Service Role Mode (Already Done)

✅ **Completed Steps:**
1. Created migration to disable RLS on all tables
2. Documented architecture decision in `database.py`
3. Created this architecture documentation

### If You Need to Switch to RLS Mode (Not Recommended)

1. Remove custom JWT creation
2. Return Supabase JWT from login endpoint
3. Create per-request Supabase clients with user JWT
4. Enable RLS on all tables
5. Write comprehensive RLS policies
6. Test extensively (RLS failures are hard to debug)

---

## Troubleshooting

### "Permission denied for table X"

**Cause:** RLS is enabled but you're using service_role (which should bypass RLS).  
**Fix:** Run migration to disable RLS: `20251123000000_disable_rls_for_service_role_architecture.sql`

### "auth.uid() returns null"

**Cause:** RLS policy expects Supabase JWT, but you're using custom FastAPI JWT.  
**Fix:** Disable RLS (we don't need it with service_role).

### "Invalid token"

**Causes:**
1. Token expired → Use refresh token flow
2. Token blacklisted → User logged out
3. Wrong JWT_SECRET_KEY → Check environment variables
4. Malformed token → Client error

### "Forbidden" errors

**Causes:**
1. Missing authorization check in endpoint
2. Role mismatch (customer trying to access vendor endpoint)
3. Resource ownership violation

---

## Future Considerations

### Potential Improvements

1. **Rate Limiting** ✅ IMPLEMENTED
   - `slowapi` integrated for brute-force protection
   - Login attempts: 5/minute per IP
   - Signup: 3/minute per IP
   - Standard endpoints: 60/minute per IP

2. **Token Rotation**
   - Automatically rotate refresh tokens on use
   - Invalidate old refresh token when new one is issued

3. **Multi-Factor Authentication (MFA)**
   - OTP via SMS or email
   - TOTP (Google Authenticator)

4. **Session Management**
   - Track active sessions per user
   - Allow users to view/revoke active sessions

5. **Audit Logging** ✅ PARTIALLY IMPLEMENTED
   - Activity logs table tracks key events
   - Authentication events logged
   - Email notification logs tracked
   - Failed login tracking: TODO

---

## References

- [FastAPI Security Documentation](https://fastapi.tiangolo.com/tutorial/security/)
- [Supabase Auth Documentation](https://supabase.com/docs/guides/auth)
- [JWT Best Practices](https://tools.ietf.org/html/rfc8725)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)

---

## Current API Endpoints (December 2025)

### Authentication Endpoints
- `POST /api/v1/auth/login` - User login (rate limited: 5/min)
- `POST /api/v1/auth/signup` - User signup (rate limited: 3/min)
- `POST /api/v1/auth/refresh` - Refresh access token
- `POST /api/v1/auth/logout` - Logout (blacklist token)
- `POST /api/v1/auth/logout-all` - Logout all sessions
- `POST /api/v1/auth/password-reset` - Request password reset
- `POST /api/v1/auth/password-reset-confirm` - Confirm password reset
- `GET /api/v1/auth/me` - Get current user profile

### Protected Endpoint Categories
- **Customer**: `/api/v1/customers/*` (cart, bookings, favorites, reviews)
- **Vendor**: `/api/v1/vendors/*` (salon, services, staff, analytics)
- **RM**: `/api/v1/rm/*` (vendor requests, salons, profile, leaderboard)
- **Admin**: `/api/v1/admin/*` (users, salons, config, dashboard, rms)
- **Payments**: `/api/v1/payments/*` (orders, verify, history)
- **Public**: `/api/v1/salons/*` (browse, search, details)

---

**Last Reviewed:** December 11, 2025  
**Author:** Development Team  
**Status:** Production Ready ✅
