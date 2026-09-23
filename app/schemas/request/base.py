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
from typing import Any

from pydantic import BaseModel, model_validator


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
