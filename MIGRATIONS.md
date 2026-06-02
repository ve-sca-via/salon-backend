# Database Migrations

How we manage Supabase schema changes. Read this before touching the DB.

## The only workflow

```powershell
# 1. Create a tracked migration file (auto-timestamped)
supabase migration new descriptive_name

# 2. Write your SQL in the new file under supabase/migrations/

# 3. Apply it to the remote DB
supabase db push
```

## Three rules

1. **Never run CREATE / ALTER / DROP in the dashboard SQL editor.** That is what
   causes local/remote drift. The editor is fine for SELECTs and inspecting data.
2. **One logical change = one new migration file.** Never edit a migration that
   has already been pushed — always add a new one.
3. After pulling teammate changes or returning from a break, run `supabase db push`
   to get current.

## Check sync status anytime

```powershell
supabase migration list --linked
```

Every row should show matching **Local** and **Remote** columns.

## Fix: "Local and Remote don't match" / push fails

This means the tracking table (`supabase_migrations.schema_migrations`) disagrees
with your files. It does NOT mean your data is broken.

**If the schema already exists on remote** (app is live, tables are there) but the
Remote column is blank for some migrations — mark them as already applied. This
runs ZERO SQL against your tables; it only fixes bookkeeping:

```powershell
supabase migration repair --status applied <version1> <version2> ...
```

Generate the version list (all except ones already showing on Remote):

```powershell
# lists every version in the migrations folder
ls supabase/migrations/*.sql | ForEach-Object { ($_.Name -split '_')[0] }
```

Then re-check with `supabase migration list --linked` — all rows should match.

**If a migration genuinely never ran on remote**, do NOT mark it applied (that
permanently skips it). Run `supabase db push` so it actually executes.

> Never run `supabase db reset` against remote — it wipes data.
