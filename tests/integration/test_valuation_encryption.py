"""Integration test — ValuationCertificate.appraised_value is ciphertext at rest.

Fix item **C3** — encrypts the one remaining plaintext financial field on
``valuation_certificates`` to match CLAUDE.md "Data Privacy Rules (CRITICAL)":

    > Insurance Valuations: Valuation data MUST be encrypted at rest

Guards the end-to-end contract:

1. Writing a ``ValuationCertificate`` persists **ciphertext** in the raw DB
   column (verified via ``SELECT appraised_value FROM valuation_certificates``
   bypassing the ORM).
2. Reading the same row via the ORM returns a **numeric** value (the
   ``EncryptedString`` TypeDecorator decrypts transparently and the
   ``@property`` on ``appraised_value`` casts back to ``Decimal``).
3. Searching by exact appraised value via the ``appraised_value_hmac``
   blind-index finds the row — the canonical equality-search path now that
   the column is non-deterministic ciphertext.

These tests set ``ENCRYPTION_KEY`` at import time BEFORE the
``goldsmith_erp`` imports pick up ``settings.ENCRYPTION_KEY``, then reset
any cached blind-index / encryption state so real encryption is in effect
for the whole module. Mirrors ``tests/integration/test_customer_pii_encryption.py``
(C1) — consistency with its primed-env pattern.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet


# ---------------------------------------------------------------------------
# Env priming — must happen before the goldsmith_erp imports pick up
# settings.ENCRYPTION_KEY via `from core.config import settings`.
# ---------------------------------------------------------------------------

_TEST_KEY = Fernet.generate_key().decode("utf-8")
os.environ.setdefault("ENCRYPTION_KEY", _TEST_KEY)
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("ANONYMIZATION_SALT", "abcdefghijklmnop")
os.environ.setdefault(
    "SECRET_KEY",
    "abcdefghijklmnopqrstuvwxyz0123456789ABCDEF0123",
)
os.environ.setdefault("POSTGRES_PASSWORD", "test")

from sqlalchemy import select, text  # noqa: E402

from goldsmith_erp.core import encryption as encryption_mod  # noqa: E402
from goldsmith_erp.core.encryption import hmac_blind_index  # noqa: E402
from goldsmith_erp.db.models import (  # noqa: E402
    Customer,
    Order,
    OrderStatusEnum,
    ValuationCertificate,
)


@pytest.fixture(autouse=True)
def _prime_encryption(monkeypatch):
    """Pin the encryption key and force a fresh singleton each test."""
    monkeypatch.setattr(encryption_mod.settings, "ENCRYPTION_KEY", _TEST_KEY)
    monkeypatch.setattr(
        encryption_mod,
        "_BLIND_INDEX_KEY",
        encryption_mod._derive_blind_index_key(),
    )
    encryption_mod._encryption_service = None
    yield
    encryption_mod._encryption_service = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_customer_and_order(db_session) -> tuple[Customer, Order]:
    """Create a minimal customer + order for attaching a valuation to."""
    customer = Customer(
        first_name="Valuation",
        last_name="Owner",
        email=f"valuation.owner.{os.urandom(4).hex()}@example.com",
    )
    # Let the before_insert event hook populate email_hash (C1 pattern).
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)

    order = Order(
        title="Valuation Encryption Test Order",
        description="Order used by the C3 valuation encryption tests",
        customer_id=customer.id,
        status=OrderStatusEnum.COMPLETED,
        actual_weight_g=4.8,
        alloy="750",
        is_deleted=False,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return customer, order


def _make_cert(
    order_id: int,
    customer_id: int,
    appraised_value: float,
    certificate_number: str,
) -> ValuationCertificate:
    """Build a ValuationCertificate with the minimum required fields."""
    now = datetime.utcnow()
    return ValuationCertificate(
        certificate_number=certificate_number,
        order_id=order_id,
        customer_id=customer_id,
        item_description="Brillantring 750 Gelbgold (C3 encryption test fixture)",
        metal_type="Gelbgold 750",
        metal_weight_g=4.8,
        metal_purity="750",
        appraised_value=appraised_value,
        valuation_date=now,
        valid_until=now + timedelta(days=730),
        goldsmith_name="Test Goldsmith",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_appraised_value_stored_as_ciphertext(db_session):
    """Raw DB shows Fernet ciphertext; ORM shows the numeric plaintext."""
    customer, order = await _create_customer_and_order(db_session)

    cert = _make_cert(
        order_id=order.id,
        customer_id=customer.id,
        appraised_value=12500.0,
        certificate_number="WG-C3-CIPHER",
    )
    db_session.add(cert)
    await db_session.commit()
    await db_session.refresh(cert)

    # Raw SQL bypasses the EncryptedString decrypt step — should be ciphertext.
    raw = await db_session.execute(
        text("SELECT appraised_value FROM valuation_certificates WHERE id = :id"),
        {"id": cert.id},
    )
    raw_value = raw.scalar()

    # The plaintext numeric representation must NOT appear in the stored value.
    assert raw_value is not None
    assert raw_value != "12500.00"
    assert raw_value != "12500"
    assert raw_value != 12500.0
    # Fernet tokens are long base64-ish strings starting with a version marker.
    assert isinstance(raw_value, str)
    assert len(raw_value) > 40
    assert raw_value.startswith("gAAAAA")


@pytest.mark.asyncio
async def test_appraised_value_numeric_round_trip(db_session):
    """Writing a numeric value and re-reading via ORM returns the same number."""
    customer, order = await _create_customer_and_order(db_session)

    cert = _make_cert(
        order_id=order.id,
        customer_id=customer.id,
        appraised_value=9876.54,
        certificate_number="WG-C3-ROUND",
    )
    db_session.add(cert)
    await db_session.commit()
    cert_id = cert.id

    # Expire so the next access re-hydrates from the DB (not the unit-of-work).
    db_session.expire_all()

    fetched = await db_session.get(ValuationCertificate, cert_id)
    assert fetched is not None
    # Value comes back as Decimal (preferred) but float-compat is required.
    assert float(fetched.appraised_value) == pytest.approx(9876.54, abs=0.001)
    # Callers that format for display (PDF, repr) rely on `:.2f`; verify it.
    assert f"{fetched.appraised_value:.2f}" == "9876.54"


@pytest.mark.asyncio
async def test_search_by_appraised_value_via_hmac(db_session):
    """Equality-search lands on the ``appraised_value_hmac`` column."""
    customer, order = await _create_customer_and_order(db_session)

    cert = _make_cert(
        order_id=order.id,
        customer_id=customer.id,
        appraised_value=4321.00,
        certificate_number="WG-C3-HMAC",
    )
    db_session.add(cert)
    await db_session.commit()

    # The canonical equality-search path: hash the normalised plaintext
    # representation (fixed 2-decimal) and compare against the hash column.
    hashed = hmac_blind_index("4321.00")
    result = await db_session.execute(
        select(ValuationCertificate).where(
            ValuationCertificate.appraised_value_hmac == hashed
        )
    )
    found = result.scalar_one_or_none()
    assert found is not None
    assert found.id == cert.id
    # The hash column itself is the 64-char hex digest.
    assert found.appraised_value_hmac == hashed
    assert len(found.appraised_value_hmac) == 64
