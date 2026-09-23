# Partial updates: how edit forms save

## The bug this fixes

Open an edit form, change one field, submit, get an error that names nothing.

The reported case, and the one the regression tests reproduce: **an RM opens
their profile, edits their name, leaves the phone input empty, and saves.**
`PUT /rm/profile` wrote `phone: ""`, `profiles.valid_phone_format`
(`phone IS NULL OR phone ~ '^\+?[1-9]\d{1,14}$'`) rejected it with SQLSTATE
23514, nothing on that route caught it, and the RM got a bare 500. Cover lives
in `tests/test_rm_mocked.py` — the fake `profiles` table there enforces the real
CHECK constraint, so a blank reaching the write fails the test the same way it
failed in production.

Two independent causes, both now closed.

**1. The form posts every field it rendered.** Optional inputs the user never
touched arrive as `""`. An empty string is not a valid `min_length=2` business
name, `^\d{6}$` pincode or `EmailStr`, so the request failed validation on
fields the user had not looked at.

**2. The 422 said only "Validation failed".** Every field name was already in
`errors[]`, but the only client that read that array was the Next.js app. The
admin panel and the legacy SPA read `message`/`detail`, both generic — so the
toast named nothing and the failure looked silent.

A third, quieter fault came out of the same audit: update paths were split
roughly half and half between `model_dump(exclude_none=True)` and
`exclude_unset=True`. Under `exclude_none` a `null` is indistinguishable from an
absent key, so **clearing a field silently did nothing** — blank out a product's
description, hit save, get "updated successfully", and the old text is still
there.

## The contract

For any request body whose schema inherits `PartialUpdateModel`
(`app/schemas/request/base.py`), each key means one of three things:

| Body | Meaning |
| --- | --- |
| key absent | leave the column alone |
| key present, `""` (or whitespace) | leave the column alone — "I didn't touch this" |
| key present, `null` | clear the column (set it to NULL) |

Blank means *untouched* rather than *clear* on purpose: the legacy SPA and the
mobile app post blanks for fields the user never opened, and treating those as a
clear would have wiped stored data the moment this shipped. `null` is the
explicit clear, for clients that send only what actually changed.

Blanks are dropped **before** validation, so they can neither fail a constraint
nor reach the database.

### Pairing at the call site

`PartialUpdateModel` only works paired with `exclude_unset`:

```python
update_data = payload.model_dump(exclude_unset=True)   # correct
update_data = payload.model_dump(exclude_none=True)    # throws away the clear
```

All update paths now use `exclude_unset`. Create paths still use `exclude_none`
deliberately — a create has no "leave it alone" case, and its schema defaults
should survive the dump.

## Clearing a required column

Since `null` now reaches the database, a client can ask to clear a column the
schema requires. Postgres answers SQLSTATE 23502, which
`required_field_cleared_response` turns into a **400 naming the column**
(`error_code: REQUIRED_FIELD`) rather than a generic 500.

## Error shape

A 422 body:

```json
{
  "success": false,
  "message": "pincode: String should match pattern '^\\d{6}$'",
  "errors": [{ "field": "pincode", "message": "String should match pattern '^\\d{6}$'" }],
  "error_code": "VALIDATION_ERROR"
}
```

`message` now names up to three offending fields, then "(and N more fields)".
That matters because it is the field *every* client already reads — the legacy
SPA and the mobile app get a useful toast without any change on their side.
`field` is the leaf path: `body.items.0.price` is reported as `items.price`.

## Adding a new edit-form schema

Inherit `PartialUpdateModel`, not `BaseModel`.

Two tests in `tests/test_partial_updates.py` keep this in place:

- `test_no_put_or_patch_route_takes_an_unguarded_edit_form_body` walks every
  PUT/PATCH route the app actually serves and fails on any all-optional body
  with a text field that does not inherit `PartialUpdateModel`. This is the one
  that matters — it needs no list to be maintained.
- `test_every_edit_form_schema_drops_blanks` checks a named list, which also
  documents where the schemas live.

### Two homes for update schemas

There are **two** `UserProfileUpdate`s and **two** `ServiceUpdate`s in the tree,
and live routes use both:

| Class | Module | Route |
| --- | --- | --- |
| `UserProfileUpdate` | `app/schemas/request/auth.py` | `PUT /auth/me` |
| `UserProfileUpdate` | `app/schemas/user.py` | `PUT /rm/profile` |
| `ServiceUpdate` | `app/schemas/request/vendor.py` | `PUT /vendors/services/{id}` |
| `ServiceUpdate` | `app/schemas/admin.py` | *(unused)* |

`app/schemas/request/` is the newer home; `app/schemas/user.py` and
`app/schemas/admin.py` are the older one. Grepping only the newer package
misses live routes — which is exactly how the first pass at this fix left
`PUT /rm/profile` and the admin service-category forms unguarded. The
route-walking test is there because that mistake is easy to repeat.

## Frontend side

- **`salon_management_next`** — `src/lib/changed-values.ts` narrows a form's
  values to react-hook-form's `dirtyFields`, so an edit posts only what moved.
  `src/lib/api-error.ts` already parses `errors[]` into `fieldErrors` for
  wiring straight into react-hook-form. `edit-profile-form.tsx` is the
  reference usage.
- **`salon-admin-panel`** — `src/utils/apiErrorMessage.js` now reads `errors[]`
  and FastAPI's array `detail`. Every page benefits without being touched,
  because `axiosBaseQuery` funnels all errors through it into `error.data.detail`,
  which is what the pages read.
- **Legacy SPA and mobile** — no code change. They inherit the improved 422
  `message`.
