from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import logging

from goldsmith_erp.db.models import Order as OrderModel, Material, Customer, OrderStatusEnum, LocationHistory, TimeEntry
from goldsmith_erp.models.order import OrderCreate, OrderUpdate
from goldsmith_erp.core.pubsub import publish_event  # Import the Redis publish function
from goldsmith_erp.db.transaction import transactional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slice 5 — Punzierungs-Check guard constants (M4 / R8 / A5.3).
#
# The Feingehaltsgesetz / DIN 8238 require that any piece bearing a
# Feingehalts-Punze be verified before final handover. The ERP enforces
# this at the state-machine boundary: a transition to COMPLETED on an
# order with a declared alloy and no verified marks is refused.
#
# Orders without an alloy (e.g. silver sample pieces, gemstone-only
# repairs) are allowed through — the hallmark law doesn't apply.
# ---------------------------------------------------------------------------
_PUNZIERUNG_REQUIRED_TARGETS: frozenset[OrderStatusEnum] = frozenset(
    {OrderStatusEnum.COMPLETED}
)


class PunzierungRequiredError(HTTPException):
    """Raised when advancing to COMPLETED without a verified Punzierung (M4).

    409 with structured detail so the frontend can open the
    PunzierungsCheckModal directly from the error response instead of
    requiring a separate endpoint probe.
    """

    def __init__(self, *, order_id: int, alloy: str) -> None:
        super().__init__(
            status_code=409,
            detail={
                "code": "PUNZIERUNG_REQUIRED",
                "order_id": order_id,
                "alloy": alloy,
                "message": (
                    "Feingehalts-Punze muss vor Status COMPLETED geprueft werden."
                ),
            },
        )


def _check_punzierung_requirement(
    order: OrderModel,
    new_status: Optional[OrderStatusEnum],
    pending_marks: Optional[list],
) -> None:
    """Enforce the A5.3 guard at every status-write path.

    ``pending_marks`` carries the punzierung_verified_marks value that
    the same PATCH is about to apply, so a caller can complete-and-verify
    in a single request (used by the scan flow: scan ORDER:42, complete
    Punzierung + advance to COMPLETED in one round-trip).
    """
    if new_status not in _PUNZIERUNG_REQUIRED_TARGETS:
        return
    # Orders without an alloy are exempt — hallmark law only applies
    # to pieces that carry a Feingehalts-Punze.
    if not order.alloy:
        return

    # A piece counts as verified if EITHER the existing row has marks
    # OR the same update supplies them.
    existing_marks = order.punzierung_verified_marks or []
    pending = pending_marks or []
    if len(existing_marks) == 0 and len(pending) == 0:
        raise PunzierungRequiredError(
            order_id=order.id,
            alloy=order.alloy,
        )


class OrderService:

    @staticmethod
    def validate_for_confirmation(order: OrderModel) -> List[str]:
        """
        Prueft ob alle Pflichtfelder fuer eine Auftragsbestaetigung ausgefuellt sind.

        Returns a list of human-readable field names that are missing.
        An empty list means the order is ready for confirmation.

        Required for all orders:
          - customer_id (structural FK — always set)
          - title
          - metal_type
          - alloy
          - deadline

        Conditionally required:
          - ring_size_mm  when order_type contains 'ring'
        """
        missing: List[str] = []

        if not order.title or not order.title.strip():
            missing.append("Bezeichnung")
        if not order.metal_type:
            missing.append("Metallart")
        if not order.alloy:
            missing.append("Legierung")
        if not order.deadline:
            missing.append("Abgabetermin")

        # Ring-specific check
        order_type_str = order.order_type or ""
        if "ring" in order_type_str.lower() and not order.ring_size_mm:
            missing.append("Ringmass")

        return missing

    @staticmethod
    async def get_orders(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        customer_id: Optional[int] = None,
    ) -> List[OrderModel]:
        """
        Holt alle Aufträge mit Pagination.

        Uses eager loading to prevent N+1 queries when accessing relationships.
        Optionally filters by customer_id to avoid client-side filtering over large datasets.
        """
        query = (
            select(OrderModel)
            .options(
                selectinload(OrderModel.materials),
                selectinload(OrderModel.customer),
                selectinload(OrderModel.gemstones),  # FIXED: Added gemstones
            )
            .where(OrderModel.is_deleted == False)  # noqa: E712 — SQLAlchemy requires == not is
            .order_by(OrderModel.created_at.desc())
        )
        if customer_id is not None:
            query = query.where(OrderModel.customer_id == customer_id)
        result = await db.execute(query.offset(skip).limit(limit))
        return result.scalars().all()

    @staticmethod
    async def get_order(db: AsyncSession, order_id: int) -> Optional[OrderModel]:
        """
        Holt einen einzelnen Auftrag über seine ID.

        Uses eager loading to prevent N+1 queries when accessing relationships.
        """
        result = await db.execute(
            select(OrderModel)
            .options(
                selectinload(OrderModel.materials),
                selectinload(OrderModel.customer),
                selectinload(OrderModel.gemstones),  # FIXED: Added gemstones
            )
            .filter(OrderModel.id == order_id, OrderModel.is_deleted == False)  # noqa: E712
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create_order(db: AsyncSession, order_in: OrderCreate) -> OrderModel:
        """
        Erstellt einen neuen Auftrag mit transaktionaler Integrität.

        All database operations are wrapped in a transaction to ensure ACID properties.
        Event publishing happens after successful commit.
        """
        async with transactional(db):
            order_data = order_in.dict(exclude={"materials", "costing_method"})
            # OrderCreate uses 'costing_method' but the ORM column is 'costing_method_used'
            if order_in.costing_method is not None:
                order_data["costing_method_used"] = order_in.costing_method
            db_order = OrderModel(**order_data)

            # Materialien verknüpfen, falls angegeben
            if order_in.materials:
                material_results = await db.execute(
                    select(Material)
                    .filter(Material.id.in_(order_in.materials))
                )
                materials = material_results.scalars().all()

                # Validate all materials exist
                if len(materials) != len(order_in.materials):
                    found_ids = {m.id for m in materials}
                    missing_ids = set(order_in.materials) - found_ids
                    raise ValueError(f"Materials not found: {missing_ids}")

                db_order.materials = materials

            db.add(db_order)
            # Flush to get the ID before commit
            await db.flush()

        # Re-fetch with eager loading after commit so relationships are available
        # for response serialization without requiring an active greenlet
        db_order = await OrderService.get_order(db, db_order.id)

        # Publish event to Redis AFTER successful transaction commit
        # If this fails, the order is still created (eventual consistency)
        try:
            await publish_event(
                "order_updates",
                json.dumps({
                    "action": "create",
                    "source": "manual",  # A5.4 — non-scan creation
                    "order_id": db_order.id,
                    "status": db_order.status.value if hasattr(db_order.status, "value") else db_order.status,
                    "data": {
                        "id": db_order.id,
                        "customer_id": db_order.customer_id,
                        "title": db_order.title if hasattr(db_order, "title") else None,
                        "created_at": db_order.created_at.isoformat() if hasattr(db_order, "created_at") else None,
                        "status": db_order.status.value if hasattr(db_order.status, "value") else db_order.status,
                        "price": str(db_order.price) if db_order.price else None,
                    }
                })
            )
        except Exception as e:
            # Log but don't fail the request if event publishing fails
            logger.error(f"Failed to publish order creation event: {str(e)}", exc_info=True)

        return db_order
    
    @staticmethod
    async def advance_status(
        db: AsyncSession,
        order_id: int,
        target_status: OrderStatusEnum,
        user_id: Optional[int] = None,
        *,
        punzierung_verified_marks: Optional[List[str]] = None,
    ) -> Optional[OrderModel]:
        """Status-transition entry point used by the scan flow (Slice 5).

        This is a thin wrapper over :meth:`update_order` — the guard
        logic (``_check_punzierung_requirement``) lives inside
        ``update_order`` so every status-write path, scan or admin,
        goes through the same check. ``advance_status`` exists as a
        clear name for the scan router to call and to pass the
        goldsmith's ``user_id`` as ``punzierung_verified_by`` when marks
        are supplied.
        """
        payload: Dict[str, Any] = {"status": target_status}
        if punzierung_verified_marks is not None:
            payload["punzierung_verified_marks"] = list(punzierung_verified_marks)
            payload["punzierung_verified_at"] = datetime.utcnow()

        # Use OrderUpdate so the guard path is exercised. We bypass the
        # Pydantic request schema at the Pydantic level by constructing
        # OrderUpdate directly — validators still run.
        order_in = OrderUpdate(**payload)
        updated = await OrderService.update_order(
            db,
            order_id,
            order_in,
            verified_by_user_id=user_id,
            origin="scan",
        )
        return updated

    @staticmethod
    async def update_order(
        db: AsyncSession,
        order_id: int,
        order_in: OrderUpdate,
        *,
        verified_by_user_id: Optional[int] = None,
        origin: str = "manual",
    ) -> Optional[OrderModel]:
        """
        Aktualisiert einen bestehenden Auftrag mit transaktionaler Integrität.

        All database operations are wrapped in a transaction to ensure ACID properties.

        When status transitions to COMPLETED or DELIVERED for the first time,
        the following ML data fields are auto-populated:
          - completed_at: set to utcnow()
          - actual_hours: calculated from closed time entries minus interruptions
        """
        # Zuerst prüfen, ob der Auftrag existiert
        order = await OrderService.get_order(db, order_id)
        if not order:
            return None

        update_data = order_in.dict(exclude_unset=True, exclude={"costing_method"})

        # OrderUpdate uses 'costing_method' but the ORM column is 'costing_method_used'
        if order_in.costing_method is not None:
            update_data["costing_method_used"] = order_in.costing_method

        new_status = update_data.get("status")

        # ------------------------------------------------------------------
        # Slice 5 / M4 / R8 / A5.3 — Punzierungs-Check guard.
        #
        # This guard fires for EVERY call into update_order, regardless of
        # whether the caller is a scan flow, the admin PATCH endpoint, or
        # an import/bulk tool that lands here. Status-write paths that
        # bypass OrderService.update_order are enumerated in the Slice 5
        # report; any new path MUST also call _check_punzierung_requirement.
        # ------------------------------------------------------------------
        pending_marks = update_data.get("punzierung_verified_marks")
        _check_punzierung_requirement(order, new_status, pending_marks)

        # A2.8 — when a Punzierungs-Check is recorded (first time marks
        # are supplied), tag retention_class='hallmark_10y' for the
        # Feingehaltsgesetz retention bucket. Only promote, never demote.
        if (
            pending_marks is not None
            and len(pending_marks) > 0
            and (order.punzierung_verified_marks is None
                 or len(order.punzierung_verified_marks) == 0)
        ):
            update_data["retention_class"] = "hallmark_10y"
            # Auto-populate verification timestamp if the caller left it
            # unset. verified_by is sourced from the caller-supplied
            # verified_by_user_id (which the router threads from
            # current_user.id); never trust a client-supplied value.
            if update_data.get("punzierung_verified_at") is None:
                update_data["punzierung_verified_at"] = datetime.utcnow()
            if verified_by_user_id is not None:
                update_data["punzierung_verified_by"] = verified_by_user_id

        # Guard: status transition to CONFIRMED requires all Pflichtfelder
        if new_status == OrderStatusEnum.CONFIRMED:
            # Merge pending update data with current order state for validation
            # (the update may itself supply the missing fields)
            class _MergedOrder:
                """Lightweight proxy that overlays update_data onto the current order."""
                def __getattr__(self, name: str):
                    if name in update_data:
                        return update_data[name]
                    return getattr(order, name)

            merged = _MergedOrder()
            missing = OrderService.validate_for_confirmation(merged)  # type: ignore[arg-type]
            if missing:
                raise ValueError(
                    f"Pflichtfelder nicht ausgefuellt: {', '.join(missing)}"
                )

        # Detect completion transition: only set completed_at once (idempotent)
        _completion_statuses = {OrderStatusEnum.COMPLETED, OrderStatusEnum.DELIVERED}
        is_completing = (
            new_status in _completion_statuses
            and order.status not in _completion_statuses
        )
        if is_completing and order.completed_at is None:
            update_data["completed_at"] = datetime.utcnow()

        async with transactional(db):
            # Update durchführen
            await db.execute(
                update(OrderModel)
                .where(OrderModel.id == order_id)
                .values(**update_data)
            )
            # Flush to ensure update is visible in same transaction
            await db.flush()

            # Auto-calculate actual_hours from time entries inside the same transaction.
            # Import here to avoid circular dependency at module level.
            if is_completing:
                from goldsmith_erp.services.ml_data_service import MLDataService  # noqa: PLC0415
                await MLDataService.auto_calculate_actual_hours(db, order_id)

        # Aktualisiertes Objekt holen after transaction commits
        updated_order = await OrderService.get_order(db, order_id)

        # A5.4 + A5.5 — publish with source=origin envelope + in-app
        # notification on failure so stale-widget retry loops don't
        # create duplicate scans.
        await OrderService._safe_publish_order_event(
            db=db,
            order=updated_order,
            action="update",
            source=origin,
            user_id=verified_by_user_id,
        )

        return updated_order

    @staticmethod
    async def _safe_publish_order_event(
        *,
        db: AsyncSession,
        order: OrderModel,
        action: str,
        source: str,
        user_id: Optional[int],
    ) -> None:
        """Publish order_updates + notify user on pubsub failure (A5.4 / A5.5)."""
        envelope = {
            "action": action,
            "source": source,
            "order_id": order.id,
            "status": (
                order.status.value if hasattr(order.status, "value") else order.status
            ),
            "data": {
                "id": order.id,
                "customer_id": order.customer_id,
                "title": order.title if hasattr(order, "title") else None,
                "updated_at": (
                    order.updated_at.isoformat()
                    if hasattr(order, "updated_at") and order.updated_at
                    else None
                ),
                "status": (
                    order.status.value
                    if hasattr(order.status, "value")
                    else order.status
                ),
                "price": str(order.price) if order.price else None,
            },
        }
        publish_ok = False
        try:
            await publish_event("order_updates", json.dumps(envelope))
            publish_ok = True
        except Exception as e:
            logger.error(
                f"Failed to publish order update event: {str(e)}",
                exc_info=True,
            )

        if publish_ok or user_id is None:
            return

        try:
            from goldsmith_erp.services.notification_service import (  # noqa: PLC0415
                NotificationService,
            )
            from goldsmith_erp.db.models import (  # noqa: PLC0415
                NotificationSeverityEnum,
                NotificationTypeEnum,
            )

            await NotificationService.create_notification(
                db=db,
                user_id=user_id,
                title="Auftragsaenderung nicht live verteilt",
                message=(
                    "Die Aenderung wurde gespeichert, aber andere Geraete "
                    "erfahren sie nicht automatisch. Bitte Seite neu laden."
                ),
                notification_type=NotificationTypeEnum.SYSTEM,
                severity=NotificationSeverityEnum.WARNING,
                related_order_id=order.id,
            )
        except Exception as notify_exc:
            logger.error(
                "Failed to write order pubsub-failure notification",
                extra={"user_id": user_id, "order_id": order.id, "error": str(notify_exc)},
                exc_info=True,
            )
    
    @staticmethod
    async def delete_order(db: AsyncSession, order_id: int) -> Dict[str, Any]:
        """
        Soft-loescht einen Auftrag (setzt is_deleted=True, deleted_at=utcnow).

        Hard delete is intentionally avoided — financial audit trail must be
        preserved.  GDPR erasure requests are handled separately via the
        customer anonymisation workflow.

        Deletion is blocked when:
          - The order has open (non-completed) time entries — the goldsmith is
            still actively working on it.
          - The order has invoices in status other than CANCELLED — altering the
            financial record would break the Rechnungsprufung audit trail.

        Returns:
            {"success": True}  on success
            {"success": False, "message": "..."}  when blocked
        """
        order = await OrderService.get_order(db, order_id)
        if not order:
            return {"success": False, "message": "Auftrag nicht gefunden"}

        if order.is_deleted:
            return {"success": False, "message": "Auftrag wurde bereits geloescht"}

        # Block if open time entries exist
        time_entry_result = await db.execute(
            select(TimeEntry)
            .where(
                TimeEntry.order_id == order_id,
                TimeEntry.end_time.is_(None),
            )
            .limit(1)
        )
        open_time_entry = time_entry_result.scalar_one_or_none()
        if open_time_entry is not None:
            return {
                "success": False,
                "message": "Auftrag kann nicht geloescht werden: offene Zeiterfassungen vorhanden",
            }

        # Block if non-cancelled invoices exist (import inline to avoid circular deps)
        try:
            from goldsmith_erp.db.models import Invoice, InvoiceStatus  # noqa: PLC0415
            invoice_result = await db.execute(
                select(Invoice)
                .where(
                    Invoice.order_id == order_id,
                    Invoice.status != InvoiceStatus.CANCELLED,
                )
                .limit(1)
            )
            active_invoice = invoice_result.scalar_one_or_none()
            if active_invoice is not None:
                return {
                    "success": False,
                    "message": "Auftrag kann nicht geloescht werden: aktive Rechnung vorhanden",
                }
        except Exception:
            # Invoice model may not exist in all deployments — skip the check
            pass

        async with transactional(db):
            await db.execute(
                update(OrderModel)
                .where(OrderModel.id == order_id)
                .values(is_deleted=True, deleted_at=datetime.utcnow())
            )

        # Publish event to Redis AFTER successful transaction commit
        try:
            await publish_event(
                "order_updates",
                json.dumps({
                    "action": "delete",
                    "order_id": order_id,
                    "message": f"Auftrag {order_id} wurde geloescht",
                })
            )
        except Exception as e:
            logger.error(f"Failed to publish order deletion event: {str(e)}", exc_info=True)

        return {"success": True}

    @staticmethod
    async def change_location(
        db: AsyncSession,
        order_id: int,
        location: str,
        user_id: int,
    ) -> Optional[OrderModel]:
        """
        Setzt den aktuellen Lagerort eines Auftrags und schreibt einen Verlaufseintrag.

        Both the order update and the LocationHistory insert are committed in a
        single transaction.  The WebSocket event is published after commit to
        keep the real-time feed in sync.
        """
        order = await OrderService.get_order(db, order_id)
        if not order:
            return None

        async with transactional(db):
            await db.execute(
                update(OrderModel)
                .where(OrderModel.id == order_id)
                .values(current_location=location, updated_at=datetime.utcnow())
            )
            history_entry = LocationHistory(
                order_id=order_id,
                location=location,
                changed_by=user_id,
            )
            db.add(history_entry)
            await db.flush()

        updated_order = await OrderService.get_order(db, order_id)

        try:
            await publish_event(
                "order_updates",
                json.dumps({
                    "action": "location_change",
                    "order_id": order_id,
                    "location": location,
                    "changed_by": user_id,
                })
            )
        except Exception as e:
            logger.error(
                f"Failed to publish location change event for order {order_id}: {e}",
                exc_info=True,
            )

        return updated_order

    @staticmethod
    async def get_location_history(
        db: AsyncSession,
        order_id: int,
    ) -> List[LocationHistory]:
        """Gibt den vollständigen Lagerort-Verlauf eines Auftrags zurück."""
        result = await db.execute(
            select(LocationHistory)
            .where(LocationHistory.order_id == order_id)
            .order_by(LocationHistory.timestamp.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def get_orders_with_deadlines(
        db: AsyncSession,
        start: Optional[str] = None,
        end: Optional[str] = None
    ) -> List[OrderModel]:
        """Get orders with deadlines for calendar view."""
        query = (
            select(OrderModel)
            .where(OrderModel.deadline.isnot(None))
            .options(selectinload(OrderModel.customer))
            .order_by(OrderModel.deadline)
        )
        if start:
            query = query.where(OrderModel.deadline >= datetime.fromisoformat(start))
        if end:
            query = query.where(OrderModel.deadline <= datetime.fromisoformat(end))
        result = await db.execute(query)
        return result.scalars().all()