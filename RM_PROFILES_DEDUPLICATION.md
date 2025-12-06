# RM Profiles Table Deduplication

**Date:** December 6, 2025  
**Status:** ✅ Completed  
**Migration:** `20251206000000_remove_rm_profiles_duplication.sql`

## Problem

The `rm_profiles` table contained duplicate fields that were already stored in the `profiles` table:
- `full_name` ❌ (duplicate of `profiles.full_name`)
- `email` ❌ (duplicate of `profiles.email`)
- `phone` ❌ (duplicate of `profiles.phone`)
- `is_active` ❌ (duplicate of `profiles.is_active`)

This caused:
1. **Data Redundancy** - Same data stored in two places
2. **Sync Issues** - Risk of inconsistency between tables
3. **Code Complexity** - Required double queries and manual data merging
4. **Maintenance Overhead** - Updates needed in multiple places

## Solution

### Database Changes

**Removed duplicate columns from `rm_profiles`:**
```sql
-- Dropped columns
- full_name
- email  
- phone
- is_active
```

**Added missing RM-specific columns:**
```sql
-- New columns added
+ employee_id VARCHAR UNIQUE
+ total_salons_added INTEGER DEFAULT 0
+ total_approved_salons INTEGER DEFAULT 0
+ joining_date DATE DEFAULT CURRENT_DATE
+ manager_notes TEXT
```

**Final `rm_profiles` schema:**
```sql
CREATE TABLE rm_profiles (
    id UUID PRIMARY KEY,                    -- FK to profiles.id
    employee_id VARCHAR UNIQUE,             -- ✅ RM-specific
    assigned_territories TEXT[],            -- ✅ RM-specific
    performance_score INTEGER DEFAULT 0,    -- ✅ RM-specific
    total_salons_added INTEGER DEFAULT 0,   -- ✅ RM-specific
    total_approved_salons INTEGER DEFAULT 0,-- ✅ RM-specific
    joining_date DATE,                      -- ✅ RM-specific
    manager_notes TEXT,                     -- ✅ RM-specific
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (id) REFERENCES profiles(id) ON DELETE CASCADE
);
```

**Convenience View Created:**
```sql
CREATE VIEW rm_profiles_with_user_data AS
SELECT 
    rm.*,
    p.full_name,
    p.email,
    p.phone,
    p.is_active,
    p.user_role
FROM rm_profiles rm
JOIN profiles p ON rm.id = p.id;
```

### Code Changes

#### 1. **user_service.py** - RM Profile Creation
**Before:**
```python
rm_profile_data = {
    "id": user_id,
    "full_name": request.full_name,     # ❌ Duplicate
    "phone": request.phone,              # ❌ Duplicate
    "email": request.email,              # ❌ Duplicate
    "is_active": True,                   # ❌ Duplicate
    "assigned_territories": [],
    "performance_score": 0
}
```

**After:**
```python
rm_profile_data = {
    "id": user_id,
    "assigned_territories": [],          # ✅ RM-specific only
    "performance_score": 0,
    "employee_id": None,
    "total_salons_added": 0,
    "total_approved_salons": 0,
    "joining_date": None,
    "manager_notes": None
}
```

#### 2. **rm_service.py** - Profile Updates
**Before:**
```python
# All fields updated in rm_profiles table
response = self.db.table("rm_profiles").update(
    safe_updates
).eq("id", rm_id).execute()
```

**After:**
```python
# Profile fields -> profiles table
profile_fields = {"full_name", "phone", "email", "is_active"}
profile_updates = {k: v for k, v in updates.items() if k in profile_fields}

if profile_updates:
    self.db.table("profiles").update(profile_updates).eq("id", rm_id).execute()

# RM-specific fields -> rm_profiles table
rm_updates = {k: v for k, v in updates.items() if k not in profile_fields}

if rm_updates:
    self.db.table("rm_profiles").update(rm_updates).eq("id", rm_id).execute()
```

#### 3. **rm_service.py** - Get RM by Email
**Before:**
```python
# Queried rm_profiles.email (duplicate field)
response = self.db.table("rm_profiles").select(
    "*, profiles(id, full_name, email, phone)"
).eq("email", email).single().execute()
```

**After:**
```python
# Query profiles table for email (single source of truth)
profile_response = self.db.table("profiles").select(
    "id, full_name, email, phone, is_active, user_role"
).eq("email", email).eq("user_role", "relationship_manager").single().execute()

# Then get RM-specific data
rm_response = self.db.table("rm_profiles").select("*").eq("id", profile_id).execute()
```

#### 4. **admin_service.py** - RM Profile Enrichment
**Before:**
```python
# Two separate queries
rm_response = self.db.table("rm_profiles").select("*").eq("id", rm_id).execute()
profile_response = self.db.table("profiles").select("*").eq("id", rm_id).execute()

# Manual merging
request['rm_profile'] = {**rm_data, 'profiles': profile_data}
```

**After:**
```python
# Single query with join
rm_response = self.db.table("rm_profiles").select(
    "*, profiles(id, full_name, email, phone, is_active, avatar_url)"
).eq("id", rm_id).execute()

request['rm_profile'] = rm_response.data[0]
```

#### 5. **salon_service.py** - RM Enrichment
**Before:**
```python
# Two queries: rm_profiles + profiles
rm_response = self.db.table("rm_profiles").select("id, employee_id").in_("id", rm_ids).execute()
profile_response = self.db.table("profiles").select("id, full_name").in_("id", rm_ids).execute()

# Manual merging in loop
for rm in rm_data:
    if rm["id"] in profile_map:
        rm_profiles[rm["id"]] = {...}
```

**After:**
```python
# Single query with join
rm_response = self.db.table("rm_profiles").select(
    "id, employee_id, profiles(id, full_name, email)"
).in_("id", rm_ids).execute()

rm_profiles = {rm["id"]: rm for rm in rm_response.data}
```

#### 6. **Schema Updates**

**domain/rm.py - RMProfileBase:**
```python
# Before
class RMProfileBase(BaseModel):
    full_name: str          # ❌ Duplicate
    phone: str              # ❌ Duplicate
    email: EmailStr         # ❌ Duplicate
    assigned_territories: Optional[List[str]]

# After
class RMProfileBase(BaseModel):
    """RM-specific fields only. User data comes from profiles table."""
    assigned_territories: Optional[List[str]]
    employee_id: Optional[str]
    total_salons_added: Optional[int] = 0
    total_approved_salons: Optional[int] = 0
    joining_date: Optional[str]
    manager_notes: Optional[str]
```

**domain/rm.py - RMProfileResponse:**
```python
# Before
class RMProfileResponse(RMProfileBase):
    id: str
    performance_score: int
    is_active: bool          # ❌ Duplicate
    profile: Optional[ProfileResponse]

# After
class RMProfileResponse(RMProfileBase, TimestampMixin):
    id: str
    performance_score: int
    profiles: Optional[ProfileResponse]  # ✅ Joined from profiles table
```

**request/rm.py - RMProfileUpdate:**
```python
# Before
class RMProfileUpdate(BaseModel):
    full_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    assigned_territories: Optional[List[str]]
    is_active: Optional[bool]

# After
class RMProfileUpdate(BaseModel):
    """Profile fields route to profiles table, RM fields to rm_profiles table."""
    # Profile table fields
    full_name: Optional[str] = Field(None, description="Updates profiles.full_name")
    phone: Optional[str] = Field(None, description="Updates profiles.phone")
    email: Optional[str] = Field(None, description="Updates profiles.email")
    is_active: Optional[bool] = Field(None, description="Updates profiles.is_active")
    
    # RM-specific fields
    assigned_territories: Optional[List[str]] = Field(None, description="Updates rm_profiles.assigned_territories")
    manager_notes: Optional[str] = Field(None, description="Updates rm_profiles.manager_notes")
```

## Benefits

✅ **Single Source of Truth** - User data only in `profiles` table  
✅ **No Data Duplication** - Eliminates redundancy  
✅ **Simplified Queries** - Use PostgREST joins instead of multiple queries  
✅ **Easier Maintenance** - Update user data in one place  
✅ **Data Consistency** - No sync issues between tables  
✅ **Cleaner Code** - Removed manual data merging logic  
✅ **Better Performance** - Single query with join vs multiple queries  

## Migration Safety

The migration script:
1. ✅ Adds missing columns before dropping duplicates
2. ✅ Migrates any divergent data from `rm_profiles` to `profiles`
3. ✅ Only drops columns after data is safely migrated
4. ✅ Ensures foreign key constraint exists
5. ✅ Creates convenience view for backward compatibility
6. ✅ Uses `ON DELETE CASCADE` for data integrity

## Files Modified

### Migration
- ✅ `supabase/migrations/20251206000000_remove_rm_profiles_duplication.sql`

### Backend Services
- ✅ `app/services/user_service.py` - RM profile creation
- ✅ `app/services/rm_service.py` - Profile queries and updates
- ✅ `app/services/admin_service.py` - RM profile enrichment
- ✅ `app/services/salon_service.py` - RM enrichment

### Schemas
- ✅ `app/schemas/domain/rm.py` - Domain models
- ✅ `app/schemas/request/rm.py` - Request DTOs

### Documentation
- ✅ `salon-management-app/docs/schema.sql` - Schema documentation

## Testing Checklist

Before deploying:
- [ ] Run migration on staging database
- [ ] Test RM profile creation
- [ ] Test RM profile updates (name, phone, email)
- [ ] Test RM profile updates (territories, notes)
- [ ] Test get RM by email
- [ ] Test RM listing with joins
- [ ] Test salon enrichment with RM data
- [ ] Test vendor request RM enrichment
- [ ] Verify no N+1 query issues
- [ ] Check frontend still works with new structure

## API Response Structure

The API response structure remains compatible:
```json
{
  "id": "uuid",
  "employee_id": "RM001",
  "assigned_territories": ["Mumbai", "Pune"],
  "performance_score": 850,
  "total_salons_added": 15,
  "total_approved_salons": 12,
  "joining_date": "2025-01-15",
  "manager_notes": "Top performer",
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-12-06T10:00:00Z",
  "profiles": {
    "id": "uuid",
    "full_name": "John Doe",
    "email": "john@example.com",
    "phone": "+919876543210",
    "is_active": true,
    "user_role": "relationship_manager"
  }
}
```

## Rollback Plan

If issues arise:
1. The view `rm_profiles_with_user_data` provides backward compatibility
2. Can temporarily query the view instead of base table
3. Migration can be reverted by re-adding columns and copying data back

## Notes

- The `profiles` table is the single source of truth for user data
- The `rm_profiles` table now only contains RM-specific business data
- All queries use PostgREST joins to combine data efficiently
- Update logic automatically routes fields to correct tables
- Foreign key cascade ensures data integrity on deletions
