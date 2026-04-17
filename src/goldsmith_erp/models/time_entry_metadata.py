"""Schema-enforced whitelist for ``time_entries.extra_metadata`` (O3).

Background
----------
``time_entries.extra_metadata`` is a JSON column used for timing and
telemetry breadcrumbs. Until now it was unstructured: any key, any
value. That is a latent GDPR Art. 5(1)(c) ("data minimisation") risk —
a future developer could add nested keys containing customer PII
(e.g. ``{"customer_name": "Mueller"}``) that would bypass the
``CustomerService.scrub_customer_pii`` walk, which only scans typed
columns and does not traverse JSON nested keys.

This module closes that door by:

  1. Defining an explicit, enumerable whitelist of keys the column may
     contain (``ALLOWED_TIME_ENTRY_METADATA_KEYS``).
  2. Providing a Pydantic model (``TimeEntryMetadata``) that validates
     both keys and values at the API boundary.
  3. Enforcing absolute PII patterns (email-like strings, suspiciously
     long alphabetic runs, customer-ish key suffixes, oversize values,
     nested depth, total serialized size) that are rejected even if a
     key is nominally on the whitelist.

The schema is intentionally small. If a genuine future use-case needs a
new key, add it here with a code comment explaining the semantics — do
not loosen the guards.

See also
--------
* ``docs/superpowers/plans/qr-barcode-workflow/PII-SCRUB-AUDIT.md`` — O3.
* ``docs/superpowers/plans/qr-barcode-workflow/V1.1-AMENDMENTS.md`` — O3
  row in "Pre-existing codebase hygiene".
* ``goldsmith_erp.models._base.StrictRequestBase`` — sibling "deny
  unknowns + reject audit fields" pattern used at the request boundary.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --------------------------------------------------------------------------- #
# Whitelist
# --------------------------------------------------------------------------- #

# The literal, human-auditable set of keys this column may carry. Any key
# outside this set MUST be rejected. The set is duplicated as a frozenset
# below (derived from the TimeEntryMetadata field names) so external
# callers and tests can reference it without introspecting Pydantic.
ALLOWED_TIME_ENTRY_METADATA_KEYS: frozenset[str] = frozenset(
    {
        # Client environment — bench tablet vs. office PC vs. phone.
        "device_type",
        # How the entry was initiated (matches ScanContext.input_source
        # vocabulary introduced in Slice 3 of the QR/barcode workflow).
        "input_source",
        # Semantic version of the frontend that wrote the entry — useful
        # for correlating telemetry to a release when investigating bug
        # reports. Bounded format; cannot contain freetext.
        "client_version",
        # Why a timer ended: auto-closed by the backend, user-stopped,
        # or replaced by an activity switch.
        "interrupted_by",
        # When ``input_source == "scan"`` and this entry replaced a
        # previously-running timer, records whether the origin switch
        # came from a scan or a manual activity pick.
        "switch_origin",
        # Populated on rows produced by the V1.1 "recovery" flow where
        # a mis-routed scan creates a compensating entry. Free-ish text
        # (bounded length) but explicitly not customer-linked.
        "recovery_reason",
    }
)


# --------------------------------------------------------------------------- #
# Absolute forbidden patterns (applied to every string value, every key)
# --------------------------------------------------------------------------- #

# An ``@`` anywhere in a value is assumed email-like. The metadata shape
# has no legitimate need for addresses.
_EMAIL_SENTINEL = "@"

# Consecutive alphabetic runs longer than this threshold look like names
# ("Mueller", "Schmidt-Johansson") or freetext. The whitelisted values
# are either enums, semver, or short reason codes — none need long runs.
_MAX_ALPHABETIC_RUN = 20
_LONG_ALPHA_RE = re.compile(rf"[A-Za-zÄÖÜäöüß]{{{_MAX_ALPHABETIC_RUN + 1},}}")

# Any key ending in these suffixes is a customer-linked field name —
# rejected even if somehow allowed by the whitelist (defence-in-depth
# against an accidental whitelist extension that shadows PII).
_FORBIDDEN_KEY_SUFFIXES: tuple[str, ...] = (
    "_name",
    "_email",
    "_phone",
    "_customer",
)

# Per-value cap (characters) — whitelisted values are enums or short
# semver / reason codes; 200 chars is a generous ceiling.
_MAX_VALUE_LEN = 200

# Maximum object nesting depth. A primitive is depth 0; a flat dict is
# depth 1; one level of dict-of-dict is depth 2. Anything deeper is
# rejected. In practice the whitelisted values are all scalars, so this
# guard also short-circuits the "nested PII dict" attack surface.
_MAX_NESTED_DEPTH = 2

# Total serialized size in bytes. 4 KiB is far larger than any
# legitimate telemetry payload and well within PostgreSQL JSON column
# comfort — but small enough that an attempt to stash a customer
# profile in the column will fail here instead of silently succeeding.
_MAX_SERIALIZED_BYTES = 4 * 1024


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _value_depth(value: Any) -> int:
    """Return nesting depth of a JSON-compatible value.

    Scalars (str / int / float / bool / None) are depth 0. A list or
    dict is ``1 + max(depth of each child)``. Empty collections are
    depth 1 — the container itself counts.
    """
    if isinstance(value, dict):
        if not value:
            return 1
        return 1 + max(_value_depth(v) for v in value.values())
    if isinstance(value, list):
        if not value:
            return 1
        return 1 + max(_value_depth(v) for v in value)
    return 0


def _walk_strings(value: Any):
    """Yield every string leaf in an arbitrarily-nested JSON value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_strings(child)


def _reject_pii_patterns_in_value(value: Any, key_for_error: str) -> None:
    """Raise ``ValueError`` if ``value`` contains any forbidden pattern.

    The caller has already validated that ``value`` is JSON-compatible.
    """
    # Depth guard — catches nested dict attacks regardless of key
    # whitelist. Applied before per-string checks so oversized nested
    # payloads are rejected quickly.
    if _value_depth(value) > _MAX_NESTED_DEPTH:
        raise ValueError(
            f"metadata[{key_for_error!r}] exceeds max nested depth "
            f"({_MAX_NESTED_DEPTH})"
        )

    for s in _walk_strings(value):
        if len(s) > _MAX_VALUE_LEN:
            raise ValueError(
                f"metadata[{key_for_error!r}] contains a string "
                f"longer than {_MAX_VALUE_LEN} characters"
            )
        if _EMAIL_SENTINEL in s:
            raise ValueError(
                f"metadata[{key_for_error!r}] contains an email-like "
                f"'@' character and is rejected as possible PII"
            )
        if _LONG_ALPHA_RE.search(s):
            raise ValueError(
                f"metadata[{key_for_error!r}] contains a run of more "
                f"than {_MAX_ALPHABETIC_RUN} alphabetic characters "
                f"(possible name/freetext); rejected"
            )


# --------------------------------------------------------------------------- #
# The schema
# --------------------------------------------------------------------------- #


# Pre-declared regex for client_version: semver with optional
# alphanumeric pre-release suffix. The ``max_length`` / pattern combined
# also upper-bounds the field independently of ``_MAX_VALUE_LEN``.
_CLIENT_VERSION_PATTERN = r"^\d+\.\d+\.\d+(-[a-z0-9]+)?$"


class TimeEntryMetadata(BaseModel):
    """Whitelist schema for ``time_entries.extra_metadata``.

    Instantiation rules:

    * Unknown top-level keys produce a 422 (``extra="forbid"``).
    * Every string leaf in every value is scanned for the forbidden
      patterns listed at the top of this module.
    * Nested objects deeper than :data:`_MAX_NESTED_DEPTH` are rejected.
    * Total serialised payload must stay under
      :data:`_MAX_SERIALIZED_BYTES`.

    The whitelist is synchronised with
    :data:`ALLOWED_TIME_ENTRY_METADATA_KEYS` by the model_validator
    below — a test pins that both lists are equal so drift is caught in
    CI.
    """

    model_config = ConfigDict(
        extra="forbid",
        # Keep the rejection messages crisp — no schema URL in the 422.
        str_strip_whitespace=False,
        # Pydantic v2: validate field assignments too (defence in depth
        # against ``obj.device_type = "evil"`` after construction).
        validate_assignment=True,
    )

    device_type: Optional[Literal["mobile", "desktop", "tablet"]] = Field(
        default=None,
        description="Client class that produced the entry.",
    )
    input_source: Optional[Literal["camera", "usb_hid", "manual"]] = Field(
        default=None,
        description=(
            "How the entry was initiated. Vocabulary shared with "
            "ScanContext.input_source (QR/barcode Slice 3)."
        ),
    )
    client_version: Optional[str] = Field(
        default=None,
        max_length=32,
        pattern=_CLIENT_VERSION_PATTERN,
        description="Semver of the frontend that wrote the entry.",
    )
    interrupted_by: Optional[
        Literal["system", "user", "activity_switch"]
    ] = Field(
        default=None,
        description="Reason a running timer was ended.",
    )
    switch_origin: Optional[Literal["scan", "manual"]] = Field(
        default=None,
        description=(
            "When this entry replaces a previous running timer: "
            "whether the switch originated from a scan or a manual UI "
            "action."
        ),
    )
    recovery_reason: Optional[str] = Field(
        default=None,
        max_length=_MAX_VALUE_LEN,
        description=(
            "Populated on recovery/compensating rows. Free-ish text "
            "but subject to the universal PII-pattern rejection."
        ),
    )

    # --------------------------------------------------------------------- #
    # Validators
    # --------------------------------------------------------------------- #

    @model_validator(mode="before")
    @classmethod
    def _reject_forbidden_key_suffixes(cls, data: Any) -> Any:
        """Reject customer-linked key suffixes BEFORE extra="forbid" runs.

        ``extra="forbid"`` also catches these (they aren't whitelisted),
        but a tailored error message makes the security intent explicit
        in logs and test output. This also matters if the whitelist is
        ever extended by mistake — the suffix check still fires.
        """
        if not isinstance(data, dict):
            return data
        offenders = [
            k
            for k in data.keys()
            if isinstance(k, str)
            and any(k.endswith(suffix) for suffix in _FORBIDDEN_KEY_SUFFIXES)
        ]
        if offenders:
            raise ValueError(
                "metadata keys matching customer-linked suffixes "
                f"({', '.join(_FORBIDDEN_KEY_SUFFIXES)}) are forbidden: "
                + ", ".join(sorted(offenders))
            )
        return data

    @model_validator(mode="after")
    def _reject_pii_patterns(self) -> "TimeEntryMetadata":
        """Scan every populated value for the absolute forbidden patterns.

        Runs after field-level validation so that the ``Literal``
        fields have already narrowed their values. String-typed fields
        (``client_version``, ``recovery_reason``) are scanned here for
        the universal patterns.
        """
        dumped = self.model_dump(exclude_none=True)
        for key, value in dumped.items():
            _reject_pii_patterns_in_value(value, key)

        # Total-size ceiling. ``json.dumps`` is deterministic enough to
        # serve as a size proxy here; the ceiling is far above any
        # legitimate payload so exact byte-accounting is not required.
        serialised = json.dumps(dumped, separators=(",", ":"), ensure_ascii=False)
        if len(serialised.encode("utf-8")) > _MAX_SERIALIZED_BYTES:
            raise ValueError(
                f"metadata exceeds {_MAX_SERIALIZED_BYTES}-byte "
                "serialised-size limit"
            )
        return self


# --------------------------------------------------------------------------- #
# Drift-guard
# --------------------------------------------------------------------------- #


def _assert_whitelist_matches_model() -> None:
    """Pinning helper — import-time guarantee that the whitelist and
    the model field set are in sync.

    If they drift a developer has added a field without updating the
    external constant (or vice versa). Raising at import time fails
    loudly during the test-collection phase.
    """
    model_fields = set(TimeEntryMetadata.model_fields.keys())
    if model_fields != set(ALLOWED_TIME_ENTRY_METADATA_KEYS):
        missing_in_model = ALLOWED_TIME_ENTRY_METADATA_KEYS - model_fields
        extra_in_model = model_fields - ALLOWED_TIME_ENTRY_METADATA_KEYS
        raise RuntimeError(
            "TimeEntryMetadata whitelist drift: "
            f"missing in model={sorted(missing_in_model)}, "
            f"extra in model={sorted(extra_in_model)}"
        )


_assert_whitelist_matches_model()


__all__ = [
    "ALLOWED_TIME_ENTRY_METADATA_KEYS",
    "TimeEntryMetadata",
]
