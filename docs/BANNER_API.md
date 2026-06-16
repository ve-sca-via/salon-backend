# Home Banner (Carousel) API

> **New feature — added 2026-06-14.** Lets an admin manage the mobile home-screen
> **carousel banners** (the hero images) without a code change or app release —
> upload an image, set the order, enable/disable, and delete. Replaces the
> previously hardcoded hero image. Built on a small, reusable `banners` table.
>
> ✅ **Already wired:** the **admin panel (`salon-admin-panel`)** has a full
> management page, the **Lubist mobile app (`lubist_mobile_application`)** renders
> the carousel from this API, and the **customer web app (`salon-management-app`)**
> now renders the same admin-managed banners on its home hero (with a bundled
> fallback). See the [web-app reference section](#web-app-salon-management-app-reference-now-wired) below.

---

## Summary

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET`    | `/api/v1/banners`                       | **Public** | List active, in-window banners for the carousel (ordered) |
| `GET`    | `/api/v1/banners/admin/all`             | Bearer (admin) | List ALL banners incl. inactive (management) |
| `POST`   | `/api/v1/banners`                       | Bearer (admin) | Create a banner |
| `PUT`    | `/api/v1/banners/reorder`               | Bearer (admin) | Bulk-update display order |
| `PUT`    | `/api/v1/banners/{banner_id}`           | Bearer (admin) | Update a banner |
| `DELETE` | `/api/v1/banners/{banner_id}`           | Bearer (admin) | Soft-delete (`?hard=true` to purge) |
| `POST`   | `/api/v1/upload/cloudinary-banner-image`| Bearer | Upload a banner image → Cloudinary URL |

- **Base URL:** `http://localhost:8000` (dev) · **Global prefix:** `/api/v1`
- **Auth:** standard JWT bearer token (`Authorization: Bearer <access_token>`).
  - `GET /banners` is **fully public** (no token) — the home screen loads it for logged-out users.
  - All write endpoints require an **admin** token (`require_admin`).
  - The upload endpoint requires any authenticated user; banner create/update additionally require admin.
- **Storage:** banner images go to **Cloudinary via the same path as product images**
  (`CloudinaryService`). If product images render in your clients, banners do too.

---

## Data model

New table `banners` (migration `supabase/migrations/20260614000000_create_banners_table.sql`):

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` PK | `gen_random_uuid()` |
| `title` | `text` | Optional caption / alt text / admin label |
| `image_url` | `text` **NOT NULL** | Cloudinary URL (from the upload endpoint) |
| `link_url` | `text` | Optional tap target (deep link or external URL) |
| `sort_order` | `integer` NOT NULL default `0` | Ascending display order in the carousel |
| `is_active` | `boolean` NOT NULL default `true` | Soft on/off without deleting |
| `starts_at` | `timestamptz` | Optional schedule-window start (NULL = always) |
| `ends_at` | `timestamptz` | Optional schedule-window end (NULL = never expires) |
| `created_at` | `timestamptz` | default `now()` |
| `updated_at` | `timestamptz` | auto-updated by trigger |

- **Ordering:** the public feed returns `sort_order ASC`, then `created_at DESC` as a tiebreak.
- **Schedule window:** the public feed hides banners where `now < starts_at` or `now > ends_at`. The admin feed ignores the window so you can manage scheduled/expired banners.
- RLS is **enabled** with a service-role full-access policy (backend uses the service-role key), consistent with `products`, `activity_logs`, etc.

---

## Endpoints

### 1. List banners (public carousel feed)

```
GET /api/v1/banners
```

No auth. Returns only **active** banners currently **within their schedule window**, ordered by `sort_order`.

**200 OK**
```json
{
  "success": true,
  "banners": [
    {
      "id": "b3c1...",
      "title": "Flat 10% OFF this week",
      "image_url": "https://res.cloudinary.com/<cloud>/image/upload/banners/abc.jpg",
      "link_url": "https://lubist.app/offers/festive",
      "sort_order": 0,
      "is_active": true,
      "starts_at": null,
      "ends_at": null,
      "created_at": "2026-06-14T08:00:00Z",
      "updated_at": "2026-06-14T08:00:00Z"
    }
  ],
  "count": 1
}
```

Empty → `{ "success": true, "banners": [], "count": 0 }` (clients fall back to a bundled hero).

---

### 2. List all banners (admin)

```
GET /api/v1/banners/admin/all
Authorization: Bearer <admin token>
```

Same shape as above but includes **inactive** banners and banners **outside their window** — for the management table. Returned in `sort_order ASC` order.

---

### 3. Create a banner (admin)

```
POST /api/v1/banners
Authorization: Bearer <admin token>
Content-Type: application/json

{
  "image_url": "https://res.cloudinary.com/<cloud>/image/upload/banners/abc.jpg",
  "title": "New Year Sale",
  "link_url": "https://lubist.app/sale",
  "sort_order": 5,
  "is_active": true,
  "starts_at": "2026-12-31T00:00:00Z",
  "ends_at": "2027-01-07T00:00:00Z"
}
```

Only `image_url` is required. `starts_at`/`ends_at` are optional; if both are set, `ends_at` must be after `starts_at`.

**200 OK**
```json
{
  "success": true,
  "message": "Banner created successfully",
  "banner": { "id": "...", "image_url": "...", "title": "New Year Sale", "...": "..." }
}
```

---

### 4. Reorder banners (admin)

```
PUT /api/v1/banners/reorder
Authorization: Bearer <admin token>
Content-Type: application/json

{
  "orders": [
    { "id": "b1...", "sort_order": 0 },
    { "id": "b2...", "sort_order": 1 },
    { "id": "b3...", "sort_order": 2 }
  ]
}
```

Send the **full ordered set**. Each entry updates that banner's `sort_order`. Duplicate ids are rejected (`422`); ids that no longer exist are skipped rather than failing the batch.

**200 OK** → `{ "success": true, "banners": [ ...updated rows... ], "count": 3 }`

---

### 5. Update a banner (admin)

```
PUT /api/v1/banners/{banner_id}
Authorization: Bearer <admin token>
Content-Type: application/json

{ "title": "Updated caption", "is_active": false }
```

Only provided fields are changed.

**200 OK** → `{ "success": true, "message": "Banner updated successfully", "banner": { "...": "..." } }`

**404 Not Found** → `{ "detail": "Banner not found: {banner_id}" }`

---

### 6. Delete a banner (admin)

```
DELETE /api/v1/banners/{banner_id}          # soft-delete (is_active = false)
DELETE /api/v1/banners/{banner_id}?hard=true # permanent
```

**200 OK** (soft) → `{ "success": true, "message": "Banner deactivated", "banner_id": "..." }`
**200 OK** (hard) → `{ "success": true, "message": "Banner permanently deleted", "banner_id": "..." }`

---

### 7. Upload a banner image

```
POST /api/v1/upload/cloudinary-banner-image
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: <image>   (JPG / PNG / WebP, ≤ 5MB)
```

Uploads to Cloudinary (folder `banners`) and returns the URL to store in `image_url`.

**200 OK**
```json
{ "success": true, "url": "https://res.cloudinary.com/.../banners/abc.jpg", "path": "https://res.cloudinary.com/.../banners/abc.jpg", "filename": "promo.jpg" }
```

---

## Error / status reference

| Status | When |
|--------|------|
| `200` | Success (incl. idempotent soft/hard delete) |
| `401` / `403` | Missing / invalid / expired token, or non-admin calling a write endpoint |
| `404` | `PUT`/`DELETE` with an unknown `banner_id` |
| `422` | Malformed body (missing `image_url`, `ends_at <= starts_at`, duplicate reorder ids) |
| `500` | Unexpected DB / server error (e.g. table not migrated) |

---

## Backend source

| Layer | Location |
|-------|----------|
| Routes | `app/api/banners.py` → `list_banners`, `admin_list_all_banners`, `create_banner`, `reorder_banners`, `update_banner`, `delete_banner` |
| Upload route | `app/api/upload.py` → `upload_cloudinary_banner_image` |
| Service | `app/services/banner_service.py` → `BannerService` |
| Request schemas | `app/schemas/request/banner.py` → `BannerCreate`, `BannerUpdate`, `BannerReorder`, `BannerOrderItem` |
| Response schemas | `app/schemas/response/banner.py` → `BannerResponse`, `BannerListResponse`, `BannerOperationResponse`, `BannerDeleteResponse` |
| Migration | `supabase/migrations/20260614000000_create_banners_table.sql` |
| Tests | `tests/test_banner_mocked.py` (15 tests) |

---

## Admin panel reference (already wired)

`salon-admin-panel` (`src/services/api/bannerApi.js`, RTK Query) + page `src/pages/Banners.jsx`:

- `useGetAllBannersQuery()` → `GET /banners/admin/all`
- `useCreateBannerMutation()` → `POST /banners`
- `useUpdateBannerMutation({ bannerId, data })` → `PUT /banners/{id}`
- `useReorderBannersMutation(orders)` → `PUT /banners/reorder`
- `useDeleteBannerMutation({ bannerId, hard })` → `DELETE /banners/{id}`
- `useUploadBannerImageMutation(file)` → `POST /upload/cloudinary-banner-image`

UI: an ordered list with thumbnails, **move up / down** to reorder, toggle active,
and a create/edit modal with single-image upload + optional tap link. Nav item:
**Home Banners** (`/banners`). Tests: `src/services/api/bannerApi.test.jsx` (7 tests).

---

## Mobile reference (already wired)

`lubist_mobile_application` (`src/services/api/hooks/useBannersAPI.ts`):

- `useBanners()` → `GET /banners` (public, 5-min `staleTime`)
- `bannerImageUri(banner)` → image URL rewritten for the dev LAN host

UI: `ClientHomeScreen.tsx` → `HeroCarousel` renders a **swipeable, paged** carousel
with live pagination dots; banners with a `link_url` are tappable (http(s) links open
via `Linking`). Falls back to the bundled `hero.png` while loading or when empty, so
the screen never looks broken. The "active?" / window filtering is done server-side,
so the client just renders whatever `GET /banners` returns.

## Web-app (`salon-management-app`) reference (now wired)

`salon-management-app` (`src/services/api/bannerApi.js`, RTK Query):

- `useGetBannersQuery()` → `GET /banners` (public, no auth, 5-min `keepUnusedDataFor`)
- Registered in `src/store/index.js` (reducer + middleware + serializable-check ignore).

UI: `src/pages/public/Home.jsx` → `HeroSection` renders the admin-managed banners
(ordered by `sort_order` as returned) as a crossfading, auto-rotating carousel with
prev/next arrows and dot indicators. Banners with a `link_url` are clickable —
`http(s)` links open in a new tab, anything else is treated as an in-app route via
React Router. When the feed is empty or still loading, it falls back to the bundled
hero images/video, so the home page never looks broken. Tests:
`src/services/api/bannerApi.test.jsx` (3 tests).

- [x] `bannerApi` with `GET /api/v1/banners` — **no auth**.
- [x] Hero carousel on the home page driven by `banners` (ordered as returned).
- [x] Banners with a `link_url` are clickable (external new-tab or in-app route).
- [x] Falls back to the bundled hero when the list is empty / loading.
