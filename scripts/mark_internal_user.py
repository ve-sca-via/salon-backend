"""
Mark an admin account as internal staff (or revoke it).

An internal account keeps user_role = 'admin' and gains profiles.is_internal,
which does two things and nothing else:

  * it bypasses feature entitlement gates, so staff can use a feature that is
    still at status='internal' in production before the client has bought it;
  * it hides the account from the client's Users list.

It grants NO role permissions of its own — an internal user still has to pass
require_admin exactly like any other admin.

Run this once against production for your own account after applying
supabase/migrations/20260821000000_create_feature_flags.sql. Nothing else in
the system sets this flag; there is deliberately no UI for it, because a UI
would have to live somewhere the client could find.

Usage (venv active, .env pointing at the target environment):
    python scripts/mark_internal_user.py --email dev@youragency.com
    python scripts/mark_internal_user.py --email dev@youragency.com --revoke
    python scripts/mark_internal_user.py --list
"""

import argparse
import os
import sys

# Allow `from app...` imports when run as `python scripts/mark_internal_user.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client

from app.core.config import settings


def list_internal(db) -> None:
    """Show every account currently flagged internal."""
    rows = (
        db.table("profiles")
        .select("email, full_name, user_role, is_internal")
        .eq("is_internal", True)
        .execute()
        .data
        or []
    )

    if not rows:
        print("No internal accounts. Feature gates apply to everyone.")
        return

    print(f"Internal accounts ({len(rows)}):")
    for row in rows:
        print(f"  - {row['email']:<40} role={row['user_role']}")


def set_internal(db, email: str, value: bool) -> None:
    existing = (
        db.table("profiles")
        .select("id, email, user_role, is_internal")
        .eq("email", email)
        .maybe_single()
        .execute()
    )
    profile = getattr(existing, "data", None)

    if not profile:
        sys.exit(f"No profile found for {email}")

    if profile["user_role"] != "admin":
        # is_internal on a non-admin is not dangerous, just useless: every
        # gated route sits behind an admin role check first.
        print(
            f"WARNING: {email} has role '{profile['user_role']}', not 'admin'. "
            "The flag will have no effect on admin-panel features."
        )

    if bool(profile.get("is_internal")) == value:
        print(f"{email} is already is_internal={value}. Nothing to do.")
        return

    db.table("profiles").update({"is_internal": value}).eq("id", profile["id"]).execute()

    if value:
        print(f"{email} is now INTERNAL — sees features at status='internal'.")
    else:
        print(f"{email} is no longer internal — sees only entitled features.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", help="Account to flag")
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Clear the flag instead of setting it",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="List internal accounts and exit",
    )
    args = parser.parse_args()

    # Service-role client, same as the other seed scripts: this writes a
    # column no API endpoint exposes.
    db = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    if args.list_only:
        list_internal(db)
        return

    if not args.email:
        parser.error("--email is required unless --list is given")

    set_internal(db, args.email.strip().lower(), not args.revoke)
    print()
    list_internal(db)


if __name__ == "__main__":
    main()
