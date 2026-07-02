"""Integration test — Customer PII is ciphertext at rest, plaintext via ORM.

Fix item **C1** — foundational PII encryption infrastructure.

Guards the end-to-end contract:

1. Writing a ``Customer`` persists **ciphertext** in the raw DB column
   (verified via ``SELECT <col> FROM customers`` bypassing the ORM).
2. Reading the same row via the ORM returns **plaintext** (the
   ``EncryptedString`` TypeDecorator decrypts transparently).
3. ``CustomerService.search_customers`` + ``.get_customer_by_email`` find
   a customer via the ``email_hash`` blind-index — NOT via ``.ilike(email)``
   which cannot match Fernet ciphertext.
4. Two customers with the same name but different emails each get a unique
   ``email_hash`` (uniqueness constraint enforceable even though the raw
   ``email`` column is ciphertext and non-deterministic).

These tests set ``ENCRYPTION_KEY`` at import time BEFORE the singleton
is constructed, then reset any cached state so real encryption is in
effect for the whole module.
"""

from __future__ import annotations

import os

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

from sqlalchemy import text  # noqa: E402

from goldsmith_erp.core import encryption as encryption_mod  # noqa: E402
from goldsmith_erp.core.encryption import hmac_blind_index  # noqa: E402
from goldsmith_erp.db.models import Customer, CustomerNoGo, NoGoCategory  # noqa: E402
from goldsmith_erp.services.customer_service import CustomerService  # noqa: E402


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


@pytest.mark.asyncio
async def test_customer_email_stored_as_ciphertext(db_session):
    """Raw DB shows ciphertext; ORM shows plaintext."""
    customer = Customer(
        first_name="Alice",
        last_name="Schmidt",
        email="alice.cipher@example.com",
        email_hash=hmac_blind_index("alice.cipher@example.com"),
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)

    # Raw SQL bypasses the ORM's decrypt step — should return ciphertext.
    raw = await db_session.execute(
        text("SELECT email FROM customers WHERE id = :id"),
        {"id": customer.id},
    )
    raw_value = raw.scalar()
    assert raw_value != "alice.cipher@example.com"
    assert raw_value is not None and len(raw_value) > 30  # Fernet token
    assert raw_value.startswith("gAAAAA")  # Fernet version marker

    # ORM read decrypts transparently.
    orm_customer = await db_session.get(Customer, customer.id)
    assert orm_customer.email == "alice.cipher@example.com"


@pytest.mark.asyncio
async def test_customer_names_stored_as_ciphertext(db_session):
    """first_name, last_name, company_name also encrypted at rest."""
    customer = Customer(
        first_name="Bob",
        last_name="Mueller",
        company_name="Goldsmiths United",
        email="bob@example.com",
        email_hash=hmac_blind_index("bob@example.com"),
    )
    db_session.add(customer)
    await db_session.commit()

    raw = await db_session.execute(
        text(
            "SELECT first_name, last_name, company_name FROM customers "
            "WHERE id = :id"
        ),
        {"id": customer.id},
    )
    row = raw.one()
    # None of the encrypted columns should equal the plaintext.
    assert row[0] != "Bob"
    assert row[1] != "Mueller"
    assert row[2] != "Goldsmiths United"
    # All three should look like Fernet tokens.
    assert row[0].startswith("gAAAAA")
    assert row[1].startswith("gAAAAA")
    assert row[2].startswith("gAAAAA")


@pytest.mark.asyncio
async def test_customer_allergies_stored_as_ciphertext(db_session):
    """I15 — ``allergies`` (health-adjacent PII) is ciphertext at rest,
    plaintext via the ORM. Same contract as the C1 columns, mirrored here
    for the standalone I15 fix."""
    customer = Customer(
        first_name="Hannah",
        last_name="Allergy",
        email="hannah.allergy@example.com",
        email_hash=hmac_blind_index("hannah.allergy@example.com"),
        allergies="Nickel, Kupfer",
    )
    db_session.add(customer)
    await db_session.commit()

    raw = await db_session.execute(
        text("SELECT allergies FROM customers WHERE id = :id"),
        {"id": customer.id},
    )
    raw_value = raw.scalar()
    assert raw_value != "Nickel, Kupfer"
    assert raw_value is not None and len(raw_value) > 30  # Fernet token
    assert raw_value.startswith("gAAAAA")  # Fernet version marker

    orm_customer = await db_session.get(Customer, customer.id)
    assert orm_customer.allergies == "Nickel, Kupfer"


@pytest.mark.asyncio
async def test_customer_no_go_value_and_note_stored_as_ciphertext(db_session):
    """Item A (ECC-review fix wave) — CustomerNoGo.value/note are
    health-adjacent PII (this table is the source of truth for allergies)
    and are encrypted at rest, same C1 pattern as the other PII columns.
    ``value_hash`` is a deterministic HMAC tag, NOT ciphertext — it must
    look nothing like a Fernet token."""
    customer = Customer(
        first_name="Ida",
        last_name="NoGo",
        email="ida.nogo@example.com",
        email_hash=hmac_blind_index("ida.nogo@example.com"),
    )
    db_session.add(customer)
    await db_session.commit()

    no_go = CustomerNoGo(
        customer_id=customer.id,
        category=NoGoCategory.ALLERGY,
        value="Nickelsulfat",
        note="Schwere Reaktion bei Hautkontakt",
    )
    db_session.add(no_go)
    await db_session.commit()

    raw = await db_session.execute(
        text("SELECT value, note, value_hash FROM customer_no_gos WHERE id = :id"),
        {"id": no_go.id},
    )
    row = raw.one()
    assert row[0] != "Nickelsulfat"
    assert row[0] is not None and len(row[0]) > 30  # Fernet token
    assert row[0].startswith("gAAAAA")  # Fernet version marker
    assert row[1] != "Schwere Reaktion bei Hautkontakt"
    assert row[1].startswith("gAAAAA")
    # value_hash is a 64-char hex HMAC tag — deterministic, not ciphertext.
    assert row[2] is not None
    assert len(row[2]) == 64
    assert not row[2].startswith("gAAAAA")

    orm_no_go = await db_session.get(CustomerNoGo, no_go.id)
    assert orm_no_go.value == "Nickelsulfat"
    assert orm_no_go.note == "Schwere Reaktion bei Hautkontakt"


@pytest.mark.asyncio
async def test_customer_email_searchable_via_hash(db_session):
    """``get_customer_by_email`` finds the row through the blind-index."""
    customer = Customer(
        first_name="Carla",
        last_name="Jones",
        email="carla.search@example.com",
        email_hash=hmac_blind_index("carla.search@example.com"),
    )
    db_session.add(customer)
    await db_session.commit()

    found = await CustomerService.get_customer_by_email(
        db_session, "carla.search@example.com"
    )
    assert found is not None
    assert found.id == customer.id


@pytest.mark.asyncio
async def test_email_hash_normalises_case_and_whitespace(db_session):
    """Case/whitespace variations of the same email resolve to the same row."""
    customer = Customer(
        first_name="Dana",
        last_name="Normalise",
        email="dana@example.com",
        email_hash=hmac_blind_index("dana@example.com"),
    )
    db_session.add(customer)
    await db_session.commit()

    # Search with mixed case + leading whitespace.
    found = await CustomerService.get_customer_by_email(
        db_session, "  Dana@Example.COM  "
    )
    assert found is not None
    assert found.id == customer.id


@pytest.mark.asyncio
async def test_duplicate_emails_rejected_via_email_hash(db_session):
    """Two customers cannot share an email — uniqueness enforced by
    ``email_hash`` unique constraint now that ``email`` is ciphertext."""
    c1 = Customer(
        first_name="Eva",
        last_name="First",
        email="dup@example.com",
        email_hash=hmac_blind_index("dup@example.com"),
    )
    db_session.add(c1)
    await db_session.commit()

    c2 = Customer(
        first_name="Eva",
        last_name="Second",
        email="dup@example.com",
        email_hash=hmac_blind_index("dup@example.com"),
    )
    db_session.add(c2)

    with pytest.raises(Exception):  # IntegrityError on email_hash unique
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_two_different_emails_get_distinct_hashes(db_session):
    """Sanity: distinct emails → distinct hash tags → both rows persist."""
    c1 = Customer(
        first_name="Fritz",
        last_name="Test",
        email="fritz1@example.com",
        email_hash=hmac_blind_index("fritz1@example.com"),
    )
    c2 = Customer(
        first_name="Fritz",
        last_name="Test",
        email="fritz2@example.com",
        email_hash=hmac_blind_index("fritz2@example.com"),
    )
    db_session.add_all([c1, c2])
    await db_session.commit()

    assert c1.email_hash != c2.email_hash
    assert c1.id != c2.id


@pytest.mark.asyncio
async def test_search_customers_uses_blind_index_for_full_email(db_session):
    """``search_customers`` fast-path uses the ``email_hash`` blind-index
    when the query is a full email. Verified indirectly: the exact match
    returns the row.

    The slow path (Python-level substring filter over decrypted values)
    intentionally still finds partial email matches — that's the C1
    accept-search-substring-on-decrypted-ORM-values contract. See the
    docstring on ``search_customers``.
    """
    customer = Customer(
        first_name="Grace",
        last_name="Unique",
        email="grace.unique@example.com",
        email_hash=hmac_blind_index("grace.unique@example.com"),
    )
    db_session.add(customer)
    await db_session.commit()

    # Exact full email ⇒ blind-index fast path.
    results = await CustomerService.search_customers(
        db_session, "grace.unique@example.com"
    )
    assert any(c.id == customer.id for c in results)

    # Case / whitespace normalisation must reach the same blind-index tag.
    results = await CustomerService.search_customers(
        db_session, "Grace.Unique@Example.COM"
    )
    assert any(c.id == customer.id for c in results)

    # Non-matching email ⇒ blind-index miss ⇒ no result from that path.
    results = await CustomerService.search_customers(
        db_session, "someone.else@example.com"
    )
    assert not any(c.id == customer.id for c in results)


@pytest.mark.asyncio
async def test_no_plaintext_ilike_on_email_column(db_session):
    """The service implementation must not reference a SQL ILIKE over the
    encrypted ``email`` column — that would be a silent bug (would match
    ciphertext fragments, never plaintext). We grep the service source
    as a belt-and-braces guard.
    """
    import inspect

    from goldsmith_erp.services import customer_service

    source = inspect.getsource(customer_service)
    # Any remaining ``email.ilike`` or ``Customer.email.ilike`` is a
    # regression — the C1 refactor replaces those with blind-index
    # equality on ``email_hash``.
    assert "email.ilike" not in source, (
        "customer_service still uses `.email.ilike()` — Fernet ciphertext "
        "cannot match SQL ILIKE. Switch to blind-index equality."
    )
