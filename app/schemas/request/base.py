"""
Base model for partial-update (edit form) request schemas.

The problem this solves
-----------------------
Every edit form in the admin panel and the web app renders the whole record,
not just the field being changed, and posts the whole form back. Optional
inputs the user never touched arrive as `""`, and an empty string is not a
valid value for most of our optional fields -- `min_length=2`, the `pincode`
pattern, `EmailStr`. So changing one field failed validation on a handful of
*other* fields the user never looked at, and the 422 that came back was
rendered as a bare "Validation failed" toast. See docs/PARTIAL_UPDATES.md.

The contract
------------
For a schema inheriting `PartialUpdateModel`, each field key in the request
body means one of three things:

    key absent            -> leave the column alone
    key present, ""       -> leave the column alone ("I didn't touch this")
    key present, null     -> clear the column (set it to NULL)

The blank case is what makes a whole-form POST behave like a partial update:
blanks are dropped from the payload *before* validation, so they can neither
fail a constraint nor reach the database. `null` stays the explicit way to
clear a field, for clients that send only what the user actually changed.

Blank means "untouched" rather than "clear" deliberately: the existing SPA and
mobile clients post blanks for untouched fields, and treating those as a clear
would have silently wiped stored data the moment this shipped.

Paired with `model_dump(exclude_unset=True)` at the call site -- `exclude_none`
would throw away the explicit-null clear along with the absent keys.
"""
from typing import Annotated, Any, Optional

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from app.utils.phone import INDIAN_MOBILE_RULE, to_indian_mobile_e164

def _local_indian_mobile(value: Any) -> Any:
    """Validate via the E.164 helper, then hand back the local 10 digits."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return value
    normalized = to_indian_mobile_e164(value)
    return normalized[len("+91"):] if normalized else normalized


#: An optional phone field that accepts what a form actually sends (10 digits, or
#: a +91/91-prefixed number) and stores E.164. Use this instead of a bare
#: `Optional[str]`: the admin panel's "at least 10 digits" check let 11- and
#: 15-digit numbers through to `profiles.phone`, whose own CHECK allows up to 15.
IndianMobile = Annotated[
    Optional[str],
    BeforeValidator(to_indian_mobile_e164),
    Field(default=None, description=INDIAN_MOBILE_RULE, examples=["9876543210"]),
]

#: Same validation, but kept as the bare 10 digits the form sent. Salon and
#: join-request numbers are shown on the public site and handed to the WhatsApp
#: sender, so these deliberately are not rewritten into E.164 - the field only
#: refuses what isn't a real mobile number.
IndianMobileDigits = Annotated[
    str,
    BeforeValidator(_local_indian_mobile),
    Field(description=INDIAN_MOBILE_RULE, examples=["9876543210"]),
]

OptionalIndianMobileDigits = Annotated[
    Optional[str],
    BeforeValidator(_local_indian_mobile),
    Field(default=None, description=INDIAN_MOBILE_RULE, examples=["9876543210"]),
]

#: Indian PINs are six digits. `vendor_join_requests` and `salons` used to accept
#: a 10-digit form too, which was never a real postal code - it only ever caused
#: the varchar(6)/varchar(10) approval crash. See the migration that tightens the
#: matching CHECK constraints.
PINCODE_PATTERN = r"^\d{6}$"
PINCODE_RULE = "6-digit Indian pincode"

Pincode = Annotated[str, Field(pattern=PINCODE_PATTERN, description=PINCODE_RULE, examples=["400001"])]
OptionalPincode = Annotated[
    Optional[str],
    Field(default=None, pattern=PINCODE_PATTERN, description=PINCODE_RULE, examples=["400001"]),
]


class PartialUpdateModel(BaseModel):
    """A request body where every key present is an intentional change."""

    @model_validator(mode="before")
    @classmethod
    def _drop_blank_strings(cls, data: Any) -> Any:
        # `data` is the raw body for the normal JSON path. It can also arrive as
        # an already-built model (e.g. `Model.model_validate(instance)`), which
        # has no blanks to strip and must be passed through untouched.
        if not isinstance(data, dict):
            return data
        return {
            key: value
            for key, value in data.items()
            if not (isinstance(value, str) and not value.strip())
        }
