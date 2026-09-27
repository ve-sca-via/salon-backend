"""
Edit forms must be able to change one field without resending a valid whole record.

The reported symptom: open an edit form, change one value, submit, get an error
with no indication of what was wrong. Two causes, both covered here.

1. The form posts every input it rendered, so optional fields the user never
   touched arrive as `""`. An empty string is not a valid `min_length=2` name,
   `^\\d{6}$` pincode or `EmailStr`, so the request failed validation on fields
   the user had not looked at. `PartialUpdateModel` drops blanks before
   validation -- see app/schemas/request/base.py.

2. The 422 that came back said only "Validation failed". Every field name was
   in `errors[]`, which no client except the Next.js app read, so the toast
   named nothing. `_validation_message` now puts the fields in `message`.

Smoke-tier: no Supabase stack. The schemas and the error handlers are the whole
surface under test.
"""
import pytest

from app.core.config import settings
from app.core.handlers import _leaf_field, _validation_message
from app.schemas.admin import (
    ServiceCategoryUpdate,
    ServiceSubcategoryUpdate,
)
from app.schemas.admin import ServiceUpdate as AdminServiceUpdate
from app.schemas.domain.user import ProfileUpdate
from app.schemas.request.admin import SystemConfigUpdate
from app.schemas.request.auth import UserProfileUpdate
from app.schemas.request.banner import BannerUpdate
from app.schemas.request.blog import BlogPostUpdate
from app.schemas.request.coupon import CouponUpdate
from app.schemas.request.customer import ReviewUpdate
from app.schemas.request.product import ProductUpdate
from app.schemas.request.rm import RMProfileUpdate
from app.schemas.request.vendor import SalonUpdate, ServiceUpdate
from app.schemas.response import ErrorDetail
from app.schemas.user import UserUpdate
from app.schemas.user import UserProfileUpdate as LegacyUserProfileUpdate

# Every schema behind an edit form. A new one added without PartialUpdateModel
# reintroduces the bug, so the contract tests below walk this list.
#
# Note there are two `UserProfileUpdate`s and two `ServiceUpdate`s in the tree
# -- `app/schemas/request/` is the newer home, `app/schemas/user.py` and
# `app/schemas/admin.py` the older one, and live routes still use both
# (`/auth/me` takes the first, `/rm/profile` the second). Both are listed here
# on purpose; missing one is exactly how this bug survived the first pass.
PARTIAL_UPDATE_SCHEMAS = [
    SystemConfigUpdate,
    UserProfileUpdate,
    LegacyUserProfileUpdate,
    UserUpdate,
    ProfileUpdate,
    BannerUpdate,
    BlogPostUpdate,
    CouponUpdate,
    ReviewUpdate,
    ProductUpdate,
    RMProfileUpdate,
    SalonUpdate,
    ServiceUpdate,
    AdminServiceUpdate,
    ServiceCategoryUpdate,
    ServiceSubcategoryUpdate,
]


# =====================================================
# THE CONTRACT: absent / blank / null
# =====================================================

def test_blank_optional_field_is_treated_as_untouched():
    """
    The exact reported case. A salon edit form posts the whole record; the user
    changed only the business name. `pincode=""` used to fail the 6-digit
    pattern, `email=""` used to fail EmailStr -- neither field was touched.
    """
    payload = SalonUpdate.model_validate({
        "business_name": "Glow Studio",
        "pincode": "",
        "email": "",
        "description": "   ",
        "gst_number": "",
    })

    dumped = payload.model_dump(exclude_unset=True)
    assert dumped == {"business_name": "Glow Studio"}


def test_absent_field_is_not_in_the_update():
    """A client that sends only what changed keeps working unchanged."""
    dumped = ProductUpdate.model_validate({"price": 499.0}).model_dump(exclude_unset=True)
    assert dumped == {"price": 499.0}


def test_explicit_null_clears_the_field():
    """
    The escape hatch. Blank means "untouched", so `null` is how a client says
    "clear this" -- and `exclude_unset` is what keeps it in the payload.
    `exclude_none` would throw it away along with the absent keys, which is why
    a cleared description silently stayed put before.
    """
    dumped = ProductUpdate.model_validate(
        {"description": None}
    ).model_dump(exclude_unset=True)

    assert "description" in dumped
    assert dumped["description"] is None


def test_blank_does_not_mean_clear():
    """
    Deliberate, and the reason blanks are dropped rather than coerced to None:
    the legacy SPA and the mobile app post blanks for untouched fields. Treating
    those as a clear would have wiped stored data the moment this shipped.
    """
    dumped = ProductUpdate.model_validate({"description": ""}).model_dump(exclude_unset=True)
    assert "description" not in dumped


def test_a_real_value_still_validates():
    """Dropping blanks must not become a way to smuggle bad values through."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SalonUpdate.model_validate({"pincode": "12"})

    with pytest.raises(ValidationError):
        ProductUpdate.model_validate({"price": -5})


def test_whitespace_only_counts_as_blank():
    """A textarea the user spacebarred into is still untouched."""
    dumped = BlogPostUpdate.model_validate({"excerpt": "  \n\t "}).model_dump(exclude_unset=True)
    assert "excerpt" not in dumped


def test_every_edit_form_schema_drops_blanks():
    """
    The guard that keeps this fixed. A new `*Update` schema that inherits
    BaseModel instead of PartialUpdateModel silently reopens the bug -- nothing
    fails until a user reports a form that will not save.
    """
    from app.schemas.request.base import PartialUpdateModel

    missing = [
        schema.__name__
        for schema in PARTIAL_UPDATE_SCHEMAS
        if not issubclass(schema, PartialUpdateModel)
    ]
    assert not missing, (
        "edit-form schemas not inheriting PartialUpdateModel "
        "(app/schemas/request/base.py):\n  " + "\n  ".join(missing)
    )


# Escape hatch for a PUT/PATCH body that is all-optional with a text field but
# is deliberately NOT a partial update -- somewhere a blank must stay an error
# rather than be read as "untouched". Empty today, and worth keeping that way:
# each entry is a form that can never clear a field by blanking it.
PARTIAL_UPDATE_EXEMPT: set[str] = set()


def _body_models(app):
    """Every Pydantic body model reachable through a PUT or PATCH route."""
    from fastapi.routing import APIRoute
    from pydantic import BaseModel

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not (route.methods & {"PUT", "PATCH"}):
            continue
        field = getattr(route, "body_field", None)
        model = getattr(field, "type_", None) if field else None
        if isinstance(model, type) and issubclass(model, BaseModel):
            yield route, model


def _is_edit_form_shaped(model) -> bool:
    """
    All-optional with at least one text field -- i.e. a form that renders a
    whole record and can post blanks for the parts nobody touched.

    An all-required body (a status toggle, a cart quantity) is not an edit form
    and has nothing to gain here: a blank there should still be an error.
    """
    fields = model.model_fields
    if not fields:
        return False
    if any(f.is_required() for f in fields.values()):
        return False
    return any("str" in str(f.annotation) for f in fields.values())


def test_no_put_or_patch_route_takes_an_unguarded_edit_form_body(app):
    """
    The guard that does not depend on anyone maintaining a list.

    The first pass at this fix missed `app/schemas/user.py` and
    `app/schemas/admin.py` entirely, because the obvious grep only looked in
    `app/schemas/request/`. This walks the routes the app actually serves, so a
    schema in a module nobody remembered still gets caught.
    """
    from app.schemas.request.base import PartialUpdateModel

    unguarded = [
        f"{sorted(route.methods)[0]} {route.path} -> {model.__name__}"
        for route, model in _body_models(app)
        if model.__name__ not in PARTIAL_UPDATE_EXEMPT
        and _is_edit_form_shaped(model)
        and not issubclass(model, PartialUpdateModel)
    ]
    assert not unguarded, (
        "all-optional PUT/PATCH bodies that will 422 on a blank untouched "
        "field (inherit PartialUpdateModel, or justify an entry in "
        "PARTIAL_UPDATE_EXEMPT):\n  " + "\n  ".join(unguarded)
    )


def test_blank_required_field_reports_as_missing_not_malformed():
    """
    Dropping a blank makes a *required* field absent rather than invalid. It is
    still rejected -- and "Field required" points at the empty dropdown more
    plainly than an enum-parse error does.
    """
    from pydantic import ValidationError

    from app.schemas.request.vendor import VendorJoinRequestUpdate

    with pytest.raises(ValidationError) as exc_info:
        VendorJoinRequestUpdate.model_validate({"status": "", "admin_notes": "n"})

    errors = exc_info.value.errors()
    assert [e["type"] for e in errors] == ["missing"]
    assert errors[0]["loc"] == ("status",)


def test_taxonomy_blank_ids_still_resolve_by_name():
    """
    Regression cover for the vendor service flow: `category_id=""` alongside a
    typed `category_name` resolves by name and works today. Blank-dropping must
    not change that -- `update_service` branches on `is not None`, and an absent
    key reads the same as the None that BlankableUUIDStr produced before.
    """
    update = ServiceUpdate.model_validate({
        "category_id": "",
        "category_name": "Hair",
    })
    assert update.category_id is None
    assert update.category_name == "Hair"


# =====================================================
# THE 422 MESSAGE
# =====================================================

def test_leaf_field_strips_wrapper_and_indices():
    assert _leaf_field(["body", "pincode"]) == "pincode"
    assert _leaf_field(["body", "items", 0, "price"]) == "items.price"
    assert _leaf_field(["query", "status"]) == "status"


def test_validation_message_names_the_fields():
    """
    What turns the silent toast into an actionable one. A client reading only
    `message` -- the legacy SPA, the mobile app -- now shows the field name
    without needing to learn the `errors[]` shape.
    """
    message = _validation_message([
        ErrorDetail(field="pincode", message="String should match pattern"),
    ])
    assert "pincode" in message
    assert "String should match pattern" in message


def test_validation_message_caps_the_field_list():
    """A form with twelve bad fields must not produce an unreadable toast."""
    errors = [ErrorDetail(field=f"f{i}", message="bad") for i in range(6)]
    message = _validation_message(errors)

    assert "f0" in message and "f2" in message
    assert "f5" not in message
    assert "and 3 more fields" in message


def test_validation_message_falls_back_when_no_field_is_named():
    """A body that is not even an object has no field to point at."""
    assert _validation_message([]) == "Validation failed"


def test_422_body_carries_the_field_summary(app, client):
    """
    End to end through the real handler: the response a frontend actually
    receives names the offending field in `message`, not only in `errors[]`.
    That is the difference between the old "Validation failed" toast and one
    the user can act on.
    """
    from app.core.auth import TokenData, require_admin

    app.dependency_overrides[require_admin] = lambda: TokenData(
        user_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        email="admin@example.com",
        user_role="admin",
    )
    try:
        resp = client.put(
            f"{settings.API_PREFIX}/products/a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
            json={"price": -1, "name": ""},
        )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["error_code"] == "VALIDATION_ERROR"
    # The blank name was dropped as untouched; only the real problem is reported.
    assert "price" in body["message"]
    assert [e["field"] for e in body["errors"]] == ["price"]


# =====================================================
# CLEARING A REQUIRED COLUMN
# =====================================================

@pytest.mark.asyncio
async def test_not_null_violation_becomes_400_naming_the_column():
    """
    `null` means "clear it", so a client can now ask to clear a column the
    schema requires. That is a client mistake with a useful answer, not an
    "An unexpected error occurred" 500.
    """
    from postgrest.exceptions import APIError
    from starlette.requests import Request

    from app.core.handlers import general_exception_handler

    request = Request({
        "type": "http", "method": "PUT", "path": "/api/v1/admin/users/x",
        "headers": [], "query_string": b"",
    })
    exc = APIError({
        "code": "23502",
        "message": 'null value in column "full_name" of relation "profiles" '
                   "violates not-null constraint",
    })

    resp = await general_exception_handler(request, exc)
    assert resp.status_code == 400
    assert b"REQUIRED_FIELD" in resp.body
    assert b"full_name" in resp.body


@pytest.mark.asyncio
async def test_unrelated_database_errors_still_500():
    """The new backstop stays as narrow as the 22P02 one it sits beside."""
    from postgrest.exceptions import APIError
    from starlette.requests import Request

    from app.core.handlers import general_exception_handler

    request = Request({
        "type": "http", "method": "PUT", "path": "/api/v1/admin/users/x",
        "headers": [], "query_string": b"",
    })
    exc = APIError({"code": "23505", "message": "duplicate key value"})

    resp = await general_exception_handler(request, exc)
    assert resp.status_code == 500
