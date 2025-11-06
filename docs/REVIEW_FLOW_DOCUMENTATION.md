# Review System - Complete Flow Documentation

## Overview
This document describes the complete end-to-end flow of the review system from customer booking to published review.

---

## 👤 CUSTOMER JOURNEY

### **Phase 1: Browse & Book** 🛍️

1. **Customer discovers salon**
   - Browses `/salons` page
   - Searches by location/services
   - Views salon ratings and existing reviews

2. **Customer books services**
   - Clicks "Book Services" on Salon Detail page
   - Selects services from catalog
   - Chooses date and time
   - Adds to cart or books directly

3. **Payment & Confirmation**
   - Completes payment (online or pay-after-service)
   - Booking status: `pending` → `confirmed`
   - Receives confirmation email
   - Booking appears in "My Bookings"

---

### **Phase 2: Service Delivery** 💇

4. **Customer visits salon**
   - Arrives at scheduled time
   - Receives booked services
   - Interacts with staff

5. **Vendor marks booking complete**
   - Vendor logs into dashboard
   - Marks booking as `completed`
   - Payment processed (if pay-after-service)
   - **Review eligibility unlocked** ✅

---

### **Phase 3: Review Prompt** ⭐

6. **Customer sees review option**
   - Returns to "My Bookings" page
   - Completed bookings show **"Write Review"** button
   - Button only visible if:
     - Booking status = `completed`
     - No review exists for this booking yet
     - Customer owns the booking

7. **Alternative entry points**
   - Email notification: "How was your service at [Salon]?"
   - Toast notification after booking completion
   - "Write a Review" on Salon Detail page (if completed booking exists)

---

### **Phase 4: Write Review** ✍️

8. **Customer clicks "Write Review"**
   - Review modal opens
   - Pre-filled data:
     - Salon name (read-only)
     - Booking date (read-only)
     - Services received (display only)

9. **Customer fills review form**
   ```
   ┌─────────────────────────────────────┐
   │   Write Your Review                 │
   │                                     │
   │   Salon Name: The Beauty Lounge     │
   │   Service Date: Nov 5, 2025         │
   │                                     │
   │   Your Rating: ⭐⭐⭐⭐⭐          │
   │   (Click stars to rate 1-5)         │
   │                                     │
   │   Your Review:                      │
   │   ┌─────────────────────────────┐   │
   │   │ Amazing experience! The     │   │
   │   │ staff was professional and  │   │
   │   │ the results exceeded my...  │   │
   │   └─────────────────────────────┘   │
   │   250/500 characters                │
   │                                     │
   │   [Optional] Rate Staff Member:     │
   │   [ Select Staff... ▼ ]             │
   │                                     │
   │   [Optional] Add Photos:            │
   │   [+] Upload Images                 │
   │                                     │
   │   [ Cancel ]  [ Submit Review ]     │
   └─────────────────────────────────────┘
   ```

10. **Form validation**
    - Rating: Required (1-5 stars)
    - Comment: Required (10-500 characters)
    - Staff: Optional
    - Images: Optional (max 5 images, 5MB each)

---

### **Phase 5: Submit & Save** 💾

11. **Customer submits review**
    - Frontend validates form
    - API call: `POST /api/customers/reviews`
    - Request body:
      ```json
      {
        "booking_id": "uuid-here",
        "salon_id": "uuid-here",
        "rating": 5,
        "comment": "Amazing experience!...",
        "staff_id": "uuid-here", // optional
        "images": ["url1", "url2"] // optional
      }
      ```

12. **Backend processing**
    - Validates customer owns booking
    - Checks booking is completed
    - Ensures no duplicate review (unique constraint)
    - Creates review record:
      ```sql
      INSERT INTO reviews (
        booking_id,
        customer_id,
        salon_id,
        staff_id,
        rating,
        review_text,
        images,
        is_verified, -- false
        is_visible,  -- true
        created_at
      ) VALUES (...);
      ```
    - **Initial Status:** `is_verified = false` (pending approval)

13. **Success response**
    - Shows success toast: "Review submitted! It will be published after approval."
    - Modal closes
    - Redirects to "My Reviews" page
    - Review appears with **"Under Review"** badge

---

### **Phase 6: Admin Moderation** 👮

14. **Admin receives notification**
    - Email: "New review pending approval"
    - Admin dashboard shows pending reviews count
    - Badge on "Reviews" menu item

15. **Admin reviews submission**
    - Opens Admin Panel → Reviews → Pending
    - Sees review details:
      - Customer name
      - Salon name
      - Rating and comment
      - Images (if any)
      - Booking context
    - Checks for:
      - Inappropriate language
      - Spam content
      - Fake reviews
      - Policy violations

16. **Admin takes action**

    **Option A: Approve** ✅
    - Clicks "Approve"
    - API: `PUT /api/admin/reviews/{id}/approve`
    - Sets `is_verified = true`, `is_visible = true`
    - Triggers rating update
    - Customer notification: "Your review has been published!"

    **Option B: Reject** ❌
    - Clicks "Reject"
    - Adds rejection reason (optional)
    - API: `PUT /api/admin/reviews/{id}/reject`
    - Sets `is_visible = false`
    - Customer notification: "Review could not be published" (with reason)

    **Option C: Delete** 🗑️
    - For severe violations
    - Permanently removes review
    - API: `DELETE /api/admin/reviews/{id}`

---

### **Phase 7: Review Published** 📢

17. **Review appears publicly**
    - **Salon Detail Page:**
      - Reviews tab shows approved review
      - Sorted by date (newest first)
      - Shows customer name, rating, comment, date
      - Shows images if uploaded
    
    - **My Reviews Page:**
      - Status changes to **"Published"** badge
      - Green badge instead of yellow
      - Customer can still edit or delete

18. **Salon rating auto-updates** 🔄
    - Database trigger executes:
      ```sql
      -- Calculate new average
      UPDATE salons
      SET 
        average_rating = (
          SELECT AVG(rating)
          FROM reviews
          WHERE salon_id = {salon_id}
          AND is_visible = true
          AND is_verified = true
        ),
        total_reviews = (
          SELECT COUNT(*)
          FROM reviews
          WHERE salon_id = {salon_id}
          AND is_visible = true
          AND is_verified = true
        )
      WHERE id = {salon_id};
      ```
    
    - **Salon listing updated:**
      - Average rating: 4.5 ⭐
      - Total reviews: 23
      - Rating badge color updates based on score

19. **Staff rating updates** (if staff selected)
    - Similar trigger for `salon_staff` table
    - Updates individual staff member ratings

---

### **Phase 8: Post-Publication** 🔄

20. **Customer can edit review**
    - Goes to "My Reviews" page
    - Clicks edit icon on review card
    - Modal opens with existing data
    - Makes changes
    - Submits: `PUT /api/customers/reviews/{id}`
    - **Important:** Review status resets to `pending` (requires re-approval)
    - Admin re-reviews edited content

21. **Customer can delete review**
    - Clicks delete button (with confirmation)
    - API: `DELETE /api/customers/reviews/{id}`
    - Review removed from all displays
    - Salon rating recalculated automatically

22. **Review remains linked to booking**
    - One review per booking (enforced by unique constraint)
    - Booking history always shows if reviewed
    - Customer cannot write multiple reviews for same booking

---

## 🔧 TECHNICAL FLOW

### **Database State Changes**

```
┌─────────────────┐
│ Booking Created │ → status: pending
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ Booking Paid    │ → status: confirmed
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ Service Done    │ → status: completed ✅ (can review)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ Review Created  │ → is_verified: false, is_visible: true
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ Admin Approves  │ → is_verified: true, is_visible: true ✅
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ Public Display  │ → Shows in salon reviews
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ Rating Updated  │ → Salon average_rating recalculated
└─────────────────┘
```

---

### **API Call Sequence**

#### **1. Customer Writes Review**
```
Frontend                  Backend                    Database
   │                         │                          │
   │ POST /customers/reviews │                          │
   ├────────────────────────→│                          │
   │                         │ Validate ownership       │
   │                         │ Check booking completed  │
   │                         │ Check no duplicate       │
   │                         │                          │
   │                         │ INSERT INTO reviews      │
   │                         ├─────────────────────────→│
   │                         │                          │
   │                         │←─────────────────────────┤
   │    201 Created          │        Review ID         │
   │←────────────────────────┤                          │
   │                         │                          │
```

#### **2. Customer Views Reviews**
```
Frontend                  Backend                    Database
   │                         │                          │
   │ GET /customers/reviews  │                          │
   │     /my-reviews         │                          │
   ├────────────────────────→│                          │
   │                         │ SELECT reviews           │
   │                         │ JOIN salons              │
   │                         ├─────────────────────────→│
   │                         │                          │
   │                         │←─────────────────────────┤
   │    200 OK               │     Reviews + Salons     │
   │    [{reviews}]          │                          │
   │←────────────────────────┤                          │
   │                         │                          │
```

#### **3. Public Views Salon Reviews**
```
Frontend                  Backend                    Database
   │                         │                          │
   │ GET /salons/{id}        │                          │
   │     /reviews            │                          │
   ├────────────────────────→│                          │
   │                         │ SELECT reviews           │
   │                         │ WHERE salon_id = {id}    │
   │                         │ AND is_visible = true    │
   │                         │ AND is_verified = true   │
   │                         ├─────────────────────────→│
   │                         │                          │
   │                         │←─────────────────────────┤
   │    200 OK               │     Public Reviews       │
   │    [{reviews}]          │                          │
   │←────────────────────────┤                          │
   │                         │                          │
```

#### **4. Admin Approves Review**
```
Admin Panel              Backend                    Database
   │                         │                          │
   │ PUT /admin/reviews/{id} │                          │
   │     /approve            │                          │
   ├────────────────────────→│                          │
   │                         │ Verify admin role        │
   │                         │                          │
   │                         │ UPDATE reviews           │
   │                         │ SET is_verified = true   │
   │                         ├─────────────────────────→│
   │                         │                          │
   │                         │ 🔔 TRIGGER FIRES         │
   │                         │ update_salon_rating()    │
   │                         │                          │
   │                         │ UPDATE salons            │
   │                         │ SET average_rating = ... │
   │                         │     total_reviews = ...  │
   │                         │←─────────────────────────┤
   │                         │                          │
   │    200 OK               │                          │
   │←────────────────────────┤                          │
   │                         │                          │
   │                         │ Send notification        │
   │                         │ to customer              │
   │                         │                          │
```

---

## 📊 DATA FLOW DIAGRAM

```
Customer                    System                      Admin
   │                          │                           │
   │  1. Books Service        │                           │
   ├─────────────────────────→│                           │
   │                          │                           │
   │  2. Service Completed    │                           │
   │←─────────────────────────┤                           │
   │                          │                           │
   │  3. Writes Review        │                           │
   ├─────────────────────────→│                           │
   │                          │  4. Stores Review         │
   │                          │  (pending approval)       │
   │                          │                           │
   │  5. "Under Review"       │  6. Notification          │
   │     Badge Shown          ├──────────────────────────→│
   │←─────────────────────────┤                           │
   │                          │                           │
   │                          │  7. Reviews Content       │
   │                          │←──────────────────────────┤
   │                          │                           │
   │                          │  8. Approves Review       │
   │                          │←──────────────────────────┤
   │                          │                           │
   │                          │  9. Updates Rating        │
   │                          │  (auto-trigger)           │
   │                          │                           │
   │  10. "Published" Badge   │                           │
   │      + Notification      │                           │
   │←─────────────────────────┤                           │
   │                          │                           │
   │  11. Review Visible      │                           │
   │      on Salon Page       │                           │
   │←─────────────────────────┤                           │
   │                          │                           │
```

---

## 🚦 REVIEW STATES

### **State Machine**

```
                    ┌──────────────────┐
                    │   NOT STARTED    │
                    │  (No Review Yet) │
                    └────────┬─────────┘
                             │
                    Customer writes review
                             │
                             ↓
                    ┌──────────────────┐
              ┌────→│     PENDING      │
              │     │  (Under Review)  │
              │     └────────┬─────────┘
              │              │
              │              ├──────────┐
              │              │          │
              │        Admin Approves   Admin Rejects
              │              │          │
              │              ↓          ↓
              │     ┌──────────────────┐ ┌──────────────────┐
              │     │    APPROVED      │ │     REJECTED     │
              │     │   (Published)    │ │    (Hidden)      │
              │     └────────┬─────────┘ └──────────────────┘
              │              │
              │    Customer edits review
              │              │
              └──────────────┘
```

### **State Definitions**

| State | Database Fields | Visible to Customer | Visible to Public | Actions Available |
|-------|----------------|---------------------|-------------------|------------------|
| **Not Started** | No record | N/A | N/A | Write Review |
| **Pending** | `is_verified=false`, `is_visible=true` | Yes (My Reviews) | No | Edit, Delete, Wait |
| **Approved** | `is_verified=true`, `is_visible=true` | Yes | Yes | Edit, Delete |
| **Rejected** | `is_verified=false`, `is_visible=false` | Yes (with reason) | No | Edit & Resubmit, Delete |
| **Edited** | Returns to Pending | Yes | No (hidden until re-approved) | Wait for re-approval |

---

## 🎯 BUSINESS RULES

### **Review Eligibility**
✅ **Customer CAN write review if:**
- Booking status is `completed`
- Customer owns the booking
- No review exists for this booking yet
- Customer is authenticated

❌ **Customer CANNOT write review if:**
- Booking is not completed (pending/cancelled)
- Review already exists (use Edit instead)
- Customer doesn't own booking
- Not logged in

---

### **Review Visibility**
✅ **Review is PUBLIC if:**
- `is_verified = true` (admin approved)
- `is_visible = true` (not hidden/deleted)
- Salon is active

❌ **Review is HIDDEN if:**
- `is_verified = false` (pending approval)
- `is_visible = false` (rejected/deleted)
- Salon is inactive

---

### **Rating Calculation**
**Average Rating Formula:**
```sql
AVG(rating) FROM reviews
WHERE salon_id = {id}
AND is_verified = true
AND is_visible = true
```

**Recalculation Triggers:**
- New review approved
- Existing review deleted
- Review edited and re-approved
- Review rejected (rating decreases)

**Display Rules:**
- Show stars only if `total_reviews > 0`
- Round to 1 decimal: `4.3 ⭐`
- Show review count: `(23 reviews)`

---

## 📧 NOTIFICATIONS

### **Customer Notifications**

1. **Review Submitted** (Immediate)
   - Subject: "Thank you for your review!"
   - Body: "Your review has been submitted and is under review."

2. **Review Approved** (Within 24-48h)
   - Subject: "Your review has been published!"
   - Body: "Your review for [Salon Name] is now visible to others."

3. **Review Rejected** (If rejected)
   - Subject: "Review update needed"
   - Body: "Your review couldn't be published. Reason: [reason]"

4. **Review Reminder** (3 days after completed booking)
   - Subject: "How was your experience at [Salon Name]?"
   - Body: "We'd love to hear about your recent visit!"

### **Admin Notifications**

1. **New Review Pending** (Immediate)
   - Email digest (every hour if pending reviews exist)
   - Dashboard badge count

2. **Multiple Reports** (If review reporting implemented)
   - Alert when review receives 3+ reports

---

## 🔒 SECURITY & VALIDATION

### **Backend Validation**
```python
# Ownership check
if review.customer_id != current_user.id:
    raise HTTPException(403, "Unauthorized")

# Booking completion check
booking = get_booking(booking_id)
if booking.status != "completed":
    raise HTTPException(400, "Booking not completed")

# Duplicate check (enforced by unique constraint)
existing = get_review_by_booking(booking_id)
if existing:
    raise HTTPException(409, "Review already exists")

# Content validation
if len(comment) < 10 or len(comment) > 500:
    raise HTTPException(400, "Comment must be 10-500 characters")

if rating < 1 or rating > 5:
    raise HTTPException(400, "Rating must be 1-5")
```

### **Frontend Validation**
- Real-time character counter
- Star rating visual feedback
- Disable submit until valid
- Confirm before delete

---

## ⚡ PERFORMANCE CONSIDERATIONS

### **Database Indexes** (Already defined)
```sql
-- Fast salon review queries
idx_reviews_salon_id_created_at (salon_id, created_at DESC)

-- Fast customer review queries  
idx_reviews_customer_id_created_at (customer_id, created_at DESC)

-- Fast staff review queries
idx_reviews_staff_id_created_at (staff_id, created_at DESC)

-- Fast admin moderation queries
idx_reviews_is_verified (salon_id, is_verified, created_at DESC)
```

### **Caching Strategy**
- **Salon reviews:** Cache for 5 minutes (frequently viewed)
- **My reviews:** Cache for 5 minutes (infrequent changes)
- **Pending count:** Real-time (no cache)
- Invalidate on: approve, reject, delete, edit

---

## 🎨 UI/UX BEST PRACTICES

### **Review Form**
✅ **Do:**
- Pre-fill salon name and booking date
- Show character counter
- Provide star rating with hover preview
- Allow optional staff selection
- Enable draft saving (future feature)
- Show validation errors inline

❌ **Don't:**
- Make form too long (keep under 5 fields)
- Require images (make optional)
- Ask for personal info (already known)

### **Review Display**
✅ **Do:**
- Show customer name (first name + last initial)
- Display relative dates ("2 weeks ago")
- Use star icons for ratings
- Show verified badge if applicable
- Enable helpful/not helpful votes (future)

❌ **Don't:**
- Show full customer names (privacy)
- Display pending reviews publicly
- Allow unverified reviews to affect ratings

---

## 📈 ANALYTICS & METRICS

### **Track These Metrics**

1. **Review Rate**
   - % of completed bookings with reviews
   - Target: 20-30%

2. **Average Rating**
   - Overall platform rating
   - Per salon ratings
   - Trend over time

3. **Review Volume**
   - Reviews per week/month
   - Peak review times

4. **Moderation Stats**
   - Average approval time
   - Approval vs rejection rate
   - Most common rejection reasons

5. **Customer Engagement**
   - Time to write review after booking
   - Edit frequency
   - Delete frequency

---

## 🚀 FUTURE ENHANCEMENTS

### **Phase 2 Features**
- 👍 Review helpfulness voting
- 🖼️ Multiple image uploads
- 👥 Staff-specific ratings
- 💬 Salon owner responses
- 📊 Review sentiment analysis
- 🎖️ Verified customer badge (multiple bookings)

### **Phase 3 Features**
- 🚩 Review reporting system
- 📸 Before/after photo galleries
- 🎥 Video reviews
- 🏆 Top reviewer leaderboard
- 💎 Incentivized reviews (rewards)

---

## ✅ IMPLEMENTATION CHECKLIST

Use this to track review flow implementation:

### **Backend**
- [ ] Fix schema mismatches (customer_id, UUID)
- [ ] Create `/api/salons/{id}/reviews` endpoint
- [ ] Add review eligibility check endpoint
- [ ] Create admin approval endpoints
- [ ] Implement rating aggregation triggers
- [ ] Add notification system

### **Frontend - Write Flow**
- [ ] Create `WriteReviewModal` component
- [ ] Add "Write Review" button to My Bookings
- [ ] Add review form validation
- [ ] Integrate with API
- [ ] Show success/error states

### **Frontend - Display Flow**
- [ ] Replace mock reviews with API data
- [ ] Add pagination for reviews
- [ ] Add filter/sort options
- [ ] Show review status badges
- [ ] Enable edit/delete actions

### **Admin Panel**
- [ ] Create Reviews page
- [ ] List pending reviews
- [ ] Add approve/reject actions
- [ ] Show review context (booking, customer)
- [ ] Add bulk moderation

### **Database**
- [ ] Deploy review indexes
- [ ] Create rating update triggers
- [ ] Add review status column (if needed)
- [ ] Test trigger performance

---

## 📖 SUMMARY

**The Complete Review Flow:**
1. Customer books and completes service ✅
2. "Write Review" button appears on completed bookings
3. Customer fills review form (rating + comment)
4. Review submitted with `pending` status
5. Admin reviews and approves/rejects
6. Approved reviews appear publicly
7. Salon rating auto-updates via trigger
8. Customer can edit (re-approval) or delete

**Key Principles:**
- ✅ One review per booking (unique constraint)
- ✅ Only completed bookings can be reviewed
- ✅ All reviews require admin approval
- ✅ Ratings update automatically via triggers
- ✅ Customer controls their reviews (edit/delete)
- ✅ Public only sees approved reviews

**Current Status:**
- Database: Ready (needs triggers)
- Backend: 40% (needs fixes + missing endpoints)
- Frontend: 45% (needs write flow)
- Admin: 0% (needs full implementation)

**Estimated Time to Complete:** 20 hours for MVP
