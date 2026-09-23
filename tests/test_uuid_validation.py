"""
Malformed identifiers must never produce a 5xx.

Regression cover for docs/INCIDENT_salon_id_500.md: a path id that is not a
well-formed UUID reached Postgres, which rejected the comparison with SQLSTATE
22P02, and every service's `except Exception` turned that into a 500 -- on
public, unauthenticated routes.

These are smoke-tier tests. They need no Supabase stack, and that is the point:
validation now happens at the routing layer, before any database call, so the
rejection is observable without one.
"""
import pytest
from fastapi.routing import APIRoute

from app.core.validators import (
    UUID_CSV_PATTERN,
    UUID_PATTERN,
    BlankableUUIDStr,
    is_uuid,
)

VALID_UUID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MALFORMED = "not-a-uuid"

# Path parameters that are deliberately NOT uuids, verified against
# db-schema/current_schema.sql: system_config.config_key, feature_flags.key and
# the blog/product slugs are text columns, and document_type is a label.
# Anything else named like an id must be UUID-validated -- see
# test_every_id_path_param_is_uuid_validated.
TEXT_KEY_PARAMS = {"config_key", "slug", "document_type", "key"}


def _id_routes(app):
    """Every (route, param) pair where the path segment should be a UUID."""
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for param in route.dependant.path_params:
            if param.name in TEXT_KEY_PARAMS:
                continue
            yield route, param


def _has_uuid_pattern(param) -> bool:
    return any(
        getattr(meta, "pattern", None) == UUID_PATTERN
        for meta in (getattr(param.field_info, "metadata", None) or [])
    )


# =====================================================
# THE CONTRACT
# =====================================================

def test_every_id_path_param_is_uuid_validated(app):
    """
    The guard that keeps this fixed.

    A new route declaring `salon_id: str` instead of `salon_id: UUIDPath`
    reopens the incident silently, because nothing else fails until production
    logs a 500. This fails the build instead. If a genuinely non-UUID path
    parameter is ever added, add it to TEXT_KEY_PARAMS above -- deliberately.
    """
    missing = [
        f"{sorted(route.methods)[0]} {route.path} -> {param.name}"
        for route, param in _id_routes(app)
        if not _has_uuid_pattern(param)
    ]
    assert not missing, (
        "path parameters reaching a uuid column without UUID validation "
        "(use app.core.validators.UUIDPath):\n  " + "\n  ".join(missing)
    )


def test_uuid_path_params_stay_strings(app):
    """
    Services are written against `str` ids and index into raw dicts from
    PostgREST. The annotated types keep the value a `str` on purpose; switching
    them to `uuid.UUID` would mean a `str(...)` at every service boundary.
    """
    wrong = [
        f"{route.path} -> {param.name}: {param.type_}"
        for route, param in _id_routes(app)
        if _has_uuid_pattern(param) and param.type_ is not str
    ]
    assert not wrong, wrong


def test_the_route_inventory_is_not_empty(app):
    """Guard against the two tests above passing because they found nothing."""
    assert sum(1 for _ in _id_routes(app)) > 50


# =====================================================
# THE REPORTED BUG
# =====================================================

@pytest.mark.parametrize("suffix", ["", "/related", "/reviews", "/services"])
def test_malformed_salon_id_is_rejected_not_500(client, app, suffix):
    """
    The exact reproduction table from docs/INCIDENT_salon_id_500.md. Each of
    these returned 500 in production; all are public and unauthenticated.
    """
    from app.core.config import settings

    resp = client.get(f"{settings.API_PREFIX}/salons/{MALFORMED}{suffix}")
    assert resp.status_code == 422, resp.text
    assert resp.status_code < 500


def test_malformed_service_ids_query_is_rejected_not_500(client):
    """
    Same bug on a query parameter: `service_ids` is split and passed into
    `.in_("id", ...)` against a uuid column on a public route, with no
    try/except above it, so a malformed member was an uncaught 500.
    """
    from app.core.config import settings

    resp = client.get(
        f"{settings.API_PREFIX}/salons/{VALID_UUID}/available-slots",
        params={"date": "2030-01-01", "service_ids": f"{VALID_UUID},{MALFORMED}"},
    )
    assert resp.status_code == 422, resp.text


def test_empty_service_ids_query_still_accepted(client):
    """
    A frontend that selects no services sends `?service_ids=`. That worked
    before and must keep working -- the validation must not turn an empty list
    into a 422.
    """
    from app.core.config import settings

    resp = client.get(
        f"{settings.API_PREFIX}/salons/{VALID_UUID}/available-slots",
        params={"date": "2030-01-01", "service_ids": ""},
    )
    # No stack here, so this will not be a 200 -- but it must get past
    # validation rather than being rejected on the empty list.
    assert resp.status_code != 422, resp.text


# =====================================================
# THE WHOLE SURFACE
# =====================================================

def test_no_id_route_returns_5xx_for_a_malformed_id(client, app):
    """
    Walk every route that takes an id and call it with a malformed one.

    Authenticated routes answer 401/403 before or instead of validating, which
    is fine -- the property under test is only that nothing answers 5xx. This
    is safe to run against every verb: the id never validates, so no handler
    body runs and nothing is mutated.
    """
    failures = []
    for route, param in _id_routes(app):
        path = route.path
        for other in route.dependant.path_params:
            path = path.replace(
                "{%s}" % other.name,
                MALFORMED if other.name == param.name else "x",
            )
        for method in sorted(route.methods):
            if method in ("HEAD", "OPTIONS"):
                continue
            resp = client.request(method, path)
            if resp.status_code >= 500:
                failures.append(f"{method} {path} -> {resp.status_code}")
    assert not failures, "malformed id produced a 5xx:\n  " + "\n  ".join(failures)


# =====================================================
# THE TYPES
# =====================================================

@pytest.mark.parametrize("value", [
    VALID_UUID,
    VALID_UUID.upper(),                        # Postgres normalises case
    "00000000-0000-0000-0000-000000000000",    # the nil uuid is well-formed
])
def test_is_uuid_accepts(value):
    assert is_uuid(value)


@pytest.mark.parametrize("value", [
    MALFORMED,
    "",
    " ",
    VALID_UUID + "\n",                         # must not slip past the anchors
    VALID_UUID[:-1],
    VALID_UUID.replace("-", ""),               # Postgres would take it; we don't
    "{" + VALID_UUID + "}",
    None,
    12345,
])
def test_is_uuid_rejects(value):
    assert not is_uuid(value)


def test_blank_optional_uuid_is_treated_as_absent():
    """
    `category_id=""` alongside a typed `category_name` resolves by name and
    succeeds today (ServiceTaxonomy.resolve_fields lets a name win over an id),
    so "" must mean "not provided" rather than become a 422.
    """
    from pydantic import BaseModel, ValidationError

    class M(BaseModel):
        category_id: BlankableUUIDStr = None

    assert M(category_id="").category_id is None
    assert M(category_id="   ").category_id is None
    assert M().category_id is None
    assert M(category_id=VALID_UUID).category_id == VALID_UUID
    with pytest.raises(ValidationError):
        M(category_id=MALFORMED)


@pytest.mark.parametrize("value,ok", [
    ("", True),                                 # nothing selected
    (VALID_UUID, True),
    (f"{VALID_UUID},{VALID_UUID}", True),
    (f"{VALID_UUID}, {VALID_UUID}", True),      # the route strips members
    (f"{VALID_UUID},", True),                   # trailing comma was tolerated
    (MALFORMED, False),
    (f"{VALID_UUID},{MALFORMED}", False),
])
def test_uuid_csv_pattern(value, ok):
    from pydantic import BaseModel, StringConstraints, ValidationError
    from typing import Annotated

    class M(BaseModel):
        v: Annotated[str, StringConstraints(pattern=UUID_CSV_PATTERN)]

    if ok:
        assert M(v=value).v == value
    else:
        with pytest.raises(ValidationError):
            M(v=value)


# =====================================================
# THE SAME FAULT ON ENUM COLUMNS
# =====================================================
# Postgres answers an unknown enum label with "invalid input value for enum
# <type>", which is also SQLSTATE 22P02. An unvalidated ?status= filter passed
# into .eq("status", ...) was therefore a 500 in exactly the same way.

# (path suffix, query parameter) pairs that filter on an enum column.
ENUM_BACKED_FILTERS = [
    ("/admin/bookings/", "status"),
    ("/admin/users/", "role"),
    ("/admin/vendor-requests", "status_filter"),
    ("/rm/vendor-requests", "status_filter"),
    ("/vendors/bookings", "status_filter"),
]


@pytest.mark.parametrize("suffix,param", ENUM_BACKED_FILTERS)
def test_enum_filters_publish_their_allowed_values(app, suffix, param):
    """
    Each enum-backed filter must be declared with the labels it accepts, so an
    unknown one is a 422 from the routing layer instead of a 22P02 from
    Postgres. Checked through the OpenAPI document, which is also what the
    admin panel's generated client reads.
    """
    from app.core.config import settings

    path = f"{settings.API_PREFIX}{suffix}"
    spec = app.openapi()
    assert path in spec["paths"], f"{path} not in the OpenAPI document"

    params = spec["paths"][path]["get"]["parameters"]
    match = next((p for p in params if p["name"] == param), None)
    assert match is not None, f"{param} not a query parameter of GET {path}"

    schema = match["schema"]
    # Optional filters come through as anyOf[Literal, null].
    options = schema.get("anyOf", [schema])
    assert any("enum" in o for o in options), (
        f"GET {path}?{param}= accepts any string; it reaches an enum column and "
        f"must be constrained (see app.core.validators). Got: {schema}"
    )


@pytest.mark.parametrize("value,ok", [
    ("completed", True),
    ("no_show", True),
    ("", True),          # "?status=" clears the filter and must stay accepted
    (None, True),
    ("bogus", False),
    ("COMPLETED", False),
])
def test_booking_status_filter(value, ok):
    from pydantic import BaseModel, ValidationError

    from app.core.validators import BookingStatusFilter

    class M(BaseModel):
        status: BookingStatusFilter = None

    if ok:
        assert M(status=value).status == (value or None)
    else:
        with pytest.raises(ValidationError):
            M(status=value)


def test_enum_filter_labels_match_the_database_schema():
    """
    The Literals mirror CREATE TYPE in db-schema/current_schema.sql. A migration
    that adds a label without updating them would make the new value a 422.
    """
    import pathlib
    import re
    from typing import get_args

    from app.core.validators import BookingStatus, RequestStatusFilter, UserRoleFilter

    schema_sql = pathlib.Path("db-schema/current_schema.sql").read_text(
        encoding="utf-8", errors="replace"
    )

    for enum_name, literal in [
        ("booking_status", BookingStatus),
        ("request_status", RequestStatusFilter),
        ("user_role", UserRoleFilter),
    ]:
        match = re.search(
            rf'CREATE TYPE "public"\."{enum_name}" AS ENUM \((.*?)\);',
            schema_sql, re.S,
        )
        assert match, f"{enum_name} not found in the schema dump"
        in_db = set(re.findall(r"'([^']+)'", match.group(1)))
        assert set(get_args(literal)) == in_db, (
            f"{enum_name}: validators say {sorted(get_args(literal))}, "
            f"the database says {sorted(in_db)}"
        )


# =====================================================
# THE BACKSTOP
# =====================================================

@pytest.mark.asyncio
async def test_uncaught_22P02_becomes_400_not_500():
    """
    Anything that still reaches Postgres with a malformed id -- a webhook body,
    a route added without UUIDPath -- degrades to a 400 rather than a 500.
    """
    from postgrest.exceptions import APIError
    from starlette.requests import Request

    from app.core.handlers import general_exception_handler

    request = Request({
        "type": "http", "method": "GET", "path": "/api/salons/x",
        "headers": [], "query_string": b"",
    })
    exc = APIError({
        "code": "22P02",
        "message": 'invalid input syntax for type uuid: "not-a-uuid"',
    })

    resp = await general_exception_handler(request, exc)
    assert resp.status_code == 400
    assert b"INVALID_IDENTIFIER" in resp.body


@pytest.mark.asyncio
async def test_other_database_errors_still_500():
    """The backstop is narrow: only 22P02. A real fault must stay a 500."""
    from postgrest.exceptions import APIError
    from starlette.requests import Request

    from app.core.handlers import general_exception_handler

    request = Request({
        "type": "http", "method": "GET", "path": "/api/salons/x",
        "headers": [], "query_string": b"",
    })
    exc = APIError({"code": "42P01", "message": 'relation "salons" does not exist'})

    resp = await general_exception_handler(request, exc)
    assert resp.status_code == 500
