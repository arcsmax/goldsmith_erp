"""Customer Service - Business logic for customer/CRM operations"""
import logging
import re
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    Customer as CustomerModel,
    CustomerAuditLog,
    Gemstone,
    GDPRRequest,
    Order as OrderModel,
    OrderComment,
    OrderHandoff,
    OrderStatusHistory,
    Quote,
    RepairJob,
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

        Scope of scrubbing:

        H2 (initial hotfix):
        - orders.description
        - orders.special_instructions
        - order_comments.text
        - time_entries.notes

        H5 (extension — this commit):
        - order_status_history.notes
        - order_handoffs.notes
        - order_handoffs.response_notes
        - gemstones.notes  (via order_id → customer_id)
        - repair_jobs.item_description  (customer_id direct)
        - repair_jobs.diagnosis_notes   (customer_id direct)
        - valuation_certificates.item_description       (customer_id direct)
        - valuation_certificates.gemstones_description  (customer_id direct)
        - quotes.notes                                  (customer_id direct)
        - quotes.customer_signature_data                (customer_id direct;
          entire blob replaced with ``[REDACTED_SIGNATURE]`` sentinel —
          freetext overlays on the signature image are opaque to regex)

        Guarantees:
        - Atomic: all updates commit together or roll back together.
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
            in the scrub scope — a value of 0 means the field was examined
            but contained no PII tokens. ``total`` is the sum across all
            fields. Returns all-zero counts if the customer does not exist
            (caller should 404 before calling this).
        """
        # Step 1: fetch customer and decrypt PII (needed for matching tokens).
        customer_result = await db.execute(
            select(CustomerModel).filter(CustomerModel.id == customer_id)
        )
        customer = customer_result.scalar_one_or_none()

        counts: Dict[str, int] = {
            # H2 scope
            "orders.description": 0,
            "orders.special_instructions": 0,
            "order_comments.text": 0,
            "time_entries.notes": 0,
            # H5 scope — order-scoped free-text
            "order_status_history.notes": 0,
            "order_handoffs.notes": 0,
            "order_handoffs.response_notes": 0,
            "gemstones.notes": 0,
            # H5 scope — customer-scoped free-text
            "repair_jobs.item_description": 0,
            "repair_jobs.diagnosis_notes": 0,
            "valuation_certificates.item_description": 0,
            "valuation_certificates.gemstones_description": 0,
            "quotes.notes": 0,
            "quotes.customer_signature_data": 0,
            "total": 0,
        }

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

        # Step 2: scrub orders.description and orders.special_instructions.
        orders_result = await db.execute(
            select(OrderModel).filter(OrderModel.customer_id == customer_id)
        )
        orders = list(orders_result.scalars().all())
        order_ids = [o.id for o in orders]

        for order in orders:
            new_desc, desc_count = CustomerService._redact_text(
                order.description, tokens
            )
            if desc_count > 0:
                order.description = new_desc
                counts["orders.description"] += desc_count

            new_instr, instr_count = CustomerService._redact_text(
                order.special_instructions, tokens
            )
            if instr_count > 0:
                order.special_instructions = new_instr
                counts["orders.special_instructions"] += instr_count

        # Step 3: scrub order_comments.text for all comments on the
        # customer's orders.
        if order_ids:
            comments_result = await db.execute(
                select(OrderComment).filter(OrderComment.order_id.in_(order_ids))
            )
            for comment in comments_result.scalars().all():
                new_text, text_count = CustomerService._redact_text(
                    comment.text, tokens
                )
                if text_count > 0:
                    comment.text = new_text
                    counts["order_comments.text"] += text_count

            # Step 4: scrub time_entries.notes for all time entries on the
            # customer's orders.
            time_entries_result = await db.execute(
                select(TimeEntry).filter(TimeEntry.order_id.in_(order_ids))
            )
            for entry in time_entries_result.scalars().all():
                new_notes, notes_count = CustomerService._redact_text(
                    entry.notes, tokens
                )
                if notes_count > 0:
                    entry.notes = new_notes
                    counts["time_entries.notes"] += notes_count

            # ── H5 order-scoped fields ──────────────────────────────────
            # Step 5: scrub order_status_history.notes — this is the short
            # free-text column written when an order's status transitions
            # (e.g. "Bei Abholung durch Frau Schmidt bemerkt...").
            status_history_result = await db.execute(
                select(OrderStatusHistory).filter(
                    OrderStatusHistory.order_id.in_(order_ids)
                )
            )
            for history in status_history_result.scalars().all():
                new_notes, notes_count = CustomerService._redact_text(
                    history.notes, tokens
                )
                if notes_count > 0:
                    history.notes = new_notes
                    counts["order_status_history.notes"] += notes_count

            # Step 6: scrub order_handoffs.notes + response_notes — both
            # can reference customer names ("Frau Mueller holt morgen ab").
            handoffs_result = await db.execute(
                select(OrderHandoff).filter(
                    OrderHandoff.order_id.in_(order_ids)
                )
            )
            for handoff in handoffs_result.scalars().all():
                new_notes, notes_count = CustomerService._redact_text(
                    handoff.notes, tokens
                )
                if notes_count > 0:
                    handoff.notes = new_notes
                    counts["order_handoffs.notes"] += notes_count

                new_response, response_count = CustomerService._redact_text(
                    handoff.response_notes, tokens
                )
                if response_count > 0:
                    handoff.response_notes = new_response
                    counts["order_handoffs.response_notes"] += response_count

            # Step 7: scrub gemstones.notes — gemstone provenance notes
            # often quote the customer (e.g. "Stein vom Kunden Meier").
            # Gemstones are attached to orders, so filter through order_ids.
            gemstones_result = await db.execute(
                select(Gemstone).filter(Gemstone.order_id.in_(order_ids))
            )
            for gem in gemstones_result.scalars().all():
                new_notes, notes_count = CustomerService._redact_text(
                    gem.notes, tokens
                )
                if notes_count > 0:
                    gem.notes = new_notes
                    counts["gemstones.notes"] += notes_count

        # ── H5 customer-scoped fields (no order_ids dependency) ─────────
        # These tables carry a direct customer_id FK, so they are scrubbed
        # even if the customer has zero orders (e.g. standalone repair
        # jobs, standalone quotes).

        # Step 8: scrub repair_jobs.item_description + diagnosis_notes.
        repairs_result = await db.execute(
            select(RepairJob).filter(RepairJob.customer_id == customer_id)
        )
        for repair in repairs_result.scalars().all():
            new_desc, desc_count = CustomerService._redact_text(
                repair.item_description, tokens
            )
            if desc_count > 0:
                repair.item_description = new_desc
                counts["repair_jobs.item_description"] += desc_count

            new_diag, diag_count = CustomerService._redact_text(
                repair.diagnosis_notes, tokens
            )
            if diag_count > 0:
                repair.diagnosis_notes = new_diag
                counts["repair_jobs.diagnosis_notes"] += diag_count

        # Step 9: scrub valuation_certificates.{item_description,
        # gemstones_description}. The H5 row in V1.1-AMENDMENTS.md names
        # ``notes`` / ``customer_signature_data`` on this table, but those
        # columns do not exist on the model. The PII leak surface is on
        # ``item_description`` + ``gemstones_description`` (printed on the
        # certificate next to the customer name) — those fields are what
        # actually need Art. 17 scrubbing here.
        valuations_result = await db.execute(
            select(ValuationCertificate).filter(
                ValuationCertificate.customer_id == customer_id
            )
        )
        for valuation in valuations_result.scalars().all():
            new_item, item_count = CustomerService._redact_text(
                valuation.item_description, tokens
            )
            if item_count > 0:
                valuation.item_description = new_item
                counts["valuation_certificates.item_description"] += item_count

            new_gems, gems_count = CustomerService._redact_text(
                valuation.gemstones_description, tokens
            )
            if gems_count > 0:
                valuation.gemstones_description = new_gems
                counts["valuation_certificates.gemstones_description"] += gems_count

        # Step 10: scrub quotes.notes + customer_signature_data. The
        # signature blob is base64-encoded PNG — regex cannot reliably
        # redact freetext overlays inside the image, so the ENTIRE blob
        # is replaced with the SIGNATURE_REDACTION_TOKEN sentinel. One
        # replacement per populated field counts as a single redaction.
        quotes_result = await db.execute(
            select(Quote).filter(Quote.customer_id == customer_id)
        )
        for quote in quotes_result.scalars().all():
            new_notes, notes_count = CustomerService._redact_text(
                quote.notes, tokens
            )
            if notes_count > 0:
                quote.notes = new_notes
                counts["quotes.notes"] += notes_count

            # Signature blob: treat as all-or-nothing. Skip if already
            # redacted (idempotency) or empty.
            if (
                quote.customer_signature_data
                and quote.customer_signature_data != SIGNATURE_REDACTION_TOKEN
            ):
                quote.customer_signature_data = SIGNATURE_REDACTION_TOKEN
                counts["quotes.customer_signature_data"] += 1

        counts["total"] = sum(
            v for k, v in counts.items() if k != "total"
        )

        # Step 5: write audit records.
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
        """
        audit_log = CustomerAuditLog(
            customer_id=customer_id,
            user_id=performed_by,
            action="gdpr_pii_scrub",
            entity="customer",
            entity_id=customer_id,
            details={
                "counts": counts,
                "token_count": token_count,
                "scope": [
                    # H2 scope
                    "orders.description",
                    "orders.special_instructions",
                    "order_comments.text",
                    "time_entries.notes",
                    # H5 scope
                    "order_status_history.notes",
                    "order_handoffs.notes",
                    "order_handoffs.response_notes",
                    "gemstones.notes",
                    "repair_jobs.item_description",
                    "repair_jobs.diagnosis_notes",
                    "valuation_certificates.item_description",
                    "valuation_certificates.gemstones_description",
                    "quotes.notes",
                    "quotes.customer_signature_data",
                ],
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
                f"Art. 17 erasure — scrubbed {counts['total']} PII occurrence(s) "
                f"across {token_count} token(s) in related free-text fields."
            ),
        )
        db.add(gdpr_request)
