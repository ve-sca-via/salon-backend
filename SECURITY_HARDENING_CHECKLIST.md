# Security & Production Hardening Checklist

## Critical Issues to Fix Before Production

This document outlines the security vulnerabilities and production issues that must be addressed before deploying to production with real customers and real money.

---

## 🔴 CRITICAL - Fix Before Production

### 1. Encrypt Sensitive Values in Database (Razorpay Keys)

**Current State:**
```sql
razorpay_key_secret: "rzp_test_1234567890" -- STORED AS PLAIN TEXT ❌
```

**The Problem:**
- Database breach = instant access to payment gateway credentials
- Attackers can process refunds, steal money, access customer payment data
- **PCI DSS compliance violation** - payment credentials MUST be encrypted
- Unencrypted database backups contain API keys
- One SQL injection = game over

**Implementation:**
```python
from cryptography.fernet import Fernet
import os

# Use environment variable for encryption key (NOT in DB!)
ENCRYPTION_KEY = os.getenv("DB_ENCRYPTION_KEY")
cipher = Fernet(ENCRYPTION_KEY)

# Before saving to DB
def encrypt_value(plain_text: str) -> str:
    return cipher.encrypt(plain_text.encode()).decode()

# When reading from DB
def decrypt_value(encrypted_text: str) -> str:
    return cipher.decrypt(encrypted_text.encode()).decode()

# In config_service.py
async def get_config(self, config_key: str):
    config = await self.db.table("system_config").select("*").eq("config_key", config_key).single().execute()
    
    # Auto-decrypt sensitive values
    if config_key in ['razorpay_key_secret', 'razorpay_key_id']:
        config.config_value = decrypt_value(config.config_value)
    
    return config
```

**Files to Modify:**
- `app/core/encryption.py` (new file)
- `app/services/config_service.py`
- Add `DB_ENCRYPTION_KEY` to environment variables

**Severity:** 🔴 **CRITICAL**
**Impact:** Legal liability, compliance violation, financial fraud risk
**Timeline:** Fix before storing any real payment credentials

---

### 2. Config Validation (Prevent Invalid Values)

**Current State:**
Admin can set ANY value - including negative fees, zero limits, impossible dates.

**Real Scenarios That Will Break Your App:**
```javascript
// Admin typos/mistakes:
convenience_fee_percentage: -10      // ❌ Negative fees = you PAY customers
convenience_fee_percentage: 150      // ❌ 150% fee = nobody will book
max_booking_advance_days: 0          // ❌ Nobody can book anything
max_booking_advance_days: 99999      // ❌ Book appointments in year 2299?
cancellation_window_hours: -5        // ❌ Time travel cancellations
rm_score_per_approval: 999999        // ❌ RM gaming the system
registration_fee_amount: -5000       // ❌ You pay vendors to join
```

**Implementation:**

**Option 1: Backend Validation (Recommended)**
```python
# app/schemas/__init__.py
class SystemConfigUpdate(BaseModel):
    config_value: Optional[Any] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    
    @validator('config_value')
    def validate_config_value(cls, v, values):
        # This runs BEFORE saving to DB
        return v

# app/services/config_service.py
async def update_config(self, config_key: str, updates: Dict[str, Any]):
    # Validate based on config type
    new_value = updates.get('config_value')
    
    if new_value is not None:
        # Percentage validations
        if 'percentage' in config_key or 'commission' in config_key:
            if not (0 <= float(new_value) <= 100):
                raise ValueError(f"{config_key} must be between 0 and 100")
        
        # Amount validations
        if 'fee_amount' in config_key or 'amount' in config_key:
            if float(new_value) < 0:
                raise ValueError(f"{config_key} cannot be negative")
        
        # Day/hour validations
        if 'days' in config_key or 'hours' in config_key:
            val = int(new_value)
            if val < 0:
                raise ValueError(f"{config_key} cannot be negative")
            if 'advance_days' in config_key and val > 365:
                raise ValueError("Booking advance days cannot exceed 365")
        
        # Score validations
        if 'score' in config_key:
            val = int(new_value)
            if val < 0:
                raise ValueError(f"{config_key} cannot be negative")
            if val > 1000:
                raise ValueError("Score cannot exceed 1000 points")
    
    # Proceed with update if validation passes
    response = self.db.table("system_config").update(updates).eq("config_key", config_key).execute()
    return response.data[0]
```

**Option 2: Database Constraints**
```sql
-- Add CHECK constraints to system_config table
ALTER TABLE system_config 
ADD CONSTRAINT check_percentage_range 
CHECK (
  (config_key NOT LIKE '%percentage%' AND config_key NOT LIKE '%commission%') 
  OR 
  (config_value::numeric >= 0 AND config_value::numeric <= 100)
);

ALTER TABLE system_config 
ADD CONSTRAINT check_amount_positive 
CHECK (
  (config_type != 'number' OR config_key NOT LIKE '%amount%' OR config_key NOT LIKE '%fee%') 
  OR 
  config_value::numeric >= 0
);
```

**Files to Modify:**
- `app/services/config_service.py`
- `app/schemas/__init__.py`
- `supabase/migrations/` (new migration file)

**Severity:** 🔴 **HIGH**
**Impact:** Broken payment flow, customer complaints, revenue loss
**Timeline:** Fix before allowing admin config changes

---

### 3. Rate Limiting & Caching on Public Endpoint

**Current State:**
```python
@router.get("/salons/config/public")
async def get_public_configs():
    # NO RATE LIMIT ❌
    # NO CACHING ❌
    # Hits DB on EVERY request
```

**The Attack:**
```python
# Script kiddie DDoS
import requests
while True:
    requests.get("https://yourapp.com/salons/config/public")
# Result: 10,000 requests/sec = site down
```

**Real Numbers:**
- 1,000 users load homepage = 1,000 config DB queries
- With caching: 1,000 users = 1 DB query per 5 minutes
- **Savings: 99.9% reduction in DB load + cost**

**Implementation:**

**Option 1: FastAPI Cache (Recommended)**
```python
# app/core/cache.py
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache

# In main.py startup
@app.on_event("startup")
async def startup():
    FastAPICache.init(InMemoryBackend())

# In salons.py
from fastapi_cache.decorator import cache

@router.get("/config/public")
@cache(expire=300)  # Cache for 5 minutes
async def get_public_configs():
    # Only hits DB once per 5 minutes
    # All other requests served from in-memory cache
    ...
```

**Option 2: Rate Limiting**
```python
# requirements.txt
slowapi==0.1.9

# app/core/rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# In salons.py
@router.get("/config/public")
@limiter.limit("30/minute")  # 30 requests per minute per IP
async def get_public_configs(request: Request):
    ...
```

**Option 3: Both (Best)**
```python
@router.get("/config/public")
@cache(expire=300)
@limiter.limit("30/minute")
async def get_public_configs(request: Request):
    # Cached + rate limited = maximum protection
    ...
```

**Files to Modify:**
- `app/api/salons.py`
- `app/core/cache.py` (new file)
- `app/core/rate_limit.py` (new file)
- `requirements.txt`
- `main.py`

**Severity:** 🔴 **HIGH**
**Impact:** Site downtime, DDoS vulnerability, excessive DB costs
**Timeline:** Fix before public launch

---

## 🟡 IMPORTANT - Fix Within First Month

### 4. Config Change History / Audit Log

**Current State:**
```
Admin changes convenience_fee from 10% to 25%
Customer: "Why was I charged 25%?"
You: "Uh... I don't know who changed it or when" 🤷
```

**The Problem:**
- **Zero accountability** - no record of who changed what
- **No rollback capability** - can't undo bad changes
- **Compliance nightmare** - SOC 2/ISO 27001 require audit trails
- **Debugging hell** - revenue dropped 20%, which config changed?

**Real-World Scenario:**
```
3 AM: Revenue down 50%
Check audit log: "Admin_ID_123 changed platform_commission from 10% to 5% at 2:47 PM"
Contact admin: "Oh crap, meant to change staging, not production!"
Rollback in 30 seconds via audit log instead of 3 hours of panic
```

**Implementation:**

**Migration:**
```sql
-- supabase/migrations/YYYYMMDDHHMMSS_add_config_audit_log.sql
CREATE TABLE config_change_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  config_id uuid REFERENCES system_config(id) ON DELETE SET NULL,
  config_key text NOT NULL,
  old_value text,
  new_value text NOT NULL,
  old_description text,
  new_description text,
  changed_by uuid REFERENCES profiles(id),
  changed_by_email text,
  changed_at timestamp with time zone DEFAULT now(),
  change_reason text,
  ip_address text,
  user_agent text
);

CREATE INDEX idx_config_audit_key ON config_change_history(config_key);
CREATE INDEX idx_config_audit_time ON config_change_history(changed_at DESC);
CREATE INDEX idx_config_audit_user ON config_change_history(changed_by);
```

**Service Layer:**
```python
# app/services/config_service.py
async def update_config(self, config_key: str, updates: Dict[str, Any], changed_by: str, ip_address: str = None):
    # Get old value first
    old_config = await self.get_config(config_key)
    
    # Perform update
    response = self.db.table("system_config").update(updates).eq("config_key", config_key).execute()
    updated_config = response.data[0]
    
    # Log the change
    await self._log_config_change(
        config_id=updated_config['id'],
        config_key=config_key,
        old_value=old_config.get('config_value'),
        new_value=updated_config['config_value'],
        old_description=old_config.get('description'),
        new_description=updated_config.get('description'),
        changed_by=changed_by,
        ip_address=ip_address
    )
    
    return updated_config

async def _log_config_change(self, **kwargs):
    self.db.table("config_change_history").insert(kwargs).execute()
    logger.info(f"Config change logged: {kwargs['config_key']} by {kwargs['changed_by']}")
```

**API Endpoint:**
```python
# app/api/admin.py
@router.get("/config/{config_key}/history")
async def get_config_history(
    config_key: str,
    limit: int = 50,
    current_user: TokenData = Depends(require_admin)
):
    """Get change history for a specific config"""
    history = db.table("config_change_history")\
        .select("*")\
        .eq("config_key", config_key)\
        .order("changed_at", desc=True)\
        .limit(limit)\
        .execute()
    
    return history.data

@router.post("/config/{config_key}/rollback/{history_id}")
async def rollback_config(
    config_key: str,
    history_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Rollback config to a previous value"""
    # Get historical record
    history = db.table("config_change_history").select("*").eq("id", history_id).single().execute()
    
    # Update config to old value
    config_service = ConfigService()
    await config_service.update_config(
        config_key=config_key,
        updates={"config_value": history.data['old_value']},
        changed_by=current_user.user_id,
        ip_address="rollback"
    )
    
    return {"message": f"Rolled back {config_key} to previous value"}
```

**Files to Create/Modify:**
- `supabase/migrations/` (new migration)
- `app/services/config_service.py`
- `app/api/admin.py`

**Severity:** 🟡 **IMPORTANT**
**Impact:** Difficult debugging, no accountability, compliance issues
**Timeline:** Before handling real revenue

---

## Summary

| Issue | Severity | Fix Before | Impact if Ignored |
|-------|----------|------------|-------------------|
| Encrypt Razorpay Keys | 🔴 Critical | Production | Legal liability, fraud risk |
| Config Validation | 🔴 High | Admin access | Broken payments, lost revenue |
| Rate Limiting/Cache | 🔴 High | Public launch | DDoS, site downtime, high costs |
| Audit Logging | 🟡 Important | Month 1 | Hard debugging, no compliance |

---

## Installation Commands

```bash
# For encryption
pip install cryptography

# For caching
pip install fastapi-cache2

# For rate limiting
pip install slowapi

# Update requirements.txt
pip freeze > requirements.txt
```

---

## Test Checklist

- [ ] Try setting `convenience_fee_percentage = -10` (should fail)
- [ ] Try setting `convenience_fee_percentage = 150` (should fail)
- [ ] Try setting `max_booking_advance_days = -5` (should fail)
- [ ] Hit `/salons/config/public` 100 times in 10 seconds (should be rate limited)
- [ ] Change a config and verify audit log entry created
- [ ] Decrypt Razorpay key from DB and verify it works
- [ ] Test rollback functionality

---

**Remember:** The difference between a "learning project" and "production software" is handling edge cases, security, and scale. These aren't optional - they're the bare minimum for handling real money.
