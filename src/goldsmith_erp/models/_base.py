"""Pydantic request-model foundation for V1.1.

`StrictRequestBase` is the common base class for every new Pydantic
REQUEST model introduced from Slice 2 onward. It ships in Slice 1 (this
file) so that the base class exists before it has consumers — Anna's
compliance amendment A14.8 requires **every** new V1.1 request model to
inherit from it.

Guarantees:

  1. ``extra="forbid"`` — unknown keys in a request body produce a 422,
     not a silent no-op. Prevents payload drift and unknown-field
     injection.

  2. Audit-column rejection — any field whose name is ``user_id``,
     ``created_by``, ``modified_by``, ``updated_by``, ``deleted_by`` or
     ends in ``_by`` raises a ValueError during model construction.
     These fields are audit metadata that must be filled from the
     authenticated session (``current_user.id``), never from the
     request body. Supplying them via the client is a metadata-spoofing
     surface (Anna B1 / A14.8).

The class is deliberately lightweight — no validators that require
database access, no side-effects at import time. It is safe to inherit
from in any request schema regardless of whether a session is available.

Usage::

    class ResolveRequest(StrictRequestBase):
        raw_payload: str = Field(max_length=500)
        context: ScanContext | None = None

    # POST /resolve with {"raw_payload": "...", "user_id": 42}
    #   → 422 Unprocessable Entity (user_id is an audit field)

The list of forbidden names is intentionally small and explicit — the
final catch-all ``endswith("_by")`` covers future audit columns that
share the convention (e.g. ``reviewed_by``, ``approved_by``).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


# Explicit list for readability; the trailing ``_by`` suffix check below
# catches future additions without needing to update this tuple.
_AUDIT_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "user_id",
        "created_by",
        "modified_by",
        "updated_by",
        "deleted_by",
    }
)


def _is_audit_field(name: str) -> bool:
    """Return True if `name` looks like an audit / actor-metadata field."""
    if name in _AUDIT_FIELD_NAMES:
        return True
    # Catch anything like "reviewed_by", "approved_by", "authored_by"
    # without having to enumerate every flavour. Keep the match strict
    # (requires the literal "_by" suffix) so benign names like "nearby"
    # or "lullaby" are not rejected.
    return name.endswith("_by") and len(name) > len("_by")


class StrictRequestBase(BaseModel):
    """Base class for all V1.1+ mutating request models.

    Rejects unknown keys and any field whose name indicates an audit /
    actor-metadata column. Slice 2 will extend this in response to the
    security-floor work; the base contract landed in Slice 1 per Anna
    A14.8 so every downstream PR inherits the guarantee.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _reject_audit_fields(cls, data: Any) -> Any:
        """Refuse request bodies that try to smuggle audit metadata.

        Runs before Pydantic field-level validation so the rejection
        surfaces as a clean ValidationError ("user_id is an audit field
        and cannot be supplied in a request body") rather than a
        Pydantic internal error about unknown keys.

        Only activates on dict-shaped input — instances constructed
        from the ORM (e.g. ``Model.model_validate(obj)``) pass through
        unchanged so that auto-generated response objects containing
        audit columns are not accidentally rejected.
        """
        if not isinstance(data, dict):
            return data

        offenders = [k for k in data.keys() if _is_audit_field(k)]
        if offenders:
            # Pydantic converts the ValueError into a field-level 422.
            raise ValueError(
                "Audit / actor-metadata fields are not accepted in "
                "request bodies: " + ", ".join(sorted(offenders))
            )
        return data
