# src/goldsmith_erp/services/outbox_service.py
"""
Transactional outbox (ARCH-04 / ARCH-05, ADR-2026-09-25-outbox).

Producers call ``OutboxService.enqueue`` inside the transaction that makes
the business change, so the message exists if and only if the change was
committed (a rollback removes it). The worker (``python -m
goldsmith_erp.worker``) calls ``OutboxService.run_once`` in a loop:

1. ``lease_due`` picks due rows (``pending``/``failed`` with
   ``next_attempt_at <= now``) with ``FOR UPDATE SKIP LOCKED`` on
   PostgreSQL (a plain SELECT on SQLite), increments ``attempts`` and pushes
   ``next_attempt_at`` out by ``OUTBOX_LEASE_SECONDS``. That commit is the
   lease: a second worker skips the row, and a worker that dies mid-send
   leaves it to be retried once the lease runs out.
2. ``process`` runs the handler for the row's ``kind``. A handler returns
   True when the message was delivered (or no longer needs delivering) and
   False on a failure worth retrying; an exception counts as False.
3. Success -> ``sent``. Failure -> ``failed`` with exponential backoff
   (``OUTBOX_BACKOFF_BASE_SECONDS * 2**(attempts-1)``, capped at
   ``OUTBOX_BACKOFF_MAX_SECONDS``) until ``OUTBOX_MAX_ATTEMPTS``, then
   ``dead`` and the handler's ``on_dead`` hook (e.g. flip the CustomerUpdate
   to SEND_FAILED and notify the sender).

Payloads carry ids only; ``last_error`` carries a short code or exception
class name, never an address, subject or body. Log lines carry ids only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import OutboxMessage, OutboxStatus
from goldsmith_erp.db.transaction import transactional

logger = logging.getLogger(__name__)

MAX_ERROR_LEN = 500
DUE_STATUSES = (OutboxStatus.PENDING.value, OutboxStatus.FAILED.value)
RETRYABLE_STATUSES = (OutboxStatus.FAILED.value, OutboxStatus.DEAD.value)

HandlerFn = Callable[[AsyncSession, Dict[str, Any]], Awaitable[bool]]
DeadHookFn = Callable[[AsyncSession, Dict[str, Any]], Awaitable[None]]
SessionFactory = Callable[[], Any]


@dataclass(frozen=True)
class OutboxHandler:
    send: HandlerFn
    on_dead: Optional[DeadHookFn] = None


class OutboxNotFoundError(LookupError):
    """No outbox row with that id."""


class OutboxNotRetryableError(ValueError):
    """Only failed or dead rows can be retried by an admin."""


def is_worker_mode() -> bool:
    """True when mail goes through the worker (``OUTBOX_MODE=worker``)."""
    return settings.outbox_mode == "worker"


def backoff_seconds(attempts: int) -> float:
    """Delay before the next try after ``attempts`` failed attempts."""
    exponent = max(attempts - 1, 0)
    delay = settings.OUTBOX_BACKOFF_BASE_SECONDS * (2**exponent)
    return float(min(delay, settings.OUTBOX_BACKOFF_MAX_SECONDS))


def _handlers() -> Dict[str, OutboxHandler]:
    """Kind -> handler. Imported lazily to keep the import graph acyclic."""
    from goldsmith_erp.services import quote_delivery  # noqa: PLC0415
    from goldsmith_erp.services.customer_message_service import (  # noqa: PLC0415
        deliver_queued_update,
        fail_queued_update,
    )

    return {
        KIND_CUSTOMER_UPDATE: OutboxHandler(
            send=deliver_queued_update, on_dead=fail_queued_update
        ),
        KIND_QUOTE_EMAIL: OutboxHandler(
            send=quote_delivery.deliver_queued_quote,
            on_dead=quote_delivery.fail_queued_quote,
        ),
    }


KIND_CUSTOMER_UPDATE = "customer_update"
KIND_QUOTE_EMAIL = "quote_email"


def _log(event: str, msg: OutboxMessage, **extra: Any) -> None:
    logger.info(
        "Outbox %s",
        event,
        extra={
            "outbox_id": msg.id,
            "outbox_kind": msg.kind,
            "attempts": msg.attempts,
            **extra,
        },
    )


class OutboxService:
    """Static-method service; every method takes the AsyncSession first."""

    @staticmethod
    async def enqueue(
        db: AsyncSession,
        *,
        kind: str,
        payload: Dict[str, Any],
        dedupe_key: Optional[str] = None,
    ) -> OutboxMessage:
        """Stage a message in the caller's transaction (caller commits).

        With a ``dedupe_key`` that already exists, the existing row is
        returned and nothing new is staged.
        """
        if dedupe_key is not None:
            existing = (
                await db.execute(
                    select(OutboxMessage).where(OutboxMessage.dedupe_key == dedupe_key)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing
        msg = OutboxMessage(
            kind=kind,
            payload=dict(payload),
            dedupe_key=dedupe_key,
            status=OutboxStatus.PENDING.value,
            attempts=0,
            next_attempt_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        db.add(msg)
        await db.flush()
        _log("enqueued", msg)
        return msg

    @staticmethod
    async def lease_due(
        db: AsyncSession, *, limit: int, now: Optional[datetime] = None
    ) -> List[int]:
        """Lease up to ``limit`` due rows; returns their ids (committed)."""
        moment = now or datetime.utcnow()
        stmt = (
            select(OutboxMessage)
            .where(
                OutboxMessage.status.in_(DUE_STATUSES),
                OutboxMessage.next_attempt_at <= moment,
            )
            .order_by(OutboxMessage.next_attempt_at, OutboxMessage.id)
            .limit(limit)
        )
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        lease_until = moment + timedelta(seconds=settings.OUTBOX_LEASE_SECONDS)
        async with transactional(db):
            rows = list((await db.execute(stmt)).scalars().all())
            for leased in rows:
                row = cast(Any, leased)
                row.attempts = cast(int, row.attempts or 0) + 1
                row.next_attempt_at = lease_until
        return [cast(int, row.id) for row in rows]

    @staticmethod
    async def process(db: AsyncSession, msg_id: int) -> str:
        """Run the handler for one leased row; returns the new status."""
        msg = await db.get(OutboxMessage, msg_id)
        if msg is None:
            raise OutboxNotFoundError(msg_id)
        payload = dict(cast(Dict[str, Any], msg.payload or {}))
        handler = _handlers().get(cast(str, msg.kind))
        delivered = False
        error_code = "unknown_kind"
        if handler is not None:
            try:
                delivered = await handler.send(db, payload)
                error_code = "delivery_failed"
            except Exception as exc:  # the row records it; never silent
                await db.rollback()
                error_code = type(exc).__name__
                logger.error(
                    "Outbox handler raised",
                    extra={"outbox_id": msg_id, "error_type": error_code},
                    exc_info=True,
                )
            msg = cast(
                OutboxMessage,
                await db.get(OutboxMessage, msg_id, populate_existing=True),
            )
        if delivered:
            return await OutboxService._mark_sent(db, msg)
        return await OutboxService._mark_failed(db, msg, error_code, handler, payload)

    @staticmethod
    async def _mark_sent(db: AsyncSession, msg: Any) -> str:
        async with transactional(db):
            msg.status = OutboxStatus.SENT.value
            msg.sent_at = datetime.utcnow()
            msg.last_error = None
        _log("sent", msg)
        return OutboxStatus.SENT.value

    @staticmethod
    async def _mark_failed(
        db: AsyncSession,
        msg: Any,
        error_code: str,
        handler: Optional[OutboxHandler],
        payload: Dict[str, Any],
    ) -> str:
        attempts = cast(int, msg.attempts or 0)
        is_dead = handler is None or attempts >= settings.OUTBOX_MAX_ATTEMPTS
        async with transactional(db):
            msg.last_error = error_code[:MAX_ERROR_LEN]
            if is_dead:
                msg.status = OutboxStatus.DEAD.value
            else:
                msg.status = OutboxStatus.FAILED.value
                msg.next_attempt_at = datetime.utcnow() + timedelta(
                    seconds=backoff_seconds(attempts)
                )
        if not is_dead:
            _log("failed", msg, error=error_code)
            return OutboxStatus.FAILED.value
        logger.error(
            "Outbox message dead-lettered",
            extra={
                "outbox_id": msg.id,
                "outbox_kind": msg.kind,
                "attempts": attempts,
                "error": error_code,
            },
        )
        if handler is not None and handler.on_dead is not None:
            try:
                await handler.on_dead(db, payload)
            except Exception:
                await db.rollback()
                logger.error(
                    "Outbox on_dead hook failed",
                    extra={"outbox_id": msg.id},
                    exc_info=True,
                )
        return OutboxStatus.DEAD.value

    @staticmethod
    async def run_once(session_factory: SessionFactory) -> int:
        """Lease one batch and process it, one session per row. Returns count."""
        async with session_factory() as db:
            ids = await OutboxService.lease_due(db, limit=settings.OUTBOX_BATCH_SIZE)
        for msg_id in ids:
            async with session_factory() as db:
                try:
                    await OutboxService.process(db, msg_id)
                except Exception:
                    logger.error(
                        "Outbox processing crashed; lease will expire",
                        extra={"outbox_id": msg_id},
                        exc_info=True,
                    )
        return len(ids)

    @staticmethod
    async def list_messages(
        db: AsyncSession, *, status: Optional[str] = None, limit: int = 100
    ) -> List[OutboxMessage]:
        stmt = select(OutboxMessage).order_by(OutboxMessage.id.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(OutboxMessage.status == status)
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def retry(db: AsyncSession, msg_id: int) -> OutboxMessage:
        """Admin retry: a failed/dead row becomes pending with fresh attempts."""
        async with transactional(db):
            msg: Any = await db.get(OutboxMessage, msg_id, with_for_update=True)
            if msg is None:
                raise OutboxNotFoundError(msg_id)
            if msg.status not in RETRYABLE_STATUSES:
                raise OutboxNotRetryableError(msg_id)
            msg.status = OutboxStatus.PENDING.value
            msg.attempts = 0
            msg.next_attempt_at = datetime.utcnow()
        await db.refresh(msg)
        _log("retry_requested", msg)
        return cast(OutboxMessage, msg)
