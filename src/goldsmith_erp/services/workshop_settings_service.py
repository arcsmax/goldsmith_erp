# src/goldsmith_erp/services/workshop_settings_service.py
"""
Werkstatt-Stammdaten (W2-04, DOM-24): the seller block of every Rechnung.

One singleton row (``workshop_settings.id = 1``). Until an ADMIN saves the
form, reads fall back to ``settings.WORKSHOP_NAME`` / ``WORKSHOP_CONTACT``
so existing deployments keep rendering. ``seller_block`` is what the
invoice snapshot copies (at creation, refreshed when the invoice is issued),
so an issued Rechnung never changes when the settings change later.

Every change is audit-logged (who, which fields; values of the workshop's
own business data are not personal customer data, but only field names are
logged to keep log volume small). The HTTP layer adds a CustomerAuditLog
row per request via ``middleware/audit_logging.py``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.db.models import WorkshopSettings
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.workshop_settings import (
    WorkshopPublicContact,
    WorkshopSettingsRead,
    WorkshopSettingsUpdate,
)

logger = logging.getLogger(__name__)

SINGLETON_ID = 1
DEFAULT_VAT_RATE = 19.0
KLEINUNTERNEHMER_NOTE = "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet."

_FIELDS = (
    "name",
    "owner_name",
    "street",
    "postal_code",
    "city",
    "country",
    "phone",
    "email",
    "tax_number",
    "vat_id",
    "iban",
    "bic",
    "bank_name",
    "is_kleinunternehmer",
    "default_vat_rate",
    "invoice_footer",
)


def missing_fields(values: Dict[str, Any]) -> List[str]:
    """§14 Abs. 4 Nr. 1/2 UStG seller fields that are still empty."""
    missing: List[str] = []
    if not values.get("name"):
        missing.append("Name der Werkstatt")
    if not values.get("street"):
        missing.append("Straße und Hausnummer")
    if not values.get("postal_code"):
        missing.append("PLZ")
    if not values.get("city"):
        missing.append("Ort")
    if not values.get("tax_number") and not values.get("vat_id"):
        missing.append("Steuernummer oder USt-IdNr.")
    return missing


def _defaults() -> Dict[str, Any]:
    values: Dict[str, Any] = {field: None for field in _FIELDS}
    values.update(
        name=settings.WORKSHOP_NAME,
        country="Deutschland",
        is_kleinunternehmer=False,
        default_vat_rate=DEFAULT_VAT_RATE,
    )
    return values


def _values(row: Optional[WorkshopSettings]) -> Dict[str, Any]:
    if row is None:
        return _defaults()
    return {field: getattr(row, field) for field in _FIELDS}


class WorkshopSettingsService:
    """Static-method service; all methods take the AsyncSession first."""

    @staticmethod
    async def get_row(db: AsyncSession) -> Optional[Any]:
        """The singleton row (typed Any: legacy Column() declarations)."""
        result = await db.execute(
            select(WorkshopSettings).where(WorkshopSettings.id == SINGLETON_ID)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def read(db: AsyncSession) -> WorkshopSettingsRead:
        row = await WorkshopSettingsService.get_row(db)
        values = _values(row)
        missing = missing_fields(values)
        return WorkshopSettingsRead(
            **values,
            updated_at=row.updated_at if row is not None else None,
            missing_fields=missing,
            is_complete=not missing,
        )

    @staticmethod
    async def public_contact(db: AsyncSession) -> WorkshopPublicContact:
        """Public subset for the customer portal footer (no auth): name,
        phone, email only — never bank/tax fields (see
        ``WorkshopPublicContact``)."""
        values = _values(await WorkshopSettingsService.get_row(db))
        return WorkshopPublicContact(
            name=values["name"],
            phone=values["phone"],
            email=values["email"],
        )

    @staticmethod
    async def update(
        db: AsyncSession, data: WorkshopSettingsUpdate, current_user: UserModel
    ) -> WorkshopSettingsRead:
        """Replace the settings (creates the singleton row on first save)."""
        new_values = data.model_dump()
        async with transactional(db):
            row = await WorkshopSettingsService.get_row(db)
            old_values = _values(row)
            if row is None:
                row = cast(Any, WorkshopSettings(id=SINGLETON_ID))
                db.add(row)
            for field, value in new_values.items():
                setattr(row, field, value)
            row.updated_at = datetime.now(timezone.utc)
            row.updated_by = current_user.id
        changed = sorted(
            field for field in _FIELDS if old_values.get(field) != new_values.get(field)
        )
        logger.info(
            "Workshop settings updated",
            extra={
                "audit": True,
                "action": "workshop_settings_updated",
                "entity": "workshop_settings",
                "user_id": current_user.id,
                "changed_fields": changed,
            },
        )
        return await WorkshopSettingsService.read(db)

    @staticmethod
    async def seller_block(db: AsyncSession) -> Dict[str, Any]:
        """Seller data for the invoice snapshot (§14 Abs. 4 Nr. 1/2 UStG)."""
        values = _values(await WorkshopSettingsService.get_row(db))
        return {
            **{k: values[k] for k in _FIELDS if k != "default_vat_rate"},
            "is_kleinunternehmer": bool(values["is_kleinunternehmer"]),
            "contact": settings.WORKSHOP_CONTACT,
        }

    @staticmethod
    async def vat_rate_for_new_invoice(
        db: AsyncSession, requested: Optional[float]
    ) -> float:
        """VAT rate for a new invoice.

        Kleinunternehmer (§19 UStG): always 0. Otherwise the requested rate,
        else the configured default.
        """
        values = _values(await WorkshopSettingsService.get_row(db))
        if values["is_kleinunternehmer"]:
            return 0.0
        if requested is not None:
            return float(requested)
        return float(values["default_vat_rate"] or DEFAULT_VAT_RATE)
