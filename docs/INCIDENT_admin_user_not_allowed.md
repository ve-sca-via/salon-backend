# Incident: Admin "User not allowed" when creating users (RM/customer)

Creating a Relationship Manager (or customer) from the admin panel fails. The panel
shows "Failed to create authentication account"; the backend logs show GoTrue's
`User not allowed` (HTTP 403) from `POST /auth/v1/admin/users`.

> **This document was rewritten on 2026-09-21.** The original version blamed stale
> process/config state and prescribed a restart/redeploy. **That conclusion was wrong**
> and cost real debugging time — see "Disproven theories" below. The actual cause is a
> bug in the pinned `supabase` library.

## Root cause

`supabase==2.0.3` has a mutable-default-argument bug in `Client.__init__`:

```python
def __init__(self, supabase_url, supabase_key,
             options: ClientOptions = ClientOptions()):   # evaluated ONCE at import
    ...
    options.headers.update(self._get_auth_headers())      # mutates that ONE shared dict
    self.options = options
```

Every `create_client()` call that does not pass an explicit `options` receives **the same
`ClientOptions` instance**, and then mutates its `headers` dict with its own key. The
GoTrue client keeps a reference to that dict and hands the same reference to
`client.auth.admin`, so the headers are shared across every client in the process.

Our `app/core/database.py` creates two clients from that shared default:

1. `get_db()` → service-role client. Shared headers now carry the **service_role** key.
2. `get_auth_client()` → anon client. The shared dict is **overwritten with the anon key**.

From that moment, every `db.auth.admin.*` call sends the anon key, and GoTrue rejects it
with `User not allowed`.

Verified directly against the deployed configuration (decoding only the `role` claim):

```
WITH FIX    -> db client admin calls send role: service_role
WITHOUT FIX -> db client admin calls send role: anon
```

### Why restart/redeploy never fixed it

It is deterministic, not drift. An admin **must log in before they can create an RM**, and
login is what constructs the anon client. So a freshly started process is re-broken within
seconds, every time.

The apparent intermittency has a separate cause: `get_storage_client()` builds another
service-role client, which flips the shared headers *back* to `service_role`. So whether
admin creation works depends on which client was constructed most recently — which is why
it occasionally appeared to "fix itself" after a deploy.

### Why only admin user creation broke

RLS is disabled project-wide (`supabase/migrations/20251123000000_disable_rls_for_service_role_architecture.sql`),
so PostgREST table reads/writes succeed with either key. GoTrue's admin API is the only
thing in the stack that checks the JWT's `role` claim. That masking is what makes this
class of failure so misleading: the app looks completely healthy except for one feature.

## The fix

`app/core/database.py` now passes a fresh `ClientOptions()` to every `create_client()`
call, so each client owns its headers dict (`ClientOptions.headers` uses
`field(default_factory=DEFAULT_HEADERS.copy)`).

## Upstream status — do NOT file a bug

Already fixed upstream. **No bug report to Supabase is needed.**

| supabase-py | mutable default | mutates caller's headers |
| --- | --- | --- |
| 2.0.3 (pinned here) – 2.4.0 | **yes — buggy** | yes |
| 2.5.0 | fixed (`options=None`) | yes |
| 2.15.3+ | fixed | no |
| 2.31.0 (latest as of 2026-09) | fixed | no |

The real remediation is upgrading off 2.0.3; `2.5.0` is the minimum that removes the bug.
**When the upgrade happens, delete the `_isolated_options()` workaround** in
`app/core/database.py` — and note that later versions rename the class to `SyncClient`
and move `ClientOptions`, so the import there needs checking.

## Disproven theories (do not re-chase these)

- **Wrong/anon key in the DigitalOcean env var.** Decoding the key the running process
  actually holds shows `role: service_role`, with a `ref` matching `SUPABASE_URL`, not
  expired. The key was never the problem.
- **Stale process/config state fixed by redeploy** (the original conclusion of this doc).
  Disproven: the failure reproduces deterministically on every fresh process.
- **`vendor_service.py`'s old `self.db.auth.sign_up()` fallback poisoning the shared
  client.** Plausible-sounding but false: `gotrue==1.3.1` never mutates `_headers` on
  `sign_up`/`sign_in`, and admin calls only override `Authorization` when an explicit
  `jwt=` is passed. Verified in the installed library source. (That fallback was removed
  anyway, for unrelated reasons — it masked real errors and created vendors without
  email confirmation.)

## How to diagnose this next time

Check what key the **running** process actually sends, not what the dashboard shows.
Inside the deployed container:

```
python scripts/check_service_role_key.py
```

or, without deploying anything, a one-liner in the platform console:

```
python -c "import os,base64,json;t=os.environ['SUPABASE_SERVICE_ROLE_KEY'].strip().split('.')[1];print(json.loads(base64.urlsafe_b64decode(t+'='*(-len(t)%4))))"
```

Two process lessons from this incident:

- **Check what is deployed before diagnosing.** Production runs `main`; the local `main`
  and `staging` refs were seven months stale, which produced a confidently wrong analysis
  of code that was not running anywhere. The remote is `ve-sca-via`, not `origin`.
- **Verify the mechanism, don't reason about it.** Both wrong theories survived because
  they sounded plausible. Reading the installed library source and running a five-line
  reproduction settled it in minutes.
