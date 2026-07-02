# src/goldsmith_erp/services/notification_service.py
"""
Notification service — business logic for in-app notifications.

Responsibilities:
- Persist Notification rows, scoped per recipient user.
- Publish real-time events to Redis channel ``notifications:{user_id}``
  so that connected WebSocket clients receive them immediately.
- Scan orders for approaching deadlines and materials for low stock,
  creating Notification rows for each affected user (ADMIN + GOLDSMITH).
- Deduplicate: do NOT create a deadline warning if an unread one already
  exists for the same order on the same day.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Import the module (not the function) so the unit-test conftest monkeypatch on
# goldsmith_erp.core.pubsub.publish_event actually intercepts our calls (see
# services/consultation_service.py for the pattern this follows).
from goldsmith_erp.core import pubsub
from goldsmith_erp.db.models import (
    Customer,
    Material,
    Notification,
    NotificationPreference,
    NotificationSeverityEnum,
    NotificationTypeEnum,
    Order,
    OrderStatusEnum,
    User,
    UserRole,
)
from goldsmith_erp.models.notification import NotificationCreate, NotificationRead

logger = logging.getLogger(__name__)

# Notification types that should trigger a customer email when a customer
# is associated with the notification. Internal-only types (LOW_STOCK,
# DEADLINE_WARNING, HANDOFF, COMMENT) are excluded — those are for
# workshop staff only.
_CUSTOMER_EMAIL_TYPES: frozenset[NotificationTypeEnum] = frozenset(
    [
        NotificationTypeEnum.ORDER_STATUS,
        NotificationTypeEnum.PICKUP_READY,
        NotificationTypeEnum.FITTING_REMINDER,
        NotificationTypeEnum.REPAIR_RECEIVED,
        NotificationTypeEnum.REPAIR_READY,
    ]
)

# Threshold below which a material stock triggers a LOW_STOCK alert.
# Using a simple fixed threshold for MVP — can be per-material later.
LOW_STOCK_THRESHOLD = 10.0


class NotificationService:
    """Static-method service — all methods accept AsyncSession as first arg."""

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def create_notification(
        db: AsyncSession,
        user_id: int,
        title: str,
        message: str,
        notification_type: NotificationTypeEnum,
        severity: NotificationSeverityEnum = NotificationSeverityEnum.INFO,
        related_order_id: Optional[int] = None,
        related_customer_id: Optional[int] = None,
    ) -> Notification:
        """
        Persist a notification row and publish it to Redis.

        The caller is responsible for committing the session if this is
        called outside a transaction block. Here we use flush() + commit()
        so the notification gets an ID before we publish.
        """
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            severity=severity,
            related_order_id=related_order_id,
            related_customer_id=related_customer_id,
        )
        db.add(notification)
        await db.commit()
        await db.refresh(notification)

        # Publish to Redis AFTER commit so the DB row is durable first.
        await NotificationService._publish_notification(notification)

        # Attempt customer email — failure must never block the caller.
        if notification_type in _CUSTOMER_EMAIL_TYPES and (
            related_customer_id or related_order_id
        ):
            await NotificationService._try_send_customer_email(
                db=db,
                notification=notification,
            )

        logger.info(
            "Notification created",
            extra={
                "notification_id": notification.id,
                "user_id": user_id,
                "type": notification_type.value,
                "severity": severity.value,
            },
        )
        return notification

    @staticmethod
    async def get_notifications(
        db: AsyncSession,
        user_id: int,
        unread_only: bool = False,
        limit: int = 50,
    ) -> List[Notification]:
        """
        Return notifications for a single user, newest first.

        Enforces per-user scoping — callers must never pass another user's ID
        unless they have an admin-level justification.
        """
        stmt = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_unread_count(db: AsyncSession, user_id: int) -> int:
        """Return the number of unread notifications for the user."""
        stmt = select(func.count(Notification.id)).where(
            and_(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def mark_as_read(
        db: AsyncSession, notification_id: int, user_id: int
    ) -> Optional[Notification]:
        """
        Mark a single notification as read.

        Returns None if the notification does not exist or belongs to a
        different user (silent 404 to avoid information leakage).
        """
        stmt = select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        result = await db.execute(stmt)
        notification = result.scalar_one_or_none()

        if notification is None:
            return None

        if not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.utcnow()
            await db.commit()
            await db.refresh(notification)

        return notification

    @staticmethod
    async def mark_all_read(db: AsyncSession, user_id: int) -> int:
        """
        Mark all unread notifications for a user as read.

        Returns the number of rows updated.
        """
        stmt = select(Notification).where(
            and_(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        )
        result = await db.execute(stmt)
        notifications = result.scalars().all()

        now = datetime.utcnow()
        count = 0
        for n in notifications:
            n.is_read = True
            n.read_at = now
            count += 1

        if count:
            await db.commit()

        return count

    # ------------------------------------------------------------------
    # Automated scans
    # ------------------------------------------------------------------

    @staticmethod
    async def check_deadline_warnings(db: AsyncSession) -> int:
        """
        Scan open orders for approaching deadlines and create notifications.

        Rules:
        - Warn at 1 day and 3 days before deadline (hard-coded for MVP; can
          be overridden per-user via NotificationPreference.advance_days).
        - Skip orders that are COMPLETED or DELIVERED.
        - Skip if an unread DEADLINE_WARNING notification already exists for
          the same order today (deduplication).
        - Notify all ADMIN and GOLDSMITH users.

        Returns the number of notifications created.
        """
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # Load all active orders with deadlines in the next 4 days
        stmt = select(Order).where(
            and_(
                Order.deadline.isnot(None),
                Order.deadline >= now,
                Order.deadline <= now + timedelta(days=4),
                Order.status.notin_([
                    OrderStatusEnum.COMPLETED,
                    OrderStatusEnum.DELIVERED,
                ]),
                Order.is_deleted.is_(False),
            )
        ).options(selectinload(Order.customer))

        result = await db.execute(stmt)
        orders = result.scalars().all()

        # Load all ADMIN and GOLDSMITH users
        users_stmt = select(User).where(
            and_(
                User.is_active.is_(True),
                User.role.in_([UserRole.ADMIN, UserRole.GOLDSMITH]),
            )
        )
        users_result = await db.execute(users_stmt)
        target_users = users_result.scalars().all()

        created_count = 0
        for order in orders:
            days_until = (order.deadline - now).days

            # Determine severity based on proximity
            if days_until <= 1:
                severity = NotificationSeverityEnum.URGENT
                days_label = "1 Tag" if days_until == 1 else "heute"
            elif days_until <= 3:
                severity = NotificationSeverityEnum.WARNING
                days_label = f"{days_until} Tagen"
            else:
                # 4 days out — only warning level
                severity = NotificationSeverityEnum.WARNING
                days_label = f"{days_until} Tagen"

            title = f"Deadline in {days_label}: Auftrag #{order.id}"
            message = (
                f"Auftrag #{order.id} \"{order.title}\" hat die Deadline in "
                f"{days_label}. Status: {order.status.value}."
            )

            for user in target_users:
                # Deduplication: skip if already notified today for this order
                existing_stmt = select(Notification).where(
                    and_(
                        Notification.user_id == user.id,
                        Notification.related_order_id == order.id,
                        Notification.notification_type == NotificationTypeEnum.DEADLINE_WARNING,
                        Notification.is_read.is_(False),
                        Notification.created_at >= today_start,
                        Notification.created_at < today_end,
                    )
                )
                existing_result = await db.execute(existing_stmt)
                if existing_result.scalar_one_or_none() is not None:
                    continue  # Already warned today

                await NotificationService.create_notification(
                    db=db,
                    user_id=user.id,
                    title=title,
                    message=message,
                    notification_type=NotificationTypeEnum.DEADLINE_WARNING,
                    severity=severity,
                    related_order_id=order.id,
                    related_customer_id=order.customer_id,
                )
                created_count += 1

        logger.info(
            "Deadline warning scan complete",
            extra={"orders_checked": len(orders), "notifications_created": created_count},
        )
        return created_count

    @staticmethod
    async def check_low_stock_alerts(db: AsyncSession) -> int:
        """
        Scan materials below LOW_STOCK_THRESHOLD and notify ADMIN users.

        Returns the number of notifications created.
        """
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        stmt = select(Material).where(Material.stock <= Material.min_stock)
        result = await db.execute(stmt)
        low_stock_materials = result.scalars().all()

        # Only notify ADMIN for stock alerts
        users_stmt = select(User).where(
            and_(
                User.is_active.is_(True),
                User.role == UserRole.ADMIN,
            )
        )
        users_result = await db.execute(users_stmt)
        admin_users = users_result.scalars().all()

        created_count = 0
        for material in low_stock_materials:
            title = f"Mindestbestand unterschritten: {material.name}"
            message = (
                f"Material \"{material.name}\" hat nur noch {material.stock} {material.unit} "
                f"auf Lager (Mindestbestand: {material.min_stock} {material.unit})."
            )

            for user in admin_users:
                # Deduplication per material per day
                existing_stmt = select(Notification).where(
                    and_(
                        Notification.user_id == user.id,
                        Notification.notification_type == NotificationTypeEnum.LOW_STOCK,
                        Notification.is_read.is_(False),
                        Notification.created_at >= today_start,
                        Notification.created_at < today_end,
                        # Use title as proxy for material identity (no FK to materials)
                        Notification.title == title,
                    )
                )
                existing_result = await db.execute(existing_stmt)
                if existing_result.scalar_one_or_none() is not None:
                    continue

                await NotificationService.create_notification(
                    db=db,
                    user_id=user.id,
                    title=title,
                    message=message,
                    notification_type=NotificationTypeEnum.LOW_STOCK,
                    severity=NotificationSeverityEnum.WARNING,
                )
                created_count += 1

        logger.info(
            "Low stock alert scan complete",
            extra={
                "materials_checked": len(low_stock_materials),
                "notifications_created": created_count,
            },
        )
        return created_count

    @staticmethod
    async def check_pickup_reminders(db: AsyncSession) -> int:
        """
        Scan COMPLETED orders and notify ADMIN + GOLDSMITH users that the order
        is ready for pickup.

        Rules:
        - Only orders with status COMPLETED and is_deleted == False.
        - Only fire when EITHER:
            a) The order's deadline is within the next 2 days (urgent pickup), OR
            b) The order has been in COMPLETED state for more than 3 days (overdue pickup).
        - Severity is INFO for deadline-approaching orders; WARNING for orders
          waiting more than 3 days without delivery.
        - Deduplicate: skip if an unread PICKUP_READY notification already exists
          for the same order today.
        - Include customer name in the notification message.

        Returns the number of notifications created.
        """
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        overdue_threshold = now - timedelta(days=3)
        deadline_window = now + timedelta(days=2)

        stmt = (
            select(Order)
            .where(
                and_(
                    Order.status == OrderStatusEnum.COMPLETED,
                    Order.is_deleted.is_(False),
                )
            )
            .options(selectinload(Order.customer))
        )
        result = await db.execute(stmt)
        all_completed = result.scalars().all()

        # Apply business-rule filter in Python to avoid complex OR SQL
        orders = [
            o for o in all_completed
            if (
                # Condition a: deadline approaching within 2 days
                (o.deadline is not None and o.deadline <= deadline_window)
                # Condition b: completed more than 3 days ago without delivery
                or (
                    getattr(o, "completed_at", None) is not None
                    and o.completed_at <= overdue_threshold
                )
            )
        ]

        users_stmt = select(User).where(
            and_(
                User.is_active.is_(True),
                User.role.in_([UserRole.ADMIN, UserRole.GOLDSMITH]),
            )
        )
        users_result = await db.execute(users_stmt)
        target_users = users_result.scalars().all()

        created_count = 0
        for order in orders:
            completed_at = getattr(order, "completed_at", None)
            days_waiting = (now - completed_at).days if completed_at else 0
            severity = (
                NotificationSeverityEnum.WARNING
                if days_waiting > 3
                else NotificationSeverityEnum.INFO
            )

            customer_name = (
                f"{order.customer.first_name} {order.customer.last_name}"
                if order.customer
                else f"Kunde #{order.customer_id}"
            )

            title = f"Auftrag #{order.id} abholbereit"
            message = (
                f"Auftrag #{order.id} \"{order.title}\" fuer {customer_name} "
                f"ist fertig und wartet auf Abholung."
            )
            if days_waiting > 3:
                message += f" Wartet seit {days_waiting} Tagen."

            for user in target_users:
                existing_stmt = select(Notification).where(
                    and_(
                        Notification.user_id == user.id,
                        Notification.related_order_id == order.id,
                        Notification.notification_type == NotificationTypeEnum.PICKUP_READY,
                        Notification.is_read.is_(False),
                        Notification.created_at >= today_start,
                        Notification.created_at < today_end,
                    )
                )
                existing_result = await db.execute(existing_stmt)
                if existing_result.scalar_one_or_none() is not None:
                    continue

                await NotificationService.create_notification(
                    db=db,
                    user_id=user.id,
                    title=title,
                    message=message,
                    notification_type=NotificationTypeEnum.PICKUP_READY,
                    severity=severity,
                    related_order_id=order.id,
                    related_customer_id=order.customer_id,
                )
                created_count += 1

        logger.info(
            "Pickup reminder scan complete",
            extra={
                "orders_checked": len(all_completed),
                "orders_eligible": len(orders),
                "notifications_created": created_count,
            },
        )
        return created_count

    @staticmethod
    async def check_fitting_reminders(db: AsyncSession) -> int:
        """
        Scan orders in WAITING_FOR_FITTING status and notify ADMIN + GOLDSMITH
        users to arrange a fitting appointment with the customer.

        Rules:
        - Only orders with status WAITING_FOR_FITTING and is_deleted == False.
        - Severity is always WARNING.
        - Deduplicate: skip if an unread FITTING_REMINDER notification already
          exists for the same order today.

        Returns the number of notifications created.
        """
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        stmt = select(Order).where(
            and_(
                Order.status == OrderStatusEnum.WAITING_FOR_FITTING,
                Order.is_deleted.is_(False),
            )
        )
        result = await db.execute(stmt)
        orders = result.scalars().all()

        users_stmt = select(User).where(
            and_(
                User.is_active.is_(True),
                User.role.in_([UserRole.ADMIN, UserRole.GOLDSMITH]),
            )
        )
        users_result = await db.execute(users_stmt)
        target_users = users_result.scalars().all()

        created_count = 0
        for order in orders:
            title = f"Anprobe erforderlich: Auftrag #{order.id}"
            message = (
                f"Anprobe fuer Auftrag #{order.id} \"{order.title}\" "
                f"-- Termin mit Kunden vereinbaren."
            )

            for user in target_users:
                existing_stmt = select(Notification).where(
                    and_(
                        Notification.user_id == user.id,
                        Notification.related_order_id == order.id,
                        Notification.notification_type == NotificationTypeEnum.FITTING_REMINDER,
                        Notification.is_read.is_(False),
                        Notification.created_at >= today_start,
                        Notification.created_at < today_end,
                    )
                )
                existing_result = await db.execute(existing_stmt)
                if existing_result.scalar_one_or_none() is not None:
                    continue

                await NotificationService.create_notification(
                    db=db,
                    user_id=user.id,
                    title=title,
                    message=message,
                    notification_type=NotificationTypeEnum.FITTING_REMINDER,
                    severity=NotificationSeverityEnum.WARNING,
                    related_order_id=order.id,
                    related_customer_id=order.customer_id,
                )
                created_count += 1

        logger.info(
            "Fitting reminder scan complete",
            extra={"orders_checked": len(orders), "notifications_created": created_count},
        )
        return created_count

    # ------------------------------------------------------------------
    # Customer email delivery (graceful degradation)
    # ------------------------------------------------------------------

    @staticmethod
    async def _try_send_customer_email(
        db: AsyncSession,
        notification: Notification,
    ) -> None:
        """
        Attempt to send a customer-facing email for order-lifecycle events.

        This method resolves the customer email from the DB and dispatches the
        appropriate typed EmailService method. All exceptions are caught here —
        email failure must NEVER propagate to the caller.

        PII note: the customer email address is resolved from the DB each time
        and never stored on the Notification row.
        """
        # Import lazily to avoid circular imports at module load time.
        from goldsmith_erp.services.email_service import EmailService

        try:
            customer_email: Optional[str] = None
            order: Optional[Order] = None

            # Resolve customer email — prefer direct customer link, fall back
            # to order's customer.
            if notification.related_customer_id:
                stmt = select(Customer).where(
                    Customer.id == notification.related_customer_id
                )
                result = await db.execute(stmt)
                customer = result.scalar_one_or_none()
                if customer:
                    customer_email = getattr(customer, "email", None)

            if not customer_email and notification.related_order_id:
                stmt = (
                    select(Order)
                    .where(Order.id == notification.related_order_id)
                    .options(selectinload(Order.customer))
                )
                result = await db.execute(stmt)
                order = result.scalar_one_or_none()
                if order and order.customer:
                    customer_email = getattr(order.customer, "email", None)

            if not customer_email:
                logger.debug(
                    "No customer email found for notification, skipping email",
                    extra={"notification_id": notification.id},
                )
                return

            ntype = notification.notification_type
            order_id = notification.related_order_id or 0

            if ntype == NotificationTypeEnum.PICKUP_READY:
                await EmailService.send_ready_for_pickup(
                    to=customer_email,
                    order_id=order_id,
                )
            elif ntype == NotificationTypeEnum.FITTING_REMINDER:
                # Fitting date is embedded in the notification message for now;
                # pass the message as a proxy until a structured field exists.
                await EmailService.send_fitting_reminder(
                    to=customer_email,
                    order_id=order_id,
                    fitting_date=notification.message[:80],
                )
            elif ntype == NotificationTypeEnum.REPAIR_RECEIVED:
                await EmailService.send_repair_received(
                    to=customer_email,
                    order_id=order_id,
                    description=notification.message[:120],
                    bag_number=str(order_id),
                )
            elif ntype == NotificationTypeEnum.REPAIR_READY:
                await EmailService.send_ready_for_pickup(
                    to=customer_email,
                    order_id=order_id,
                )
            elif ntype == NotificationTypeEnum.ORDER_STATUS:
                await EmailService.send_order_confirmed(
                    to=customer_email,
                    order_id=order_id,
                    deadline=None,
                )
            # All other types: no customer email — silently skip.

        except Exception as exc:
            logger.error(
                "Customer email dispatch failed — notification already persisted",
                extra={
                    "notification_id": notification.id,
                    "type": notification.notification_type.value,
                    "error": str(exc),
                },
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Real-time delivery
    # ------------------------------------------------------------------

    @staticmethod
    async def _publish_notification(notification: Notification) -> None:
        """
        Publish a notification payload to Redis channel ``notifications:{user_id}``.

        The WebSocket endpoint subscribes to this channel and forwards the
        JSON payload to the connected browser client in real time.
        """
        channel = f"notifications:{notification.user_id}"
        payload = json.dumps(
            {
                "id": notification.id,
                "title": notification.title,
                "message": notification.message,
                "notification_type": notification.notification_type.value,
                "severity": notification.severity.value,
                "related_order_id": notification.related_order_id,
                "related_customer_id": notification.related_customer_id,
                "is_read": notification.is_read,
                "created_at": notification.created_at.isoformat(),
            }
        )
        try:
            await pubsub.publish_event(channel, payload)
        except Exception as exc:
            # Delivery failure must NOT roll back the persisted notification.
            # The client will fetch unread notifications on next page load.
            logger.error(
                "Failed to publish notification to Redis",
                extra={
                    "notification_id": notification.id,
                    "user_id": notification.user_id,
                    "channel": channel,
                    "error": str(exc),
                },
                exc_info=True,
            )
