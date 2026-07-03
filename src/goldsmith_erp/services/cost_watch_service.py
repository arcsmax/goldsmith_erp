# src/goldsmith_erp/services/cost_watch_service.py
"""
CostWatchService — §649 BGB Anzeigepflicht cost projection + threshold alerts.

Rolls up an order's actual-cost-so-far (material + gemstones + billable
labor) and compares it against the order's referenceable Quote
(Kostenvoranschlag). When the projected total crosses either the percent or
the absolute-EUR threshold (``settings.COST_ALERT_THRESHOLD_PERCENT`` /
``COST_ALERT_THRESHOLD_ABS_EUR``), a COST_ALERT Notification is raised for
every active ADMIN/GOLDSMITH user — deduplicated so the same still-unread
alert is not repeated on every subsequent crossing.

Material-cost-source decision (documented per plan Task 3):
    ``Order.material_cost_calculated`` is NOT authoritative for cumulative
    consumption — ``MetalInventoryService.consume_material`` OVERWRITES it
    with just the latest call's ``allocation.total_cost``
    (metal_inventory_service.py, "5. Update Order.material_cost_calculated":
    ``order.material_cost_calculated = allocation.total_cost``). An order
    consumed from in two separate ``consume_material`` calls (e.g. shank
    material, then a later repair/rework consumption) would lose the first
    call's cost entirely if that field were read here. ``MaterialUsage`` rows
    are never overwritten or deleted on this path, so
    ``SUM(MaterialUsage.cost_at_time)`` filtered by ``order_id`` is the only
    value that reflects the true cumulative material spend, and is what
    ``get_projected_cost`` uses.

Hook sites (post-commit, fire-and-forget — see ``safe_check``):
    - ``MetalInventoryService.consume_material``, after
      ``_safe_publish_material_event``.
    - ``TimeTrackingService.stop_time_entry``, after
      ``_check_and_publish_anomaly``.
Both call ``CostWatchService.safe_check(db, order_id)`` via a late import
(mirrors the ``_safe_publish`` / anomaly-detection guarded fire-and-forget
convention already used at both sites) so a failure here can never roll back
or interrupt the caller's already-committed mutation.

Approved-cost-change baseline (issue #27 fix):
    Once a customer APPROVES a §649 cost-change notice
    (``CostChangeRequest.status == APPROVED``), every subsequent material
    consumption / timer stop must stop comparing against the ORIGINAL
    quote's net subtotal — that overrun is exactly what the customer just
    approved. ``get_projected_cost`` now selects the latest (by
    ``created_at``, ties broken by ``id``) APPROVED CostChangeRequest for
    the order and, when one exists, uses its ``new_amount`` as the
    comparison baseline instead of the quote's ``subtotal``.
    ``CostChangeRequest.new_amount`` is set verbatim from
    ``CostChangeCreate.new_amount`` (cost_change_service.py ``create()``)
    and compared directly against ``original_amount`` — which is itself
    derived from THIS service's own ``quote_total`` (the NET quote
    subtotal, see the netto/brutto note above) — so ``new_amount`` is on
    the same NET basis as ``quote_total`` and no unit conversion is
    needed. If multiple APPROVED requests exist (e.g. a second approved
    change after the first was superseded is not possible via the normal
    flow, but nothing prevents more than one row reaching APPROVED across
    the order's lifetime), the most recent one wins. A DRAFT/SENT/
    DECLINED/SUPERSEDED request never moves the baseline. This baseline
    swap is reflected in ``ProjectedCost.quote_total`` (field name kept
    for API stability) and exposed explicitly via
    ``ProjectedCost.baseline_source``.

Dedup decision (documented per plan Task 3):
    Adapted from ``NotificationService.check_deadline_warnings``
    (notification_service.py:292-318), which checks per-TARGET-USER whether
    an unread notification of the relevant type already exists for the
    order, inside the loop that creates one row per user. This service
    mirrors that exact per-user structure (not a single global check across
    all recipients) — the existing test precedent
    (test_notification_service.py::test_deduplication_allows_new_notification_after_reading)
    demonstrates the per-user contract by marking each user's notifications
    read individually before asserting a re-alert. A global "any unread row
    for this order, from any user" check was considered and rejected: it
    would let one admin who already dealt with an alert silently suppress a
    fresh notification for a goldsmith who never saw the first one. The one
    change from the deadline-warning precedent is dropping the
    ``created_at``-range (today) bound — this alert is scoped by read state
    only, not by day, per the plan.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional, cast

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    Activity,
    CostChangeRequest,
    CostChangeStatus,
    Gemstone,
    MaterialUsage,
    Notification,
    NotificationSeverityEnum,
    NotificationTypeEnum,
    Order,
    Quote,
    QuoteStatus,
    TimeEntry,
    User,
    UserRole,
)
from goldsmith_erp.models.customer_update import ProjectedCost

logger = logging.getLogger(__name__)


class CostWatchService:
    """Static-method service — all methods accept AsyncSession as first arg."""

    # ------------------------------------------------------------------
    # Cost rollup
    # ------------------------------------------------------------------

    @staticmethod
    async def get_projected_cost(db: AsyncSession, order_id: int) -> ProjectedCost:
        """
        Compute the projected total cost for an order and, when a
        referenceable Quote exists, the delta against it.

        Rollup sources:
            - material_cost: SUM(MaterialUsage.cost_at_time) for the order
              (see module docstring for why this — not
              Order.material_cost_calculated — is authoritative).
            - gemstone_cost: SUM(Gemstone.cost * Gemstone.quantity) for the
              order (not Gemstone.total_cost — that column is nullable and
              may be stale; cost*quantity is always derivable).
            - labor_cost: billable-only minutes (Activity.is_billable),
              completed entries only (end_time IS NOT NULL), converted to
              hours × the order's hourly_rate, falling back to
              settings.DEFAULT_HOURLY_RATE when the order has none.

        Quote reference (None-safe): latest Quote for the order with status
        in (SENT, APPROVED); if none, fallback to the latest DRAFT Quote.
        When no Quote at all exists AND no approved cost change exists,
        quote_id/quote_total/delta_percent/delta_abs are None and
        over_threshold is False (nothing to compare against).

        NETTO/BRUTTO — the comparison basis is NET (Quote.subtotal), not
        gross (Quote.total): the cost rollup above is a net-cost figure
        (material cost_at_time, gemstone purchase cost, labor at the hourly
        rate — none carry VAT), so comparing it against the gross quote
        total (×1.19 by default) would systematically understate the
        overrun (a 15% percent threshold would only fire at ~37% real
        overrun), defeating the §649 early-warning purpose. Consequences:
        ``ProjectedCost.quote_total`` carries ``Quote.subtotal`` (the NET
        reference), ``delta_abs`` is in NET euros — so
        ``settings.COST_ALERT_THRESHOLD_ABS_EUR`` is interpreted as a NET
        amount — and ``delta_percent`` is scale-invariant (net-vs-net gives
        the legally correct percentage).

        Approved-cost-change baseline override (issue #27, see module
        docstring): if the order has a latest APPROVED CostChangeRequest,
        its ``new_amount`` (already NET, same basis) REPLACES the quote's
        subtotal as the comparison baseline for delta_abs/delta_percent/
        over_threshold — ``ProjectedCost.quote_total`` then carries
        ``new_amount``, not ``Quote.subtotal``, and
        ``ProjectedCost.baseline_source`` is set to ``"approved_change"``
        (else ``"quote"``, or ``None`` when neither exists). ``quote_id``
        still identifies the underlying reference Quote (if any) —
        independent of which value won the baseline — so callers can still
        link back to the original Kostenvoranschlag.

        delta_percent is None when the effective baseline is 0 (or neither
        a Quote nor an approved change exists) — a percentage delta against
        a zero total is not meaningful; over_threshold in that case falls
        back to the absolute-EUR comparison only.
        """
        order = (
            await db.execute(select(Order).where(Order.id == order_id))
        ).scalar_one_or_none()

        material_cost = (
            await db.execute(
                select(func.coalesce(func.sum(MaterialUsage.cost_at_time), 0.0)).where(
                    MaterialUsage.order_id == order_id
                )
            )
        ).scalar_one()

        gemstone_cost = (
            await db.execute(
                select(
                    func.coalesce(func.sum(Gemstone.cost * Gemstone.quantity), 0.0)
                ).where(Gemstone.order_id == order_id)
            )
        ).scalar_one()

        billable_minutes = (
            await db.execute(
                select(
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    Activity.is_billable.is_(True),
                                    TimeEntry.duration_minutes,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    )
                )
                .join(Activity, TimeEntry.activity_id == Activity.id)
                .where(
                    and_(
                        TimeEntry.order_id == order_id,
                        TimeEntry.end_time.isnot(None),
                    )
                )
            )
        ).scalar_one()

        # `is not None`, NOT truthiness: an explicit 0.0 rate (e.g. warranty
        # rework billed at zero) is a valid override and must not silently
        # fall back to the default rate.
        hourly_rate = (
            order.hourly_rate
            if order is not None and order.hourly_rate is not None
            else settings.DEFAULT_HOURLY_RATE
        )
        labor_cost = (billable_minutes / 60.0) * hourly_rate
        projected_total = material_cost + gemstone_cost + labor_cost

        quote = await CostWatchService._select_reference_quote(db, order_id)
        approved_change = await CostWatchService._select_latest_approved_cost_change(
            db, order_id
        )

        quote_id: Optional[int] = None
        baseline: Optional[float] = None
        baseline_source: Optional[Literal["quote", "approved_change"]] = None
        delta_abs: Optional[float] = None
        delta_percent: Optional[float] = None
        over_threshold = False

        if quote is not None:
            # cast(): mypy sees Column[int]/Column[float] at class level for
            # these attributes (classic Column() style, no Mapped[] here) —
            # at runtime, on a loaded instance, these are plain int/float.
            quote_id = cast(int, quote.id)

        if approved_change is not None:
            # Approved-cost-change baseline override (issue #27) — see
            # module docstring + this method's docstring. new_amount is
            # already NET, same basis as Quote.subtotal, no conversion.
            baseline = cast(float, approved_change.new_amount)
            baseline_source = "approved_change"
        elif quote is not None:
            # NET reference — Quote.subtotal, NOT Quote.total (gross incl.
            # VAT). See the netto/brutto note in this method's docstring.
            baseline = cast(float, quote.subtotal)
            baseline_source = "quote"

        if baseline is not None:
            delta_abs = projected_total - baseline
            delta_percent = (delta_abs / baseline) * 100.0 if baseline else None
            over_threshold = (
                delta_percent is not None
                and delta_percent >= settings.COST_ALERT_THRESHOLD_PERCENT
            ) or (delta_abs >= settings.COST_ALERT_THRESHOLD_ABS_EUR)

        return ProjectedCost(
            material_cost=round(material_cost, 2),
            gemstone_cost=round(gemstone_cost, 2),
            labor_minutes_billable=float(billable_minutes),
            labor_cost=round(labor_cost, 2),
            projected_total=round(projected_total, 2),
            quote_id=quote_id,
            quote_total=round(baseline, 2) if baseline is not None else None,
            delta_percent=(
                round(delta_percent, 2) if delta_percent is not None else None
            ),
            delta_abs=round(delta_abs, 2) if delta_abs is not None else None,
            over_threshold=bool(over_threshold),
            baseline_source=baseline_source,
        )

    @staticmethod
    async def get_projected_cost_or_404(
        db: AsyncSession, order_id: int
    ) -> Optional[ProjectedCost]:
        """
        Like ``get_projected_cost``, but returns ``None`` when the order
        itself does not exist — used ONLY by
        ``GET /orders/{id}/projected-cost`` (final-review fix: that
        endpoint must 404 on an unknown order rather than silently
        returning a cost breakdown computed against a fallback hourly
        rate for a non-existent order).

        ``get_projected_cost``'s own tolerant behaviour (defaulting
        ``hourly_rate`` when ``order`` is ``None``) is deliberately left
        untouched: ``check_order``'s fire-and-forget hook-site callers
        (``MetalInventoryService.consume_material``,
        ``TimeTrackingService.stop_time_entry``) only ever run against a
        real, just-mutated order and must keep their existing
        never-raises contract — they must not start branching on a
        lookup that "shouldn't" fail there.
        """
        order_exists = (
            await db.execute(select(Order.id).where(Order.id == order_id))
        ).scalar_one_or_none()
        if order_exists is None:
            return None
        return await CostWatchService.get_projected_cost(db, order_id)

    @staticmethod
    async def _select_reference_quote(
        db: AsyncSession, order_id: int
    ) -> Optional[Quote]:
        """Latest SENT/APPROVED Quote for the order; fallback latest DRAFT."""
        primary_stmt = (
            select(Quote)
            .where(
                and_(
                    Quote.order_id == order_id,
                    Quote.status.in_([QuoteStatus.SENT, QuoteStatus.APPROVED]),
                )
            )
            .order_by(Quote.created_at.desc())
            .limit(1)
        )
        quote = (await db.execute(primary_stmt)).scalar_one_or_none()
        if quote is not None:
            return quote

        fallback_stmt = (
            select(Quote)
            .where(and_(Quote.order_id == order_id, Quote.status == QuoteStatus.DRAFT))
            .order_by(Quote.created_at.desc())
            .limit(1)
        )
        return (await db.execute(fallback_stmt)).scalar_one_or_none()

    @staticmethod
    async def _select_latest_approved_cost_change(
        db: AsyncSession, order_id: int
    ) -> Optional[CostChangeRequest]:
        """Latest APPROVED CostChangeRequest for the order, if any (issue
        #27 baseline override — see module + get_projected_cost
        docstrings).

        Ordered by created_at desc, ties broken by id desc: two APPROVED
        rows for the same order could in principle share a created_at
        timestamp under a low-resolution clock (or in tests that stub
        datetime.utcnow), so the id tiebreak keeps "most recent" fully
        deterministic ("latest-of-multiple-approved wins" contract).
        """
        stmt = (
            select(CostChangeRequest)
            .where(
                and_(
                    CostChangeRequest.order_id == order_id,
                    CostChangeRequest.status == CostChangeStatus.APPROVED,
                )
            )
            .order_by(CostChangeRequest.created_at.desc(), CostChangeRequest.id.desc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Threshold check + alert
    # ------------------------------------------------------------------

    @staticmethod
    async def check_order(db: AsyncSession, order_id: int) -> Optional[ProjectedCost]:
        """
        Compute the projected cost and, if over threshold, raise a deduped
        COST_ALERT notification to all active ADMIN/GOLDSMITH users.

        Never raises — every stage is guarded so this is safe to call from
        a post-commit hook. Returns None only when the rollup itself failed
        (logged); otherwise always returns the computed ProjectedCost,
        whether or not an alert was actually created.
        """
        try:
            projected = await CostWatchService.get_projected_cost(db, order_id)
        except Exception:
            logger.error(
                "CostWatchService.get_projected_cost failed",
                extra={"order_id": order_id},
                exc_info=True,
            )
            return None

        if not projected.over_threshold:
            return projected

        try:
            await CostWatchService._raise_cost_alert(
                db, order_id=order_id, projected=projected
            )
        except Exception:
            logger.error(
                "CostWatchService failed to raise cost alert",
                extra={"order_id": order_id},
                exc_info=True,
            )

        return projected

    @staticmethod
    async def _raise_cost_alert(
        db: AsyncSession, *, order_id: int, projected: ProjectedCost
    ) -> None:
        """Create a COST_ALERT Notification for each ADMIN/GOLDSMITH user,
        deduped per-user against any still-unread COST_ALERT for this order
        (see module docstring for the dedup-scope decision)."""
        # Late import — avoids a module-load cycle risk and mirrors the
        # existing _safe_publish_material_event / anomaly-detection
        # convention of deferring cross-service imports to call time.
        from goldsmith_erp.services.notification_service import (  # noqa: PLC0415
            NotificationService,
        )

        target_users_result = await db.execute(
            select(User).where(
                and_(
                    User.is_active.is_(True),
                    User.role.in_([UserRole.ADMIN, UserRole.GOLDSMITH]),
                )
            )
        )
        target_users = target_users_result.scalars().all()

        percent_label = (
            f"{projected.delta_percent:.1f}%"
            if projected.delta_percent is not None
            else "n/a"
        )
        title = f"Kostenvoranschlag überschritten: Auftrag #{order_id}"
        message = (
            f"Auftrag #{order_id}: projizierte Kosten "
            f"{projected.projected_total:.2f} EUR überschreiten den "
            f"Kostenvoranschlag von {projected.quote_total:.2f} EUR "
            f"um {percent_label} ({projected.delta_abs:+.2f} EUR)."
        )

        for user in target_users:
            # .limit(1) + .first(), NOT scalar_one_or_none(): two unread
            # COST_ALERTs can legitimately coexist for the same user/order
            # (concurrent hook invocations racing the dedup check) —
            # scalar_one_or_none() would raise MultipleResultsFound and
            # abort the alert loop for the remaining users.
            dedup_stmt = (
                select(Notification.id)
                .where(
                    and_(
                        Notification.user_id == user.id,
                        Notification.related_order_id == order_id,
                        Notification.notification_type
                        == NotificationTypeEnum.COST_ALERT,
                        Notification.is_read.is_(False),
                    )
                )
                .limit(1)
            )
            existing = (await db.execute(dedup_stmt)).scalars().first()
            if existing is not None:
                continue  # Unread alert already outstanding for this user

            try:
                await NotificationService.create_notification(
                    db=db,
                    user_id=cast(int, user.id),
                    title=title,
                    message=message,
                    notification_type=NotificationTypeEnum.COST_ALERT,
                    severity=NotificationSeverityEnum.WARNING,
                    related_order_id=order_id,
                )
            except Exception:
                # create_notification self-commits; if that commit fails the
                # session is left in pending-rollback state and the next
                # user's dedup SELECT would raise (consultation_service.py
                # precedent — _ensure_follow_up_reminder's notification
                # guard).
                await db.rollback()
                logger.error(
                    "Failed to create COST_ALERT notification",
                    extra={"order_id": order_id, "user_id": user.id},
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Fire-and-forget hook entry point
    # ------------------------------------------------------------------

    @staticmethod
    async def safe_check(db: AsyncSession, order_id: Optional[int]) -> None:
        """
        Guarded fire-and-forget entry point for the post-commit hook sites
        (MetalInventoryService.consume_material,
        TimeTrackingService.stop_time_entry).

        Mirrors the ``_safe_publish`` convention: never raises, logs with
        IDs only (no user-text — CLAUDE.md PII rule), and is a no-op when
        order_id is None (defensive — both current hook sites always pass a
        concrete order_id since MaterialUsage.order_id and
        TimeEntry.order_id are NOT NULL, but this keeps the contract safe
        for any future caller with an optional order link).
        """
        if order_id is None:
            return
        try:
            await CostWatchService.check_order(db, order_id)
        except Exception:
            # check_order() already guards internally — this is a
            # belt-and-suspenders outer guard so a bug in check_order
            # itself can never propagate into the caller's flow.
            logger.error(
                "CostWatchService.safe_check failed unexpectedly",
                extra={"order_id": order_id},
                exc_info=True,
            )
