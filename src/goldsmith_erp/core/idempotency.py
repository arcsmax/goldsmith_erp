"""Idempotency-Key + X-Client-Created-At dependency (Slice 2, M1).

Every mutating endpoint that ships from Slice 4 onward accepts two
optional headers from the client:

  * ``Idempotency-Key``       — UUIDv4. Lets the server dedupe a retried
                                request to the SAME side-effect. Stored
                                on write (e.g. ``scan_logs.idempotency_key``
                                with a ``UNIQUE WHERE NOT NULL`` index
                                from Slice 1).
  * ``X-Client-Created-At``   — ISO-8601 timestamp the client recorded
                                when it produced the event. Used by
                                Lena §4 row b metric (FAB-tap-to-timer)
                                and rejected if nonsensical
                                (>30 days old or >1 h in the future —
                                clock-skew tolerance).

This module exposes:

  * ``IdempotencyContext``      — a dataclass carrying the two parsed
                                  values. Routers depend on this via
                                  ``Depends(get_idempotency_context)``.
  * ``get_idempotency_context`` — the FastAPI dependency. Raises
                                  HTTP 400 on malformed UUID or an
                                  implausible timestamp.
  * ``check_and_store_idempotency`` — stub for the V1.1.5 server-side
                                  dedupe. In V1.1 it returns ``None``
                                  always; clients rely on their own
                                  retry + the DB UNIQUE index for
                                  exactly-once semantics.

Security-floor design notes (per V1.1-PRIORITY-REVIEW.md M1 + A14.8):

  * The dependency NEVER reads ``user_id`` from the headers. The JWT
    auth dependency is the sole source of ``current_user.id`` — see
    ``StrictRequestBase`` for the symmetric request-body rule.
  * ``Idempotency-Key`` is validated as UUIDv4 specifically. Raw
    ``uuid.UUID(...)`` accepts any version; a request carrying a v1
    MAC-address UUID is rejected on principle (v1 UUIDs leak host
    identity on older Linux systems). A malformed header returns 400,
    not 422, because the header is a transport contract not a body
    field.
  * ``X-Client-Created-At`` is parsed with the stdlib ``datetime.
    fromisoformat`` plus a trailing-Z normalisation. Timezones other
    than UTC are accepted; naive datetimes are assumed UTC.

Re-using this dependency from Slice 4 onward means every mutating
endpoint in V1.1 inherits the security floor without per-endpoint code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Constants — tolerance windows.
# ---------------------------------------------------------------------------

# Reject client-created-at timestamps older than this — Lena §4 defines the
# metric window as 30 days; anything older is an old cached retry or a
# replay attack surface.
MAX_CLIENT_CREATED_AT_AGE = timedelta(days=30)

# Tolerate up to one hour of future skew. Clients on mis-configured clocks
# are common (workshop tablets in particular) but 1 h is a generous ceiling
# that still blocks an obviously-wrong payload.
MAX_CLIENT_CREATED_AT_FUTURE_SKEW = timedelta(hours=1)


# ---------------------------------------------------------------------------
# Context carrier.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdempotencyContext:
    """Parsed headers passed to a mutating endpoint.

    Both fields are optional — V1.1 clients MAY omit either header and
    the server treats the request as "best-effort online". From V1.1.5
    onward the offline-queue replay always sends both.
    """

    key: Optional[UUID] = None
    client_created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Header validation helpers.
# ---------------------------------------------------------------------------


def _validate_uuid_v4(raw: str) -> UUID:
    """Parse + validate a UUIDv4 string. Raises HTTPException(400) on error."""
    try:
        parsed = UUID(raw)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must be a valid UUIDv4.",
        )
    # UUID version check — we want v4 specifically. v1 UUIDs leak MAC
    # address on older Linuxes; v3/v5 imply a namespace contract we
    # don't have.
    if parsed.version != 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must be a UUIDv4 "
            f"(got version {parsed.version}).",
        )
    return parsed


def _parse_iso_datetime(raw: str) -> datetime:
    """Parse an ISO-8601 timestamp. Accepts trailing 'Z' (UTC)."""
    normalised = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalised)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "X-Client-Created-At must be an ISO-8601 timestamp "
                "(YYYY-MM-DDTHH:MM:SS[.ffffff][+HH:MM|Z])."
            ),
        )
    # Treat naive datetimes as UTC so downstream comparisons stay valid.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _validate_client_created_at(parsed: datetime) -> None:
    """Enforce the 30-day-old / 1-hour-future tolerance window."""
    now = datetime.now(tz=timezone.utc)
    # Too-old check.
    if now - parsed > MAX_CLIENT_CREATED_AT_AGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "X-Client-Created-At is older than 30 days; the client "
                "should not replay this event."
            ),
        )
    # Future-skew check.
    if parsed - now > MAX_CLIENT_CREATED_AT_FUTURE_SKEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "X-Client-Created-At is more than 1 hour in the future; "
                "check client clock."
            ),
        )


# ---------------------------------------------------------------------------
# FastAPI dependency.
# ---------------------------------------------------------------------------


def get_idempotency_context(
    idempotency_key: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key",
        description="UUIDv4 identifying this logical mutation for retry safety.",
    ),
    x_client_created_at: Optional[str] = Header(
        default=None,
        alias="X-Client-Created-At",
        description="ISO-8601 timestamp of the client-side event.",
    ),
) -> IdempotencyContext:
    """Validate + parse the two idempotency headers.

    Returns an ``IdempotencyContext`` with the parsed values (either of
    which may be ``None`` if the header was omitted). Raises
    ``HTTPException(400)`` with a plain-German-or-English detail if the
    header is present but malformed.
    """
    parsed_key: Optional[UUID] = None
    if idempotency_key is not None:
        parsed_key = _validate_uuid_v4(idempotency_key)

    parsed_ts: Optional[datetime] = None
    if x_client_created_at is not None:
        parsed_ts = _parse_iso_datetime(x_client_created_at)
        _validate_client_created_at(parsed_ts)

    return IdempotencyContext(key=parsed_key, client_created_at=parsed_ts)


# ---------------------------------------------------------------------------
# V1.1 stub — V1.1.5 will implement server-side replay dedupe.
# ---------------------------------------------------------------------------


async def check_and_store_idempotency(
    db: AsyncSession,
    key: Optional[UUID],
    user_id: int,
) -> Optional[dict]:
    """V1.1 stub — always returns None.

    In V1.1.5 this will:
      1. Look up `(user_id, key)` in a server-side idempotency store
         (either a dedicated table or a Redis hash with TTL).
      2. If a successful result already exists for the key, return it
         (router replays the cached response instead of re-applying).
      3. Otherwise, write a "pending" marker so concurrent retries are
         serialised.

    V1.1 relies on:
      * Client behaviour (only retries with the same key).
      * The DB-level ``UNIQUE WHERE idempotency_key IS NOT NULL`` index
        on ``scan_logs.idempotency_key`` (from Slice 1 migration).

    The signature is stable so that Slice 4 routers can call this today
    and the V1.1.5 PR only touches this function body.
    """
    # Intentionally unused — signature reserved for V1.1.5.
    del db, key, user_id
    return None
