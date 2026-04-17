"""Scanner resolution + role-filtered projection service (Slice 3).

Pipeline (spec §3 + plan Slice 3):

  1. **Prefix match** — payload split on ``:``; first segment checked
     against :data:`KNOWN_PREFIXES_V1_1`. A match routes to the
     entity handler (ORDER / REPAIR / METAL / MATERIAL / ACTIVITY /
     INTERRUPT).
  2. **Alias lookup** — stub in V1.1 (returns ``None``). Wired in
     V1.1.5 against ``barcode_aliases``. The pipeline step still
     exists so V1.1.5 is a drop-in; no branching added there later.
  3. **Numeric fallback** — a *purely* numeric payload is treated as
     ``ORDER:<n>``. ``"42"`` → ORDER 42. ``"42a"`` → unknown.
  4. **Unknown** — ``resolved=False, resolution_path="unknown"``.
     Empty ``actions`` list. UI renders the V1.2 unknown-code modal.

Role-filtered projections (R9 + Anna A3.3):

  * ``*_FIELDS_BY_ROLE`` dicts are **allow-lists** — every entity dict
    on a ``ResolveResponse`` contains only fields that appear in the
    caller-role's set. Adding a new field to the ORM does NOT
    automatically expose it; you must also add it to the role set.
  * Tests assert ``assertEqual(keys, expected_set)``, not
    ``assertNotIn``, so silent additions break CI (cf. A3.3).

Action computation:

  * ``compute_actions`` is recomputed **every call**. The caller-role
    filter is applied here, not at the router — moving the filter
    into the service layer means batch / background paths inherit the
    same guarantee.

user_id:

  * Never read from the payload. ``log_scan`` / ``log_scan_batch``
    accept ``user_id`` as a parameter supplied by the router from
    ``current_user.id`` (derived from the validated JWT). Attempts to
    sneak a ``user_id`` into the request body are rejected by
    :class:`StrictRequestBase` long before reaching this service.

Idempotency dedupe:

  * ``log_scan`` inserts the row; if the DB raises ``IntegrityError``
    matching the partial unique index
    ``UNIQUE WHERE idempotency_key IS NOT NULL`` (Slice 1), we
    look up the existing row by ``idempotency_key`` and return it.
    Not a non-portable ``INSERT ... ON CONFLICT`` — this uses only
    standard SQLAlchemy + DB-portable behaviour and works on both
    SQLite (test) and PostgreSQL (prod).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from goldsmith_erp.db.models import (
    Activity as ActivityModel,
)
from goldsmith_erp.db.models import (
    Material as MaterialModel,
)
from goldsmith_erp.db.models import (
    MetalPurchase as MetalPurchaseModel,
)
from goldsmith_erp.db.models import (
    Order as OrderModel,
)
from goldsmith_erp.db.models import (
    OrderStatusEnum,
)
from goldsmith_erp.db.models import (
    RepairJob as RepairJobModel,
)
from goldsmith_erp.db.models import (
    RepairJobStatus,
)
from goldsmith_erp.db.models import (
    ScanLog as ScanLogModel,
)
from goldsmith_erp.db.models import (
    User as UserModel,
)
from goldsmith_erp.db.models import (
    UserRole,
)
from goldsmith_erp.models.scanner import (
    ActionItem,
    ResolveResponse,
    ScanContext,
    ScanLogCreate,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Known prefix set
# --------------------------------------------------------------------------- #

# Spec §1.a: V1.1 ships 6 prefixes only. Remaining prefixes
# (CUSTOMER, SCRAP, INVOICE, CERT, REORDER, NAV, STATION) resolve to
# ``unknown`` intentionally until their wave lands. Keeping this as a
# frozenset (not an enum) so membership check is O(1) and the constant
# cannot be mutated at runtime.
KNOWN_PREFIXES_V1_1: FrozenSet[str] = frozenset(
    {"ORDER", "REPAIR", "METAL", "MATERIAL", "ACTIVITY", "INTERRUPT"}
)

# Entity-type token emitted in ``ResolveResponse.entity_type`` —
# canonical lowercase form. Separated from the prefix token so the API
# payload is snake_case while the wire prefix stays SHOUTY.
_PREFIX_TO_ENTITY_TYPE: Dict[str, str] = {
    "ORDER": "order",
    "REPAIR": "repair",
    "METAL": "metal_purchase",
    "MATERIAL": "material",
    "ACTIVITY": "activity",
    "INTERRUPT": "interruption",
}


# --------------------------------------------------------------------------- #
# Role-filtered field allow-lists  (R9 / Anna A3.3)
# --------------------------------------------------------------------------- #
#
# Every `*_FIELDS_BY_ROLE` dict is an allow-list. The projection helper
# :func:`_project_entity` intersects the set of ORM attributes actually
# populated with the role-specific set, so a VIEWER never receives
# fields that are not in `ORDER_FIELDS_BY_ROLE[VIEWER]`, regardless of
# ORM drift.
#
# Field philosophy:
#   * VIEWER       — identifiers + non-financial status/deadline data.
#   * GOLDSMITH    — everything VIEWER has + production-floor fields
#                    (title, alloy, ring_size_mm, current_location,
#                    punzierung status). No pricing.
#   * ADMIN        — everything GOLDSMITH has + financial fields
#                    (material cost, labor cost, margin, customer_id).


# ORDER — :class:`goldsmith_erp.db.models.Order`
ORDER_FIELDS_VIEWER: FrozenSet[str] = frozenset(
    {"id", "status", "deadline"}
)
ORDER_FIELDS_GOLDSMITH: FrozenSet[str] = ORDER_FIELDS_VIEWER | frozenset(
    {
        "title",
        "alloy",
        "ring_size_mm",
        "current_location",
        "punzierung_verified_at",
        "order_type",
        "surface_finish",
        "complexity_rating",
    }
)
ORDER_FIELDS_ADMIN: FrozenSet[str] = ORDER_FIELDS_GOLDSMITH | frozenset(
    {
        "customer_id",
        "price",
        "material_cost_calculated",
        "material_cost_override",
        "labor_cost",
        "labor_hours",
        "hourly_rate",
        "calculated_price",
        "profit_margin_percent",
    }
)

ORDER_FIELDS_BY_ROLE: Dict[UserRole, FrozenSet[str]] = {
    UserRole.VIEWER: ORDER_FIELDS_VIEWER,
    UserRole.GOLDSMITH: ORDER_FIELDS_GOLDSMITH,
    UserRole.ADMIN: ORDER_FIELDS_ADMIN,
}

# REPAIR — :class:`goldsmith_erp.db.models.RepairJob`
REPAIR_FIELDS_VIEWER: FrozenSet[str] = frozenset(
    {"id", "repair_number", "bag_number", "status",
     "estimated_completion_date"}
)
REPAIR_FIELDS_GOLDSMITH: FrozenSet[str] = REPAIR_FIELDS_VIEWER | frozenset(
    {"item_type", "metal_type", "diagnosis_notes"}
)
REPAIR_FIELDS_ADMIN: FrozenSet[str] = REPAIR_FIELDS_GOLDSMITH | frozenset(
    {"customer_id", "estimated_cost", "actual_cost", "estimated_value"}
)
REPAIR_FIELDS_BY_ROLE: Dict[UserRole, FrozenSet[str]] = {
    UserRole.VIEWER: REPAIR_FIELDS_VIEWER,
    UserRole.GOLDSMITH: REPAIR_FIELDS_GOLDSMITH,
    UserRole.ADMIN: REPAIR_FIELDS_ADMIN,
}

# METAL — :class:`goldsmith_erp.db.models.MetalPurchase`
# MetalPurchase is a financial entity (supplier invoices, price-per-gram).
# VIEWER gets *no* access — the caller returns an empty projection and
# no financial actions.
METAL_FIELDS_VIEWER: FrozenSet[str] = frozenset()  # deliberate empty set
METAL_FIELDS_GOLDSMITH: FrozenSet[str] = frozenset(
    {"id", "metal_type", "remaining_weight_g", "weight_g", "lot_number"}
)
METAL_FIELDS_ADMIN: FrozenSet[str] = METAL_FIELDS_GOLDSMITH | frozenset(
    {"price_total", "price_per_gram", "supplier", "invoice_number",
     "date_purchased"}
)
METAL_FIELDS_BY_ROLE: Dict[UserRole, FrozenSet[str]] = {
    UserRole.VIEWER: METAL_FIELDS_VIEWER,
    UserRole.GOLDSMITH: METAL_FIELDS_GOLDSMITH,
    UserRole.ADMIN: METAL_FIELDS_ADMIN,
}

# MATERIAL — :class:`goldsmith_erp.db.models.Material`
MATERIAL_FIELDS_VIEWER: FrozenSet[str] = frozenset(
    {"id", "name", "unit", "stock", "min_stock"}
)
MATERIAL_FIELDS_GOLDSMITH: FrozenSet[str] = MATERIAL_FIELDS_VIEWER | frozenset(
    {"description"}
)
MATERIAL_FIELDS_ADMIN: FrozenSet[str] = MATERIAL_FIELDS_GOLDSMITH | frozenset(
    {"unit_price", "supplier", "webshop_url"}
)
MATERIAL_FIELDS_BY_ROLE: Dict[UserRole, FrozenSet[str]] = {
    UserRole.VIEWER: MATERIAL_FIELDS_VIEWER,
    UserRole.GOLDSMITH: MATERIAL_FIELDS_GOLDSMITH,
    UserRole.ADMIN: MATERIAL_FIELDS_ADMIN,
}


# --------------------------------------------------------------------------- #
# Projection helper
# --------------------------------------------------------------------------- #


def _project_entity(
    entity: Any,
    allowed_fields: FrozenSet[str],
) -> Dict[str, Any]:
    """Return a dict of ``entity`` attributes whose names are in allow set.

    Uses ``getattr`` rather than ``__dict__`` so SQLAlchemy lazy-loaded
    columns work. Enum values are unwrapped to their raw string for
    JSON-friendly output. Datetimes are kept as ``datetime`` — Pydantic
    serialisation at the response layer handles ISO conversion.

    An allow-set of length 0 (e.g. ``METAL_FIELDS_VIEWER``) is a valid
    input and returns an empty dict — that is the deliberate
    "no-access" signal for financial entities viewed by VIEWER role.
    """
    if not allowed_fields:
        return {}
    projection: Dict[str, Any] = {}
    for field_name in allowed_fields:
        value = getattr(entity, field_name, None)
        # Unwrap SQLAlchemy Enum-typed columns to their raw string.
        # ``OrderStatusEnum.IN_PROGRESS.value == "in_progress"``.
        if hasattr(value, "value") and not isinstance(value, (bool, int, float, str)):
            value = value.value
        projection[field_name] = value
    return projection


# --------------------------------------------------------------------------- #
# Resolution pipeline
# --------------------------------------------------------------------------- #


class ScannerService:
    """Service facade — methods are ``@staticmethod`` and accept
    ``AsyncSession`` as first arg, matching the project convention
    (cf. ``TimeTrackingService``)."""

    # ------------------------------------------------------------------ #
    # Top-level entry point
    # ------------------------------------------------------------------ #

    @staticmethod
    async def resolve_payload(
        db: AsyncSession,
        raw_payload: str,
        context: ScanContext,
        user: UserModel,
    ) -> ResolveResponse:
        """Resolve a raw scan payload into an entity + Quick Actions.

        ``user`` is the authenticated :class:`User` ORM instance — its
        ``role`` drives both the projection allow-list and the action
        filter. Passing the ORM instance (rather than a role literal)
        keeps the contract compatible with future per-user rules
        (e.g. Meister vs. Lehrling differentiation).
        """
        # 1. Prefix match.
        prefix, rest = _split_prefix(raw_payload)
        if prefix in KNOWN_PREFIXES_V1_1:
            return await _resolve_prefix(db, prefix, rest, context, user)

        # 2. Alias lookup — stub. V1.1.5 wires this.
        alias_hit = await _lookup_alias(db, raw_payload)
        if alias_hit is not None:
            # The alias resolver returns a (prefix, rest) pair that has
            # already been validated to be a known prefix. Re-enter
            # the entity-handler branch with resolution_path="alias".
            aliased_prefix, aliased_rest = alias_hit
            response = await _resolve_prefix(
                db, aliased_prefix, aliased_rest, context, user
            )
            # Override the resolution_path emitted by the prefix handler.
            return response.model_copy(update={"resolution_path": "alias"})

        # 3. Numeric fallback — purely numeric strings map to ORDER:<n>.
        if raw_payload.isdigit():
            response = await _resolve_prefix(
                db, "ORDER", raw_payload, context, user
            )
            return response.model_copy(
                update={"resolution_path": "numeric_fallback"}
            )

        # 4. Unknown.
        return ResolveResponse(
            resolved=False,
            resolution_path="unknown",
            entity_type=None,
            entity_id=None,
            entity=None,
            actions=[],
            status_hint=None,
        )

    # ------------------------------------------------------------------ #
    # Action computation — recomputed every call, role-filtered
    # ------------------------------------------------------------------ #

    @staticmethod
    async def compute_actions(
        entity_type: str,
        entity: Any,
        context: ScanContext,
        user_role: UserRole,
    ) -> List[ActionItem]:
        """Return the action list for ``entity``, filtered by role.

        Allow-list dispatch: for every entity type we enumerate the
        candidate actions and include only those the role has
        permission for. ADMIN-only actions are absent for GOLDSMITH /
        VIEWER, GOLDSMITH / ADMIN-only actions are absent for VIEWER.
        """
        return _compute_actions_sync(entity_type, entity, context, user_role)

    # ------------------------------------------------------------------ #
    # Status-hint — short human-readable line
    # ------------------------------------------------------------------ #

    @staticmethod
    async def compute_status_hint(
        entity_type: str,
        entity: Any,
    ) -> Optional[str]:
        """Human-readable context line shown above the action list.

        Only reads fields that are present in **every** role's
        projection so no PII or financial info leaks via the hint.
        """
        if entity_type == "order":
            return _order_status_hint(entity)
        if entity_type == "repair":
            return _repair_status_hint(entity)
        return None

    # ------------------------------------------------------------------ #
    # Multi-entity search (role-filtered) — used by alias-register UI
    # ------------------------------------------------------------------ #

    @staticmethod
    async def search_entities(
        db: AsyncSession,
        query: str,
        types: Sequence[str],
        user: UserModel,
    ) -> List[Dict[str, Any]]:
        """Search across entity types, role-filtering results.

        VIEWER never sees financial-entity matches — ``metal_purchase``
        results are dropped for VIEWER even if the caller asked for
        them (M8, spec §8.b).
        """
        query = query.strip()
        if not query:
            return []
        results: List[Dict[str, Any]] = []
        role_allowed_types = _allowed_search_types(user.role, types)
        for type_token in role_allowed_types:
            if type_token == "order":
                results.extend(
                    await _search_orders(db, query, user.role)
                )
            elif type_token == "repair":
                results.extend(
                    await _search_repairs(db, query, user.role)
                )
            elif type_token == "metal_purchase":
                results.extend(
                    await _search_metal(db, query, user.role)
                )
            elif type_token == "material":
                results.extend(
                    await _search_materials(db, query, user.role)
                )
            # ACTIVITY / INTERRUPT are by-code, not searched here.
        return results

    # ------------------------------------------------------------------ #
    # scan_logs writers
    # ------------------------------------------------------------------ #

    @staticmethod
    async def log_scan(
        db: AsyncSession,
        user_id: int,
        event: ScanLogCreate,
    ) -> ScanLogModel:
        """Insert a ``scan_logs`` row.

        ``user_id`` comes from the JWT via the router — never from
        the request body.

        Idempotency: if ``event.idempotency_key`` is set and a row
        with that key already exists, we return the existing row
        rather than raising. Two strategies coexist:

          * Pre-insert check — quick SELECT to see if the key is
            taken. Cheap for the happy path (no-op), turns an
            INSERT into a read on the dedupe path.
          * Post-insert IntegrityError catch — race-safe. Two
            concurrent inserts with the same key will both hit
            IntegrityError on the loser; we re-query and return
            the winner's row.

        We do **both**: pre-insert SELECT for the common case, catch
        IntegrityError as the race-safe fallback.
        """
        # Pre-insert dedupe — covers the common "client retried the
        # same offline event" case without burning an INSERT attempt.
        if event.idempotency_key is not None:
            existing = await _find_by_idempotency_key(
                db, str(event.idempotency_key)
            )
            if existing is not None:
                return existing

        db_row = _build_scan_log_row(user_id, event)

        try:
            db.add(db_row)
            await db.commit()
            await db.refresh(db_row)
            return db_row
        except IntegrityError:
            # Race-safe retry: concurrent inserts with the same
            # idempotency_key hit here. Rollback the failed attempt
            # and return the row that won.
            await db.rollback()
            if event.idempotency_key is not None:
                existing = await _find_by_idempotency_key(
                    db, str(event.idempotency_key)
                )
                if existing is not None:
                    return existing
            # Not an idempotency-key collision — propagate so the
            # caller sees the real constraint violation.
            raise

    @staticmethod
    async def log_scan_batch(
        db: AsyncSession,
        user_id: int,
        events: List[ScanLogCreate],
    ) -> "BatchLogResponseDTO":
        """Insert up to 100 rows, per-row idempotency dedupe.

        Returns a summary DTO (not a Pydantic model — the Pydantic
        :class:`BatchLogResponse` is built by the router). Each row
        is wrapped in its own try/except so a single malformed event
        does not poison the whole batch. Validation failures are
        counted and a short reason string appended; individual row
        payloads are **not** returned (defence-in-depth, spec §8.a).
        """
        ingested = 0
        deduplicated = 0
        rejected = 0
        reasons: List[str] = []

        for event in events:
            # Pre-check dedupe. Catching IntegrityError still covers
            # the concurrent-insert race but is cheaper when the
            # client simply replays a known key.
            if event.idempotency_key is not None:
                existing = await _find_by_idempotency_key(
                    db, str(event.idempotency_key)
                )
                if existing is not None:
                    deduplicated += 1
                    continue

            db_row = _build_scan_log_row(user_id, event)
            try:
                db.add(db_row)
                await db.commit()
                await db.refresh(db_row)
                ingested += 1
            except IntegrityError as exc:
                await db.rollback()
                # Retry dedupe on the race. If still a collision —
                # counted as dedupe; otherwise as rejection.
                if event.idempotency_key is not None:
                    existing = await _find_by_idempotency_key(
                        db, str(event.idempotency_key)
                    )
                    if existing is not None:
                        deduplicated += 1
                        continue
                rejected += 1
                reason = _shorten_reason(str(exc))
                if reason not in reasons and len(reasons) < 10:
                    reasons.append(reason)
                # Logged for ops debugging but NO per-row detail in
                # the HTTP response.
                logger.warning(
                    "scan_logs batch insert rejected: %s", reason
                )
            except Exception as exc:  # pragma: no cover - defensive
                await db.rollback()
                rejected += 1
                reason = _shorten_reason(str(exc))
                if reason not in reasons and len(reasons) < 10:
                    reasons.append(reason)
                logger.warning(
                    "scan_logs batch insert rejected: %s", reason
                )

        return BatchLogResponseDTO(
            ingested=ingested,
            deduplicated=deduplicated,
            rejected=rejected,
            reasons=reasons,
        )


# --------------------------------------------------------------------------- #
# Plain DTO returned from `log_scan_batch` — router wraps into Pydantic.
# --------------------------------------------------------------------------- #


class BatchLogResponseDTO:
    """Lightweight value object returned by ``log_scan_batch``.

    Kept as a plain class (not a dataclass or Pydantic model) so the
    service layer does not import schemas from its own router layer —
    the router constructs :class:`BatchLogResponse` from this DTO.
    """

    __slots__ = ("ingested", "deduplicated", "rejected", "reasons")

    def __init__(
        self,
        *,
        ingested: int,
        deduplicated: int,
        rejected: int,
        reasons: List[str],
    ) -> None:
        self.ingested = ingested
        self.deduplicated = deduplicated
        self.rejected = rejected
        self.reasons = reasons


# --------------------------------------------------------------------------- #
# Internal helpers — kept module-level for easier testing.
# --------------------------------------------------------------------------- #


def _split_prefix(raw_payload: str) -> Tuple[str, str]:
    """Return ``(prefix, rest)``. Non-prefixed input returns ``("", raw)``."""
    if ":" not in raw_payload:
        return ("", raw_payload)
    prefix, _, rest = raw_payload.partition(":")
    # Prefix is canonical-uppercase on the wire. Strip whitespace so
    # CR/LF tails that slipped past the control-char filter don't
    # break matching (defensive — the schema validator strips these
    # already).
    return (prefix.strip().upper(), rest)


async def _lookup_alias(
    db: AsyncSession,
    raw_payload: str,
) -> Optional[Tuple[str, str]]:
    """V1.1 stub — returns ``None``. Wired in V1.1.5.

    The signature is preserved so the resolve pipeline does not need
    to branch at all when the alias table starts being populated.
    """
    # Deliberate no-op. Kept async so callers don't need to change
    # shape when the real implementation lands.
    del db, raw_payload
    return None


async def _resolve_prefix(
    db: AsyncSession,
    prefix: str,
    rest: str,
    context: ScanContext,
    user: UserModel,
) -> ResolveResponse:
    """Dispatch a prefix-matched payload to its entity handler."""
    entity_type = _PREFIX_TO_ENTITY_TYPE[prefix]

    # ACTIVITY and INTERRUPT are by-code shortcuts — no ORM lookup,
    # no entity dict; they return a resolved=True response with an
    # empty actions list (toast-only on the client per spec §4.f/g).
    if prefix == "ACTIVITY":
        return _build_activity_response(rest, context)
    if prefix == "INTERRUPT":
        return _build_interrupt_response(rest, context)

    # Entity prefixes need an integer ID.
    entity_id = _parse_entity_id(rest)
    if entity_id is None:
        # Prefix recognised but ID malformed — treat as unknown so the
        # client renders the generic "unbekannter Code" path.
        return ResolveResponse(
            resolved=False,
            resolution_path="unknown",
            entity_type=entity_type,
            entity_id=None,
            entity=None,
            actions=[],
            status_hint=None,
        )

    if prefix == "ORDER":
        return await _resolve_order(db, entity_id, context, user)
    if prefix == "REPAIR":
        return await _resolve_repair(db, entity_id, context, user)
    if prefix == "METAL":
        return await _resolve_metal(db, entity_id, context, user)
    if prefix == "MATERIAL":
        return await _resolve_material(db, entity_id, context, user)

    # Unreachable — prefix was already filtered against KNOWN_PREFIXES.
    return ResolveResponse(
        resolved=False,
        resolution_path="unknown",
        entity_type=entity_type,
        entity_id=entity_id,
        entity=None,
        actions=[],
        status_hint=None,
    )


def _parse_entity_id(rest: str) -> Optional[int]:
    """Parse the post-prefix segment as a positive integer.

    Anything that is not a pure positive integer is rejected. Matches
    spec §3.a — IDs are internal ``SERIAL`` integers.
    """
    rest = rest.strip()
    if not rest.isdigit():
        return None
    try:
        value = int(rest)
    except (TypeError, ValueError):  # pragma: no cover - belt+braces
        return None
    if value <= 0:
        return None
    return value


# ---------- Order ---------- #


async def _resolve_order(
    db: AsyncSession,
    order_id: int,
    context: ScanContext,
    user: UserModel,
) -> ResolveResponse:
    """Fetch order, project fields for role, compute actions."""
    result = await db.execute(
        select(OrderModel).where(OrderModel.id == order_id)
    )
    order = result.scalar_one_or_none()
    if order is None:
        return ResolveResponse(
            resolved=False,
            resolution_path="prefix",
            entity_type="order",
            entity_id=order_id,
            entity=None,
            actions=[],
            status_hint=None,
        )
    allowed = ORDER_FIELDS_BY_ROLE.get(user.role, ORDER_FIELDS_VIEWER)
    entity_dict = _project_entity(order, allowed)
    actions = _compute_actions_sync("order", order, context, user.role)
    status_hint = _order_status_hint(order)
    return ResolveResponse(
        resolved=True,
        resolution_path="prefix",
        entity_type="order",
        entity_id=order.id,
        entity=entity_dict,
        actions=actions,
        status_hint=status_hint,
    )


def _order_status_hint(order: Any) -> Optional[str]:
    """German short status line (spec §4.a)."""
    status = getattr(order, "status", None)
    status_value = getattr(status, "value", status)
    if status_value == OrderStatusEnum.IN_PROGRESS.value:
        return "In Bearbeitung"
    if status_value == OrderStatusEnum.WAITING_FOR_FITTING.value:
        return "Wartet auf Anprobe"
    if status_value == OrderStatusEnum.QUALITY_CHECK.value:
        return "Endkontrolle ausstehend"
    if status_value == OrderStatusEnum.COMPLETED.value:
        return "Fertig — Kunde noch nicht benachrichtigt"
    return None


# ---------- Repair ---------- #


async def _resolve_repair(
    db: AsyncSession,
    repair_id: int,
    context: ScanContext,
    user: UserModel,
) -> ResolveResponse:
    result = await db.execute(
        select(RepairJobModel).where(RepairJobModel.id == repair_id)
    )
    repair = result.scalar_one_or_none()
    if repair is None:
        return ResolveResponse(
            resolved=False,
            resolution_path="prefix",
            entity_type="repair",
            entity_id=repair_id,
            entity=None,
            actions=[],
            status_hint=None,
        )
    allowed = REPAIR_FIELDS_BY_ROLE.get(user.role, REPAIR_FIELDS_VIEWER)
    entity_dict = _project_entity(repair, allowed)
    actions = _compute_actions_sync("repair", repair, context, user.role)
    status_hint = _repair_status_hint(repair)
    return ResolveResponse(
        resolved=True,
        resolution_path="prefix",
        entity_type="repair",
        entity_id=repair.id,
        entity=entity_dict,
        actions=actions,
        status_hint=status_hint,
    )


def _repair_status_hint(repair: Any) -> Optional[str]:
    status = getattr(repair, "status", None)
    status_value = getattr(status, "value", status)
    if status_value == RepairJobStatus.RECEIVED.value:
        return "Eingegangen — Diagnose ausstehend"
    if status_value == RepairJobStatus.READY.value:
        return "Fertig — Kundenabholung ausstehend"
    return None


# ---------- Metal ---------- #


async def _resolve_metal(
    db: AsyncSession,
    metal_id: int,
    context: ScanContext,
    user: UserModel,
) -> ResolveResponse:
    result = await db.execute(
        select(MetalPurchaseModel).where(MetalPurchaseModel.id == metal_id)
    )
    metal = result.scalar_one_or_none()
    if metal is None:
        return ResolveResponse(
            resolved=False,
            resolution_path="prefix",
            entity_type="metal_purchase",
            entity_id=metal_id,
            entity=None,
            actions=[],
            status_hint=None,
        )
    # VIEWER gets no fields at all — financial entity (CLAUDE.md Data
    # Privacy Rules, "Financial Data"). We still emit a resolved=True
    # response so the client can render a "kein Zugriff"-style hint
    # rather than the unknown-code modal.
    allowed = METAL_FIELDS_BY_ROLE.get(user.role, METAL_FIELDS_VIEWER)
    entity_dict = _project_entity(metal, allowed)
    actions = _compute_actions_sync("metal_purchase", metal, context, user.role)
    return ResolveResponse(
        resolved=True,
        resolution_path="prefix",
        entity_type="metal_purchase",
        entity_id=metal.id,
        entity=entity_dict,
        actions=actions,
        status_hint=None,
    )


# ---------- Material ---------- #


async def _resolve_material(
    db: AsyncSession,
    material_id: int,
    context: ScanContext,
    user: UserModel,
) -> ResolveResponse:
    result = await db.execute(
        select(MaterialModel).where(MaterialModel.id == material_id)
    )
    material = result.scalar_one_or_none()
    if material is None:
        return ResolveResponse(
            resolved=False,
            resolution_path="prefix",
            entity_type="material",
            entity_id=material_id,
            entity=None,
            actions=[],
            status_hint=None,
        )
    allowed = MATERIAL_FIELDS_BY_ROLE.get(user.role, MATERIAL_FIELDS_VIEWER)
    entity_dict = _project_entity(material, allowed)
    actions = _compute_actions_sync("material", material, context, user.role)
    return ResolveResponse(
        resolved=True,
        resolution_path="prefix",
        entity_type="material",
        entity_id=material.id,
        entity=entity_dict,
        actions=actions,
        status_hint=None,
    )


# ---------- ACTIVITY / INTERRUPT shortcuts ---------- #


def _build_activity_response(
    code: str,
    context: ScanContext,
) -> ResolveResponse:
    """Toast-only response for ACTIVITY:<code>.

    No actions list — the client renders a toast and optionally
    switches the running timer's activity via a separate endpoint
    wired in Slice 5. No DB lookup here; the activity-code is
    forwarded verbatim for the toast.
    """
    clean = code.strip()
    # Sentinel entity dict carries the code so the client can render
    # "Aktivität: Hartlöten" without a round-trip. The code itself is
    # not PII — just a domain vocabulary token.
    return ResolveResponse(
        resolved=bool(clean),
        resolution_path="prefix",
        entity_type="activity",
        entity_id=None,
        entity={"code": clean} if clean else None,
        actions=[],
        status_hint=None,
    )


def _build_interrupt_response(
    code: str,
    context: ScanContext,
) -> ResolveResponse:
    """Toast-only response for INTERRUPT:<code>."""
    clean = code.strip()
    return ResolveResponse(
        resolved=bool(clean),
        resolution_path="prefix",
        entity_type="interruption",
        entity_id=None,
        entity={"code": clean} if clean else None,
        actions=[],
        status_hint=None,
    )


# --------------------------------------------------------------------------- #
# Action computation (sync — pure function)
# --------------------------------------------------------------------------- #
#
# Emitted action IDs — keep a single source of truth as a frozenset so
# tests can import and assert against the canonical list.
#
# NOTE: ``consume_material`` is GOLDSMITH/ADMIN only (financial write).
# ``change_status`` is GOLDSMITH/ADMIN only (workflow write).
# ``print_label``, ``open_entity`` are safe for all roles.

_ACTION_START_TIMER = ActionItem(
    id="start_timer", label="Timer starten", icon="play", primary=True
)
_ACTION_STOP_TIMER = ActionItem(
    id="stop_timer", label="Timer stoppen", icon="pause", primary=True
)
_ACTION_SWITCH_TIMER = ActionItem(
    id="switch_timer", label="Timer wechseln", icon="swap", primary=True
)
_ACTION_CHANGE_STATUS = ActionItem(
    id="change_status", label="Status ändern", icon="clipboard"
)
_ACTION_CHANGE_LOCATION = ActionItem(
    id="change_location", label="Lagerort ändern", icon="pin"
)
_ACTION_TAKE_PHOTO = ActionItem(
    id="take_photo", label="Foto aufnehmen", icon="camera"
)
_ACTION_ADD_MATERIAL = ActionItem(
    id="add_material", label="Material zuordnen", icon="gem"
)
_ACTION_ADD_NOTE = ActionItem(
    id="add_note", label="Notiz hinzufügen", icon="note"
)
_ACTION_CONTACT_CUSTOMER = ActionItem(
    id="contact_customer", label="Kunde kontaktieren", icon="phone"
)
_ACTION_PRINT_LABEL = ActionItem(
    id="print_label", label="Etikett drucken", icon="label"
)
_ACTION_OPEN_ENTITY = ActionItem(
    id="open_entity", label="Öffnen", icon="link"
)
_ACTION_PUNZIERUNG_CHECK = ActionItem(
    id="punzierung_check",
    label="Feingehalts-Punze kontrolliert",
    icon="stamp",
    primary=True,
)
# METAL
_ACTION_CONSUME_METAL = ActionItem(
    id="consume_material", label="Material entnehmen", icon="scale",
    primary=True,
)
_ACTION_CHECK_STOCK = ActionItem(
    id="check_stock", label="Bestand prüfen", icon="chart"
)
_ACTION_REORDER = ActionItem(
    id="reorder", label="Nachbestellen", icon="cart"
)
# REPAIR
_ACTION_ADVANCE_REPAIR = ActionItem(
    id="advance_repair", label="Status weiterschalten", icon="clipboard",
    primary=True,
)
_ACTION_REPAIR_DIAGNOSIS = ActionItem(
    id="repair_diagnosis", label="Diagnose eingeben", icon="magnifier"
)


def _compute_actions_sync(
    entity_type: str,
    entity: Any,
    context: ScanContext,
    user_role: UserRole,
) -> List[ActionItem]:
    # H13 — if the role's allow-list projection is empty for this
    # entity type, the user has no field-level access. Returning a
    # non-empty action list (e.g. ``open_entity``) in that case is a
    # sloppy UX: tapping the action lands on a "kein Zugriff" detail
    # page. Cleanest signal is an empty action list — the Quick-Action
    # Modal then renders the entity identifier only, no actions.
    #
    # Currently this triggers for VIEWER on METAL (METAL_FIELDS_VIEWER
    # is a deliberately empty frozenset). Future entity types that
    # add an empty-projection role inherit the same behaviour for
    # free.
    if _is_empty_projection(entity_type, user_role):
        return []

    if entity_type == "order":
        return _compute_order_actions(entity, context, user_role)
    if entity_type == "repair":
        return _compute_repair_actions(entity, context, user_role)
    if entity_type == "metal_purchase":
        return _compute_metal_actions(entity, context, user_role)
    if entity_type == "material":
        return _compute_material_actions(entity, context, user_role)
    # ACTIVITY / INTERRUPT — no actions (toast-only).
    return []


# Map of entity_type string to the role-keyed allow-list dict. Defined
# after the *_FIELDS_BY_ROLE constants exist (below). The lookup is
# populated lazily in _is_empty_projection to avoid a forward-reference
# tangle with the module's load order.
_FIELDS_BY_ROLE_LOOKUP: Dict[str, Dict[UserRole, FrozenSet[str]]] = {}


def _is_empty_projection(entity_type: str, user_role: UserRole) -> bool:
    """H13 — true if the role's allow-list for this entity is empty."""
    global _FIELDS_BY_ROLE_LOOKUP
    if not _FIELDS_BY_ROLE_LOOKUP:
        _FIELDS_BY_ROLE_LOOKUP = {
            "order": ORDER_FIELDS_BY_ROLE,
            "repair": REPAIR_FIELDS_BY_ROLE,
            "metal_purchase": METAL_FIELDS_BY_ROLE,
            "material": MATERIAL_FIELDS_BY_ROLE,
        }
    table = _FIELDS_BY_ROLE_LOOKUP.get(entity_type)
    if table is None:
        # activity / interruption have no field projection — not empty,
        # just not applicable. Default to False so the normal action
        # path runs.
        return False
    return len(table.get(user_role, frozenset())) == 0


def _compute_order_actions(
    order: Any,
    context: ScanContext,
    user_role: UserRole,
) -> List[ActionItem]:
    actions: List[ActionItem] = []

    # Timer logic — context-aware.
    running = context.running_timer_id
    running_order_id = context.current_order_id
    order_id = getattr(order, "id", None)

    if running and running_order_id and running_order_id != order_id:
        # Timer is on a different order — switch is primary.
        actions.append(_ACTION_SWITCH_TIMER)
    elif running and running_order_id == order_id:
        # Timer on this order — stop is primary.
        actions.append(_ACTION_STOP_TIMER)
    else:
        # No timer — start is primary.
        actions.append(_ACTION_START_TIMER)

    # Status-awareness — inject Punzierungs-Check for QUALITY_CHECK
    # when the role can write it (goldsmith/admin) and the order has
    # a declared alloy (spec §4.h, Henrik M4/R8).
    status_value = getattr(getattr(order, "status", None), "value", None)
    alloy = getattr(order, "alloy", None)
    if (
        status_value == OrderStatusEnum.QUALITY_CHECK.value
        and alloy
        and user_role in (UserRole.GOLDSMITH, UserRole.ADMIN)
    ):
        actions.append(_ACTION_PUNZIERUNG_CHECK)

    # Goldsmith / Admin — write-capable actions.
    if user_role in (UserRole.GOLDSMITH, UserRole.ADMIN):
        actions.append(_ACTION_CHANGE_STATUS)
        actions.append(_ACTION_CHANGE_LOCATION)
        actions.append(_ACTION_TAKE_PHOTO)
        actions.append(_ACTION_ADD_MATERIAL)
        actions.append(_ACTION_ADD_NOTE)
        actions.append(_ACTION_CONTACT_CUSTOMER)

    # Label printing — safe for all roles per spec §4.a.
    actions.append(_ACTION_PRINT_LABEL)
    actions.append(_ACTION_OPEN_ENTITY)
    return actions


def _compute_repair_actions(
    repair: Any,
    context: ScanContext,
    user_role: UserRole,
) -> List[ActionItem]:
    actions: List[ActionItem] = []
    status_value = getattr(getattr(repair, "status", None), "value", None)
    if user_role in (UserRole.GOLDSMITH, UserRole.ADMIN):
        actions.append(_ACTION_ADVANCE_REPAIR)
        # Timer-start only while the piece is actually being worked.
        if status_value == RepairJobStatus.IN_REPAIR.value:
            actions.append(_ACTION_START_TIMER)
        if status_value == RepairJobStatus.RECEIVED.value:
            actions.append(_ACTION_REPAIR_DIAGNOSIS)
        actions.append(_ACTION_TAKE_PHOTO)
        actions.append(_ACTION_ADD_NOTE)
    actions.append(_ACTION_PRINT_LABEL)
    actions.append(_ACTION_OPEN_ENTITY)
    return actions


def _compute_metal_actions(
    metal: Any,
    context: ScanContext,
    user_role: UserRole,
) -> List[ActionItem]:
    actions: List[ActionItem] = []
    if user_role == UserRole.VIEWER:
        # Dead branch after H13 — the empty-projection guard in
        # `_compute_actions_sync` returns [] before this function is
        # reached for VIEWER on METAL. Kept defensively so a future
        # call that bypasses the top-level guard still returns an
        # empty list (no access to financial entity).
        return actions
    # GOLDSMITH / ADMIN
    actions.append(_ACTION_CONSUME_METAL)
    actions.append(_ACTION_CHECK_STOCK)
    actions.append(_ACTION_REORDER)
    actions.append(_ACTION_PRINT_LABEL)
    actions.append(_ACTION_OPEN_ENTITY)
    return actions


def _compute_material_actions(
    material: Any,
    context: ScanContext,
    user_role: UserRole,
) -> List[ActionItem]:
    actions: List[ActionItem] = []
    if user_role in (UserRole.GOLDSMITH, UserRole.ADMIN):
        actions.append(_ACTION_CONSUME_METAL)  # reused id; semantically same
        actions.append(_ACTION_CHECK_STOCK)
        actions.append(_ACTION_REORDER)
    else:
        # VIEWER — read-only
        actions.append(_ACTION_CHECK_STOCK)
    actions.append(_ACTION_PRINT_LABEL)
    actions.append(_ACTION_OPEN_ENTITY)
    return actions


# --------------------------------------------------------------------------- #
# Search helpers
# --------------------------------------------------------------------------- #


def _allowed_search_types(
    role: UserRole,
    requested: Sequence[str],
) -> List[str]:
    """Intersect requested search types with role-allowed types.

    VIEWER cannot search financial entities — ``metal_purchase`` is
    always dropped for VIEWER, even if explicitly requested.
    """
    allowed_for_role: FrozenSet[str]
    if role == UserRole.VIEWER:
        allowed_for_role = frozenset({"order", "repair", "material"})
    else:
        allowed_for_role = frozenset(
            {"order", "repair", "metal_purchase", "material"}
        )
    return [t for t in requested if t in allowed_for_role]


async def _search_orders(
    db: AsyncSession,
    query: str,
    role: UserRole,
) -> List[Dict[str, Any]]:
    """Title-substring search. Cap at 20 hits per type."""
    stmt = (
        select(OrderModel)
        .where(OrderModel.title.ilike(f"%{query}%"))
        .limit(20)
    )
    result = await db.execute(stmt)
    allowed = ORDER_FIELDS_BY_ROLE.get(role, ORDER_FIELDS_VIEWER)
    return [
        {"type": "order", **_project_entity(row, allowed)}
        for row in result.scalars().all()
    ]


async def _search_repairs(
    db: AsyncSession,
    query: str,
    role: UserRole,
) -> List[Dict[str, Any]]:
    stmt = (
        select(RepairJobModel)
        .where(RepairJobModel.repair_number.ilike(f"%{query}%"))
        .limit(20)
    )
    result = await db.execute(stmt)
    allowed = REPAIR_FIELDS_BY_ROLE.get(role, REPAIR_FIELDS_VIEWER)
    return [
        {"type": "repair", **_project_entity(row, allowed)}
        for row in result.scalars().all()
    ]


async def _search_metal(
    db: AsyncSession,
    query: str,
    role: UserRole,
) -> List[Dict[str, Any]]:
    # VIEWER reaches _allowed_search_types filter first, but double-guard.
    if role == UserRole.VIEWER:
        return []
    stmt = (
        select(MetalPurchaseModel)
        .where(MetalPurchaseModel.lot_number.ilike(f"%{query}%"))
        .limit(20)
    )
    result = await db.execute(stmt)
    allowed = METAL_FIELDS_BY_ROLE.get(role, METAL_FIELDS_VIEWER)
    return [
        {"type": "metal_purchase", **_project_entity(row, allowed)}
        for row in result.scalars().all()
    ]


async def _search_materials(
    db: AsyncSession,
    query: str,
    role: UserRole,
) -> List[Dict[str, Any]]:
    stmt = (
        select(MaterialModel)
        .where(MaterialModel.name.ilike(f"%{query}%"))
        .limit(20)
    )
    result = await db.execute(stmt)
    allowed = MATERIAL_FIELDS_BY_ROLE.get(role, MATERIAL_FIELDS_VIEWER)
    return [
        {"type": "material", **_project_entity(row, allowed)}
        for row in result.scalars().all()
    ]


# --------------------------------------------------------------------------- #
# scan_logs helpers
# --------------------------------------------------------------------------- #


async def _find_by_idempotency_key(
    db: AsyncSession,
    key: str,
) -> Optional[ScanLogModel]:
    """SELECT the scan_logs row for a given idempotency key or None.

    The column is indexed (``idx_scan_idem``, Slice 1 unique partial
    index) so this is cheap on PostgreSQL. On SQLite (test DB) the
    index is still consulted.
    """
    result = await db.execute(
        select(ScanLogModel).where(ScanLogModel.idempotency_key == key)
    )
    return result.scalar_one_or_none()


def _build_scan_log_row(
    user_id: int,
    event: ScanLogCreate,
) -> ScanLogModel:
    """Construct a ScanLogModel from a validated client event.

    ``user_id`` is sourced from the JWT-derived router parameter —
    never from the event payload (:class:`StrictRequestBase` already
    rejects payload-level ``user_id`` at schema validation).

    ``retention_class`` is left at the column default
    (``'standard_24m'``, Slice 1 A1.6). The service layer does not
    override retention bucket at write time — the future retention
    engine owns that logic.
    """
    # Serialise the ScanContext (if provided) to plain dict so
    # SQLAlchemy's JSON column can persist it. Excluding unset keys so
    # downstream readers don't see spurious defaults.
    context_dict: Optional[Dict[str, Any]]
    if event.context is None:
        context_dict = None
    else:
        context_dict = event.context.model_dump(exclude_unset=True)

    idem_key = (
        str(event.idempotency_key) if event.idempotency_key else None
    )

    # ``scanned_at`` is server-set using UTC now. The composite PK on
    # the partitioned PostgreSQL table requires ``scanned_at`` to be
    # present at INSERT; providing it explicitly avoids a NOT NULL
    # violation on SQLite (where the default is not enforced by DDL).
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)

    return ScanLogModel(
        scanned_at=now,
        user_id=user_id,
        raw_payload=event.raw_payload,
        resolved_type=event.resolved_type,
        resolved_id=event.resolved_id,
        resolution_path=event.resolution_path,
        action_taken=event.action_taken,
        context=context_dict,
        offline_queued=event.offline_queued,
        idempotency_key=idem_key,
        client_tap_at=event.client_tap_at,
        server_resolved_at=now,
        fallback_reason=event.fallback_reason,
    )


def _shorten_reason(message: str) -> str:
    """Trim a DB-error message to a compact, non-leaking reason string.

    We keep only the first line, cap at 120 chars, and normalise common
    ``IntegrityError`` phrasings so we don't leak SQL fragments into
    the response payload.
    """
    first = (message or "").splitlines()[0] if message else ""
    compact = first.strip()[:120]
    if "UNIQUE" in compact.upper():
        return "unique_constraint_violation"
    if "FOREIGN KEY" in compact.upper() or "FK " in compact.upper():
        return "foreign_key_violation"
    if "NOT NULL" in compact.upper():
        return "not_null_violation"
    return compact or "unknown_error"
