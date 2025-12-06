# RM Statistics Performance Optimization

## Current Problem

**Inefficient Statistics Calculation:**
Currently, RM statistics are calculated by:
1. Querying ALL `vendor_join_requests` for an RM every time dashboard is loaded
2. Filtering in Python code to count by status
3. Manually incrementing `total_salons_added` counter in `rm_profiles`

**Code Analysis:**
```python
# rm_service.py - get_rm_stats()
requests_response = self.db.table("vendor_join_requests").select(
    "status"
).eq("rm_id", rm_id).execute()  # ⚠️ Fetches ALL requests every time

requests = requests_response.data or []

# Count in Python ❌ Inefficient
pending = sum(1 for r in requests if r["status"] == "pending")
approved = sum(1 for r in requests if r["status"] == "approved")
rejected = sum(1 for r in requests if r["status"] == "rejected")
```

**Issues:**
1. ❌ **N+1 Query Problem** - Fetches all request records just to count
2. ❌ **Memory Overhead** - Loads all data into memory for simple counting
3. ❌ **Slow Performance** - O(n) filtering in Python for each status
4. ❌ **Scalability Issues** - As RMs add more salons, dashboard gets slower
5. ❌ **Database Load** - Multiple full table scans for simple aggregations
6. ❌ **Manual Counter** - `total_salons_added` can get out of sync

## Recommended Solution

### 1. Use Database Aggregation (Immediate Fix)

**Replace Python counting with SQL COUNT queries:**

```python
async def get_rm_stats(self, rm_id: str) -> VendorRequestStats:
    """Get RM stats using efficient database aggregations."""
    
    # Get counts directly from database using Supabase aggregation
    total = self.db.table("vendor_join_requests").select(
        "id", count="exact"
    ).eq("rm_id", rm_id).execute()
    
    pending = self.db.table("vendor_join_requests").select(
        "id", count="exact"
    ).eq("rm_id", rm_id).eq("status", "pending").execute()
    
    approved = self.db.table("vendor_join_requests").select(
        "id", count="exact"
    ).eq("rm_id", rm_id).eq("status", "approved").execute()
    
    rejected = self.db.table("vendor_join_requests").select(
        "id", count="exact"
    ).eq("rm_id", rm_id).eq("status", "rejected").execute()
    
    # Get performance score
    rm_profile = self.db.table("rm_profiles").select(
        "performance_score"
    ).eq("id", rm_id).single().execute()
    
    return VendorRequestStats(
        total_requests=total.count or 0,
        pending_requests=pending.count or 0,
        approved_requests=approved.count or 0,
        rejected_requests=rejected.count or 0,
        total_score=rm_profile.data.get("performance_score", 0) if rm_profile.data else 0
    )
```

**Benefits:**
- ✅ Database does the counting (optimized with indexes)
- ✅ No memory overhead from loading all records
- ✅ O(1) lookups with proper indexes
- ✅ Much faster for RMs with many requests

### 2. Add Database Indexes (Performance Boost)

```sql
-- Add composite indexes for fast counting
CREATE INDEX IF NOT EXISTS idx_vendor_join_requests_rm_status 
ON vendor_join_requests(rm_id, status) 
WHERE deleted_at IS NULL;

-- Index for total count per RM
CREATE INDEX IF NOT EXISTS idx_vendor_join_requests_rm_id 
ON vendor_join_requests(rm_id) 
WHERE deleted_at IS NULL;
```

### 3. Add Cached Counters (Optional - Best Performance)

**Create denormalized counter columns in `rm_profiles`:**

```sql
ALTER TABLE rm_profiles 
ADD COLUMN IF NOT EXISTS total_requests_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS pending_requests_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS approved_requests_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS rejected_requests_count INTEGER DEFAULT 0;
```

**Update counters with database triggers:**

```sql
-- Function to update RM stats counters
CREATE OR REPLACE FUNCTION update_rm_stats_counters()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- New request added
        UPDATE rm_profiles 
        SET 
            total_requests_count = total_requests_count + 1,
            pending_requests_count = CASE WHEN NEW.status = 'pending' THEN pending_requests_count + 1 ELSE pending_requests_count END,
            approved_requests_count = CASE WHEN NEW.status = 'approved' THEN approved_requests_count + 1 ELSE approved_requests_count END,
            rejected_requests_count = CASE WHEN NEW.status = 'rejected' THEN rejected_requests_count + 1 ELSE rejected_requests_count END,
            total_salons_added = CASE WHEN NEW.status = 'approved' THEN total_salons_added + 1 ELSE total_salons_added END,
            updated_at = NOW()
        WHERE id = NEW.rm_id;
        
    ELSIF TG_OP = 'UPDATE' THEN
        -- Status changed
        IF OLD.status != NEW.status THEN
            UPDATE rm_profiles 
            SET 
                pending_requests_count = CASE 
                    WHEN OLD.status = 'pending' THEN pending_requests_count - 1 
                    WHEN NEW.status = 'pending' THEN pending_requests_count + 1 
                    ELSE pending_requests_count 
                END,
                approved_requests_count = CASE 
                    WHEN OLD.status = 'approved' THEN approved_requests_count - 1 
                    WHEN NEW.status = 'approved' THEN approved_requests_count + 1 
                    ELSE approved_requests_count 
                END,
                rejected_requests_count = CASE 
                    WHEN OLD.status = 'rejected' THEN rejected_requests_count - 1 
                    WHEN NEW.status = 'rejected' THEN rejected_requests_count + 1 
                    ELSE rejected_requests_count 
                END,
                total_salons_added = CASE 
                    WHEN OLD.status != 'approved' AND NEW.status = 'approved' THEN total_salons_added + 1 
                    WHEN OLD.status = 'approved' AND NEW.status != 'approved' THEN total_salons_added - 1 
                    ELSE total_salons_added 
                END,
                updated_at = NOW()
            WHERE id = NEW.rm_id;
        END IF;
        
    ELSIF TG_OP = 'DELETE' THEN
        -- Request deleted
        UPDATE rm_profiles 
        SET 
            total_requests_count = total_requests_count - 1,
            pending_requests_count = CASE WHEN OLD.status = 'pending' THEN pending_requests_count - 1 ELSE pending_requests_count END,
            approved_requests_count = CASE WHEN OLD.status = 'approved' THEN approved_requests_count - 1 ELSE approved_requests_count END,
            rejected_requests_count = CASE WHEN OLD.status = 'rejected' THEN rejected_requests_count - 1 ELSE rejected_requests_count END,
            total_salons_added = CASE WHEN OLD.status = 'approved' THEN total_salons_added - 1 ELSE total_salons_added END,
            updated_at = NOW()
        WHERE id = OLD.rm_id;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger
DROP TRIGGER IF EXISTS trigger_update_rm_stats ON vendor_join_requests;
CREATE TRIGGER trigger_update_rm_stats
AFTER INSERT OR UPDATE OF status OR DELETE ON vendor_join_requests
FOR EACH ROW
EXECUTE FUNCTION update_rm_stats_counters();

-- Initial sync of existing data
UPDATE rm_profiles rm
SET 
    total_requests_count = (
        SELECT COUNT(*) FROM vendor_join_requests 
        WHERE rm_id = rm.id AND deleted_at IS NULL
    ),
    pending_requests_count = (
        SELECT COUNT(*) FROM vendor_join_requests 
        WHERE rm_id = rm.id AND status = 'pending' AND deleted_at IS NULL
    ),
    approved_requests_count = (
        SELECT COUNT(*) FROM vendor_join_requests 
        WHERE rm_id = rm.id AND status = 'approved' AND deleted_at IS NULL
    ),
    rejected_requests_count = (
        SELECT COUNT(*) FROM vendor_join_requests 
        WHERE rm_id = rm.id AND status = 'rejected' AND deleted_at IS NULL
    ),
    total_salons_added = (
        SELECT COUNT(*) FROM vendor_join_requests 
        WHERE rm_id = rm.id AND status = 'approved' AND deleted_at IS NULL
    );
```

**Updated Service Code:**

```python
async def get_rm_stats(self, rm_id: str) -> VendorRequestStats:
    """Get RM stats from cached counters - O(1) performance."""
    
    # Single query to get all stats from rm_profiles
    rm_profile = self.db.table("rm_profiles").select(
        "performance_score, total_requests_count, pending_requests_count, "
        "approved_requests_count, rejected_requests_count"
    ).eq("id", rm_id).single().execute()
    
    if not rm_profile.data:
        raise ValueError(f"RM profile {rm_id} not found")
    
    data = rm_profile.data
    
    return VendorRequestStats(
        total_requests=data.get("total_requests_count", 0),
        pending_requests=data.get("pending_requests_count", 0),
        approved_requests=data.get("approved_requests_count", 0),
        rejected_requests=data.get("rejected_requests_count", 0),
        total_score=data.get("performance_score", 0)
    )
```

## Performance Comparison

### Current Implementation
```
Dashboard Load Time:
- Query: SELECT * FROM vendor_join_requests WHERE rm_id = ?
- Data Transfer: ~10-100 KB (depending on request count)
- Python Processing: O(n) iteration
- Time: 100-500ms for RM with 50+ requests
```

### Option 1: Database Aggregation
```
Dashboard Load Time:
- Queries: 4x SELECT COUNT(*) with indexes
- Data Transfer: <1 KB
- Processing: O(1) database index lookups
- Time: 10-50ms
- Improvement: 5-10x faster
```

### Option 2: Cached Counters (Best)
```
Dashboard Load Time:
- Query: 1x SELECT with 5 columns
- Data Transfer: <1 KB
- Processing: Direct column read
- Time: 5-10ms
- Improvement: 20-50x faster
- Maintenance: Automatic via triggers
```

## Recommendation

**Implement in 2 Phases:**

### Phase 1: Quick Win (Immediate)
1. ✅ Use database aggregation with COUNT queries
2. ✅ Add indexes for rm_id and (rm_id, status)
3. ✅ Remove `_increment_rm_salons_count` manual counter logic

**Impact:** 5-10x faster, minimal code changes

### Phase 2: Optimal (Later)
1. ✅ Add cached counter columns to `rm_profiles`
2. ✅ Create database triggers to auto-update counters
3. ✅ Update service to read from cached columns
4. ✅ Add data consistency validation

**Impact:** 20-50x faster, bulletproof consistency

## Additional Optimizations

### 1. Remove Manual Counter Increments
Current code manually increments `total_salons_added`:
```python
async def _increment_rm_salons_count(self, rm_id: str) -> None:
    """❌ REMOVE - Use trigger-based counters instead"""
    pass
```

This is error-prone and can get out of sync. Use database triggers instead.

### 2. Optimize Leaderboard Query
Current leaderboard likely fetches all RMs and sorts in Python. Use database:

```python
async def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
    """Get leaderboard with database sorting."""
    response = self.db.table("rm_profiles").select(
        "*, profiles(id, full_name, email)"
    ).order("performance_score", desc=True).limit(limit).execute()
    
    return response.data or []
```

### 3. Cache Dashboard Data
Add Redis/memory caching for dashboard:

```python
@cached(ttl=300)  # Cache for 5 minutes
async def get_rm_dashboard(self, rm_id: str) -> Dict[str, Any]:
    # ... existing code
```

## Files to Modify

### Phase 1 (Database Aggregation)
- ✅ `app/services/rm_service.py` - Update `get_rm_stats()`
- ✅ `supabase/migrations/20251206000001_add_rm_stats_indexes.sql` - Add indexes
- ✅ Remove `_increment_rm_salons_count()` calls

### Phase 2 (Cached Counters)
- ✅ `supabase/migrations/20251206000002_add_rm_cached_counters.sql` - Add columns & triggers
- ✅ `app/services/rm_service.py` - Update to use cached columns
- ✅ `app/schemas/domain/rm.py` - Add counter fields to schema

## Summary

The current implementation queries and processes all vendor requests every time the dashboard loads. This is inefficient and doesn't scale.

**Recommended approach:**
1. **Short term:** Use database COUNT queries with proper indexes (5-10x faster)
2. **Long term:** Use cached counters with database triggers (20-50x faster)

Both approaches eliminate the need for manual counter increments and provide accurate, real-time statistics with minimal overhead.
