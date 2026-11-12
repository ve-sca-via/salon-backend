"""End-to-end API flow tests that run against a DEPLOYED environment (staging).

Separate from the unit/integration tiers: never imports `app`, talks to the
server over HTTP only, and seeds/cleans data with a Supabase service-role
client. See docs/E2E_TESTING.md.
"""
