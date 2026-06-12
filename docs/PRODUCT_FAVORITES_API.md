# Product Favorites API

> **New feature — added 2026-06-13.** Lets a logged-in customer save/un-save
> **products** (the catalog "Saved" / wishlist), mirroring the existing salon
> favorites. Built for the Lubist mobile app's **Saved** tab.
>
> ⚠️ **The salon web admin panel (`salon-management-app`) does NOT have this feature
> yet.** This doc is the contract to build the matching customer-facing UI there so
> web and mobile stay in sync (e.g. a "Saved products" / wishlist page).

---

## Summary

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET`    | `/api/v1/customers/favorites/products`               | Bearer (customer) | List the current customer's saved products |
| `POST`   | `/api/v1/customers/favorites/products`               | Bearer (customer) | Save a product (idempotent) |
| `DELETE` | `/api/v1/customers/favorites/products/{product_id}`  | Bearer (customer) | Remove a saved product |

- **Base URL:** `http://localhost:8000` (dev) · **Global prefix:** `/api/v1`
- **Auth:** standard JWT bearer token (`Authorization: Bearer <access_token>`), same as the rest of `/customers/*`. The user id is taken from the token — never sent in the body.
- These are **separate** from salon favorites (`/customers/favorites`); the two lists are independent and backed by different tables.

---

## Data model

New table `product_favorites` (migration `supabase/migrations/20260613000000_create_product_favorites_table.sql`):

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` PK | `gen_random_uuid()` |
| `user_id` | `uuid` | FK → `auth.users(id)` `ON DELETE CASCADE` |
| `product_id` | `uuid` | FK → `products(id)` `ON DELETE CASCADE` |
| `created_at` | `timestamptz` | default `now()` |

- **Unique constraint** on `(user_id, product_id)` → a product can be saved once per user (the API is idempotent on top of this).
- RLS is **disabled** (backend enforces auth via FastAPI + service-role key), consistent with `favorites`, `cart_items`, etc.

---

## Endpoints

### 1. List saved products

```
GET /api/v1/customers/favorites/products
Authorization: Bearer <token>
```

Returns **full active product rows** (same shape as `GET /products`). Inactive /
soft-deleted products are filtered out, so the list never shows dead items.

**200 OK**
```json
{
  "success": true,
  "favorites": [
    {
      "id": "f3c1...",
      "name": "Hyaluron Moisture Shampoo",
      "slug": "hyaluron-moisture-shampoo",
      "short_description": "Anti-frizz, 1L",
      "price": 1200.0,
      "discount_price": 986.0,
      "discount_percentage": 18.0,
      "brand": "L'Oreal Paris",
      "category": "haircare",
      "image_urls": ["https://..."],
      "weight": "1L",
      "is_active": true,
      "...": "all standard product columns"
    }
  ],
  "count": 1
}
```

Empty list → `{ "success": true, "favorites": [], "count": 0 }`.

---

### 2. Save a product

```
POST /api/v1/customers/favorites/products
Authorization: Bearer <token>
Content-Type: application/json

{ "product_id": "f3c1..." }
```

**Idempotent** — saving an already-saved product returns `200` with the existing row
(no duplicate is created).

**200 OK** (newly added)
```json
{
  "success": true,
  "message": "Added to favorites",
  "favorite": { "id": "...", "user_id": "...", "product_id": "f3c1...", "created_at": "..." }
}
```

**200 OK** (already saved)
```json
{ "success": true, "message": "Product already in favorites", "favorite": { "...": "..." } }
```

**404 Not Found** — product id doesn't exist or is inactive
```json
{ "detail": "Product not found" }
```

---

### 3. Remove a saved product

```
DELETE /api/v1/customers/favorites/products/{product_id}
Authorization: Bearer <token>
```

Idempotent — removing something that isn't saved still returns `200`.

**200 OK**
```json
{ "success": true, "message": "Removed from favorites" }
```

---

## Error / status reference

| Status | When |
|--------|------|
| `200` | Success (incl. idempotent add/remove) |
| `401` / `403` | Missing / invalid / expired bearer token |
| `404` | `POST` with an unknown or inactive `product_id` |
| `422` | Malformed body (e.g. missing `product_id`) |
| `500` | Unexpected DB / server error |

---

## Backend source

| Layer | Location |
|-------|----------|
| Routes | `app/api/customers.py` → `get_favorite_products`, `add_favorite_product`, `remove_favorite_product` |
| Service | `app/services/customer_service.py` → same method names |
| Request schema | `app/schemas/request/customer.py` → `ProductFavoriteCreate` |
| Response schemas | reuse `FavoritesResponse` + `FavoriteOperationResponse` (`app/schemas/response/customer.py`) |
| Migration | `supabase/migrations/20260613000000_create_product_favorites_table.sql` |
| Tests | `tests/test_customer_mocked.py` → "PRODUCT FAVORITES" section (7 tests) |

---

## Mobile reference (already wired)

For parity when building the web UI, here is how the mobile app consumes it
(`lubist_mobile_application/src/services/api/hooks/useProductsAPI.ts`):

- `useFavoriteProducts(enabled)` → `GET` (gated by auth)
- `useAddFavoriteProduct()` → `POST { product_id }`
- `useRemoveFavoriteProduct()` → `DELETE /{product_id}`

UI: a **heart toggle** on the product detail screen saves/un-saves; the **Saved tab**
(`ClientAccountScreen`) renders saved products with an un-save heart. The "is this
product saved?" state is derived by checking membership in the `useFavoriteProducts`
list — there is no per-product `is_favorited` flag on the product payload.

### Suggested web-app (salon-management-app) work to reach parity
- [ ] Add `productFavoritesApi.js` (or extend `productApi.js`) with the 3 calls above.
- [ ] Add a "Saved / Wishlist" page for customers listing `GET .../favorites/products`.
- [ ] Add a save (heart) control on product cards / product detail using `POST` / `DELETE`.
- [ ] Optionally hydrate a `Set` of saved product ids on load to render filled hearts.
