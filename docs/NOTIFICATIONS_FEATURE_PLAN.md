# Push Notifications Feature — Plan & Progress Tracker

> **Goal:** Admin-managed push notifications (like the "Dullness Detected 👋" marketing
> push) that the client composes and sends from the admin panel, delivered to the
> Lubist mobile app. Plus an in-app notification center so users see history.
>
> **Status legend:** `[ ]` not started · `[~]` in progress · `[x]` done
> **Last updated:** 2026-07-15 (initial plan)

---

## 0. Architecture Decision (read once, then skim)

**Delivery layer (never built by us):** The OS push networks — **FCM** (Android) and
**APNs** (iOS) — do the actual delivery. They are free and mandatory.

**Our transport:** **Expo Push Notifications**. The app is already Expo (`expo ~54`,
EAS `projectId: 0c5d02f8-8571-42f1-a61a-5aea92ddd8a5`). Expo's push service wraps both
FCM + APNs behind a single HTTP API (`https://exp.host/--/api/v2/push/send`), so the
backend calls **one** endpoint and Expo fans out to Google/Apple. **Free.**

**What we build:** the compose/target/store/send layer, living in *our* stack so the
client manages everything from *his* admin panel — no third-party dashboard.

```
Mobile (Expo)  --register push token-->  FastAPI  <--compose & send--  Admin panel
                                            |
                                            +--> Supabase (device_tokens, notifications)
                                            +--> Expo Push API --> FCM/APNs --> 📱 banner
```

**Two notification types, one pipeline:**
- **Marketing** — composed manually in admin panel (the client's main ask). *Build first.*
- **Transactional** — fired by backend events (booking confirmed, order shipped). *Phase 9, reuse same send service.*

**Conventions to follow (verified in repo):**
- Backend: router w/ `prefix` in `main.py`; service class wrapping Supabase; `require_admin` for admin routes; migrations `supabase/migrations/<ts>_*.sql`; static path segments before `/{id}`.
- Admin panel: RTK Query API service (`src/services/api/*Api.js` + `baseQuery.js`); page in `src/pages/`; nav entry in `src/components/layout/Sidebar.jsx`; `Card/Button/Modal/Badge` + `react-toastify`.
- Mobile: TanStack Query hooks in `src/services/api/hooks/`; `apiGet/apiPost` from `services/api/client.ts`; existing stub at `src/services/notifications/notificationService.ts`.

---

## Phase 0 — Prerequisites & Credentials (blocks device delivery)

- [ ] Install `expo-notifications` (+ `expo-device`) in mobile app
- [ ] Add `expo-notifications` plugin to `app.json` (icon, color, Android channel)
- [ ] Configure **Android FCM** credentials in EAS (`eas credentials` → upload FCM V1 service-account key). Required for standalone builds; Expo Go can't receive prod pushes.
- [ ] Configure **iOS APNs** key in EAS (when/if iOS ships) — Apple Developer account needed
- [ ] Add `EXPO_ACCESS_TOKEN` (optional, for higher rate limits / receipts) to backend `.env` + `config.py`
- [ ] Decide sender identity/branding (small icon + accent color for Android)

> ⚠️ Nothing below Phase 4 can be tested on a real device until FCM creds exist. Backend
> phases 1–4 can be built & unit-tested independently (mock the Expo call).

---

## Phase 1 — Backend: Data Model (migration)

- [ ] New migration `supabase/migrations/<ts>_create_notifications.sql`
- [ ] Table **`device_tokens`**: `id, user_id (fk→profiles), expo_push_token (unique), platform (ios|android), device_id, is_active, created_at, updated_at, last_seen_at`
  - Index on `user_id`, unique on `expo_push_token`; upsert on re-register
- [ ] Table **`notifications`** (campaigns): `id, title, body, image_url (nullable), data (jsonb, deep-link payload), audience (all|customers|vendors|city:<x>|user:<id>), status (draft|scheduled|sending|sent|failed), scheduled_at (nullable), sent_at, created_by, sent_count, failed_count, created_at, updated_at`
- [ ] Table **`notification_recipients`** (for in-app center + read tracking): `id, notification_id (fk), user_id (fk), read_at (nullable), delivered (bool), created_at`
  - Index on `(user_id, read_at)` for unread counts
- [ ] RLS: admin full access; users read only their own `notification_recipients`
- [ ] Apply migration to Supabase (follow `docs/MIGRATION_SAFETY.md`)

---

## Phase 2 — Backend: Device Token Registration

- [ ] Schemas: `DeviceTokenRegister` (request), `DeviceTokenResponse` (response)
- [ ] `notification_service.py` → `register_device_token(user_id, token, platform, device_id)` (upsert, reactivate if seen again)
- [ ] `notification_service.py` → `deactivate_device_token(token)` (on logout / push-disabled)
- [ ] Endpoints in new `app/api/notifications.py`:
  - `POST /notifications/device-token` (auth: current user) — register/refresh
  - `DELETE /notifications/device-token` — deactivate (on logout)
- [ ] Register router in `main.py` (`prefix=settings.API_PREFIX`)

---

## Phase 3 — Backend: Send Service (Expo Push integration)

- [ ] `notification_service.py` → `_resolve_audience(audience) -> list[user_id]`
- [ ] `notification_service.py` → `_collect_tokens(user_ids) -> list[expo_token]`
- [ ] `notification_service.py` → `send_via_expo(tokens, title, body, data, image)` — POST to Expo Push API, **chunked (≤100 tokens/request)**
- [ ] Handle Expo **receipts**: mark `DeviceNotRegistered` tokens inactive (prunes dead tokens)
- [ ] Write `notification_recipients` rows for the audience (feeds in-app center)
- [ ] Update campaign `status`, `sent_count`, `failed_count`
- [ ] Unit test with mocked Expo HTTP (pattern: `tests/test_*_mocked.py`)

---

## Phase 4 — Backend: Admin Campaign Endpoints

- [ ] Schemas: `NotificationCreate`, `NotificationUpdate`, `NotificationListResponse`, `NotificationOperationResponse`
- [ ] Endpoints in `app/api/notifications.py` (all `require_admin`):
  - `GET  /notifications/admin/all` — list campaigns (paginated, newest first)
  - `POST /notifications` — create draft
  - `POST /notifications/{id}/send` — send now
  - `PUT  /notifications/{id}` — edit draft / reschedule
  - `DELETE /notifications/{id}` — delete draft
- [ ] (Optional) `POST /notifications/{id}/test` — send to admin's own device only
- [ ] Scheduling: either a lightweight `scheduled_at` + cron/worker sweep, or ship "send now" first and add scheduling in a follow-up
- [ ] Audience count preview endpoint: `GET /notifications/audience-count?audience=...`

---

## Phase 5 — Mobile: Token Registration & Permissions

- [ ] Replace stub `src/services/notifications/notificationService.ts`:
  - `registerForNotifications()` — request permission, get Expo push token (via `getExpoPushTokenAsync` with `projectId`), return token + status
  - Android: create default notification channel
- [ ] New hook `src/services/api/hooks/useNotificationsAPI.ts` (TanStack) — `registerDeviceToken`, `deregister`, `getMyNotifications`, `markRead`
- [ ] Call `registerForNotifications()` + POST token **after successful login** (in AuthContext / post-login effect); deregister on logout
- [ ] Gracefully handle permission denied (don't block app; allow re-prompt from settings)

---

## Phase 6 — Mobile: Receive & Handle

- [ ] Foreground handler (`setNotificationHandler`) — show in-app toast/banner
- [ ] Notification-tapped handler (`addNotificationResponseReceivedListener`) — deep-link using `data` payload (e.g. open salon/service/product/screen)
- [ ] Cold-start: handle notification that launched the app (`getLastNotificationResponseAsync`)
- [ ] Badge count sync (optional)

---

## Phase 7 — Mobile: In-App Notification Center

- [ ] Bell icon in header with unread badge (count from `notification_recipients`)
- [ ] Notifications list screen (title, body, image thumb, timestamp, read/unread)
- [ ] Mark-as-read on open; pull-to-refresh; empty state
- [ ] Wire into navigation stack

---

## Phase 8 — Admin Panel: Notifications Management

- [ ] RTK Query service `src/services/api/notificationApi.js` (follow `bannerApi.js`): `useGetAllNotificationsQuery`, `useCreateNotificationMutation`, `useSendNotificationMutation`, `useUpdateNotificationMutation`, `useDeleteNotificationMutation`, `useUploadNotificationImageMutation`, `useGetAudienceCountQuery`
- [ ] Page `src/pages/Notifications.jsx` (follow `Banners.jsx`):
  - List of campaigns with status badges + sent/failed counts
  - Create/Edit modal: title, body, optional image (Cloudinary upload), audience selector, deep-link target, **"Send now" vs "Schedule"**
  - **Live preview** of the notification banner (mimics the phone screenshot)
  - Confirm dialog before sending (shows audience count)
- [ ] Route in router + nav entry in `src/components/layout/Sidebar.jsx` (label "Notifications")

---

## Phase 9 — Transactional Notifications (later, reuses Phase 3)

- [ ] Booking confirmed / cancelled → push to customer
- [ ] Product order status change (confirmed/shipped/delivered) → push to buyer
- [ ] New booking → push to vendor
- [ ] Central helper `notify_user(user_id, template, context)` reusing `send_via_expo`
- [ ] Per-user notification preferences (opt-out categories) — optional

---

## Phase 10 — Testing, QA & Rollout

- [ ] Backend unit tests (token register, audience resolve, send w/ mocked Expo, receipt pruning)
- [ ] End-to-end on a **real device / dev build** (Expo Go cannot receive prod push): send from admin → banner appears → tap → deep-links correctly
- [ ] Verify token lifecycle: login registers, logout deregisters, reinstall refreshes
- [ ] Ship mobile via EAS build (native change → **not** OTA-able; needs new build)
- [ ] Admin panel deploy
- [ ] Docs: write `docs/NOTIFICATIONS_API.md` (like `BANNER_API.md`) when stable
- [ ] Update this tracker + memory

---

## Open Decisions (confirm with client)

- [ ] **Scheduling now or later?** MVP = "send now"; scheduling is a fast follow.
- [ ] **iOS in scope?** Needs Apple Developer account + APNs key. Android-first is fine.
- [ ] **Audience granularity for v1?** Suggest: All / Customers / Vendors / By city. Segments (e.g. "users who booked a facial") = later.
- [ ] **In-app center in v1?** Recommended (cheap, big UX win) but could defer to v1.1.

## Key Files (created/touched)

| Layer | Path |
|-------|------|
| Backend migration | `supabase/migrations/<ts>_create_notifications.sql` |
| Backend service | `app/services/notification_service.py` |
| Backend API | `app/api/notifications.py` (+ register in `main.py`) |
| Backend schemas | `app/schemas/request/notification.py`, `app/schemas/response/notification.py` |
| Mobile service | `src/services/notifications/notificationService.ts` |
| Mobile hook | `src/services/api/hooks/useNotificationsAPI.ts` |
| Mobile UI | notification center screen + header bell |
| Admin API | `salon-admin-panel/src/services/api/notificationApi.js` |
| Admin page | `salon-admin-panel/src/pages/Notifications.jsx` (+ Sidebar + route) |
