"""
Create a Relationship Manager account directly against the database.

Mirrors app/services/user_service.py UserService.create_user() exactly (same
auth user, profiles row, rm_profiles row with auto-generated employee_id), but
runs as a standalone script with its own fresh Supabase client instead of
going through the running backend process. Use this when the admin panel's
"Create Relationship Manager" flow is broken (e.g. the process-wide
service-role client has been poisoned - see docs/INCIDENT_admin_user_not_allowed.md
and the fix in app/services/vendor_service.py) and you need to create one now.

This deliberately does NOT read this repo's default .env - your local .env may
point at a different Supabase project than production (e.g. local/dev), and
silently creating the RM in the wrong database is worse than an extra flag.
You must say explicitly which project to hit, either with --env-file (a
dotenv file containing SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for the
target environment - e.g. copy the values from the DigitalOcean app's env
vars into a local .env.production and point at that) or with
--supabase-url/--supabase-key directly.

Usage (venv active):
    python scripts/create_rm.py --env-file .env.production --email rm@example.com --full-name "Jane Doe" --age 28 --gender female
    python scripts/create_rm.py --supabase-url https://xxxx.supabase.co --supabase-key eyJ... --email rm@example.com --full-name "Jane Doe" --age 28 --gender female

If --password is omitted, a random one is generated and printed - save it,
it is not shown again. The resolved Supabase URL is printed and must be
confirmed before anything is written, unless --yes is passed.
"""

import argparse
import os
import secrets
import sys

# Allow `from app...` imports when run as `python scripts/create_rm.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import dotenv_values
from supabase import create_client


def generate_password() -> str:
    # Guarantee at least one of each required class, min_length=8 (see UserCreate).
    return f"Rm{secrets.token_urlsafe(8)}!1"


def generate_next_employee_id(db) -> str:
    response = (
        db.table("rm_profiles")
        .select("employee_id")
        .not_.is_("employee_id", "null")
        .execute()
    )

    max_number = 0
    for row in response.data or []:
        emp_id = row.get("employee_id")
        if emp_id and emp_id.startswith("RM"):
            try:
                max_number = max(max_number, int(emp_id[2:]))
            except (ValueError, IndexError):
                continue

    return f"RM{max_number + 1:04d}"


def create_rm(
    db,
    email: str,
    full_name: str,
    password: str,
    age: int,
    gender: str,
    phone: str | None,
) -> None:
    email = email.strip().lower()

    existing = db.table("profiles").select("id").eq("email", email).execute()
    if existing.data:
        sys.exit(f"A user with email {email} already exists.")

    print(f"Creating auth user for {email}...")
    auth_res = db.auth.admin.create_user({
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {
            "full_name": full_name,
            "user_role": "relationship_manager",
        },
    })
    user_id = getattr(getattr(auth_res, "user", None), "id", None)
    if not user_id:
        sys.exit("Auth user creation returned no user ID - aborting.")
    print(f"  auth user created: {user_id}")

    try:
        print("Creating profile row...")
        profile_data = {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "phone": phone or None,
            "user_role": "relationship_manager",
            "is_active": True,
            "age": age,
            "gender": gender,
        }
        profile_res = db.table("profiles").insert(profile_data).execute()
        if not profile_res.data:
            raise Exception("Failed to create profile - no data returned")
        print("  profile created")
    except Exception as e:
        print(f"  profile creation failed: {e}")
        print("  rolling back auth user...")
        db.auth.admin.delete_user(user_id)
        sys.exit("Aborted - auth user rolled back.")

    try:
        print("Creating RM profile row...")
        from datetime import datetime

        employee_id = generate_next_employee_id(db)
        rm_profile_data = {
            "id": user_id,
            "assigned_territories": [],
            "performance_score": 0,
            "employee_id": employee_id,
            "total_salons_added": 0,
            "total_approved_salons": 0,
            "joining_date": datetime.utcnow().date().isoformat(),
            "manager_notes": None,
        }
        rm_res = db.table("rm_profiles").insert(rm_profile_data).execute()
        if not rm_res.data:
            raise Exception("Failed to create RM profile - no data returned")
        print(f"  RM profile created (employee_id={employee_id})")
    except Exception as e:
        # Matches UserService: non-fatal, the user/profile already exist.
        print(f"  WARNING: RM profile creation failed, user still created: {e}")

    print()
    print("Done.")
    print(f"  email:    {email}")
    print(f"  password: {password}")
    print(f"  user_id:  {user_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--age", type=int, required=True, help="18-100")
    parser.add_argument("--gender", required=True, choices=["male", "female", "other"])
    parser.add_argument("--phone", default=None)
    parser.add_argument("--password", default=None, help="Min 8 chars. Random one generated if omitted.")
    parser.add_argument("--env-file", default=None, help="Dotenv file with SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for the target environment")
    parser.add_argument("--supabase-url", default=None, help="Overrides --env-file")
    parser.add_argument("--supabase-key", default=None, help="Service-role key. Overrides --env-file")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()

    if not (18 <= args.age <= 100):
        parser.error("--age must be between 18 and 100")

    password = args.password or generate_password()
    if len(password) < 8:
        parser.error("--password must be at least 8 characters")

    env_values = dotenv_values(args.env_file) if args.env_file else {}
    supabase_url = args.supabase_url or env_values.get("SUPABASE_URL")
    supabase_key = args.supabase_key or env_values.get("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        parser.error(
            "Target Supabase project not specified. Pass --env-file <path> "
            "(with SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY set) or both "
            "--supabase-url and --supabase-key."
        )

    print(f"Target Supabase project: {supabase_url}")
    if not args.yes:
        confirm = input("This will write real data to that project. Continue? [y/N] ").strip().lower()
        if confirm != "y":
            sys.exit("Aborted.")

    db = create_client(supabase_url, supabase_key)

    create_rm(
        db,
        email=args.email,
        full_name=args.full_name,
        password=password,
        age=args.age,
        gender=args.gender,
        phone=args.phone,
    )


if __name__ == "__main__":
    main()
