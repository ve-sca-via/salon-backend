"""
Email configuration checker.

Verifies the Resend setup end to end: reports what the app has loaded, then
optionally sends a real test email and explains any failure in plain terms.

Usage:
    python scripts/check_email.py                 # config check + send to ADMIN_EMAIL
    python scripts/check_email.py you@gmail.com   # send to a specific address
    python scripts/check_email.py --dry-run       # config check only, send nothing

Run it from the backend root so the .env is picked up.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services.email import EmailService  # noqa: E402


# Maps the failure to the thing you actually have to go fix.
HINTS = {
    422: (
        "EMAIL_FROM is not on a domain verified in Resend.\n"
        "     Resend -> Domains: the domain of "
        f"'{settings.EMAIL_FROM}' must show 'Verified'."
    ),
    401: "RESEND_API_KEY is invalid or revoked. Generate a new one in Resend -> API Keys.",
    403: "RESEND_API_KEY lacks sending permission, or is for a different Resend account.",
    429: "Resend rate limit hit. The app retries these automatically; not a config problem.",
}


def check_config() -> bool:
    """Print what the app loaded. Returns False if something is clearly wrong."""
    print("=" * 68)
    print("EMAIL CONFIGURATION")
    print("=" * 68)

    ok = True

    if settings.RESEND_API_KEY:
        key = settings.RESEND_API_KEY
        print(f"  RESEND_API_KEY   : set ({key[:6]}...{key[-4:]}, {len(key)} chars)")
        if not key.startswith("re_"):
            print("                     WARNING: Resend keys normally start with 're_'")
    else:
        print("  RESEND_API_KEY   : MISSING -- sending is disabled")
        ok = False

    print(f"  EMAIL_FROM       : {settings.EMAIL_FROM}")
    print(f"  EMAIL_FROM_NAME  : {settings.EMAIL_FROM_NAME}")
    print(f"  ADMIN_EMAIL      : {settings.ADMIN_EMAIL}")
    print(f"  ADMIN_PANEL_URL  : {settings.ADMIN_PANEL_URL}")
    print(f"  ENVIRONMENT      : {settings.ENVIRONMENT}")

    # Cheap sanity checks that catch the usual copy-paste mistakes.
    if "@" not in settings.EMAIL_FROM:
        print("\n  ERROR: EMAIL_FROM is not an email address.")
        ok = False
    if settings.ADMIN_EMAIL and "@" not in settings.ADMIN_EMAIL:
        print("\n  ERROR: ADMIN_EMAIL is not an email address.")
        ok = False
    for placeholder in ("example.com", "salonplatform.com", "test.local"):
        if settings.ADMIN_EMAIL.endswith(placeholder):
            print(
                f"\n  WARNING: ADMIN_EMAIL still points at the placeholder "
                f"'{placeholder}'. Admin notifications will go nowhere."
            )
        if settings.EMAIL_FROM.endswith(placeholder):
            print(
                f"\n  WARNING: EMAIL_FROM still points at the placeholder "
                f"'{placeholder}'. Resend will reject every send with 422."
            )
            ok = False

    print()
    return ok


async def send_test(to_email: str) -> bool:
    print("=" * 68)
    print(f"SENDING TEST EMAIL -> {to_email}")
    print("=" * 68)

    service = EmailService()
    payload = {
        "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>",
        "to": [to_email],
        "subject": "Lubist email test",
        "html": (
            "<h2>Email is working</h2>"
            "<p>This test was sent by <code>scripts/check_email.py</code>.</p>"
            f"<p>Environment: <strong>{settings.ENVIRONMENT}</strong><br>"
            f"From: <strong>{settings.EMAIL_FROM}</strong></p>"
        ),
    }

    # Call the transport directly so we see the raw provider result rather than
    # the retry loop's summarised boolean.
    success, error, permanent = await service._deliver(payload, to_email, "Lubist email test")

    print()
    if success:
        print("  RESULT: SENT")
        print(f"  Check {to_email} (including spam), and Resend -> Emails for delivery status.")
        return True

    print("  RESULT: FAILED")
    print(f"  Error: {error}")
    print(f"  Retryable: {'no - permanent' if permanent else 'yes'}")

    # Surface the actionable hint for the status code we got back.
    for status_code, hint in HINTS.items():
        if error and f"HTTP {status_code}" in error:
            print(f"\n  FIX: {hint}")
            break
    else:
        if error and "RESEND_API_KEY" in error:
            print("\n  FIX: Set RESEND_API_KEY in your .env (or deployment env vars).")

    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the Resend email setup.")
    parser.add_argument(
        "to", nargs="?", default=None,
        help="Recipient for the test email (default: ADMIN_EMAIL)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Only print the configuration; send nothing.",
    )
    args = parser.parse_args()

    config_ok = check_config()

    if args.dry_run:
        return 0 if config_ok else 1

    if not settings.RESEND_API_KEY:
        print("Cannot send a test email without RESEND_API_KEY. Set it and re-run.")
        return 1

    to_email = args.to or settings.ADMIN_EMAIL
    return 0 if asyncio.run(send_test(to_email)) else 1


if __name__ == "__main__":
    sys.exit(main())
