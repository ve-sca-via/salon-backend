"""
Shared validation for user-supplied identifiers and enum filters.

Every `id` column in this database is a Postgres `uuid` -- verified against
db-schema/current_schema.sql, where `feature_flags` is the only table keyed by
something else (a text `key`). PostgREST passes a filter value straight through
to Postgres, so an id segment that is not a well-formed UUID makes Postgres
reject the comparison with SQLSTATE 22P02, "invalid input syntax for type
uuid". That is not an HTTPException, so it fell through every service's
`except Exception` and surfaced as a 500 -- on public, unauthenticated routes.
See docs/INCIDENT_salon_id_500.md.

Declaring a parameter with one of the types below moves the check to the
routing layer: FastAPI rejects a malformed id with 422 before any database call
is made. The annotated types deliberately stay `str` rather than `uuid.UUID`,
so services keep receiving exactly the string they always received -- no
`str(...)` conversions and no normalisation anywhere downstream.

Use them for values that reach a `uuid` column. Text keys -- `config_key`,
`feature_flags.key`, blog/product `slug`, Razorpay's `order_*`/`pay_*`
references, MessageCentral's `verification_id` -- are NOT UUIDs and must stay
plain `str`.
"""
import re
from typing import Annotated, Literal, Optional

from fastapi import Path, Query
from pydantic import BeforeValidator, StringConstraints

# The canonical hyphenated form, which is what gen_random_uuid() produces and
# therefore the only form this API ever hands out. Postgres would also accept
# brace-wrapped and unhyphenated input; we deliberately don't, because
# accepting them would mean two spellings of the same id in logs and caches.
# Case-insensitive: Postgres normalises on storage, so an uppercase id echoed
# back by a client still matches.
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

UUID_PATTERN = rf"^{_UUID}$"

# A comma-separated list of ids, as `service_ids` on the public available-slots
# route. Empty members are tolerated -- the route already drops them with
# `if s.strip()`, and a frontend that selects nothing sends `?service_ids=`.
# Non-empty members must be well-formed.
UUID_CSV_PATTERN = rf"^\s*(?:{_UUID})?\s*(?:,\s*(?:{_UUID})?\s*)*$"


def is_uuid(value: object) -> bool:
    """
    True if `value` is a string in the canonical UUID form accepted above.

    For call sites that receive an id from somewhere other than a validated
    request parameter (a webhook body, a stored reference) and need to branch
    rather than reject.
    """
    return isinstance(value, str) and re.fullmatch(_UUID, value) is not None


# --- Route parameter types ---------------------------------------------------
# Annotated aliases are reusable by design: FastAPI reads the Path()/Query()
# instance as immutable metadata when it builds the route, so sharing one
# instance across every route is the documented pattern, not a mutable default.

#: A required path parameter holding a UUID. Malformed -> 422, no DB call.
UUIDPath = Annotated[str, Path(pattern=UUID_PATTERN, description="Resource UUID")]


def uuid_query(description: str, *, required: bool = False) -> Query:
    """
    A UUID-validated query parameter that keeps its own description.

    Used in the classic (non-Annotated) style the API modules already use:

        salon_id: Optional[str] = uuid_query("Filter by salon")
    """
    return Query(... if required else None, pattern=UUID_PATTERN, description=description)


def uuid_csv_query(description: str) -> Query:
    """An optional query parameter holding a comma-separated list of UUIDs."""
    return Query(None, pattern=UUID_CSV_PATTERN, description=description)


# --- Request body field types ------------------------------------------------

#: A required UUID field on a request schema. Malformed -> 422, no DB call.
UUIDStr = Annotated[str, StringConstraints(pattern=UUID_PATTERN)]

def _blank_to_none(value: object) -> object:
    """Treat a blank string as "not provided"."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


#: An optional UUID field that also accepts "" as "not provided".
#:
#: Use this where a form may post an empty select. The vendor service-taxonomy
#: fields are the live example: `category_id=""` together with a typed
#: `category_name` resolves by name and works today, so rejecting "" outright
#: would break a path that currently succeeds. Anything non-blank must still be
#: a well-formed UUID.
BlankableUUIDStr = Annotated[Optional[UUIDStr], BeforeValidator(_blank_to_none)]


# --- Enum-backed filters -----------------------------------------------------
# The same 22P02 fault, on a different column type. Postgres rejects an unknown
# label for an enum column with "invalid input value for enum <type>", which is
# also SQLSTATE 22P02, so an unvalidated ?status= filter passed into
# .eq("status", ...) produced a 500 exactly as a malformed uuid did.
#
# These mirror the CREATE TYPE statements in db-schema/current_schema.sql. They
# are Literals rather than regexes so the allowed values show up in OpenAPI and
# in the generated admin-panel client. Keep them in step with the schema; a
# migration that adds a label has to add it here too.
#
# Each is blank-tolerant: `?status=` means "no filter" to the callers today
# (the services all guard with `if status_filter:`), and that must keep working.

BookingStatus = Literal["pending", "confirmed", "cancelled", "completed", "no_show"]
RequestStatusFilter = Literal["draft", "pending", "approved", "rejected"]
UserRoleFilter = Literal["admin", "relationship_manager", "vendor", "customer", "regular_buyer"]

BookingStatusFilter = Annotated[Optional[BookingStatus], BeforeValidator(_blank_to_none)]
VendorRequestStatusFilter = Annotated[Optional[RequestStatusFilter], BeforeValidator(_blank_to_none)]
UserRoleQueryFilter = Annotated[Optional[UserRoleFilter], BeforeValidator(_blank_to_none)]
