# Home Carousel / Banner Management — Feature Tracker

**Goal:** Let admins manage the mobile home-screen carousel (hero banners) from the
admin panel — upload an image, set order, enable/disable, delete — with no code
changes or app release. Built on a small, reusable `banners` table so future
content types can follow the same shape without committing to a full CMS.

**Storage:** Cloudinary, reusing the existing `CloudinaryService` (same path as
product images). Banner delivery behaves identically to product images — if
product images render in the storefront, banners do too. No new storage service.

**Architecture parity:** mirrors the existing `products` module end-to-end
(backend service/api/schemas, admin RTK Query slice + page, mobile TanStack hook).

---

## Backend (`g:\vescavia\Projects\backend`)  ✅ done · 15 tests passing

- [x] Migration `supabase/migrations/20260614000000_create_banners_table.sql`
      (table + indexes + updated_at trigger + service-role RLS policy)
- [x] `app/schemas/request/banner.py` — `BannerCreate`, `BannerUpdate`, `BannerReorder`
- [x] `app/schemas/response/banner.py` — `BannerResponse`, `BannerListResponse`,
      `BannerOperationResponse`, `BannerDeleteResponse`
- [x] Register banner schemas in `app/schemas/__init__.py`
- [x] `app/services/banner_service.py` — `BannerService` (list / get / create /
      update / delete / reorder; active-window filtering for the public feed)
- [x] `app/api/banners.py` — router:
      - `GET    /banners`              public, active + in-window, ordered by sort_order
      - `GET    /banners/admin/all`    admin, includes inactive
      - `POST   /banners`             admin, create
      - `PUT    /banners/reorder`     admin, bulk sort_order update
      - `PUT    /banners/{id}`        admin, update
      - `DELETE /banners/{id}`        admin, soft-delete (hard=true to purge)
- [x] Add `POST /upload/cloudinary-banner-image` to `app/api/upload.py`
- [x] Register router in `main.py`
- [x] `tests/test_banner_mocked.py` (FakeSupabase pattern) — **15 passing**

## Admin panel (`g:\vescavia\Projects\salon-admin-panel`)  ✅ done · 7 tests passing

- [x] `src/services/api/bannerApi.js` (RTK Query: list/create/update/delete/reorder/upload)
- [x] Register `bannerApi` in `src/store/store.js` (reducer + middleware + blacklist)
- [x] `src/pages/Banners.jsx` — upload, list (ordered), move up/down, toggle active, delete
- [x] Route `/banners` in `src/App.jsx` + nav item in `src/components/layout/Sidebar.jsx`
- [x] `src/services/api/bannerApi.test.jsx` (MSW) — **7 passing**

## Mobile app (`g:\vescavia\Projects\lubist_mobile_application`)  ✅ done · tsc clean

- [x] `src/services/api/hooks/useBannersAPI.ts` — `useBanners()` (public GET)
- [x] Made `HeroCarousel` in `ClientHomeScreen.tsx` a dynamic, swipeable carousel
      driven by `useBanners()`, falling back to the bundled `hero.png` when empty/loading
- [x] Wired `PaginationDots` to the live banner count + active index;
      banners with a `link_url` are tappable (opens http(s) links via `Linking`)

## Migration not yet applied

The `banners` table migration is written but **not pushed to Supabase yet** —
run your usual migration step (e.g. `supabase db push` / your deploy pipeline)
before manual testing, or the API will 500 on a missing table.

## Manual verification — ✅ passed (2026-06-14)

- [x] Admin: upload a banner → appears in list
- [x] Admin: reorder → order persists after refresh
- [x] Admin: toggle inactive → drops out of mobile feed
- [x] Mobile: home carousel shows admin-managed banners; tapping a banner with a
      `link_url` navigates; empty state falls back to bundled hero
- [x] Backend pytest green · Admin vitest green

---

## Status: ✅ COMPLETE — built, automated tests green, manually verified end-to-end
