"""Customer no-gos (persistente Ausschlüsse, z. B. Nickelallergie) — V1.1.

``CustomerNoGo`` is the source of truth. The legacy ``Customer.allergies``
freetext column is kept read-compatible for UI that hasn't migrated to the
no-go list yet: adding an ALLERGY no-go also appends the value there, inside
the same transaction (see ``_sync_legacy_allergies``).
"""

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.encryption import no_go_value_blind_index
from goldsmith_erp.db.models import Consultation, Customer, CustomerNoGo, NoGoCategory
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.consultation import NoGoConflict, NoGoCreate

logger = logging.getLogger(__name__)

# Customer.allergies is Column(EncryptedString) (db/models.py) — encrypted at
# rest since issue #15, following the C1 pattern used for the other Customer
# PII columns (see db/types.py). This constant is a PLAINTEXT-length product
# decision (max allergy freetext a user may enter), not a storage constraint:
# EncryptedString maps to TEXT, so Fernet ciphertext (always longer than the
# plaintext it wraps) is never truncated regardless of this limit. Keep this
# at 500 for UX/product reasons only.
_ALLERGIES_MAX_LENGTH = 500


class DuplicateNoGoError(ValueError):
    """An equivalent no-go (same category, case-insensitively equal value)
    already exists for this customer.

    SECURITY: the message is intentionally GENERIC and must stay that way —
    no-go values are health-adjacent data (e.g. allergies), and exception
    messages end up in response bodies and log records. Never embed the
    submitted value here. Subclasses ``ValueError`` so pre-existing callers
    that catch ``ValueError`` keep working.
    """

    def __init__(self) -> None:
        super().__init__("No-Go existiert bereits für diesen Kunden")


def _norm(value: str) -> str:
    return value.strip().casefold()


def _no_go_value_hash(category: NoGoCategory, value: str) -> str:
    """Blind-index tag for (category, value) — see ``core.encryption.
    no_go_value_blind_index`` for the composite-normalisation rationale
    (casefold, not SQL ``lower()`` — closes the app/DB normalisation gap
    that issue #12's original functional index missed)."""
    return no_go_value_blind_index(category.value, value)


def _sync_legacy_allergies(customer: Customer, value: str, no_go_id: int) -> None:
    """Append ``value`` to the legacy ``Customer.allergies`` string.

    Comma-separated, case-insensitive de-dup against existing entries. Never
    truncates existing user data: if the appended result would exceed the
    column's 500-char limit, the append is skipped (and logged) instead of
    silently cutting off whatever was already stored. Health-adjacent data —
    the log only carries the customer/no-go IDs, never the value itself.
    """
    existing = customer.allergies or ""
    existing_values = [v.strip() for v in existing.split(",") if v.strip()]
    if any(_norm(v) == _norm(value) for v in existing_values):
        return

    candidate = f"{existing}, {value}" if existing else value
    if len(candidate) > _ALLERGIES_MAX_LENGTH:
        logger.warning(
            "Skipped legacy allergies sync: append would exceed "
            "%d-char column limit",
            _ALLERGIES_MAX_LENGTH,
            extra={"customer_id": customer.id, "no_go_id": no_go_id},
        )
        return

    customer.allergies = candidate


class NoGoService:
    @staticmethod
    async def add_no_go(
        db: AsyncSession,
        customer_id: int,
        no_go_in: NoGoCreate,
        source_consultation_id: Optional[int] = None,
    ) -> CustomerNoGo:
        # Business-rule pre-checks run BEFORE entering transactional(db):
        # they are read-only, and transactional's generic error handler logs
        # str(exc) at ERROR — a duplicate rejection raised inside the block
        # would write the raw no-go value (health-adjacent data, e.g. an
        # allergy) to the logs on every duplicate submission. Raising out
        # here keeps business rejections out of the transaction logger
        # entirely. Note: the duplicate check was never concurrency-safe
        # (no DB unique constraint) — moving it out of the transaction does
        # not change that pre-existing TOCTOU window.
        result = await db.execute(select(Customer).filter(Customer.id == customer_id))
        customer = result.scalar_one_or_none()
        if customer is None:
            # Safe to embed: message contains only the numeric ID.
            raise ValueError(f"Customer {customer_id} not found")

        # FK pre-validation (item B — a broad IntegrityError catch below
        # must not misreport a bad FK as a duplicate). Checked here, not
        # left to fail at flush time, so an invalid source_consultation_id
        # surfaces as its own typed ValueError rather than being
        # swallowed into DuplicateNoGoError by the catch-all below.
        if source_consultation_id is not None:
            consultation_exists = await db.execute(
                select(Consultation.id).filter(
                    Consultation.id == source_consultation_id
                )
            )
            if consultation_exists.scalar_one_or_none() is None:
                raise ValueError(f"Consultation {source_consultation_id} not found")

        # Duplicate pre-check now compares via the same HMAC blind-index tag
        # the DB-level unique index enforces (core.encryption.
        # no_go_value_blind_index — composite over category + casefolded
        # value), instead of a separate casefold string compare. Hash
        # compare matches the DB's normalisation EXACTLY by construction —
        # no risk of the app/DB semantics drifting apart again (see the
        # CustomerNoGo docstring for the 'Straße'/'STRASSE' gap this closes).
        candidate_hash = _no_go_value_hash(no_go_in.category, no_go_in.value)
        existing = await NoGoService.list_no_gos(db, customer_id)
        if any(n.value_hash == candidate_hash for n in existing):
            # Generic message — never embeds the submitted value.
            raise DuplicateNoGoError()

        async with transactional(db):
            no_go = CustomerNoGo(
                customer_id=customer_id,
                category=no_go_in.category,
                value=no_go_in.value,
                note=no_go_in.note,
                source_consultation_id=source_consultation_id,
                value_hash=candidate_hash,
            )
            db.add(no_go)
            try:
                # Explicit flush (rather than letting transactional's
                # commit surface it) so the DB-level unique index's
                # IntegrityError — the TOCTOU backstop for the app-side
                # check above, see CustomerNoGo.__table_args__ / issue
                # #12 — is caught HERE, inside this block. SQLAlchemy's
                # IntegrityError.__str__ includes the failed INSERT's
                # bound PARAMETERS, i.e. the raw (health-adjacent) no-go
                # value. transactional()'s except-clause logs str(exc) at
                # ERROR for ANY exception that escapes this block — so
                # letting the raw IntegrityError propagate would write
                # that value to the logs on every raced duplicate. Catch
                # and swap it for the generic DuplicateNoGoError before it
                # ever reaches that handler.
                #
                # Item B: this catch is intentionally broad (any
                # IntegrityError -> Duplicate), but by this point customer
                # existence AND source_consultation_id existence (if given)
                # were already validated above, outside the transaction —
                # so the only FK/constraint violation realistically left
                # to trip here is the value_hash unique index (a raced
                # concurrent insert). A genuine FK violation should not be
                # possible at this point; if one somehow still occurs, it
                # is misreported as a duplicate rather than surfaced
                # distinctly — an accepted tradeoff given the pre-checks
                # above cover every FK this row has.
                await db.flush()
            except IntegrityError:
                raise DuplicateNoGoError() from None
            await db.refresh(no_go)

            if no_go_in.category == NoGoCategory.ALLERGY:
                _sync_legacy_allergies(customer, no_go_in.value, no_go.id)

        logger.info(
            "Customer no-go added",
            extra={
                "customer_id": customer_id,
                "no_go_id": no_go.id,
                "category": no_go.category.value,
            },
        )
        return no_go

    @staticmethod
    async def list_no_gos(db: AsyncSession, customer_id: int) -> List[CustomerNoGo]:
        result = await db.execute(
            select(CustomerNoGo)
            .filter(CustomerNoGo.customer_id == customer_id)
            .order_by(CustomerNoGo.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def delete_no_go(db: AsyncSession, customer_id: int, no_go_id: int) -> None:
        async with transactional(db):
            result = await db.execute(
                select(CustomerNoGo).filter(
                    CustomerNoGo.id == no_go_id,
                    CustomerNoGo.customer_id == customer_id,
                )
            )
            no_go = result.scalar_one_or_none()
            if no_go is None:
                raise ValueError(
                    f"No-Go {no_go_id} not found for customer {customer_id}"
                )
            await db.delete(no_go)

        logger.info(
            "Customer no-go deleted",
            extra={"customer_id": customer_id, "no_go_id": no_go_id},
        )

    @staticmethod
    async def check_conflicts(
        db: AsyncSession, customer_id: int, candidates: List[str]
    ) -> List[NoGoConflict]:
        """Bidirectional normalized substring match: 'Weißgold' hits
        'Weißgold 585' and 'synthetischer Rubin' hits candidate 'Rubin'."""
        no_gos = await NoGoService.list_no_gos(db, customer_id)
        conflicts: List[NoGoConflict] = []
        for candidate in candidates:
            cand = _norm(candidate)
            if not cand:
                continue
            for no_go in no_gos:
                ng = _norm(no_go.value)
                if ng in cand or cand in ng:
                    conflicts.append(
                        NoGoConflict(
                            no_go_id=no_go.id,
                            category=no_go.category,
                            value=no_go.value,
                            matched_against=candidate,
                        )
                    )
        return conflicts
