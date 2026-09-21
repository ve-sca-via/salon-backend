"""
Diagnose the "User not allowed" error on admin user creation (RM/customer).

GoTrue's admin API (/auth/v1/admin/users) rejects any bearer JWT whose `role`
claim is not `service_role` with exactly that message. Because this project
runs with RLS disabled (see migrations/20251123000000_...sql), an anon key
sitting in the SUPABASE_SERVICE_ROLE_KEY slot still reads and writes every
table normally - so the app looks healthy and ONLY admin auth operations fail.
That makes the wrong key very easy to miss.

This prints the `role` claim of whichever key the environment actually holds,
checks that the key's project ref matches SUPABASE_URL, and makes a live
read-only admin API call. It never prints the key itself.

Run it where the answer matters - inside the deployed container (DigitalOcean
console), so you see what the RUNNING process loaded, not what your laptop has:

    python scripts/check_service_role_key.py

Or point it at a specific dotenv file locally:

    python scripts/check_service_role_key.py --env-file .env.production
"""

import argparse
import base64
import json
import os
import sys
from urllib.parse import urlparse

import requests


def decode_jwt_payload(token: str) -> dict:
    """Decode a JWT payload without verifying the signature."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("not a JWT (expected 3 dot-separated segments)")
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)  # restore base64 padding
    return json.loads(base64.urlsafe_b64decode(payload))


def describe_key(label: str, token: str, expected_role: str, supabase_url: str) -> bool:
    """Print what a key actually is. Returns True if it looks correct."""
    print(f"\n{label}:")
    print(f"  length: {len(token)} chars")

    if token != token.strip():
        print("  WARNING: value has leading/trailing whitespace - strip it in the env var")

    try:
        claims = decode_jwt_payload(token.strip())
    except Exception as e:
        print(f"  ERROR: could not decode as JWT: {e}")
        print("  (If this is a new-style key like sb_secret_..., it is not a JWT;")
        print("   this project's code expects the legacy JWT-format keys.)")
        return False

    role = claims.get("role")
    ref = claims.get("ref")
    print(f"  role claim: {role}")
    print(f"  project ref: {ref}")

    ok = True

    if role != expected_role:
        print(f"  >>> MISMATCH: expected role '{expected_role}', got '{role}'")
        if role == "anon":
            print("  >>> This is the ANON key sitting in the service-role slot.")
            print("  >>> This is the cause of 'User not allowed' on admin user creation.")
            print("  >>> Fix: copy the service_role key from Supabase Dashboard ->")
            print("  >>>      Project Settings -> API -> service_role, into this env var,")
            print("  >>>      then redeploy.")
        ok = False

    if ref and supabase_url:
        host = urlparse(supabase_url).hostname or ""
        if not host.startswith(f"{ref}."):
            print(f"  >>> MISMATCH: key belongs to project '{ref}' but SUPABASE_URL is '{host}'")
            print("  >>> The key and the URL point at DIFFERENT Supabase projects.")
            ok = False

    return ok


def live_admin_check(supabase_url: str, service_key: str) -> None:
    """Make the same admin API call the app makes, read-only."""
    print("\nLive admin API check (GET /auth/v1/admin/users?per_page=1):")
    try:
        response = requests.get(
            f"{supabase_url.rstrip('/')}/auth/v1/admin/users",
            params={"page": 1, "per_page": 1},
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
            },
            timeout=15,
        )
    except Exception as e:
        print(f"  request failed: {e}")
        return

    print(f"  status: {response.status_code}")
    if response.status_code == 200:
        print("  OK - this key CAN perform admin operations.")
    else:
        body = response.text[:300]
        print(f"  FAILED - body: {body}")
        if "not allowed" in body.lower():
            print("  >>> This is the exact failure the admin panel hits.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--env-file",
        default=None,
        help="Read values from this dotenv file instead of the live process environment",
    )
    args = parser.parse_args()

    if args.env_file:
        from dotenv import dotenv_values

        values = dotenv_values(args.env_file)
        source = f"dotenv file {args.env_file}"
    else:
        values = os.environ
        source = "live process environment"

    print(f"Reading from: {source}")

    supabase_url = (values.get("SUPABASE_URL") or "").strip()
    service_key = (values.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    anon_key = (values.get("SUPABASE_ANON_KEY") or "").strip()

    if not supabase_url:
        sys.exit("SUPABASE_URL is not set.")
    if not service_key:
        sys.exit("SUPABASE_SERVICE_ROLE_KEY is not set.")

    print(f"SUPABASE_URL: {supabase_url}")

    ok = describe_key("SUPABASE_SERVICE_ROLE_KEY", service_key, "service_role", supabase_url)

    if anon_key:
        describe_key("SUPABASE_ANON_KEY", anon_key, "anon", supabase_url)
        if anon_key == service_key:
            print("\n>>> SUPABASE_ANON_KEY and SUPABASE_SERVICE_ROLE_KEY hold the SAME value.")
            ok = False

    live_admin_check(supabase_url, service_key)

    print()
    if ok:
        print("Service-role key looks correct.")
    else:
        print("Service-role key is WRONG - see the markers above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
