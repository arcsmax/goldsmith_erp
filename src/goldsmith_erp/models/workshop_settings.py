# src/goldsmith_erp/models/workshop_settings.py
"""Pydantic schemas for the Werkstatt-Stammdaten (W2-04, DOM-24).

The workshop's own seller data that §14 Abs. 4 UStG requires on every
Rechnung: name and address (Nr. 1), Steuernummer or USt-IdNr. (Nr. 2), plus
bank details, the Kleinunternehmer switch (§19 UStG) and the default VAT
rate. No customer data lives here.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
_BIC_RE = re.compile(r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$")
_VAT_ID_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{2,12}$")
_TAX_NUMBER_RE = re.compile(r"^[\d\s/]{8,20}$")


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class WorkshopSettingsUpdate(BaseModel):
    """Full replacement of the settings (PUT). Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    owner_name: Optional[str] = Field(None, max_length=200)
    street: Optional[str] = Field(None, max_length=200)
    postal_code: Optional[str] = Field(None, max_length=20)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field("Deutschland", max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = None
    tax_number: Optional[str] = Field(None, max_length=50, description="Steuernummer")
    vat_id: Optional[str] = Field(None, max_length=20, description="USt-IdNr.")
    iban: Optional[str] = Field(None, max_length=42)
    bic: Optional[str] = Field(None, max_length=11)
    bank_name: Optional[str] = Field(None, max_length=100)
    is_kleinunternehmer: bool = False
    default_vat_rate: float = Field(19.0, ge=0, le=100)
    invoice_footer: Optional[str] = Field(None, max_length=1000)

    @field_validator(
        "owner_name",
        "street",
        "postal_code",
        "city",
        "country",
        "phone",
        "bank_name",
        "invoice_footer",
        mode="before",
    )
    @classmethod
    def strip_optional(cls, v: Optional[str]) -> Optional[str]:
        return _blank_to_none(v) if isinstance(v, str) or v is None else v

    @field_validator("email", mode="before")
    @classmethod
    def blank_email(cls, v: Optional[str]) -> Optional[str]:
        return _blank_to_none(v) if isinstance(v, str) or v is None else v

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Name der Werkstatt darf nicht leer sein")
        return stripped

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: Optional[str]) -> Optional[str]:
        value = _blank_to_none(v)
        if value is None:
            return None
        compact = value.replace(" ", "").upper()
        if not _IBAN_RE.match(compact):
            raise ValueError("Ungültige IBAN")
        return compact

    @field_validator("bic")
    @classmethod
    def validate_bic(cls, v: Optional[str]) -> Optional[str]:
        value = _blank_to_none(v)
        if value is None:
            return None
        compact = value.replace(" ", "").upper()
        if not _BIC_RE.match(compact):
            raise ValueError("Ungültige BIC")
        return compact

    @field_validator("vat_id")
    @classmethod
    def validate_vat_id(cls, v: Optional[str]) -> Optional[str]:
        value = _blank_to_none(v)
        if value is None:
            return None
        compact = value.replace(" ", "").upper()
        if not _VAT_ID_RE.match(compact):
            raise ValueError("Ungültige USt-IdNr. (z. B. DE123456789)")
        return compact

    @field_validator("tax_number")
    @classmethod
    def validate_tax_number(cls, v: Optional[str]) -> Optional[str]:
        value = _blank_to_none(v)
        if value is None:
            return None
        if not _TAX_NUMBER_RE.match(value):
            raise ValueError("Ungültige Steuernummer (z. B. 12/345/67890)")
        return value


class WorkshopSettingsRead(BaseModel):
    """Current settings plus the §14 completeness check."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    owner_name: Optional[str] = None
    street: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    tax_number: Optional[str] = None
    vat_id: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    bank_name: Optional[str] = None
    is_kleinunternehmer: bool = False
    default_vat_rate: float = 19.0
    invoice_footer: Optional[str] = None
    updated_at: Optional[datetime] = None
    # §14 Abs. 4 UStG fields still missing, German labels (empty = complete).
    missing_fields: List[str] = Field(default_factory=list)
    is_complete: bool = False
