"""Pydantic schemas for the V1.1 scanner API.

All REQUEST models in this module inherit from ``StrictRequestBase``
(Slice 1 + 2 foundation, ``models/_base.py``) which guarantees:

  * ``extra="forbid"`` — unknown keys in a request body raise 422.
  * Audit / actor-metadata fields (``user_id``, ``created_by``, ``*_by``)
    are rejected; ``user_id`` is always sourced from the JWT on the
    server, never from the request payload.
  * Server-controlled fields (``anonymization_hash``, ``tenant_id``,
    ``is_deleted``, ``retention_class``) are rejected — these are
    written exclusively by the service layer.

RESPONSE models inherit directly from :class:`pydantic.BaseModel` (they
are OUTPUTS, not user-supplied) but still set ``extra="forbid"`` so
developer drift on internal projection helpers surfaces as a test
failure rather than leaking fields.

B1 resolution (Anna, ``V1.1-AMENDMENTS.md`` §Second-round additions):
``ScanContext`` uses a strict whitelist. The spec §2.b prose-level
whitelist is enforced in code here — unknown keys cannot be silently
logged to ``scan_logs.context``, closing the Art. 5(1)(c) minimum-data
principle gap.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import (
    UUID4,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from goldsmith_erp.models._base import StrictRequestBase

# --------------------------------------------------------------------------- #
# Resolution-path literal — single source of truth
# --------------------------------------------------------------------------- #

# Used on both the router response (``ResolveResponse.resolution_path``)
# and the log-write path (``ScanLogCreate.resolution_path``). Defined
# once to guarantee the two enums cannot drift.
ResolutionPath = Literal["prefix", "alias", "numeric_fallback", "unknown"]

# Input-source literal — how the scan event entered the client.
# * ``camera``  — mobile / tablet camera via ``@yudiel/react-qr-scanner``.
# * ``usb_hid`` — bench keyboard-wedge scanner (Werkbank-Station-Modus).
# * ``manual``  — goldsmith typed the code into the text input.
InputSource = Literal["camera", "usb_hid", "manual"]

# Device class that issued the scan. Kept small — spec §2.b whitelist.
DeviceType = Literal["mobile", "desktop", "tablet"]

# Fallback-reason literal — populated when camera path failed and the
# goldsmith entered the code manually. Drives the §14.a row-d adoption
# metric (spec §14.a). Nullable everywhere.
FallbackReason = Literal["camera_denied", "camera_unavailable", "user_choice"]


# --------------------------------------------------------------------------- #
# ScanContext — B1 strict whitelist
# --------------------------------------------------------------------------- #

# Regex for semver-ish client versions: ``X.Y.Z`` with optional
# ``-<alnum>+`` suffix (e.g. ``1.2.3-beta2``). Covers all real-world
# build IDs we emit today; rejects garbage such as ``1.2`` or
# ``v1.2.3`` (no leading ``v`` allowed — that is a display convention,
# not a payload value).
_CLIENT_VERSION_PATTERN = r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9]+)?$"


class ScanContext(StrictRequestBase):
    """Client-supplied context snapshot — B1-strict whitelist.

    Every field is optional — an empty ``ScanContext`` is a valid input.
    Unknown keys are **rejected** (``StrictRequestBase`` enforces
    ``extra="forbid"``), which is the core of Anna's B1 blocker: the
    spec §2.b whitelist must be enforced in code, not merely documented.

    A developer who tries to extend the context by sending
    ``{"customer_id": 42}`` hits a 422 at the router boundary and cannot
    silently persist customer PII into ``scan_logs.context``.

    Notes on individual fields:

      * ``running_timer_id`` — a string because ``TimeEntry.id`` is a
        UUID4 string on the ORM. Forwarding an integer here is invalid
        even under a lax schema.
      * ``current_order_id`` — integer FK to ``orders.id``.
      * ``current_location`` — station label (e.g. ``"Werkbank_2"``),
        free-text within a strict length bound.
      * ``device_type`` + ``input_source`` — analytic facets, tightly
        constrained by literal unions.
      * ``client_version`` — semver-ish build identifier used for the
        §14.a metric join.
    """

    running_timer_id: Optional[str] = Field(default=None, max_length=36)
    current_order_id: Optional[int] = Field(default=None, gt=0)
    current_location: Optional[str] = Field(default=None, max_length=100)
    device_type: Optional[DeviceType] = None
    input_source: InputSource = "manual"
    client_version: Optional[str] = Field(
        default=None,
        max_length=32,
        pattern=_CLIENT_VERSION_PATTERN,
    )


# --------------------------------------------------------------------------- #
# ResolveRequest / ResolveResponse
# --------------------------------------------------------------------------- #

# ASCII control characters except horizontal tab (\t) are stripped from
# raw payloads. Null bytes (\x00) are rejected outright — they should
# never appear in a scanned string and their presence typically
# indicates an injection attempt. See spec §M6 / Henrik R6.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class ResolveRequest(StrictRequestBase):
    """Scan-payload resolution request body (``POST /scan/resolve``).

    ``raw_payload`` is the exact string the scanner emitted (or the
    user typed). The validator below strips non-tab ASCII control
    characters — scanners occasionally emit CR / LF tails which are
    legitimate transport artifacts that must not reach the DB.
    Null bytes, however, are rejected with a hard 422: they cannot
    appear in any legitimate barcode and indicate a malicious payload.
    """

    raw_payload: str = Field(..., min_length=1, max_length=500)
    context: ScanContext = Field(default_factory=ScanContext)

    @field_validator("raw_payload")
    @classmethod
    def _strip_control_chars(cls, value: str) -> str:
        # Null byte — explicit reject. Not just stripped: the presence
        # of \x00 is a strong signal that something is wrong.
        if "\0" in value:
            raise ValueError("raw_payload must not contain null bytes")
        cleaned = _CONTROL_CHAR_RE.sub("", value)
        # After stripping, the payload could become empty — re-assert
        # the min_length invariant. ``Field(min_length=1)`` only runs
        # against the raw input, not the post-validator value.
        if len(cleaned) == 0:
            raise ValueError("raw_payload must not be empty after sanitisation")
        return cleaned


class ActionItem(BaseModel):
    """A single Quick Action entry in a ``ResolveResponse``.

    Server emits these pre-sorted in the order the UI should render
    them; ``primary=True`` marks the one the FAB-modal should
    highlight (typically the first). Only one primary per list is
    expected but not structurally enforced — the UI treats multiple
    primaries as a best-effort render.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=50)
    label: str = Field(..., min_length=1, max_length=100)
    icon: str = Field(..., min_length=1, max_length=32)
    primary: bool = False


class ResolveResponse(BaseModel):
    """Server response for ``POST /scan/resolve``.

    ``entity`` is a *role-filtered projection* — see the per-role field
    allow-lists in :mod:`goldsmith_erp.services.scanner_service`. The
    projection guarantees that a VIEWER never receives financial fields
    such as ``material_cost`` or ``margin``, regardless of what the
    underlying ORM row contains.
    """

    model_config = ConfigDict(extra="forbid")

    resolved: bool
    resolution_path: ResolutionPath
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    entity: Optional[Dict[str, Any]] = None
    actions: List[ActionItem] = Field(default_factory=list)
    status_hint: Optional[str] = None


# --------------------------------------------------------------------------- #
# ScanLog create + read
# --------------------------------------------------------------------------- #


class ScanLogCreate(StrictRequestBase):
    """Request body for ``POST /scan/log``.

    Only **client**-observable fields are accepted; ``user_id``,
    ``server_resolved_at`` and ``retention_class`` are server-set and
    rejected by :class:`StrictRequestBase` before this class even runs
    its own validators.

    Field notes:

      * ``idempotency_key`` — optional UUID**4**. If present, the
        ``UNIQUE WHERE idempotency_key IS NOT NULL`` index enforces
        at-most-once insertion; the service layer traps the
        ``IntegrityError`` and returns the original row (A1 / M1).
      * ``client_tap_at`` — FAB tap timestamp measured on the client.
        Feeds the §14.a row-b adoption metric (A4.1 / A1.2). No
        server validation beyond ISO-8601 at the router layer.
      * ``fallback_reason`` — camera-denied / user-cancel analytics.
    """

    raw_payload: str = Field(..., min_length=1, max_length=500)
    resolved_type: Optional[str] = Field(default=None, max_length=50)
    resolved_id: Optional[str] = Field(default=None, max_length=100)
    resolution_path: Optional[ResolutionPath] = None
    action_taken: Optional[str] = Field(default=None, max_length=50)
    context: Optional[ScanContext] = None
    offline_queued: bool = False
    idempotency_key: Optional[UUID4] = None
    client_tap_at: Optional[datetime] = None
    fallback_reason: Optional[FallbackReason] = None

    @field_validator("raw_payload")
    @classmethod
    def _strip_control_chars(cls, value: str) -> str:
        if "\0" in value:
            raise ValueError("raw_payload must not contain null bytes")
        cleaned = _CONTROL_CHAR_RE.sub("", value)
        if len(cleaned) == 0:
            raise ValueError("raw_payload must not be empty after sanitisation")
        return cleaned


class ScanLogBatchCreate(StrictRequestBase):
    """Request body for ``POST /scan/log/batch``.

    Upper bound of 100 events matches Slice 1 operational expectation —
    offline-queue drain happens in 100-row batches. Lower bound of 1
    prevents trivial no-op calls from wasting round-trips.
    """

    events: List[ScanLogCreate] = Field(..., min_length=1, max_length=100)


class ScanLogRead(BaseModel):
    """Response row for ``GET /scan/log`` (history).

    ``user_id`` is an int (never anonymised at read time — anonymisation
    rewrites the FK to the sentinel user ID = 0; the sentinel is
    conventionally rendered as "deleted_user" in the UI). Callers are
    expected to handle the sentinel in the view layer.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID4
    scanned_at: datetime
    user_id: int
    raw_payload: str
    resolved_type: Optional[str] = None
    resolved_id: Optional[str] = None
    resolution_path: Optional[str] = None
    action_taken: Optional[str] = None
    offline_queued: bool
    synced_at: Optional[datetime] = None


class BatchLogResponse(BaseModel):
    """Summary returned by ``POST /scan/log/batch``.

    Only **counts** and a short list of top rejection reasons are
    returned — per-row error payloads are deliberately withheld to
    prevent leaking client-side queue contents through an error
    message (defence-in-depth against rogue client or MITM).

    * ``ingested``      — rows newly persisted.
    * ``deduplicated``  — rows suppressed by idempotency-key hit.
    * ``rejected``      — rows dropped on validation failure.
    * ``reasons``       — capped at 10 distinct reason strings.
    """

    model_config = ConfigDict(extra="forbid")

    ingested: int = Field(..., ge=0)
    deduplicated: int = Field(..., ge=0)
    rejected: int = Field(..., ge=0)
    reasons: List[str] = Field(default_factory=list, max_length=10)
