# Incident: Admin "User not allowed" error when creating users (RM/customer)

Creating users from the admin panel (e.g. adding a Relationship Manager) suddenly
started failing with `User not allowed`, both locally and in production, even though
the Supabase `service_role` key was correct and unchanged. The root cause was **stale
process state, not a code or key problem**: our backend creates the Supabase client
once at startup as a process-wide singleton (`app/core/database.py`) and never re-reads
it, so the long-running server kept using an out-of-sync configuration for every admin
(`auth.admin.create_user`) call, while only those privileged operations failed. We
confirmed the current key was valid by decoding its `role` claim (`service_role`) and
making a live admin API call that returned `200`, which proved a freshly-started process
with the same config works fine. Restarting locally and force-redeploying on
DigitalOcean recreated the client with the correct config and immediately fixed it. The
lesson: "works after a restart/redeploy" is the classic signature of cached config/state
drift — and it's a very common operational issue, especially the trap where a
platform-injected environment variable silently overrides the `.env` file. To prevent
recurrence we should (1) treat the platform's environment variables as the single source
of truth in production and redeploy on any change, (2) add a startup check that validates
the service-role key and fails the deploy loudly if it's wrong, and (3) stop swallowing
the underlying GoTrue error so the real cause shows up in logs/alerts instead of a
generic "Failed to create authentication account."
