"""Consent records per customer and purpose (GDPR-02 / GDPR-11).

A ``CustomerConsent`` row is the Art. 7 Abs. 1 DSGVO proof that the data
subject agreed to a purpose. The first consumer is health data: allergies
are special-category data (Art. 9) and may only be stored with explicit
consent (Art. 9 Abs. 2 lit. a). See ``require_health_data_consent``.

Transactions: every method only ``flush()``es; the caller owns the commit
(router via ``transactional(db)``, erasure via its own transaction).
Logs carry ids only, never the consent note or any health value.
"""

import logging
from datetime import datetime
from typing import Any, List, Optional, cast

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    CustomerAuditLog,
    CustomerConsent,
    CustomerNoGo,
    NoGoCategory,
)
from goldsmith_erp.models.consent import ConsentMethod, ConsentPurpose

logger = logging.getLogger(__name__)

HEALTH_CONSENT_REQUIRED_MESSAGE = (
    "Allergien sind Gesundheitsdaten (Art. 9 DSGVO) und dürfen nur mit "
    "ausdrücklicher Einwilligung der Kundin/des Kunden gespeichert werden. "
    "Bitte zuerst die Einwilligung 'Gesundheitsdaten' erfassen."
)


class ConsentCustomerNotFoundError(ValueError):
    """The customer does not exist or has been erased."""


class HealthDataConsentRequiredError(ValueError):
    """Health data was written without an active HEALTH_DATA consent."""

    def __init__(self) -> None:
        super().__init__(HEALTH_CONSENT_REQUIRED_MESSAGE)


class ConsentService:
    """Grant, revoke and query per-purpose customer consents."""

    @staticmethod
    async def _get_live_customer(db: AsyncSession, customer_id: int) -> Customer:
        customer = await db.get(Customer, customer_id)
        if customer is None or customer.is_deleted:
            raise ConsentCustomerNotFoundError("Kunde nicht gefunden")
        return customer

    @staticmethod
    async def get_active(
        db: AsyncSession, customer_id: int, purpose: ConsentPurpose
    ) -> Optional[CustomerConsent]:
        """Return the active (not revoked) consent for ``purpose``, if any."""
        result = await db.execute(
            select(CustomerConsent)
            .filter(
                CustomerConsent.customer_id == customer_id,
                CustomerConsent.purpose == purpose.value,
                CustomerConsent.revoked_at.is_(None),
            )
            .order_by(CustomerConsent.granted_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def has_consent(
        db: AsyncSession, customer_id: int, purpose: ConsentPurpose
    ) -> bool:
        """True when an active consent for ``purpose`` exists."""
        return await ConsentService.get_active(db, customer_id, purpose) is not None

    @staticmethod
    async def list_consents(
        db: AsyncSession, customer_id: int
    ) -> List[CustomerConsent]:
        """All consent rows (active and revoked), oldest first."""
        result = await db.execute(
            select(CustomerConsent)
            .filter(CustomerConsent.customer_id == customer_id)
            .order_by(CustomerConsent.granted_at.asc(), CustomerConsent.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def grant(
        db: AsyncSession,
        customer_id: int,
        *,
        purpose: ConsentPurpose,
        method: ConsentMethod,
        recorded_by_user_id: Optional[int],
        note: Optional[str] = None,
        wording_version: Optional[str] = None,
    ) -> CustomerConsent:
        """Record a consent. Idempotent while one is active for ``purpose``."""
        await ConsentService._get_live_customer(db, customer_id)

        existing = await ConsentService.get_active(db, customer_id, purpose)
        if existing is not None:
            return existing

        now = datetime.utcnow()
        consent = CustomerConsent(
            customer_id=customer_id,
            purpose=purpose.value,
            method=method.value,
            wording_version=wording_version,
            granted_at=now,
            recorded_by_user_id=recorded_by_user_id,
            note=note,
            created_at=now,
        )
        db.add(consent)
        await db.flush()
        await ConsentService._audit(
            db,
            customer_id=customer_id,
            user_id=recorded_by_user_id,
            action="consent_granted",
            consent=consent,
        )
        logger.info(
            "Customer consent granted",
            extra={
                "audit": True,
                "action": "consent_granted",
                "customer_id": customer_id,
                "user_id": recorded_by_user_id,
                "purpose": purpose.value,
                "method": method.value,
            },
        )
        return consent

    @staticmethod
    async def revoke(
        db: AsyncSession,
        customer_id: int,
        purpose: ConsentPurpose,
        *,
        revoked_by_user_id: Optional[int],
    ) -> Optional[CustomerConsent]:
        """Withdraw the active consent (Art. 7 Abs. 3). None if none active.

        Withdrawing HEALTH_DATA also deletes the health data it covered
        (``customers.allergies`` and ALLERGY no-gos) — without the consent
        there is no legal basis left to keep it (Art. 17 Abs. 1 lit. b).
        """
        await ConsentService._get_live_customer(db, customer_id)
        consent = await ConsentService.get_active(db, customer_id, purpose)
        if consent is None:
            return None

        # Statement-level UPDATE (not attribute assignment): keeps this new
        # module mypy-strict clean against the legacy Column-style models.
        await db.execute(
            update(CustomerConsent)
            .where(CustomerConsent.id == consent.id)
            .values(revoked_at=datetime.utcnow(), revoked_by_user_id=revoked_by_user_id)
        )

        if purpose is ConsentPurpose.HEALTH_DATA:
            await ConsentService._delete_health_data(db, customer_id)

        await db.flush()
        await db.refresh(consent)
        await ConsentService._audit(
            db,
            customer_id=customer_id,
            user_id=revoked_by_user_id,
            action="consent_revoked",
            consent=consent,
        )
        logger.info(
            "Customer consent revoked",
            extra={
                "audit": True,
                "action": "consent_revoked",
                "customer_id": customer_id,
                "user_id": revoked_by_user_id,
                "purpose": purpose.value,
            },
        )
        return consent

    @staticmethod
    async def delete_all_for_customer(db: AsyncSession, customer_id: int) -> int:
        """Delete every consent row of a customer (Art. 17 erasure)."""
        result = await db.execute(
            delete(CustomerConsent).where(CustomerConsent.customer_id == customer_id)
        )
        await db.flush()
        return max(cast(CursorResult[Any], result).rowcount or 0, 0)

    @staticmethod
    async def require_health_data_consent(
        db: AsyncSession, customer_id: Optional[int], allergies: Optional[str]
    ) -> None:
        """Raise unless storing ``allergies`` is covered by consent.

        Clearing the field (None / blank) never needs consent. A new
        customer (``customer_id`` None) cannot have a consent yet, so any
        non-blank value is refused.
        """
        if allergies is None or not allergies.strip():
            return
        if customer_id is None or not await ConsentService.has_consent(
            db, customer_id, ConsentPurpose.HEALTH_DATA
        ):
            raise HealthDataConsentRequiredError()

    @staticmethod
    async def _delete_health_data(db: AsyncSession, customer_id: int) -> None:
        await db.execute(
            update(Customer).where(Customer.id == customer_id).values(allergies=None)
        )
        await db.execute(
            delete(CustomerNoGo).where(
                CustomerNoGo.customer_id == customer_id,
                CustomerNoGo.category == NoGoCategory.ALLERGY,
            )
        )

    @staticmethod
    async def _audit(
        db: AsyncSession,
        *,
        customer_id: int,
        user_id: Optional[int],
        action: str,
        consent: CustomerConsent,
    ) -> None:
        db.add(
            CustomerAuditLog(
                customer_id=customer_id,
                user_id=user_id,
                action=action,
                entity="customer_consent",
                entity_id=consent.id,
                details={"purpose": consent.purpose, "method": consent.method},
                timestamp=datetime.utcnow(),
            )
        )
        await db.flush()
