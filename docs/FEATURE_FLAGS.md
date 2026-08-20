# Feature Flags (Entitlements)

Ship a feature to production before the client has paid for it, use it yourself
in the meantime, and hand it over with a single click when they do.

---

## The problem this solves

Features have to be built before they can be sold. Until now that meant either
sitting on an unmerged branch (which rots) or shipping the feature visibly and
hoping nobody notices it is not on the invoice.

A gated feature is deployed, tested and running in production. Internal staff
use it normally. The client's admin panel has no nav item for it, its routes
render the 404 page, and its API endpoints answer `404 Not Found`. When they
pay, you flip one switch — no deploy, no migration, no branch merge.

---

## The two concepts

They are deliberately separate, and neither is a role.

| | Column | Means |
|---|---|---|
| **Who you are** | `profiles.is_internal` | Internal staff. Bypasses entitlement gates. |
| **What is sold** | `feature_flags.status` | Whether the client is entitled to a feature. |

### Why not a `developer` role

`'admin'` is hardcoded in `require_admin`, in the other role dependencies in
[`app/core/auth.py`](../app/core/auth.py), and in about ten RLS policies in
`supabase/schema.sql`. Adding a `'developer'` value to the `user_role` enum
would lock that account out of every one of them until each was found and
edited — a large, risky refactor to solve a billing problem.

Internal staff stay `user_role = 'admin'` and carry `is_internal` alongside it.
Every existing permission check keeps working untouched.

**`is_internal` grants no permissions of its own.** An internal user still has
to pass `require_admin` like anybody else. It only bypasses *entitlement*
checks, and hides the account from the client's Users list.

### The three statuses

| Status | Client sees | Staff see | Use it when |
|---|---|---|---|
| `internal` | Nothing (404) | Full access | Built, not sold. **Default for new features.** |
| `enabled` | Full access | Full access | They paid. |
| `disabled` | Nothing (404) | Nothing (404) | Something is broken. Kill switch. |

`disabled` stops staff too — a kill switch that staff bypass cannot take a
broken feature out of production.

---

## Gating a new feature

### 1. Register it

Add a row in a migration. New features go in at `internal`:

```sql
INSERT INTO feature_flags (key, name, description, status) VALUES
    ('push_notifications', 'Push Notifications',
     'Admin-composed marketing and transactional push via Expo.',
     'internal')
ON CONFLICT (key) DO NOTHING;
```

`ON CONFLICT DO NOTHING` matters: without it, re-running the migration would
reset a feature the client has already paid for back to `internal`.

### 2. Gate the backend routes

```python
from app.core.auth import RequireFeature, TokenData

require_push = RequireFeature("push_notifications")

@router.post("/campaigns")
async def create_campaign(
    current_user: TokenData = Depends(require_push),
    ...
):
```

`RequireFeature` composes on top of a role dependency (`require_admin` by
default — pass `role_dependency=require_vendor` for other roles). The caller
must hold the role **and** be entitled to the feature.

**Gate every route in the feature, including uploads.** Hiding the list
endpoint while leaving the create endpoint open leaves the feature fully
usable to anyone who reads the JS bundle.

**Leave public output ungated.** The blog's public routes (`GET /blog`,
`/blog/{slug}`, sitemap) are deliberately open while the admin surface is
hidden — posts published by staff still have to render for readers and
crawlers. Only the *management* surface is gated.

### 3. Gate the admin panel

Tag the nav item in [`Sidebar.jsx`](../../salon-admin-panel/src/components/layout/Sidebar.jsx):

```js
{ path: '/push', icon: (...), label: 'Push', feature: 'push_notifications' },
```

Wrap the routes in [`App.jsx`](../../salon-admin-panel/src/App.jsx):

```jsx
<Route path="/push" element={
  <ErrorBoundary fallback="page">
    <FeatureRoute feature="push_notifications"><Push /></FeatureRoute>
  </ErrorBoundary>
} />
```

### 4. Test it

Add cases to `tests/test_feature_flags_mocked.py` following the blog ones: a
client admin gets 404, staff get through, the write routes are gated too.

---

## Selling a feature

1. Log into the admin panel with your internal account.
2. **Feature Flags** in the sidebar (visible only to internal accounts).
3. Click **Enabled** on the feature.

Effective immediately in the worker that handled the request; other workers
pick it up within the 60-second flag cache TTL. `enabled_at` is stamped
automatically, so the table records when the client actually got each feature.

---

## Setting up an internal account

There is no UI for this, deliberately — a UI would have to live somewhere the
client could find. Run once per environment, per account:

```bash
python scripts/mark_internal_user.py --email dev@youragency.com
python scripts/mark_internal_user.py --list
python scripts/mark_internal_user.py --email dev@youragency.com --revoke
```

The account must already exist and should be `user_role = 'admin'`.

---

## What is and is not a security boundary

**The server-side gate is real.** `RequireFeature` runs on every request and
returns 404. `require_internal` guards the flag-management endpoints.

**The frontend gate is cosmetic.** The admin panel is a Vite SPA; its code
ships to the browser either way. Two things limit the exposure:

- gated pages are `lazy()`-loaded, so their chunk is never fetched unless
  someone routes to them;
- the backend 404s regardless, so a forced route renders an empty screen.

Never gate something in the sidebar and forget the backend. The sidebar is a
hint; the API is the wall.

### Why 404 and not 403

A `403` says *"this feature exists and you are not entitled to it"* — exactly
the disclosure the gate exists to prevent, and exactly the conversation you are
trying to postpone. A `404` is indistinguishable from a feature that was never
deployed.

For the same reason `GET /features` **omits** unsold features from the payload
rather than returning them marked unavailable. A client admin can read that
response in devtools.

Role failures are different and still return `403`. Collapsing them into 404
would make genuine permission bugs indistinguishable from hidden features.

### The Feature Flags page gates itself

It is guarded by `is_internal` directly, never by a flag of its own. A
flag-managed flags screen would still have to be visible to somebody, and a
screen listing every feature you have built but not sold — with a toggle next
to each — is considerably worse than just leaving the feature visible.

### Internal accounts are hidden from the Users list

`list_users` filters `is_internal = false` for non-internal callers, search
included. Without it your account sits in the client's user list as an ordinary
admin, which invites questions about who published content they did not
publish.

---

## Files

**Backend**

| File | Role |
|---|---|
| `supabase/migrations/20260821000000_create_feature_flags.sql` | Table, enum, `is_internal`, trigger, seed |
| `app/core/features.py` | Cached flag reads (60s TTL), fail-closed helpers |
| `app/core/auth.py` | `RequireFeature`, `require_internal`, `TokenData.is_internal` |
| `app/services/feature_service.py` | Registry CRUD, cache invalidation |
| `app/api/features.py` | `GET /features`, `GET/PATCH /features/admin/*` |
| `scripts/mark_internal_user.py` | Set/clear `is_internal` |
| `tests/test_feature_flags_mocked.py` | Gate behaviour |

**Admin panel**

| File | Role |
|---|---|
| `src/services/api/featureApi.js` | RTK Query slice |
| `src/hooks/useFeatures.js` | `isEnabled` / `isInternal` |
| `src/components/layout/FeatureRoute.jsx` | Route guard → 404 |
| `src/pages/FeatureFlags.jsx` | Internal switchboard |
| `src/components/layout/Sidebar.jsx` | Nav filtering + "Internal" badge |

---

## Currently gated

| Key | Feature | Status |
|---|---|---|
| `blog` | Blog & SEO | `internal` |

---

## Extending to per-vendor entitlements

`feature_flags` is platform-level: it answers "does the client's admin panel
have this?". If you later sell features to individual salons, add a
`vendor_feature_flags (vendor_id, key, status)` table and a `RequireVendorFeature`
following the same pattern. Nothing here needs rewriting.

Do not build that until you actually sell something per-vendor.
