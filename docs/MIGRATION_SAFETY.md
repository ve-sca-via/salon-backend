# Migration Safety — How to change the schema without breaking production

Your breakages come from one root cause: **a schema change that the
currently-running code (and old mobile-app installs) can't tolerate**, deployed
in a single step. The fix is a discipline, not a tool: **expand / migrate /
contract**. Never make a destructive change in the same deploy that introduces
the feature needing it.

> Remember: mobile users run *old* code for days or weeks after you ship. The
> database must stay backward-compatible with at least the previous app version.

---

## The golden rule

**A migration that ships with a feature may only ADD. Anything that DROPs,
renames, narrows, or tightens must be a SEPARATE, LATER migration — after the
new code is fully deployed and proven.**

Safe to ship together with code (additive / backward-compatible):
- `ADD COLUMN ... NULL` (or with a default)
- `CREATE TABLE`, `CREATE INDEX` (use `CONCURRENTLY` on big tables)
- Adding a new enum value
- Adding a new nullable FK

Never ship in the same deploy as the code that needs it (breaking):
- `DROP COLUMN`, `DROP TABLE`
- `RENAME COLUMN` / `RENAME TABLE`  ← old code still queries the old name
- `ALTER COLUMN ... TYPE` that isn't a widening
- `SET NOT NULL` on an existing column
- Adding a `UNIQUE` / `CHECK` constraint to existing data
- Removing an enum value

---

## Expand / Migrate / Contract — the pattern for every breaking change

### Example: rename `profiles.full_name` → `profiles.display_name`

**Deploy 1 — Expand (additive only):**
1. Migration: `ADD COLUMN display_name text;` then backfill
   `UPDATE profiles SET display_name = full_name;`
2. Code: write to **both** columns; read from `display_name`, falling back to
   `full_name` if null. Old code (still reading `full_name`) keeps working.

**Deploy 2 — Contract (only after Deploy 1 is live & stable):**
3. Code: stop referencing `full_name` entirely.
4. Migration: `ALTER TABLE profiles DROP COLUMN full_name;`

A `DROP`/`RENAME` and the feature that needs it should be in **different PRs,
shipped on different days.**

### Other common cases
- **Making a column required:** add it nullable → backfill → start writing it in
  code → *later* migration `SET NOT NULL`.
- **Splitting/changing a type:** add the new column → dual-write → migrate reads
  → drop the old one in a later deploy.
- **New unique constraint:** add it `NOT VALID` first, fix offending rows, then
  `VALIDATE CONSTRAINT`.

---

## Pre-merge checklist (put this in the PR description)

- [ ] Does this migration only **ADD**? If it drops/renames/tightens, is the
      destructive part split into a **separate, later** migration?
- [ ] Will the **currently-deployed** backend keep working against the new
      schema? (i.e. old code + new DB)
- [ ] Will the **previous mobile app version** keep working? (old client + new DB)
- [ ] New columns are `NULL` or have a server `DEFAULT` (no `NOT NULL` without a
      backfill in the same migration).
- [ ] Big-table index built with `CREATE INDEX CONCURRENTLY`.
- [ ] Integration suite passes — CI applies this migration to a fresh DB and
      runs the real flows against it (see `.github/workflows/ci.yml`).

## What CI already enforces for you

The `integration` job runs `supabase start`, which **applies every file in
`supabase/migrations/` to a clean database**, then runs the integration tests
(`tests/test_integration_auth.py`, …) against it. So:
- A migration that fails to apply ⇒ red PR.
- A migration that breaks a flow the tests cover ⇒ red PR.

The more flows you add to the integration suite, the more of your "test 100
things by hand" pass becomes automatic backward-compatibility coverage.

## Local dry-run before you push

```bash
# Re-apply ALL migrations from scratch on a clean local DB — catches ordering
# and "works on my prod data but not fresh" failures.
supabase db reset

# Run the real flows against it
python -m pytest tests/ -m integration
```

## Production rollout (Supabase CLI)

```bash
supabase db push   # apply pending migrations to the linked project
```
Deploy **Expand** migrations + code first, confirm healthy, and only then open
the follow-up PR for the **Contract** migration. Never push a destructive
migration ahead of the code that stops using the old shape.
