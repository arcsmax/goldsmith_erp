"""Customer Service - Business logic for customer/CRM operations"""
import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    CalendarEvent,
    Customer as CustomerModel,
    CustomerAuditLog,
    CustomerMeasurement,
    Gemstone,
    GDPRRequest,
    Invoice,
    InvoiceLineItem,
    MaterialUsage,
    Notification,
    Order as OrderModel,
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
from goldsmith_erp.models.customer import CustomerCreate, CustomerUpdate
from goldsmith_erp.db.transaction import transactional

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
]

# ── PII encryption helpers ────────────────────────────────────────────────────
# These fields contain GDPR-sensitive personal data and must be encrypted at
# rest when ENCRYPTION_KEY is configured in settings.
PII_FIELDS = ["phone", "mobile", "street", "city", "postal_code"]


def _get_encryption():
    """Return the singleton EncryptionService, or None if not configured."""
    try:
        from goldsmith_erp.core.encryption import get_encryption_service
        return get_encryption_service()
    except Exception:
        return None


def _encrypt_pii(data: dict) -> dict:
    """Encrypt PII fields before writing to DB.

    No-op when ENCRYPTION_KEY is not configured so the app starts without
    encryption in development / migration scenarios.
    """
    enc = _get_encryption()
    if not enc:
        return data
    result = dict(data)
    for field in PII_FIELDS:
        if field in result and result[field]:
            try:
                result[field] = enc.encrypt(result[field])
            except Exception:
                # Keep plaintext if encryption fails rather than losing data
                pass
    return result


def _decrypt_pii(customer: CustomerModel) -> None:
    """Decrypt PII fields in place after reading from DB.

    Silently skips fields that cannot be decrypted — this covers both
    legacy plaintext rows and rows encrypted under a rotated key.
    """
    enc = _get_encryption()
    if not enc:
        return
    for field in PII_FIELDS:
        value = getattr(customer, field, None)
        if value:
            try:
                setattr(customer, field, enc.decrypt(value))
            except Exception:
                # Already plaintext, wrong key, or NULL — leave as-is
                pass


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
        """
        query = select(CustomerModel).options(
            selectinload(CustomerModel.orders)
        )

        # Apply filters
        filters = []

        if search:
            # Search in name, company, email
            search_term = f"%{search}%"
            filters.append(
                or_(
                    CustomerModel.first_name.ilike(search_term),
                    CustomerModel.last_name.ilike(search_term),
                    CustomerModel.company_name.ilike(search_term),
                    CustomerModel.email.ilike(search_term),
                )
            )

        if customer_type:
            filters.append(CustomerModel.customer_type == customer_type)

        if is_active is not None:
            filters.append(CustomerModel.is_active == is_active)

        if tag:
            # JSON array contains tag
            filters.append(CustomerModel.tags.contains([tag]))

        if filters:
            query = query.filter(and_(*filters))

        # Order by created_at desc (newest first)
        query = query.order_by(desc(CustomerModel.created_at))

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        customers = list(result.scalars().all())
        for customer in customers:
            _decrypt_pii(customer)
        return customers

    @staticmethod
    async def get_customer(db: AsyncSession, customer_id: int) -> Optional[CustomerModel]:
        """Get customer by ID with eager loading of relationships"""
        result = await db.execute(
            select(CustomerModel)
            .options(selectinload(CustomerModel.orders))
            .filter(CustomerModel.id == customer_id)
        )
        customer = result.scalar_one_or_none()
        if customer:
            _decrypt_pii(customer)
        return customer

    @staticmethod
    async def get_customer_by_email(db: AsyncSession, email: str) -> Optional[CustomerModel]:
        """Get customer by email address"""
        result = await db.execute(
            select(CustomerModel).filter(CustomerModel.email == email)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_customer(db: AsyncSession, customer_in: CustomerCreate) -> CustomerModel:
        """
        Create a new customer with transactional guarantees.

        Validates that email is unique.
        """
        async with transactional(db):
            # Check if email already exists
            existing = await CustomerService.get_customer_by_email(db, customer_in.email)
            if existing:
                raise ValueError("Ein Kunde mit dieser E-Mail-Adresse existiert bereits")

            # Encrypt PII before persisting to DB
            customer_data = _encrypt_pii(customer_in.model_dump())
            db_customer = CustomerModel(**customer_data)

            db.add(db_customer)
            await db.flush()
            await db.refresh(db_customer)

        # Decrypt for the response payload — never log PII in plaintext
        _decrypt_pii(db_customer)
        logger.info(
            "Customer created",
            extra={
                "customer_id": db_customer.id,
                # email intentionally omitted — PII must not appear in logs
                "customer_type": db_customer.customer_type,
            }
        )

        return db_customer

    @staticmethod
    async def update_customer(
        db: AsyncSession,
        customer_id: int,
        customer_update: CustomerUpdate
    ) -> Optional[CustomerModel]:
        """
        Update customer with transactional guarantees.

        Only updates fields that are provided (not None).
        """
        async with transactional(db):
            # Get existing customer
            db_customer = await CustomerService.get_customer(db, customer_id)
            if not db_customer:
                return None

            # Update only provided fields
            update_data = customer_update.model_dump(exclude_unset=True)

            # Check email uniqueness if email is being updated
            if 'email' in update_data and update_data['email'] != db_customer.email:
                existing = await CustomerService.get_customer_by_email(db, update_data['email'])
                if existing:
                    raise ValueError("Ein Kunde mit dieser E-Mail-Adresse existiert bereits")

            # Encrypt PII fields before writing to DB
            update_data = _encrypt_pii(update_data)

            # Apply updates
            for field, value in update_data.items():
                setattr(db_customer, field, value)

            db_customer.updated_at = datetime.utcnow()
            await db.flush()
            await db.refresh(db_customer)

        # Decrypt for the response payload
        _decrypt_pii(db_customer)
        logger.info(
            "Customer updated",
            extra={
                "customer_id": customer_id,
                "updated_fields": list(update_data.keys()),
            }
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
            order_count = await CustomerService.get_customer_order_count(db, customer_id)
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
            select(func.count(OrderModel.id))
            .filter(OrderModel.customer_id == customer_id)
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
                func.count(OrderModel.id).label('order_count'),
                func.sum(OrderModel.price).label('total_spent'),
                func.max(OrderModel.created_at).label('last_order_date'),
            )
            .filter(OrderModel.customer_id == customer_id)
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
        db: AsyncSession,
        query: str,
        limit: int = 10
    ) -> List[CustomerModel]:
        """
        Fast customer search for autocomplete.

        Searches by name, company, email.

        NOTE — encrypted field limitation: phone, mobile, street, city and
        postal_code are stored as Fernet ciphertext when ENCRYPTION_KEY is set.
        ILIKE cannot match encrypted values, so those fields are intentionally
        excluded from the WHERE clause here.  If full-address search becomes a
        requirement, implement a separate deterministic-hash index column for
        each encrypted field (HMAC-SHA256 of the normalised plaintext) and
        filter on the hash instead.
        """
        search_term = f"%{query}%"
        result = await db.execute(
            select(CustomerModel)
            .filter(
                and_(
                    CustomerModel.is_active == True,
                    or_(
                        CustomerModel.first_name.ilike(search_term),
                        CustomerModel.last_name.ilike(search_term),
                        CustomerModel.company_name.ilike(search_term),
                        CustomerModel.email.ilike(search_term),
                    )
                )
            )
            .order_by(CustomerModel.last_name, CustomerModel.first_name)
            .limit(limit)
        )
        customers = list(result.scalars().all())
        for customer in customers:
            _decrypt_pii(customer)
        return customers

    @staticmethod
    async def get_top_customers(
        db: AsyncSession,
        limit: int = 10,
        by: str = "revenue"  # revenue, orders, recent
    ) -> List[Dict[str, Any]]:
        """
        Get top customers by different criteria.

        Args:
            by: 'revenue' (total spent), 'orders' (order count), 'recent' (last order)
        """
        if by == "revenue":
            # Top customers by total revenue
            result = await db.execute(
                select(
                    CustomerModel,
                    func.sum(OrderModel.price).label('total_spent')
                )
                .join(OrderModel, CustomerModel.id == OrderModel.customer_id)
                .filter(CustomerModel.is_active == True)
                .group_by(CustomerModel.id)
                .order_by(desc('total_spent'))
                .limit(limit)
            )
        elif by == "orders":
            # Top customers by order count
            result = await db.execute(
                select(
                    CustomerModel,
                    func.count(OrderModel.id).label('order_count')
                )
                .join(OrderModel, CustomerModel.id == OrderModel.customer_id)
                .filter(CustomerModel.is_active == True)
                .group_by(CustomerModel.id)
                .order_by(desc('order_count'))
                .limit(limit)
            )
        else:  # recent
            # Customers with most recent orders
            result = await db.execute(
                select(
                    CustomerModel,
                    func.max(OrderModel.created_at).label('last_order')
                )
                .join(OrderModel, CustomerModel.id == OrderModel.customer_id)
                .filter(CustomerModel.is_active == True)
                .group_by(CustomerModel.id)
                .order_by(desc('last_order'))
                .limit(limit)
            )

        rows = result.all()
        customers = []
        for row in rows:
            customer = row[0]
            stat_value = row[1]
            customers.append({
                "customer": customer,
                "stat_value": stat_value,
                "stat_type": by
            })

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
    def _redact_text(text: Optional[str], tokens: List[str]) -> Tuple[Optional[str], int]:
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
        elif link == "order_id":
            if not order_ids:
                return []
            stmt = select(model).filter(model.order_id.in_(order_ids))
        elif link == "repair_job_id":
            if not repair_job_ids:
                return []
            stmt = select(model).filter(
                model.repair_job_id.in_(repair_job_ids)
            )
        elif link == "scrap_gold_id":
            if not scrap_gold_ids:
                return []
            stmt = select(model).filter(
                model.scrap_gold_id.in_(scrap_gold_ids)
            )
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

        Returns:
            Dict counting redactions per field. Keys enumerate every field
            in the scrub scope (from ``SCRUBBABLE_FIELDS``) — a value of 0
            means the field was examined but contained no PII tokens.
            ``total`` is the sum across all fields. Returns all-zero
            counts if the customer does not exist (caller should 404
            before calling this).
        """
        # Step 1: fetch customer and decrypt PII (needed for matching tokens).
        customer_result = await db.execute(
            select(CustomerModel).filter(CustomerModel.id == customer_id)
        )
        customer = customer_result.scalar_one_or_none()

        # Counter dict: one entry per ScrubTarget + a "total".
        counts: Dict[str, int] = {
            target.counter_key: 0 for target in SCRUBBABLE_FIELDS
        }
        counts["total"] = 0

        if customer is None:
            return counts

        # Decrypt phone / mobile / address fields in-place so the matcher
        # sees plaintext values. _decrypt_pii is a no-op when encryption
        # is not configured.
        _decrypt_pii(customer)

        tokens = CustomerService._collect_pii_tokens(customer)
        if not tokens:
            # Nothing to match — write an audit log and exit cleanly.
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
                    select(OrderModel).filter(
                        OrderModel.customer_id == customer_id
                    )
                )
            )
            .scalars()
            .all()
        ]
        repair_job_ids = [
            r.id
            for r in (
                await db.execute(
                    select(RepairJob).filter(
                        RepairJob.customer_id == customer_id
                    )
                )
            )
            .scalars()
            .all()
        ]
        scrap_gold_ids = [
            s.id
            for s in (
                await db.execute(
                    select(ScrapGold).filter(
                        ScrapGold.customer_id == customer_id
                    )
                )
            )
            .scalars()
            .all()
        ]
        quote_ids = [
            q.id
            for q in (
                await db.execute(
                    select(Quote).filter(Quote.customer_id == customer_id)
                )
            )
            .scalars()
            .all()
        ]
        invoice_ids = [
            i.id
            for i in (
                await db.execute(
                    select(Invoice).filter(
                        Invoice.customer_id == customer_id
                    )
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
                    if (
                        value
                        and value != SIGNATURE_REDACTION_TOKEN
                    ):
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

        counts["total"] = sum(
            v for k, v in counts.items() if k != "total"
        )

        # Step 4: write audit records (CustomerAuditLog + GDPRRequest).
        await CustomerService._write_scrub_audit_logs(
            db,
            customer_id=customer_id,
            performed_by=performed_by,
            counts=counts,
            token_count=len(tokens),
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
    ) -> None:
        """Write CustomerAuditLog + GDPRRequest rows documenting the scrub.

        Called from `scrub_customer_pii`. Separated so tests can assert on
        the audit side-effect without re-running the scrub logic.

        ``details.scope`` is derived from ``SCRUBBABLE_FIELDS`` so adding
        a new target automatically extends the audit payload.
        """
        scope_keys = [target.counter_key for target in SCRUBBABLE_FIELDS]
        scrubbed_field_count = sum(
            1 for key in scope_keys if counts.get(key, 0) > 0
        )

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
