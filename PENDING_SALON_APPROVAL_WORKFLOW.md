# Pending Salon Approval Workflow - Implementation Plan

## 📋 Current State Analysis

### ✅ What's Already Implemented

#### 1. **Backend APIs** (COMPLETE)
- ✅ `POST /api/admin/vendor-requests/{id}/approve` - Approve salon
- ✅ `POST /api/admin/vendor-requests/{id}/reject` - Reject salon  
- ✅ `GET /api/admin/vendor-requests` - Get pending requests
- ✅ `POST /api/vendors/complete-registration` - Vendor completes registration
- ✅ `POST /api/payments/registration/create-order` - Create payment order
- ✅ `POST /api/payments/registration/verify` - Verify payment and activate

#### 2. **Email Templates** (COMPLETE)
Located: `backend/app/templates/email/`
- ✅ `vendor_approval.html` - Approval email with registration link
- ✅ `vendor_rejection.html` - Rejection notification to RM
- ✅ `payment_receipt.html` - Payment confirmation
- ✅ `welcome_vendor.html` - Welcome after activation
- ✅ `booking_confirmation.html` - Booking confirmations
- ✅ `booking_cancellation.html` - Cancellation notifications

#### 3. **Email Service Integration** (COMPLETE)
File: `backend/app/services/email.py`

**Methods:**
- ✅ `send_vendor_approval_email()` - Sends approval with magic link
- ✅ `send_vendor_rejection_email()` - Sends rejection to RM
- ✅ `send_payment_receipt_email()` - Payment receipt
- ✅ `send_welcome_vendor_email()` - Welcome message
- ✅ `send_booking_confirmation_email()` - Booking confirmations
- ✅ `send_booking_cancellation_email()` - Cancellation emails

**Integration Points:**
- ✅ Admin approval endpoint sends email to vendor owner
- ✅ Admin rejection endpoint sends email to RM
- ✅ Payment verification sends receipt + welcome emails

#### 4. **Database Tables** (COMPLETE)
- ✅ `vendor_join_requests` - Stores RM-submitted salon requests
- ✅ `salons` - Salon records (created after approval)
- ✅ `profiles` - User profiles (vendor, RM, customer, admin)
- ✅ `rm_score_history` - RM points tracking
- ✅ `system_config` - System settings (registration fee, RM scores)
- ✅ `registration_payments` - Payment tracking

#### 5. **Frontend - Admin Panel** (COMPLETE)
File: `salon-admin-panel/src/pages/PendingSalons.jsx`
- ✅ Lists pending salon submissions
- ✅ Shows salon details in modal
- ✅ Approve/Reject functionality
- ✅ Real-time Supabase subscription for new submissions
- ✅ Toast notifications with salon name
- ✅ Uses JWT auth with backend

#### 6. **Frontend - Vendor Registration** (COMPLETE)
File: `salon-management-app/src/pages/vendor/CompleteRegistration.jsx`
- ✅ 4-step registration wizard
- ✅ Token validation
- ✅ Password setup
- ✅ Personal info collection
- ✅ Payment integration (Razorpay)
- ✅ Account activation

#### 7. **Real-time Notifications - Admin** (COMPLETE)
Files: `salon-admin-panel/src/components/layout/Header.jsx`, `Sidebar.jsx`
- ✅ Bell icon with bounce animation
- ✅ Red badge counter on header
- ✅ Yellow badge on sidebar "Pending Salons" item
- ✅ Supabase real-time subscription
- ✅ Toast notifications with clickable links

---

## ❌ What's Missing - RM Agent Notifications

### Current Gap:
**When admin approves/rejects a salon, the RM agent who submitted it does NOT receive:**
1. ❌ Real-time notification in their dashboard
2. ❌ In-app notification badge
3. ❌ Visual feedback about their submission status

**What RM Currently Gets:**
- ✅ Email notification (rejection only - sent to RM)
- ❌ NO email on approval (only vendor gets email)
- ❌ NO in-app notifications
- ❌ NO dashboard alerts

---

## 🎯 Implementation Requirements

### 1. **Database Schema - Notifications Table** ⚠️ MISSING

**Create new table: `notifications`**

```sql
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    type TEXT NOT NULL, -- 'salon_approved', 'salon_rejected', 'booking_confirmed', etc.
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    data JSONB, -- Additional data (salon_id, request_id, etc.)
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_read ON notifications(read);
CREATE INDEX idx_notifications_created_at ON notifications(created_at DESC);
CREATE INDEX idx_notifications_user_read ON notifications(user_id, read);

-- Enable RLS (Row Level Security)
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Users can only see their own notifications
CREATE POLICY "Users can view own notifications"
ON notifications FOR SELECT
USING (auth.uid() = user_id);

-- RLS Policy: Users can update their own notifications (mark as read)
CREATE POLICY "Users can update own notifications"
ON notifications FOR UPDATE
USING (auth.uid() = user_id);

-- RLS Policy: Service role can insert notifications (for system)
CREATE POLICY "Service role can insert notifications"
ON notifications FOR INSERT
WITH CHECK (true);
```

---

### 2. **Backend API Endpoints** ⚠️ PARTIALLY MISSING

#### Existing (Modify):
**File:** `backend/app/api/admin.py`

**`POST /api/admin/vendor-requests/{id}/approve`** - ✅ EXISTS, ❌ NEEDS UPDATE
```python
# CURRENT: Only sends email to vendor
# NEEDED: Also create notification for RM

# ADD THIS after email is sent:
notification_data = {
    "user_id": request_data["rm_id"],  # RM's user ID
    "type": "salon_approved",
    "title": "Salon Approved! 🎉",
    "message": f"{request_data['business_name']} has been approved by admin.",
    "data": {
        "salon_id": salon_id,
        "request_id": request_id,
        "salon_name": request_data["business_name"],
        "points_awarded": rm_score
    },
    "read": False
}

supabase.table("notifications").insert(notification_data).execute()
```

**`POST /api/admin/vendor-requests/{id}/reject`** - ✅ EXISTS, ❌ NEEDS UPDATE
```python
# CURRENT: Only sends email to RM
# NEEDED: Also create notification for RM

# ADD THIS after email is sent:
notification_data = {
    "user_id": request_data["rm_id"],
    "type": "salon_rejected",
    "title": "Salon Needs Revision 📝",
    "message": f"{request_data['business_name']} requires changes. Check your email for details.",
    "data": {
        "request_id": request_id,
        "salon_name": request_data["business_name"],
        "rejection_reason": rejection_reason
    },
    "read": False
}

supabase.table("notifications").insert(notification_data).execute()
```

#### New Endpoints Needed:
**File:** `backend/app/api/notifications.py` (CREATE NEW FILE)

```python
"""
Notification API Endpoints
Handles user notifications (in-app)
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List
from app.core.auth import get_current_user_id
from app.schemas import NotificationResponse
from supabase import create_client
from app.core.config import settings

router = APIRouter(prefix="/notifications", tags=["Notifications"])
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

@router.get("/", response_model=List[NotificationResponse])
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    user_id: str = Depends(get_current_user_id)
):
    """Get user's notifications"""
    query = supabase.table("notifications").select("*").eq("user_id", user_id)
    
    if unread_only:
        query = query.eq("read", False)
    
    response = query.order("created_at", desc=True).limit(limit).execute()
    return response.data

@router.get("/unread-count")
async def get_unread_count(user_id: str = Depends(get_current_user_id)):
    """Get count of unread notifications"""
    response = supabase.table("notifications")\
        .select("id", count="exact")\
        .eq("user_id", user_id)\
        .eq("read", False)\
        .execute()
    
    return {"unread_count": response.count}

@router.post("/{notification_id}/mark-read")
async def mark_notification_read(
    notification_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Mark notification as read"""
    supabase.table("notifications")\
        .update({"read": True})\
        .eq("id", notification_id)\
        .eq("user_id", user_id)\
        .execute()
    
    return {"success": True}

@router.post("/mark-all-read")
async def mark_all_read(user_id: str = Depends(get_current_user_id)):
    """Mark all notifications as read"""
    supabase.table("notifications")\
        .update({"read": True})\
        .eq("user_id", user_id)\
        .eq("read", False)\
        .execute()
    
    return {"success": True}
```

**Register in main.py:**
```python
from app.api import notifications
app.include_router(notifications.router, prefix="/api")
```

---

### 3. **Backend Schemas** ⚠️ MISSING

**File:** `backend/app/schemas/__init__.py`

```python
# Add to existing schemas:

class NotificationResponse(BaseModel):
    id: str
    user_id: str
    type: str
    title: str
    message: str
    data: Optional[dict] = None
    read: bool
    created_at: str
    updated_at: str
```

---

### 4. **Frontend - RM Dashboard** ⚠️ MISSING

#### Create Notification System Components

**File:** `salon-management-app/src/components/notifications/NotificationBell.jsx` (NEW)

```jsx
import { useState, useEffect } from 'react';
import { supabase } from '../../config/supabase';
import { backendApi } from '../../services/backendApi';
import { FiBell } from 'react-icons/fi';
import { toast } from 'react-toastify';

export const NotificationBell = ({ userId }) => {
  const [unreadCount, setUnreadCount] = useState(0);
  const [hasNew, setHasNew] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);

  useEffect(() => {
    fetchUnreadCount();
    fetchNotifications();
    subscribeToNotifications();
  }, [userId]);

  const fetchUnreadCount = async () => {
    try {
      const { data } = await backendApi.get('/notifications/unread-count');
      setUnreadCount(data.unread_count);
    } catch (error) {
      console.error('Failed to fetch unread count:', error);
    }
  };

  const fetchNotifications = async () => {
    try {
      const { data } = await backendApi.get('/notifications?limit=10');
      setNotifications(data);
    } catch (error) {
      console.error('Failed to fetch notifications:', error);
    }
  };

  const subscribeToNotifications = () => {
    const channel = supabase
      .channel('rm-notifications')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'notifications',
          filter: `user_id=eq.${userId}`
        },
        (payload) => {
          setUnreadCount(prev => prev + 1);
          setHasNew(true);
          
          // Show toast
          const notification = payload.new;
          toast.success(
            <div onClick={() => handleNotificationClick(notification)}>
              <strong>{notification.title}</strong>
              <p>{notification.message}</p>
            </div>,
            { autoClose: 5000 }
          );

          // Bounce animation
          setTimeout(() => setHasNew(false), 3000);

          // Refresh list
          fetchNotifications();
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  };

  const handleNotificationClick = async (notification) => {
    // Mark as read
    if (!notification.read) {
      await backendApi.post(`/notifications/${notification.id}/mark-read`);
      fetchUnreadCount();
      fetchNotifications();
    }

    // Navigate based on type
    if (notification.type === 'salon_approved') {
      window.location.href = '/rm/salons';
    } else if (notification.type === 'salon_rejected') {
      window.location.href = '/rm/submissions';
    }
  };

  const markAllRead = async () => {
    try {
      await backendApi.post('/notifications/mark-all-read');
      fetchUnreadCount();
      fetchNotifications();
    } catch (error) {
      console.error('Failed to mark all read:', error);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={() => setShowDropdown(!showDropdown)}
        className={`relative p-2 rounded-lg hover:bg-gray-100 transition-all ${
          hasNew ? 'animate-bounce' : ''
        }`}
      >
        <FiBell className="w-6 h-6 text-gray-700" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center font-semibold">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {showDropdown && (
        <div className="absolute right-0 mt-2 w-80 bg-white rounded-lg shadow-2xl border border-gray-200 z-50">
          <div className="p-4 border-b flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">Notifications</h3>
            {unreadCount > 0 && (
              <button
                onClick={markAllRead}
                className="text-xs text-blue-600 hover:text-blue-800"
              >
                Mark all read
              </button>
            )}
          </div>

          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="p-4 text-center text-gray-500">
                No notifications
              </div>
            ) : (
              notifications.map(notification => (
                <div
                  key={notification.id}
                  onClick={() => handleNotificationClick(notification)}
                  className={`p-4 border-b hover:bg-gray-50 cursor-pointer transition-colors ${
                    !notification.read ? 'bg-blue-50' : ''
                  }`}
                >
                  <div className="flex items-start">
                    <div className="flex-1">
                      <h4 className="font-semibold text-sm text-gray-900">
                        {notification.title}
                      </h4>
                      <p className="text-sm text-gray-600 mt-1">
                        {notification.message}
                      </p>
                      <p className="text-xs text-gray-400 mt-1">
                        {new Date(notification.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    {!notification.read && (
                      <div className="w-2 h-2 bg-blue-600 rounded-full ml-2 mt-2"></div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
```

**File:** `salon-management-app/src/services/backendApi.js` (UPDATE)

```javascript
// Add notification endpoints:

export const notificationApi = {
  getNotifications: (unreadOnly = false, limit = 50) =>
    apiClient.get(`/notifications?unread_only=${unreadOnly}&limit=${limit}`),
  
  getUnreadCount: () =>
    apiClient.get('/notifications/unread-count'),
  
  markAsRead: (notificationId) =>
    apiClient.post(`/notifications/${notificationId}/mark-read`),
  
  markAllRead: () =>
    apiClient.post('/notifications/mark-all-read'),
};
```

---

## 🔄 Complete Workflow (After Implementation)

### Scenario: Admin Approves Salon

1. **RM Agent** submits salon via `AddSalonForm.jsx`
   - Creates record in `vendor_join_requests` table
   - Status: `pending`

2. **Admin Panel** receives real-time notification
   - Bell bounces, badge shows count
   - Toast: "🔔 {SalonName} submitted for approval!"

3. **Admin** reviews and clicks "Approve" in `PendingSalons.jsx`
   - Backend: `POST /api/admin/vendor-requests/{id}/approve`

4. **Backend Processing:**
   ```python
   a) Update request status to 'approved'
   b) Create salon record in 'salons' table
   c) Award RM points (+10) in 'rm_score_history'
   d) Generate JWT registration token
   e) 📧 Send approval email to VENDOR OWNER (with magic link)
   f) 🔔 Create notification for RM AGENT (NEW!)
   g) Return success response
   ```

5. **RM Agent Dashboard** - Real-time Update (NEW!)
   - Bell icon bounces
   - Badge shows "1" unread
   - Toast: "🎉 {SalonName} has been approved!"
   - Notification details: "Points awarded: +10"

6. **Vendor Owner** receives email
   - Subject: "🎉 Congratulations! {SalonName} has been approved"
   - Contains magic link: `/complete-registration?token={JWT}`
   - Link expires in 7 days

7. **Vendor** clicks magic link
   - Redirected to `CompleteRegistration.jsx`
   - 4-step wizard: Personal Info → Password → Payment → Confirmation

8. **After Payment Verified:**
   - Salon status: `is_active = true`
   - 📧 Payment receipt sent
   - 📧 Welcome email sent
   - Vendor can access vendor portal

---

## 📝 Implementation Checklist

### Phase 1: Database Setup
- [ ] Create `notifications` table with proper schema
- [ ] Add indexes for performance
- [ ] Enable RLS policies
- [ ] Test RLS with different user roles

### Phase 2: Backend - Notification Service
- [ ] Create `app/api/notifications.py`
- [ ] Implement `GET /notifications`
- [ ] Implement `GET /notifications/unread-count`
- [ ] Implement `POST /notifications/{id}/mark-read`
- [ ] Implement `POST /notifications/mark-all-read`
- [ ] Add `NotificationResponse` schema
- [ ] Register router in `main.py`
- [ ] Test all endpoints with Postman

### Phase 3: Backend - Integration
- [ ] Modify `approve_vendor_request()` in `admin.py`
  - [ ] Add notification creation for RM
  - [ ] Include salon details in notification data
  - [ ] Log notification creation
- [ ] Modify `reject_vendor_request()` in `admin.py`
  - [ ] Add notification creation for RM
  - [ ] Include rejection reason in data
- [ ] Test approval flow end-to-end
- [ ] Test rejection flow end-to-end
- [ ] Verify notifications are created in database

### Phase 4: Frontend - RM Portal
- [ ] Create `NotificationBell.jsx` component
- [ ] Add Supabase real-time subscription
- [ ] Implement unread counter badge
- [ ] Add bounce animation on new notification
- [ ] Create notification dropdown UI
- [ ] Implement "Mark as Read" functionality
- [ ] Implement "Mark All Read" functionality
- [ ] Add toast notifications
- [ ] Style component to match design system

### Phase 5: Integration & Testing
- [ ] Add `NotificationBell` to RM Dashboard header
- [ ] Add `NotificationBell` to RM layout (if exists)
- [ ] Update `backendApi.js` with notification endpoints
- [ ] Test RM receives notification on approval
- [ ] Test RM receives notification on rejection
- [ ] Test notification badge updates real-time
- [ ] Test notification dropdown opens/closes
- [ ] Test marking notifications as read
- [ ] Test navigation from notification click
- [ ] Test with multiple RMs simultaneously

### Phase 6: Email Improvements (Optional)
- [ ] Send approval notification email to RM (currently only rejection)
- [ ] Create `rm_approval_notification.html` template
- [ ] Update `approve_vendor_request()` to send RM email
- [ ] Test RM receives both email + in-app notification

---

## 🧪 Testing Scenarios

### Test Case 1: Salon Approval
1. Login as RM Agent
2. Submit a salon via Add Salon form
3. Login as Admin
4. Approve the salon
5. **Verify RM Agent:**
   - ✅ Bell icon bounces
   - ✅ Badge shows "1"
   - ✅ Toast appears with salon name
   - ✅ Notification in dropdown
   - ✅ Notification shows points awarded
6. **Verify Vendor Owner:**
   - ✅ Receives approval email
   - ✅ Email contains registration link
   - ✅ Link redirects to complete registration

### Test Case 2: Salon Rejection
1. Login as RM Agent
2. Submit a salon
3. Login as Admin
4. Reject with reason: "Incomplete documents"
5. **Verify RM Agent:**
   - ✅ Bell icon bounces
   - ✅ Badge shows "1"
   - ✅ Toast appears
   - ✅ Notification shows rejection
   - ✅ Receives rejection email

### Test Case 3: Real-time Updates
1. Open 2 browsers
2. Browser A: RM Dashboard (logged in as RM)
3. Browser B: Admin Panel (logged in as admin)
4. Browser B: Approve a salon
5. **Verify Browser A:**
   - ✅ Notification appears within 1-2 seconds
   - ✅ No page refresh needed
   - ✅ Badge updates automatically

### Test Case 4: Mark as Read
1. RM has 3 unread notifications
2. Click on one notification
3. **Verify:**
   - ✅ Notification background changes
   - ✅ Badge count decreases to 2
   - ✅ Blue dot disappears from that notification

### Test Case 5: Mark All Read
1. RM has 5 unread notifications
2. Click "Mark all read"
3. **Verify:**
   - ✅ Badge disappears
   - ✅ All notifications show as read
   - ✅ No blue dots visible

---

## 📊 Summary

### Already Built ✅
- Complete backend approval/rejection APIs
- Email service with professional templates
- Admin panel with real-time notifications
- Vendor registration flow with payment
- RM submission form

### Need to Build ❌
1. **Database:** `notifications` table
2. **Backend:** Notifications API (`/api/notifications`)
3. **Backend:** Integration in approval/rejection flows
4. **Frontend:** `NotificationBell` component for RM portal
5. **Frontend:** Real-time subscription in RM dashboard
6. **Testing:** End-to-end notification flow

### Estimated Time
- Database setup: 30 minutes
- Backend API: 2 hours
- Backend integration: 1 hour
- Frontend component: 3 hours
- Testing & polish: 2 hours
- **Total: ~8-9 hours**

### Priority
**HIGH** - This completes the feedback loop for RM agents and improves user experience significantly.

---

## 🚀 Quick Start Commands

### Create Database Table
```sql
-- Run in Supabase SQL Editor
-- See "Database Schema - Notifications Table" section above
```

### Create Backend File
```bash
# In backend directory
touch app/api/notifications.py
```

### Create Frontend Component
```bash
# In salon-management-app directory
mkdir -p src/components/notifications
touch src/components/notifications/NotificationBell.jsx
```

### Test Backend
```bash
# In backend directory with venv activated
python -m pytest tests/test_notifications.py -v
```

### Test Frontend
```bash
# In salon-management-app directory
npm run dev
# Open http://localhost:3000 and test RM dashboard
```

---

## 📚 Reference Documentation

- **Supabase Real-time:** https://supabase.com/docs/guides/realtime
- **JWT Token Generation:** `app/core/auth.py` → `create_registration_token()`
- **Email Service:** `app/services/email.py`
- **Admin Approval Flow:** `PHASE_3_COMPLETE.md`
- **RM Portal Migration:** `PHASE_7_RM_PORTAL_MIGRATION.md`
- **Email Integration:** `PHASE_4_EMAIL_INTEGRATION.md`

---

**Last Updated:** November 2, 2025
**Status:** Ready for Implementation
