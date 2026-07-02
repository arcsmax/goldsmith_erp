"""Customer Service - Business logic for customer/CRM operations"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.core.encryption import EncryptionError, hmac_blind_index
from goldsmith_erp.db.models import CalendarEvent, Consultation
from goldsmith_erp.db.models import Customer as CustomerModel
from goldsmith_erp.db.models import (
    CustomerAuditLog,
    CustomerMeasurement,
    CustomerNoGo,
    GDPRRequest,
    Gemstone,
    Invoice,
    InvoiceLineItem,
    MaterialUsage,
    Notification,
)
from goldsmith_erp.db.models import Order as OrderModel
from goldsmith_erp.db.models import (
    OrderComment,
    OrderHallmark,
    OrderHandoff,
    OrderItem,
    OrderPhoto,
    OrderStatusHistory,
    Quote,
    QuoteLineItem,
    RepairJob,
    RepairPhoto,
    ScrapGold,
    ScrapGoldItem,
    TimeEntry,
    ValuationCertificate,
)
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.customer import CustomerCreate, CustomerUpdate

logger = logging.getLogger(__name__)

# Sentinel token that replaces scrubbed PII in free-text fields.
# Chosen so that repeated scrubs are idempotent: once a field contains
# only [REDACTED] tokens, no further PII tokens can match.
REDACTION_TOKEN = "[REDACTED]"

# Sentinel placeholder for signature blob fields (base64 PNG / binary-ish).
# Unlike the free-text REDACTION_TOKEN we cannot pattern-match inside a base64
# blob for individual PII tokens — freetext overlays on a signature image are
# opaque to regex. For GDPR Art. 17 we replace the ENTIRE field with this
# sentinel. Idempotent because the sentinel contains no PII tokens.
SIGNATURE_REDACTION_TOKEN = "[REDACTED_SIGNATURE]"


# ═══════════════════════════════════════════════════════════════════════════
# Declarative scrub target model (H8 + final-sweep pattern)
# ═══════════════════════════════════════════════════════════════════════════
#
# Each ScrubTarget entry in SCRUBBABLE_FIELDS describes one text column on
# one table that may leak customer PII on GDPR Art. 17 erasure. The scrubber
# walks this list at runtime — adding a new leakable field is one row here,
# not N hand-written SQL statements scattered through the service.
#
# ``link`` enumerates how a row on the target table is joined back to the
# customer whose PII is being scrubbed. This is explicit (not inferred) so
# reviewers can audit coverage without running the code.
#
# See docs/superpowers/plans/qr-barcode-workflow/PII-SCRUB-AUDIT.md for the
# full schema audit that produced this list.


@dataclass(frozen=True)
class ScrubTarget:
    """One scrubbable text/binary column on a customer-linked table.

    Attributes
    ----------
    model:
        SQLAlchemy model class for the target table.
    column:
        Attribute name of the text column on the model.
    link:
        How to find rows belonging to a customer. One of:

        - ``"customer_id"``: ``model.customer_id == customer_id``
        - ``"direct"``: this table IS the customers table — the row
          matches on ``model.id == customer_id``. Used for freetext
          columns on the customers row itself (e.g. ``customers.notes``)
          that need PII-scrubbing even before the anonymise/delete
          path fires. See F1 in PII-SCRUB-AUDIT.md.
        - ``"order_id"``: ``model.order_id IN customer's order ids``
        - ``"repair_job_id"``: ``model.repair_job_id IN customer's repair_job ids``
        - ``"scrap_gold_id"``: ``model.scrap_gold_id IN customer's scrap_gold ids``
        - ``"quote_id"``: ``model.quote_id IN customer's quote ids``
        - ``"invoice_id"``: ``model.invoice_id IN customer's invoice ids``
        - ``"notification_any"``: ``related_customer_id == cust OR
          related_order_id IN order_ids`` (notifications have two optional
          linkage columns)
        - ``"calendar_event_order"``: ``order_id IN order_ids``; calendar
          events attached to a customer's orders only.

    counter_key:
        The key in the ``counts`` dict returned by ``scrub_customer_pii``.
        By convention, ``"<tablename>.<column>"``.
    binary:
        When ``True`` the scrubber replaces the ENTIRE field value with
        ``SIGNATURE_REDACTION_TOKEN`` rather than regex-scrubbing PII tokens.
        Used for opaque base64 signature blobs.
    """

    model: type
    column: str
    link: str
    counter_key: str
    binary: bool = False


# The declarative scrub list — SINGLE source of truth for PII-leak coverage.
#
# Ordered for readability: existing H2/H5 entries at top (matches the code
# flow in scrub_customer_pii prior to the final-sweep refactor; preserving
# order avoids behavioural diffs in counters for any caller relying on it —
# e.g. audit log consumers). Final-sweep additions at the bottom.
#
# If a new PII-leakable column is discovered: add a row here AND update
# PII-SCRUB-AUDIT.md. Parametrised tests pick it up automatically.
SCRUBBABLE_FIELDS: List[ScrubTarget] = [
    # ── H2 scope ────────────────────────────────────────────────────────
    ScrubTarget(OrderModel, "description", "customer_id", "orders.description"),
    ScrubTarget(
        OrderModel,
        "special_instructions",
        "customer_id",
        "orders.special_instructions",
    ),
    ScrubTarget(OrderComment, "text", "order_id", "order_comments.text"),
    ScrubTarget(TimeEntry, "notes", "order_id", "time_entries.notes"),
    # ── H5 scope ────────────────────────────────────────────────────────
    ScrubTarget(
        OrderStatusHistory,
        "notes",
        "order_id",
        "order_status_history.notes",
    ),
    ScrubTarget(OrderHandoff, "notes", "order_id", "order_handoffs.notes"),
    ScrubTarget(
        OrderHandoff,
        "response_notes",
        "order_id",
        "order_handoffs.response_notes",
    ),
    ScrubTarget(Gemstone, "notes", "order_id", "gemstones.notes"),
    ScrubTarget(
        RepairJob,
        "item_description",
        "customer_id",
        "repair_jobs.item_description",
    ),
    ScrubTarget(
        RepairJob,
        "diagnosis_notes",
        "customer_id",
        "repair_jobs.diagnosis_notes",
    ),
    ScrubTarget(
        ValuationCertificate,
        "item_description",
        "customer_id",
        "valuation_certificates.item_description",
    ),
    ScrubTarget(
        ValuationCertificate,
        "gemstones_description",
        "customer_id",
        "valuation_certificates.gemstones_description",
    ),
    ScrubTarget(Quote, "notes", "customer_id", "quotes.notes"),
    ScrubTarget(
        Quote,
        "customer_signature_data",
        "customer_id",
        "quotes.customer_signature_data",
        binary=True,
    ),
    # ── Final-sweep (2026-04-17) — definitive coverage ─────────────────
    ScrubTarget(OrderModel, "title", "customer_id", "orders.title"),
    ScrubTarget(
        CustomerMeasurement,
        "notes",
        "customer_id",
        "customer_measurements.notes",
    ),
    ScrubTarget(OrderPhoto, "notes", "order_id", "order_photos.notes"),
    ScrubTarget(
        RepairPhoto,
        "notes",
        "repair_job_id",
        "repair_photos.notes",
    ),
    ScrubTarget(OrderHallmark, "notes", "order_id", "order_hallmarks.notes"),
    ScrubTarget(OrderItem, "description", "order_id", "order_items.description"),
    ScrubTarget(Invoice, "notes", "customer_id", "invoices.notes"),
    ScrubTarget(
        InvoiceLineItem,
        "description",
        "invoice_id",
        "invoice_line_items.description",
    ),
    ScrubTarget(
        QuoteLineItem,
        "description",
        "quote_id",
        "quote_line_items.description",
    ),
    ScrubTarget(ScrapGold, "notes", "customer_id", "scrap_gold.notes"),
    ScrubTarget(
        ScrapGold,
        "signature_data",
        "customer_id",
        "scrap_gold.signature_data",
        binary=True,
    ),
    ScrubTarget(
        ScrapGoldItem,
        "description",
        "scrap_gold_id",
        "scrap_gold_items.description",
    ),
    ScrubTarget(MaterialUsage, "notes", "order_id", "material_usage.notes"),
    ScrubTarget(
        CalendarEvent,
        "title",
        "calendar_event_order",
        "calendar_events.title",
    ),
    ScrubTarget(
        CalendarEvent,
        "description",
        "calendar_event_order",
        "calendar_events.description",
    ),
    ScrubTarget(
        Notification,
        "title",
        "notification_any",
        "notifications.title",
    ),
    ScrubTarget(
        Notification,
        "message",
        "notification_any",
        "notifications.message",
    ),
    # ── F1 (2026-04-16) — customers.notes ──────────────────────────────
    # Freetext goldsmith-entered text ABOUT the customer (allergies,
    # preferences, relationship detail). Scrubbed at the SCRUB-pass
    # layer so PII tokens are replaced before the anonymise/delete
    # path fires — belt-and-braces with the customer-row anonymise
    # step. See PII-SCRUB-AUDIT.md F1 resolution.
    ScrubTarget(CustomerModel, "notes", "direct", "customers.notes"),
    # ── Consultation module (V1.1 / Task 10) ───────────────────────────
    # Consultation rows themselves are retained (anonymised) for Art. 30
    # records — mirroring the RepairJob precedent — so their free-text
    # design-IP fields are scrubbed in place rather than the row deleted.
    ScrubTarget(Consultation, "wishes", "customer_id", "consultations.wishes"),
    ScrubTarget(Consultation, "notes", "customer_id", "consultations.notes"),
    ScrubTarget(
        Consultation, "source_material", "customer_id", "consultations.source_material"
    ),
]

# ── PII encryption helpers ────────────────────────────────────────────────────
# These fields contain GDPR-sensitive personal data and must be encrypted at
# rest when ENCRYPTION_KEY is configured in settings.
#
# As of fix item **C1** (2026-04-24), encryption is performed at the ORM
# layer by the :class:`~goldsmith_erp.db.types.EncryptedString` TypeDecorator
# — service-layer callers no longer need to invoke ``_encrypt_pii`` /
# ``_decrypt_pii`` before writing / after reading. The helpers below remain
# as library functions for programmatic PII collection (e.g. the GDPR
# scrubber's ``_collect_pii_tokens``) and as a fail-loud contract probe
# (see ``tests/unit/test_encryption_fail_loud.py`` from fix item C4). The
# full field set — names, company, email, phone, and address parts — is now
# expressed here even though the helpers are no longer on the hot path, so
# any consumer that does reach for them gets a complete view of what PII
# the Customer row carries.
PII_FIELDS = [
    "first_name",
    "last_name",
    "company_name",
    "email",
    "phone",
    "mobile",
    "street",
    "city",
    "postal_code",
]


def _get_encryption():
    """Return the singleton EncryptionService, or None if the key is unset.

    Returns None only when ``settings.ENCRYPTION_KEY`` is not configured
    (development / migration). If a key IS configured but its initialisation
    fails, the underlying ``EncryptionError`` is re-raised — we MUST NOT
    silently fall back to storing plaintext PII (CLAUDE.md: "Fail loudly —
    never swallow exceptions silently").
    """
    from goldsmith_erp.core.config import settings as _settings

    if not _settings.ENCRYPTION_KEY:
        return None
    from goldsmith_erp.core.encryption import get_encryption_service

    return get_encryption_service()


def _encrypt_pii(data: dict) -> dict:
    """Encrypt PII fields before writing to DB.

    No-op when ENCRYPTION_KEY is not configured (development only — fail-loud
    in production is enforced by ``core.config._check_encryption_key``).
    If encryption IS configured and fails for any reason, the error
    propagates as :class:`EncryptionError` so the caller aborts instead of
    silently persisting plaintext PII.
    """
    enc = _get_encryption()
    if not enc:
        return data
    result = dict(data)
    for field in PII_FIELDS:
        if field in result and result[field]:
            try:
                result[field] = enc.encrypt(result[field])
            except EncryptionError:
                raise
            except Exception as exc:  # noqa: BLE001 — wrap, then re-raise
                from goldsmith_erp.core.encryption import EncryptionError as _EE

                logger.error(
                    "PII encryption failed — refusing to persist plaintext",
                    extra={"audit": True, "field": field, "error": str(exc)},
                )
                raise _EE(f"PII encryption failed for field {field!r}: {exc}") from exc
    return result


def _decrypt_pii(customer: CustomerModel) -> None:
    """Decrypt PII fields in place after reading from DB.

    Tolerates legacy plaintext rows and rows encrypted under a rotated key:
    a per-field ``InvalidToken`` leaves the original value untouched so
    mixed-state tables (mid-migration) stay readable. Any OTHER failure
    (malformed key, backend exception) propagates as ``EncryptionError`` —
    we never hide a broken encryption pipeline behind a silent ``pass``.
    """
    enc = _get_encryption()
    if not enc:
        return
    from cryptography.fernet import InvalidToken

    for field in PII_FIELDS:
        value = getattr(customer, field, None)
        if not value:
            continue
        try:
            setattr(customer, field, enc.decrypt(value))
        except EncryptionError as exc:
            # `EncryptionService.decrypt` wraps InvalidToken → EncryptionError.
            # Unwrap via `__cause__` to distinguish "legacy plaintext / wrong
            # key row" (tolerable) from "cipher backend is broken" (fatal).
            if isinstance(
                exc.__cause__, InvalidToken
            ) or "Invalid encryption token" in str(exc):
                # Already plaintext or encrypted under a different key —
                # leave the stored value as-is.
                continue
            raise


class CustomerService:
    """Service layer for customer management"""

    @staticmethod
    async def get_customers(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        customer_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        tag: Optional[str] = None,
    ) -> List[CustomerModel]:
        """
        Get customers with optional filtering and pagination.

        Uses eager loading to prevent N+1 queries.

        Search behaviour (C1, 2026-04-24)
        ---------------------------------
        Customer name / company / email are encrypted at rest (Fernet via
        ``EncryptedString``) so SQL ``ILIKE`` cannot substring-match the
        ciphertext. When a ``search`` argument is provided we:

          * If it looks like a full email, try the ``email_hash``
            blind-index for an exact match (O(1), index-backed).
          * Otherwise (name / company fragment, or a partial email),
            load the filtered candidate set and apply the fuzzy match in
            Python on the ORM-decrypted fields. This is O(N) over the
            active customer set — acceptable for the MVP dataset size,
            documented as a known performance ceiling for the first
            workshop tenants (typically <10k customers per tenant).

        If full-text search over encrypted names becomes a hot path,
        add a secondary HMAC-indexed column per searchable prefix (e.g.
        ``last_name_hash``) and switch the fast path to equality-lookup.
        """
        # Structural filters (type / active / tag) translate directly to SQL.
        structural_filters = []
        if customer_type:
            structural_filters.append(CustomerModel.customer_type == customer_type)
        if is_active is not None:
            structural_filters.append(CustomerModel.is_active == is_active)
        if tag:
            # JSON array contains tag
            structural_filters.append(CustomerModel.tags.contains([tag]))

        # Fast path: if ``search`` is a full email, equality-lookup via
        # the blind-index. Avoids loading the whole candidate set.
        if search and "@" in search and " " not in search.strip():
            query = (
                select(CustomerModel)
                .options(selectinload(CustomerModel.orders))
                .filter(
                    and_(
                        CustomerModel.email_hash == hmac_blind_index(search),
                        *structural_filters,
                    )
                )
                .order_by(desc(CustomerModel.created_at))
                .offset(skip)
                .limit(limit)
            )
            result = await db.execute(query)
            return list(result.scalars().all())

        # General path: load candidates matching the structural filters,
        # then do Python-level substring filtering on decrypted fields.
        query = (
            select(CustomerModel)
            .options(selectinload(CustomerModel.orders))
            .order_by(desc(CustomerModel.created_at))
        )
        if structural_filters:
            query = query.filter(and_(*structural_filters))

        if not search:
            # No search term — standard pagination applies directly.
            query = query.offset(skip).limit(limit)
            result = await db.execute(query)
            return list(result.scalars().all())

        # Substring search on decrypted fields — pagination applied AFTER
        # filtering so ``skip`` / ``limit`` stay semantically correct.
        result = await db.execute(query)
        all_candidates = list(result.scalars().all())
        needle = search.lower()
        matched = [
            c
            for c in all_candidates
            if (
                (c.first_name and needle in c.first_name.lower())
                or (c.last_name and needle in c.last_name.lower())
                or (c.company_name and needle in c.company_name.lower())
                or (c.email and needle in c.email.lower())
            )
        ]
        return matched[skip : skip + limit]

    @staticmethod
    async def get_customer(
        db: AsyncSession, customer_id: int
    ) -> Optional[CustomerModel]:
        """Get customer by ID with eager loading of relationships.

        PII fields decrypt transparently on ORM read (``EncryptedString``);
        no explicit decrypt step needed here.
        """
        result = await db.execute(
            select(CustomerModel)
            .options(selectinload(CustomerModel.orders))
            .filter(CustomerModel.id == customer_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_customer_by_email(
        db: AsyncSession, email: str
    ) -> Optional[CustomerModel]:
        """Get customer by email address.

        Uses the ``email_hash`` blind-index (HMAC-SHA-256 of the normalised
        email) because the ``email`` column itself holds non-deterministic
        Fernet ciphertext and cannot be equality-compared. Normalisation
        (``.lower().strip()``) is handled by ``hmac_blind_index``.
        """
        result = await db.execute(
            select(CustomerModel).filter(
                CustomerModel.email_hash == hmac_blind_index(email)
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_customer(
        db: AsyncSession, customer_in: CustomerCreate
    ) -> CustomerModel:
        """
        Create a new customer with transactional guarantees.

        Validates that email is unique via the blind-index. PII encryption
        happens transparently at the ORM layer (``EncryptedString`` on every
        PII column); ``email_hash`` is populated here because it has no
        separate encryption layer and must be derived from plaintext.
        """
        async with transactional(db):
            # Check if email already exists (via blind-index)
            existing = await CustomerService.get_customer_by_email(
                db, customer_in.email
            )
            if existing:
                raise ValueError(
                    "Ein Kunde mit dieser E-Mail-Adresse existiert bereits"
                )

            customer_data = customer_in.model_dump()
            # Derive blind-index tag from the plaintext email so equality
            # lookups keep working against the encrypted column.
            customer_data["email_hash"] = hmac_blind_index(customer_in.email)
            db_customer = CustomerModel(**customer_data)

            db.add(db_customer)
            await db.flush()
            await db.refresh(db_customer)

        logger.info(
            "Customer created",
            extra={
                "customer_id": db_customer.id,
                # email intentionally omitted — PII must not appear in logs
                "customer_type": db_customer.customer_type,
            },
        )

        return db_customer

    @staticmethod
    async def update_customer(
        db: AsyncSession, customer_id: int, customer_update: CustomerUpdate
    ) -> Optional[CustomerModel]:
        """
        Update customer with transactional guarantees.

        Only updates fields that are provided (not None). When ``email``
        is updated, the companion ``email_hash`` blind-index is
        recomputed so the uniqueness constraint stays consistent with the
        (ciphertext) ``email`` value.
        """
        async with transactional(db):
            # Get existing customer
            db_customer = await CustomerService.get_customer(db, customer_id)
            if not db_customer:
                return None

            # Update only provided fields
            update_data = customer_update.model_dump(exclude_unset=True)

            # Check email uniqueness if email is being updated
            if "email" in update_data and update_data["email"] != db_customer.email:
                existing = await CustomerService.get_customer_by_email(
                    db, update_data["email"]
                )
                if existing:
                    raise ValueError(
                        "Ein Kunde mit dieser E-Mail-Adresse existiert bereits"
                    )
                # Keep the blind-index in lock-step with the new email.
                update_data["email_hash"] = hmac_blind_index(update_data["email"])

            # Apply updates — ORM-level EncryptedString re-encrypts PII
            # columns on flush, so no service-layer encrypt step needed.
            for field, value in update_data.items():
                setattr(db_customer, field, value)

            db_customer.updated_at = datetime.utcnow()
            await db.flush()
            await db.refresh(db_customer)

        logger.info(
            "Customer updated",
            extra={
                "customer_id": customer_id,
                "updated_fields": list(update_data.keys()),
            },
        )

        return db_customer

    @staticmethod
    async def delete_customer(db: AsyncSession, customer_id: int) -> bool:
        """
        Soft delete a customer (sets is_active = False).

        Does not delete customers with active orders.
        """
        async with transactional(db):
            db_customer = await CustomerService.get_customer(db, customer_id)
            if not db_customer:
                return False

            # Check if customer has orders
            order_count = await CustomerService.get_customer_order_count(
                db, customer_id
            )
            if order_count > 0:
                raise ValueError(
                    f"Cannot delete customer with {order_count} orders. "
                    "Please use soft delete (set is_active=False) instead."
                )

            # Soft delete
            db_customer.is_active = False
            db_customer.updated_at = datetime.utcnow()
            await db.flush()

        logger.info("Customer soft deleted", extra={"customer_id": customer_id})
        return True

    @staticmethod
    async def get_customer_order_count(db: AsyncSession, customer_id: int) -> int:
        """Get total number of orders for a customer"""
        result = await db.execute(
            select(func.count(OrderModel.id)).filter(
                OrderModel.customer_id == customer_id
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def get_customer_stats(db: AsyncSession, customer_id: int) -> Dict[str, Any]:
        """
        Get customer statistics including order count, total spent, last order.
        """
        # Get order statistics
        result = await db.execute(
            select(
                func.count(OrderModel.id).label("order_count"),
                func.sum(OrderModel.price).label("total_spent"),
                func.max(OrderModel.created_at).label("last_order_date"),
            ).filter(OrderModel.customer_id == customer_id)
        )
        stats = result.one()

        return {
            "customer_id": customer_id,
            "order_count": stats.order_count or 0,
            "total_spent": float(stats.total_spent or 0),
            "last_order_date": stats.last_order_date,
        }

    @staticmethod
    async def search_customers(
        db: AsyncSession, query: str, limit: int = 10
    ) -> List[CustomerModel]:
        """
        Fast customer search for autocomplete.

        Searches by name, company, and email over the encrypted Customer
        columns. Strategy (C1, 2026-04-24):

          * A full email ⇒ blind-index equality lookup on ``email_hash``
            (O(1), index-backed). This is the common autocomplete path
            when users paste an email into the search box.
          * Otherwise ⇒ fetch the active customer set and filter in
            Python after ORM decryption. O(N) over active customers;
            acceptable at MVP scale (<10k customers per tenant). If /
            when N grows, add per-field blind-indexes (last_name_hash,
            etc.) and switch the fast path to equality-lookup on them.

        Encrypted fields not searched here — phone, mobile, address parts —
        remain unsearchable until someone explicitly requires it and adds
        a blind-index column.
        """
        # Fast path: full email (contains '@' and no whitespace).
        if "@" in query and " " not in query.strip():
            result = await db.execute(
                select(CustomerModel)
                .filter(
                    and_(
                        CustomerModel.is_active == True,  # noqa: E712
                        CustomerModel.email_hash == hmac_blind_index(query),
                    )
                )
                .limit(limit)
            )
            return list(result.scalars().all())

        # Slow path: load active candidates and filter on decrypted values.
        result = await db.execute(
            select(CustomerModel)
            .filter(CustomerModel.is_active == True)  # noqa: E712
            .order_by(CustomerModel.last_name, CustomerModel.first_name)
        )
        candidates = list(result.scalars().all())
        needle = query.lower()
        matched = [
            c
            for c in candidates
            if (
                (c.first_name and needle in c.first_name.lower())
                or (c.last_name and needle in c.last_name.lower())
                or (c.company_name and needle in c.company_name.lower())
                or (c.email and needle in c.email.lower())
            )
        ]
        return matched[:limit]

    @staticmethod
    async def get_top_customers(
        db: AsyncSession,
        limit: int = 10,
        by: str = "revenue",  # revenue, orders, recent
    ) -> List[Dict[str, Any]]:
        """
        Get top customers by different criteria.

        Args:
            by: 'revenue' (total spent), 'orders' (order count), 'recent' (last order)
        """
        if by == "revenue":
            # Top customers by total revenue
            result = await db.execute(
                select(CustomerModel, func.sum(OrderModel.price).label("total_spent"))
                .join(OrderModel, CustomerModel.id == OrderModel.customer_id)
                .filter(CustomerModel.is_active == True)
                .group_by(CustomerModel.id)
                .order_by(desc("total_spent"))
                .limit(limit)
            )
        elif by == "orders":
            # Top customers by order count
            result = await db.execute(
                select(CustomerModel, func.count(OrderModel.id).label("order_count"))
                .join(OrderModel, CustomerModel.id == OrderModel.customer_id)
                .filter(CustomerModel.is_active == True)
                .group_by(CustomerModel.id)
                .order_by(desc("order_count"))
                .limit(limit)
            )
        else:  # recent
            # Customers with most recent orders
            result = await db.execute(
                select(
                    CustomerModel, func.max(OrderModel.created_at).label("last_order")
                )
                .join(OrderModel, CustomerModel.id == OrderModel.customer_id)
                .filter(CustomerModel.is_active == True)
                .group_by(CustomerModel.id)
                .order_by(desc("last_order"))
                .limit(limit)
            )

        rows = result.all()
        customers = []
        for row in rows:
            customer = row[0]
            stat_value = row[1]
            customers.append(
                {"customer": customer, "stat_value": stat_value, "stat_type": by}
            )

        return customers

    # ═══════════════════════════════════════════════════════════════════════
    # GDPR Art. 17 — PII scrubbing across related free-text fields
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _collect_pii_tokens(customer: CustomerModel) -> List[str]:
        """Return a deduplicated list of PII tokens to redact from free text.

        PII tokens are pulled from the customer's own fields. Encrypted
        fields (phone / mobile / street / city / postal_code) must already
        be decrypted by the caller — this function assumes plaintext.

        Tokens include:
        - first_name, last_name (separate tokens so partial matches work)
        - company_name (as a single multi-word token)
        - email address (full string)
        - phone, mobile (digits-only variant plus the raw value)

        Returns tokens sorted by length descending so the regex engine
        matches the longest possible sequence first (e.g. "Maria Mueller"
        is matched as two separate word tokens before "Maria" alone).
        Tokens shorter than 3 characters are discarded to avoid
        over-redaction of common short substrings.
        """
        tokens: List[str] = []
        seen = set()

        def _add(value: Optional[str]) -> None:
            if not value:
                return
            stripped = value.strip()
            if len(stripped) < 3:
                return
            key = stripped.lower()
            if key in seen:
                return
            seen.add(key)
            tokens.append(stripped)

        # Name fields — stored plaintext on the customer row
        _add(customer.first_name)
        _add(customer.last_name)
        _add(customer.company_name)

        # Email — stored plaintext
        _add(customer.email)

        # Phone numbers — encrypted at rest but expected to be decrypted
        # by the caller (CustomerService.get_customer or explicit _decrypt_pii).
        _add(customer.phone)
        _add(customer.mobile)

        # Add digits-only variants of phone numbers to catch formatted
        # vs. unformatted leaks ("+49 123 456789" vs. "49123456789").
        for phone_field in (customer.phone, customer.mobile):
            if phone_field:
                digits = re.sub(r"\D", "", phone_field)
                if len(digits) >= 5:
                    _add(digits)

        # Longest first so "Maria Mueller" is attempted before "Maria".
        tokens.sort(key=len, reverse=True)
        return tokens

    @staticmethod
    def _redact_text(
        text: Optional[str], tokens: List[str]
    ) -> Tuple[Optional[str], int]:
        """Replace every case-insensitive occurrence of every token with `[REDACTED]`.

        Returns a tuple (redacted_text, redaction_count). `text=None` returns
        (None, 0) unchanged.

        Matching rules:
        - Case-insensitive.
        - Each token is escaped before compilation — no regex injection.
        - Tokens containing only ASCII word characters use word-boundary
          anchors so "Max" does not match inside "Maximum".
        - Tokens with non-word characters (e.g. phone numbers with "+", emails
          with "@") are matched verbatim since \\b does not fire usefully
          around those chars.
        - REDACTION_TOKEN itself is not matched; idempotent on repeat calls.

        Args:
            text: Free-text value to scrub (may be None).
            tokens: PII tokens from `_collect_pii_tokens`.

        Returns:
            Tuple of (scrubbed_text, number_of_replacements).
        """
        if text is None:
            return None, 0
        if not tokens:
            return text, 0

        total_replacements = 0
        scrubbed = text
        for token in tokens:
            if not token:
                continue
            escaped = re.escape(token)
            # Use word boundaries only when the token is entirely word chars;
            # emails and phone numbers contain punctuation that \b treats
            # inconsistently.
            if re.fullmatch(r"\w+", token):
                pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
            else:
                pattern = re.compile(escaped, re.IGNORECASE)

            scrubbed, n = pattern.subn(REDACTION_TOKEN, scrubbed)
            total_replacements += n

        return scrubbed, total_replacements

    @staticmethod
    async def _resolve_link_rows(
        db: AsyncSession,
        target: "ScrubTarget",
        *,
        customer_id: int,
        order_ids: List[int],
        repair_job_ids: List[int],
        scrap_gold_ids: List[int],
        quote_ids: List[int],
        invoice_ids: List[int],
    ) -> List[Any]:
        """Fetch every row on ``target.model`` belonging to this customer.

        Looks up the ``target.link`` kind and applies the corresponding SQL
        filter. Returns [] for link kinds that resolve to no rows (e.g. the
        customer has no orders and the target link is ``order_id``) so the
        caller can skip cleanly.

        Separated from the scrub loop so tests can exercise the linkage
        logic per-link-kind and so a future reviewer can add a new link
        kind in exactly one place.
        """
        model = target.model
        link = target.link

        if link == "customer_id":
            stmt = select(model).filter(model.customer_id == customer_id)
        elif link == "direct":
            # The target table IS customers — match on the primary key.
            # Used for customers' own freetext columns (F1: customers.notes).
            stmt = select(model).filter(model.id == customer_id)
        elif link == "order_id":
            if not order_ids:
                return []
            stmt = select(model).filter(model.order_id.in_(order_ids))
        elif link == "repair_job_id":
            if not repair_job_ids:
                return []
            stmt = select(model).filter(model.repair_job_id.in_(repair_job_ids))
        elif link == "scrap_gold_id":
            if not scrap_gold_ids:
                return []
            stmt = select(model).filter(model.scrap_gold_id.in_(scrap_gold_ids))
        elif link == "quote_id":
            if not quote_ids:
                return []
            stmt = select(model).filter(model.quote_id.in_(quote_ids))
        elif link == "invoice_id":
            if not invoice_ids:
                return []
            stmt = select(model).filter(model.invoice_id.in_(invoice_ids))
        elif link == "calendar_event_order":
            # Calendar events link to orders via a NULL-able order_id. Only
            # scrub events attached to this customer's orders; standalone
            # workshop-task events (order_id = NULL) are not customer data.
            if not order_ids:
                return []
            stmt = select(model).filter(model.order_id.in_(order_ids))
        elif link == "notification_any":
            # Notifications have two optional linkage columns:
            #   - related_customer_id (direct)
            #   - related_order_id (indirect via customer's orders)
            # Scrub any notification referencing either.
            clauses = [model.related_customer_id == customer_id]
            if order_ids:
                clauses.append(model.related_order_id.in_(order_ids))
            stmt = select(model).filter(or_(*clauses))
        else:
            raise ValueError(
                f"ScrubTarget has unknown link kind: {link!r} "
                f"(target {target.counter_key})"
            )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def scrub_customer_pii(
        db: AsyncSession,
        customer_id: int,
        *,
        performed_by: Optional[int] = None,
        skip_gdpr_request: bool = False,
    ) -> Dict[str, int]:
        """Scrub customer PII from free-text fields on related records.

        Implements the free-text half of GDPR Art. 17 erasure: customer
        names, phone numbers, and e-mail addresses that were typed into
        workflow free-text fields are replaced with ``[REDACTED]``. The
        customer row itself is NOT modified here — the caller is responsible
        for setting ``deletion_scheduled_at`` / ``is_active`` on the
        customer.

        Scope is DECLARATIVE: every field covered is listed in
        ``SCRUBBABLE_FIELDS`` (module-level constant). Adding a new field
        is a single row there. See
        ``docs/superpowers/plans/qr-barcode-workflow/PII-SCRUB-AUDIT.md``
        for the full schema audit that justifies each entry.

        Guarantees:
        - Atomic: all updates commit together or roll back together
          (caller owns the transaction boundary; this function only
          flushes, never commits).
        - Idempotent: calling twice produces the same result (no double-
          redaction, no stacked ``[REDACTED] [REDACTED]`` tokens beyond
          what the first call produced).
        - Audit: writes one CustomerAuditLog row summarising the scrub
          (with per-field counts in ``details.counts``) and one
          GDPRRequest row (progresses H3).
        - No PII in logs: structured log records use the customer_id only.

        Args:
            db: Async SQLAlchemy session.
            customer_id: Primary key of the customer whose PII is being
                scrubbed.
            performed_by: Optional user id of the administrator who
                triggered the erasure. Written to the audit log.
            skip_gdpr_request: If True, do NOT write a GDPRRequest row
                from this call. The caller (typically the
                ``/gdpr-erase`` router) is responsible for writing the
                Art. 30 tracking row with the full request lifecycle
                (PENDING → COMPLETED / PARTIAL / FAILED). Default False
                preserves backward compatibility for standalone callers
                (tests, admin-panel bulk scrub, future batch jobs).

        Returns:
            Dict counting redactions per field. Keys enumerate every field
            in the scrub scope (from ``SCRUBBABLE_FIELDS``) — a value of 0
            means the field was examined but contained no PII tokens.
            Two extra keys cover the consultation special cases:
            ``consultations.budget`` (rows whose budget_min/budget_max
            were NULLed) and ``customer_no_gos.deleted`` (preference rows
            hard-deleted). ``total`` is the sum across all fields.
            Returns all-zero counts if the customer does not exist
            (caller should 404 before calling this).
        """
        # Step 1: fetch customer and decrypt PII (needed for matching tokens).
        customer_result = await db.execute(
            select(CustomerModel).filter(CustomerModel.id == customer_id)
        )
        customer = customer_result.scalar_one_or_none()

        # Counter dict: one entry per ScrubTarget + the consultation
        # special-case counters + a "total".
        counts: Dict[str, int] = {target.counter_key: 0 for target in SCRUBBABLE_FIELDS}
        counts["consultations.budget"] = 0
        counts["customer_no_gos.deleted"] = 0
        counts["total"] = 0

        if customer is None:
            return counts

        # Consultations: financial + preference data of the erased person.
        # These don't fit the string-scrub ScrubTarget shape (budget is a
        # NULL-out, no-gos are a hard delete — not a text redaction) and
        # they do NOT depend on PII tokens, so they run unconditionally
        # BEFORE the zero-token early return below. Consultation rows
        # themselves stay (their free-text fields are ScrubTargets); the
        # no-go rows are pure preference data with no Art. 30 retention
        # duty, so they are deleted outright rather than anonymised.
        # Rowcounts are folded into ``counts`` so the audit trail
        # reflects them. The budget UPDATE filters on non-NULL budgets
        # so the counter reflects rows actually changed and stays 0 on
        # a repeat scrub (idempotency).
        budget_result = await db.execute(
            update(Consultation)
            .where(
                Consultation.customer_id == customer_id,
                or_(
                    Consultation.budget_min.isnot(None),
                    Consultation.budget_max.isnot(None),
                ),
            )
            .values(budget_min=None, budget_max=None)
        )
        counts["consultations.budget"] = max(budget_result.rowcount or 0, 0)
        no_go_result = await db.execute(
            delete(CustomerNoGo).where(CustomerNoGo.customer_id == customer_id)
        )
        counts["customer_no_gos.deleted"] = max(no_go_result.rowcount or 0, 0)

        # Decrypt phone / mobile / address fields in-place so the matcher
        # sees plaintext values. _decrypt_pii is a no-op when encryption
        # is not configured.
        _decrypt_pii(customer)

        tokens = CustomerService._collect_pii_tokens(customer)
        if not tokens:
            # Nothing to match — write an audit log and exit cleanly.
            # The consultation budget/no-go erasure above already ran;
            # include it in the total so the audit row reflects it.
            counts["total"] = sum(v for k, v in counts.items() if k != "total")
            await CustomerService._write_scrub_audit_logs(
                db,
                customer_id=customer_id,
                performed_by=performed_by,
                counts=counts,
                token_count=0,
            )
            return counts

        # Step 2: resolve the customer's owned parent-row IDs once. Every
        # ScrubTarget link_kind that is not ``customer_id`` reads from
        # one of these lists, so we compute them up-front and pass them
        # through rather than re-querying per target.
        order_ids = [
            o.id
            for o in (
                await db.execute(
                    select(OrderModel).filter(OrderModel.customer_id == customer_id)
                )
            )
            .scalars()
            .all()
        ]
        repair_job_ids = [
            r.id
            for r in (
                await db.execute(
                    select(RepairJob).filter(RepairJob.customer_id == customer_id)
                )
            )
            .scalars()
            .all()
        ]
        scrap_gold_ids = [
            s.id
            for s in (
                await db.execute(
                    select(ScrapGold).filter(ScrapGold.customer_id == customer_id)
                )
            )
            .scalars()
            .all()
        ]
        quote_ids = [
            q.id
            for q in (
                await db.execute(select(Quote).filter(Quote.customer_id == customer_id))
            )
            .scalars()
            .all()
        ]
        invoice_ids = [
            i.id
            for i in (
                await db.execute(
                    select(Invoice).filter(Invoice.customer_id == customer_id)
                )
            )
            .scalars()
            .all()
        ]

        # Step 3: walk SCRUBBABLE_FIELDS — one pass per target.
        for target in SCRUBBABLE_FIELDS:
            rows = await CustomerService._resolve_link_rows(
                db,
                target,
                customer_id=customer_id,
                order_ids=order_ids,
                repair_job_ids=repair_job_ids,
                scrap_gold_ids=scrap_gold_ids,
                quote_ids=quote_ids,
                invoice_ids=invoice_ids,
            )

            for row in rows:
                if target.binary:
                    # Binary (signature blob) — all-or-nothing replacement.
                    value = getattr(row, target.column)
                    if value and value != SIGNATURE_REDACTION_TOKEN:
                        setattr(
                            row,
                            target.column,
                            SIGNATURE_REDACTION_TOKEN,
                        )
                        counts[target.counter_key] += 1
                else:
                    new_value, n = CustomerService._redact_text(
                        getattr(row, target.column), tokens
                    )
                    if n > 0:
                        setattr(row, target.column, new_value)
                        counts[target.counter_key] += n

        counts["total"] = sum(v for k, v in counts.items() if k != "total")

        # Step 4: write audit records (CustomerAuditLog always, plus
        # optionally GDPRRequest). The ``/gdpr-erase`` router sets
        # skip_gdpr_request=True because it manages the Art. 30 row
        # across the full request lifecycle (PENDING at entry → final
        # status on exit) — see H10 in V1.1-POST-WAVE5-COMPLIANCE-AUDIT.
        await CustomerService._write_scrub_audit_logs(
            db,
            customer_id=customer_id,
            performed_by=performed_by,
            counts=counts,
            token_count=len(tokens),
            write_gdpr_request=not skip_gdpr_request,
        )

        # Flush so the caller's transaction commits the updates atomically.
        # We do NOT commit here — the caller owns the transaction boundary.
        await db.flush()

        logger.info(
            "GDPR PII scrub complete",
            extra={
                "audit": True,
                "action": "gdpr_pii_scrub",
                "customer_id": customer_id,
                "user_id": performed_by,
                "redaction_count": counts["total"],
                "token_count": len(tokens),
                "scrubbable_field_count": len(SCRUBBABLE_FIELDS),
            },
        )

        return counts

    @staticmethod
    async def _write_scrub_audit_logs(
        db: AsyncSession,
        *,
        customer_id: int,
        performed_by: Optional[int],
        counts: Dict[str, int],
        token_count: int,
        write_gdpr_request: bool = True,
    ) -> None:
        """Write CustomerAuditLog + (optionally) GDPRRequest rows.

        Called from `scrub_customer_pii`. Separated so tests can assert on
        the audit side-effect without re-running the scrub logic.

        ``details.scope`` is derived from ``SCRUBBABLE_FIELDS`` so adding
        a new target automatically extends the audit payload.

        When ``write_gdpr_request=False`` (H10 — invoked by the
        ``/gdpr-erase`` router), the Art. 30 row is the caller's
        responsibility and is NOT written here. The CustomerAuditLog
        row is written unconditionally because it captures the scrub
        event separately from the request lifecycle.
        """
        scope_keys = [target.counter_key for target in SCRUBBABLE_FIELDS]
        scrubbed_field_count = sum(1 for key in scope_keys if counts.get(key, 0) > 0)

        audit_log = CustomerAuditLog(
            customer_id=customer_id,
            user_id=performed_by,
            action="gdpr_pii_scrub",
            entity="customer",
            entity_id=customer_id,
            details={
                "counts": counts,
                "token_count": token_count,
                "scope": scope_keys,
                "scrubbed_field_count": scrubbed_field_count,
            },
            timestamp=datetime.utcnow(),
        )
        db.add(audit_log)

        if write_gdpr_request:
            gdpr_request = GDPRRequest(
                customer_id=customer_id,
                request_type="erasure",
                status="completed",
                requested_by=performed_by,
                completed_at=datetime.utcnow(),
                notes=(
                    f"Art. 17 erasure — scrubbed {counts['total']} PII "
                    f"occurrence(s) across {token_count} token(s) in "
                    f"{scrubbed_field_count}/{len(scope_keys)} covered fields."
                ),
            )
            db.add(gdpr_request)
