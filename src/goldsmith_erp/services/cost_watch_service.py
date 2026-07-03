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
from typing import Optional, cast

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    Activity,
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
        When no Quote at all exists, quote_id/quote_total/delta_percent/
        delta_abs are None and over_threshold is False (nothing to compare
        against).

        delta_percent is None when a Quote exists but its total is 0 (or
        the order has no quote at all) — a percentage delta against a
        zero total is not meaningful; over_threshold in that case falls
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

        hourly_rate = (
            order.hourly_rate
            if order is not None and order.hourly_rate
            else settings.DEFAULT_HOURLY_RATE
        )
        labor_cost = (billable_minutes / 60.0) * hourly_rate
        projected_total = material_cost + gemstone_cost + labor_cost

        quote = await CostWatchService._select_reference_quote(db, order_id)

        quote_id: Optional[int] = None
        quote_total: Optional[float] = None
        delta_abs: Optional[float] = None
        delta_percent: Optional[float] = None
        over_threshold = False

        if quote is not None:
            # cast(): mypy sees Column[int]/Column[float] at class level for
            # these attributes (classic Column() style, no Mapped[] here) —
            # at runtime, on a loaded instance, these are plain int/float.
            quote_id = cast(int, quote.id)
            quote_total = cast(float, quote.total)
            delta_abs = projected_total - quote_total
            delta_percent = (delta_abs / quote_total) * 100.0 if quote_total else None
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
            quote_total=round(quote_total, 2) if quote_total is not None else None,
            delta_percent=(
                round(delta_percent, 2) if delta_percent is not None else None
            ),
            delta_abs=round(delta_abs, 2) if delta_abs is not None else None,
            over_threshold=bool(over_threshold),
        )

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
            dedup_stmt = select(Notification.id).where(
                and_(
                    Notification.user_id == user.id,
                    Notification.related_order_id == order_id,
                    Notification.notification_type == NotificationTypeEnum.COST_ALERT,
                    Notification.is_read.is_(False),
                )
            )
            existing = (await db.execute(dedup_stmt)).scalar_one_or_none()
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
