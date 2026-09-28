"""
One owner, one account: the duplicate check that guards salon onboarding.

Why this exists
---------------
`complete_registration` finishes onboarding by calling
``auth.admin.create_user(email=owner_email, ...)``. That call fails if the email
already belongs to *any* Supabase user, and the platform is one vendor to one
salon (``VendorService.get_vendor_salon`` reads ``data[0]``), so a second salon
under one email was never going to work.

Nothing checked for it, though. Only ``profiles.email`` is UNIQUE - there is no
constraint on ``vendor_join_requests.owner_email``, ``salons.email`` or
``salons.phone`` - so an RM could submit any number of requests under one email
(or under their own RM login's email), an admin could approve them all, and the
collision only surfaced at the very end as an opaque 500 on the vendor's
registration page. Three separate tester reports were this one hole.

The rule
--------
    owner_email  conflicts with any existing account, and with any other
                 draft / pending / approved join request
    owner_phone  conflicts with any other draft / pending / approved join
                 request only

The phone deliberately is not checked against ``profiles``: an owner's number
may legitimately already sit on a customer account (their own, or a family
member's), and the email is the identity that actually breaks registration.
Rejected requests never conflict - they are history, and an RM must be able to
resubmit the same owner after a rejection.

Checked at three points, because a request can be created before this shipped:
submission (``RMService.create_vendor_request`` / ``update_vendor_request``) and
again at approval (``VendorApprovalService.approve_vendor_request``).
"""
import logging
from typing import Any, Dict, List, Optional

from app.utils.phone import phone_lookup_variants

logger = logging.getLogger(__name__)

#: A join request in any of these states has claimed its owner's email.
#: 'rejected' is absent on purpose - see the module docstring.
LIVE_REQUEST_STATUSES = ["draft", "pending", "approved"]

ROLE_LABELS = {
    "admin": "an admin account",
    "relationship_manager": "a relationship manager account",
    "vendor": "a vendor account",
    "regular_buyer": "a business buyer account",
    "customer": "a customer account",
}


def _escape_like(value: str) -> str:
    """Make a value safe for ILIKE: `_` and `%` are wildcards, and `_` is legal in
    an email local part, so an unescaped `john_doe@x.com` would also match
    `johnXdoe@x.com`."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class OwnerConflict:
    """A reason this owner cannot be onboarded, phrased for the person who hit it."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"OwnerConflict(field={self.field!r}, message={self.message!r})"


def find_owner_conflicts(
    db,
    owner_email: Optional[str],
    owner_phone: Optional[str] = None,
    *,
    exclude_request_id: Optional[str] = None,
) -> List[OwnerConflict]:
    """
    Return every reason this owner's email/phone cannot start a new salon.

    Args:
        db: Supabase client.
        owner_email: The email the owner will register and log in with.
        owner_phone: The owner's contact number, if supplied.
        exclude_request_id: The request being edited or approved, so it does not
            conflict with itself.

    Returns:
        A list of conflicts, empty when the owner is clear. Read-only: callers
        decide whether that means a 409, a warning or nothing.
    """
    conflicts: List[OwnerConflict] = []

    if owner_email:
        email = owner_email.strip()

        account = _find_account_by_email(db, email)
        if account:
            role = ROLE_LABELS.get(account.get("user_role"), "an account")
            conflicts.append(OwnerConflict(
                "owner_email",
                f"{email} already has {role} on the platform. "
                "A salon owner needs an email that isn't registered yet - "
                "use the owner's own address, not a staff or test login.",
            ))

        duplicate = _find_request_by_email(db, email, exclude_request_id)
        if duplicate:
            conflicts.append(OwnerConflict(
                "owner_email",
                f"{email} is already used by {_describe(duplicate)}. "
                "One owner email can only ever hold one salon, so this one has "
                "to use a different address.",
            ))

    if owner_phone:
        duplicate = _find_request_by_phone(db, owner_phone, exclude_request_id)
        if duplicate:
            conflicts.append(OwnerConflict(
                "owner_phone",
                f"{owner_phone} is already used by {_describe(duplicate)}. "
                "Use the owner's own number for this salon.",
            ))

    return conflicts


def _describe(request: Dict[str, Any]) -> str:
    """Name the colliding request the way an RM or admin would recognise it."""
    name = request.get("business_name") or "another submission"
    state = request.get("status")
    label = {
        "draft": "a draft",
        "pending": "a submission awaiting approval",
        "approved": "an approved salon",
    }.get(state, "another submission")
    return f'{label}, "{name}"'


def _find_account_by_email(db, email: str) -> Optional[Dict[str, Any]]:
    """Any profile on that email, soft-deleted included: `profiles.email` is
    UNIQUE and the Supabase auth user outlives an anonymised profile, so the
    address is still taken either way."""
    try:
        response = db.table("profiles").select(
            "id, email, user_role, deleted_at"
        ).ilike("email", _escape_like(email)).limit(1).execute()
    except Exception as e:
        # A duplicate check that cannot run must not block onboarding; approval
        # re-runs it, and registration still fails loudly if it was real.
        logger.error(f"Owner email conflict check failed for {email}: {e}")
        return None

    return (response.data or [None])[0]


def _find_request_by_email(
    db, email: str, exclude_request_id: Optional[str]
) -> Optional[Dict[str, Any]]:
    try:
        query = db.table("vendor_join_requests").select(
            "id, business_name, status, owner_email"
        ).ilike("owner_email", _escape_like(email)).in_("status", LIVE_REQUEST_STATUSES)

        if exclude_request_id:
            query = query.neq("id", exclude_request_id)

        response = query.limit(1).execute()
    except Exception as e:
        logger.error(f"Owner email duplicate check failed for {email}: {e}")
        return None

    return (response.data or [None])[0]


def _find_request_by_phone(
    db, phone: str, exclude_request_id: Optional[str]
) -> Optional[Dict[str, Any]]:
    # Numbers are stored as the bare 10 digits the form sends, but older rows
    # hold E.164, so match every shape the same number can be written in.
    variants = phone_lookup_variants(phone) or [phone.strip()]

    try:
        query = db.table("vendor_join_requests").select(
            "id, business_name, status, owner_phone"
        ).in_("owner_phone", variants).in_("status", LIVE_REQUEST_STATUSES)

        if exclude_request_id:
            query = query.neq("id", exclude_request_id)

        response = query.limit(1).execute()
    except Exception as e:
        logger.error(f"Owner phone duplicate check failed for {phone}: {e}")
        return None

    return (response.data or [None])[0]
