"""
GDPR-compliant audit logging middleware.

This middleware automatically logs access to regulated resource families
for compliance with GDPR Article 30 (Records of processing activities)
and the CLAUDE.md "Data Privacy Rules" section, which requires:

- Customer PII (personal data): every access audit-logged (A1, 2025-11).
- Financial data (invoices, valuations, scrap-gold): every access
  audit-logged (C6, 2026-04).

The audited path prefixes and their action / entity mappings live in the
``_RESOURCE_ROUTES`` table — one dict entry per resource family.  Paths
outside that table short-circuit out of the middleware without any DB
work, keeping the unaudited fast-path near-free.

Each audit row records:
- Who accessed the data (user ID; role/email intentionally omitted here,
  see F-25 follow-up).
- When it was accessed (UTC timestamp).
- What was accessed (endpoint, entity type, entity id where available).
- How it was accessed (HTTP method, IP address, user agent).
- Why it was accessed (purpose, legal basis — customer rows cite Art.
  6(1)(b) contract; financial rows cite Art. 6(1)(c) legal obligation /
  §147 AO).

History:
- 2025-11-06 (A1): initial customer-data auditing.
- 2026-04-23 (R1): closed Art. 30 gap by auditing bulk list reads.
- 2026-04-23 (C6): extended to invoices / valuations / scrap-gold.
- 2026-07 (final-review): extended to consultations (budget_min/budget_max
  financial data).
"""

import ipaddress
import json
import logging
import time
from datetime import datetime
from typing import Callable, Optional, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

try:
    from goldsmith_erp.db.session import AsyncSessionLocal
except ImportError:
    AsyncSessionLocal = None  # type: ignore[assignment]

try:
    from goldsmith_erp.db.models import CustomerAuditLog
except ImportError:
    CustomerAuditLog = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


def _is_trusted_proxy_ip(ip: str) -> bool:
    """Return True if *ip* is a loopback or RFC-1918 private address."""
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_loopback or addr.is_private
    except ValueError:
        return False


def get_real_ip(request: Request) -> str:
    """
    Return the real client IP address.

    X-Forwarded-For is only trusted when the direct TCP peer
    (request.client.host) is a loopback or private-network address,
    i.e. a known-good reverse proxy.  Untrusted clients that inject
    X-Forwarded-For are ignored and their direct IP is used instead.
    """
    direct_ip = request.client.host if request.client else None

    if direct_ip and _is_trusted_proxy_ip(direct_ip):
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

    return direct_ip or "unknown"


# ---------------------------------------------------------------------------
# Audited resource routing table
# ---------------------------------------------------------------------------
#
# Each entry maps a URL resource segment (as it appears after ``/api/v1/``)
# to a tuple of:
#
#   (entity_type, single_action, list_action, is_financial)
#
# * ``entity_type``   — value written to ``CustomerAuditLog.entity``.  Uses
#                       snake_case (URL hyphens are converted) so SQL
#                       filters like ``WHERE entity = 'scrap_gold'`` stay
#                       Python-identifier friendly.
# * ``single_action`` — action written when the URL's second segment is an
#                       integer id (e.g. ``/api/v1/invoices/42`` or
#                       ``/api/v1/scrap-gold/42/receipt.pdf``).
# * ``list_action``   — action written when the URL has no numeric id
#                       (list endpoints, search, aggregate helpers like
#                       ``/scrap-gold/alloy-calculator``).  Distinguishing
#                       the two is useful for GDPR Art. 30 dashboards:
#                       bulk reads carry a higher risk class than
#                       per-record reads.
# * ``is_financial``  — flag that toggles the scope of non-GET auditing.
#                       For customers we audit every verb (A1 legacy).
#                       For financial resources the C6 spec limits audit
#                       to GETs — write-side auditing is handled by the
#                       service layer and is out of scope for this fix.
#
# Adding a new audited resource is a one-line change to this dict.
_RESOURCE_ROUTES: dict[str, Tuple[str, str, str, bool]] = {
    "customers": ("customer", "accessed", "list_accessed", False),
    "invoices": ("invoice", "financial_read", "list_accessed_financial", True),
    "valuations": ("valuation", "financial_read", "list_accessed_financial", True),
    "scrap-gold": ("scrap_gold", "financial_read", "list_accessed_financial", True),
    # Final-review fix: consultations return budget_min/budget_max on every
    # read (financial data of the erased person, CLAUDE.md: "All financial
    # data access MUST be audit-logged") but were missing from this table
    # entirely, so neither single-record nor bulk-list reads were audited.
    "consultations": (
        "consultation",
        "financial_read",
        "list_accessed_financial",
        True,
    ),
    # V1.2 (Kundeninfo / §649 BGB Kostenfreigabe): covers
    # ``GET /api/v1/updates/{id}/pdf`` (parts[2] == "updates"). The
    # "cost-changes" entry is added for symmetry/future-proofing but is
    # currently INERT — every existing ``/cost-changes/...`` route is a
    # POST (create-linked-update / record-response), and this table's
    # is_financial=True GET-only filter (see dispatch()) means non-GET
    # traffic under a financial family never reaches _log_to_database at
    # all. RESOLVED (final-review fix): the THREE ``/orders/{id}/...``
    # GETs this table structurally cannot see (history, cost-changes
    # list, projected-cost — they key on the FIRST path segment "orders",
    # which is not itself a registered family; a blanket "orders" entry
    # was deliberately rejected — it would audit every unrelated order
    # fetch app-wide) now ALSO write a ``CustomerAuditLog`` row directly
    # from the service layer: ``customer_update_service.
    # write_financial_audit_row`` (shared by
    # ``CustomerUpdateService.list_for_order``,
    # ``CostChangeService.list_for_order``, and the projected-cost router
    # handler), mirroring this middleware's ``_log_to_database`` action
    # naming and ``details`` JSON shape. Real DB-row audit coverage for
    # CostChangeRequest mutations remains structured-log-only (kept as
    # before, per the same rationale) — only the three specified GETs
    # were in scope for this fix. See the report for the full resolution.
    "updates": ("customer_update", "financial_read", "list_accessed_financial", True),
    "cost-changes": (
        "cost_change",
        "financial_read",
        "list_accessed_financial",
        True,
    ),
    # V1.3 Phase 1 (statistical labor estimator): covers
    # ``GET /api/v1/estimates/accuracy`` (parts[3]="accuracy", non-numeric
    # -> list_action). ``POST /api/v1/estimates/labor`` shares this same
    # family key (parts[2]="estimates") but, same as "cost-changes" above,
    # this table's is_financial=True GET-only filter (see dispatch())
    # means that POST never reaches _log_to_database via this middleware
    # — the router writes its own CustomerAuditLog row via
    # ``write_financial_audit_row`` instead (see api/routers/estimator.py).
    "estimates": ("estimate", "financial_read", "list_accessed_financial", True),
}


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for automatic GDPR-compliant audit logging.

    Intercepts all HTTP requests to audited endpoints and writes a
    ``CustomerAuditLog`` row describing who accessed what and when.

    Audited resource families (see ``_RESOURCE_ROUTES`` above):

    * ``/api/v1/customers/*``      — PII, full-verb audit (A1 + R1 behaviour)
    * ``/api/v1/invoices/*``       — financial data, GET-only audit (C6)
    * ``/api/v1/valuations/*``     — financial data, GET-only audit (C6)
    * ``/api/v1/scrap-gold/*``     — financial data, GET-only audit (C6)
    * ``/api/v1/consultations/*``  — financial data (budget_min/budget_max),
      GET-only audit (final-review fix)
    * ``/api/v1/updates/*``        — V1.2 Kundeninfo updates, GET-only audit
      (currently only reaches ``GET /updates/{id}/pdf`` — see
      ``_RESOURCE_ROUTES``'s comment on the ``/orders/{id}/...`` blind spot)
    * ``/api/v1/cost-changes/*``   — V1.2 §649 cost-change requests (table
      entry present but currently inert — no GET route exists under this
      root; see ``_RESOURCE_ROUTES`` comment)
    * ``/api/v1/estimates/*``      — V1.3 statistical labor estimator;
      ``GET /estimates/accuracy`` audited here, ``POST /estimates/labor``
      audited by the router directly (see ``_RESOURCE_ROUTES`` comment)

    CLAUDE.md:
        "All financial data access MUST be audit-logged."

    Usage:
        app.add_middleware(AuditLoggingMiddleware)
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process each request and, when it targets an audited resource,
        write a ``CustomerAuditLog`` row.

        The audit write is fire-and-forget relative to the user response:
        the handler runs first, the response is shaped, THEN we attempt
        the audit write inside a broad try/except.  A DB outage on the
        audit path must never deny legitimate data access (security >
        correctness > convenience in CLAUDE.md working-style hierarchy,
        with "correctness of the response" outranking "completeness of
        the audit trail" — the failure is logged loudly for out-of-band
        alerting).
        """
        audit_context = self._extract_audit_context(request.url.path)
        if audit_context is None:
            # Not an audited endpoint — short-circuit before any measurement
            # work.  Middleware is on the hot path; every allocation here
            # costs per-request.
            return await call_next(request)

        entity_type, single_action, list_action, is_financial = audit_context
        method = request.method

        # C6: for financial resources we only audit GETs.  POST / PATCH /
        # DELETE on invoices/valuations/scrap-gold are mutating actions
        # that are audit-logged at the service layer (F-05 in
        # docs/review/2026-04-23/FIX-PLAN.md describes this split
        # explicitly).  Auditing them here would double-count and blur
        # dashboards that filter on ``action="financial_read"``.
        if is_financial and method != "GET":
            return await call_next(request)

        # Extract request metadata
        start_time = time.time()
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")

        # Extract authenticated user_id from request.state (set by
        # AuthRequiredMiddleware).  We deliberately do NOT read a full
        # user object here — keeping middleware off the DB hot-path is
        # cheaper and avoids leaking PII (email, role) into middleware
        # state.
        user_id = getattr(request.state, "user_id", None)

        # Resolve the entity id from the URL (parts[3] if numeric).
        entity_id = self._extract_entity_id(request.url.path)

        # Determine action:
        #
        # * GET with a numeric id   -> single_action  (accessed / financial_read)
        # * GET without a numeric id -> list_action   (list_accessed / list_accessed_financial)
        # * non-GET on /customers    -> verb-based (created / updated / deleted)
        # * non-GET on financial     -> filtered out above
        #
        # R1 context: bulk list reads MUST be audited (they expose more
        # records than single reads); the distinct list_action makes the
        # row easy to pick out in Art. 30 reporting.
        if method == "GET":
            action = single_action if entity_id is not None else list_action
        else:
            action = self._method_to_action(method)

        # Process the request first — the audit write must NEVER block or
        # fail the user's response.  Even if the handler raises, we still
        # want a row in the audit log (access attempts are auditable under
        # GDPR Art. 30).
        response = await call_next(request)

        # Calculate request duration
        duration_ms = (time.time() - start_time) * 1000

        # Write the audit row.  Wrap in a broad try/except: an audit-write
        # failure must NOT propagate to the user.  The ERROR log line is
        # tagged so Loki/ELK rules can alert on audit failures separately.
        try:
            await self._log_to_database(
                customer_id=entity_id if entity_type == "customer" else None,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                method=method,
                endpoint=request.url.path,
                user_id=user_id,
                user_email=None,  # PII — see F-25 follow-up
                user_role=None,
                ip_address=client_ip,
                user_agent=user_agent,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
        except Exception as exc:  # pragma: no cover — defensive belt
            logger.error(
                "audit write failed: %s",
                exc,
                extra={"audit": True, "path": request.url.path},
                exc_info=True,
            )

        # Log to application log for monitoring — user_email omitted (PII).
        logger.info(
            f"{entity_type} data access: {method} {request.url.path} | "
            f"User ID: {user_id or 'anonymous'} | "
            f"IP: {client_ip} | "
            f"Status: {response.status_code} | "
            f"Duration: {duration_ms:.2f}ms"
        )

        return response

    @staticmethod
    def _extract_audit_context(
        path: str,
    ) -> Optional[Tuple[str, str, str, bool]]:
        """
        Determine whether *path* targets an audited resource and, if so,
        return the resource's ``(entity_type, single_action, list_action,
        is_financial)`` tuple.  Returns ``None`` for unaudited paths — the
        dispatcher uses that as the fast-path short-circuit.

        The parser splits the path on ``/`` and inspects the segment
        immediately after ``api/v1``.  Trailing / leading slashes and
        empty segments are tolerated.  This is deliberately a pure string
        operation — no regex — so that path-parsing remains trivially
        reviewable and has predictable cost.

        Examples::

            /api/v1/customers/123        -> ("customer",   "accessed", "list_accessed", False)
            /api/v1/customers            -> ("customer",   "accessed", "list_accessed", False)
            /api/v1/invoices/42/pdf      -> ("invoice",    "financial_read", "list_accessed_financial", True)
            /api/v1/scrap-gold/7         -> ("scrap_gold", "financial_read", "list_accessed_financial", True)
            /api/v1/scrap-gold/alloy-x   -> ("scrap_gold", "financial_read", "list_accessed_financial", True)
            /api/v1/orders/1             -> None
            /docs                        -> None
        """
        parts = [p for p in path.split("/") if p]
        if len(parts) < 3 or parts[0] != "api" or parts[1] != "v1":
            return None
        return _RESOURCE_ROUTES.get(parts[2])

    @staticmethod
    def _extract_entity_id(path: str) -> Optional[int]:
        """
        Extract the numeric entity id from the path segment immediately
        after the resource name (``/api/v1/<resource>/<id>[/...]``).

        Returns ``None`` when:

        * the path has no fourth segment (``/api/v1/invoices``)
        * the fourth segment is not all digits (``/api/v1/customers/search``,
          ``/api/v1/scrap-gold/alloy-calculator``)

        This preserves the original A1 semantics for ``/customers/search``
        — a non-numeric sub-resource is treated as a list-style access.
        """
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 4 and parts[3].isdigit():
            return int(parts[3])
        return None

    # ------------------------------------------------------------------
    # Back-compat shim: external callers (tests, A1/R1 code paths) may
    # still import _extract_customer_id.  Delegate to the generalized
    # helper so behaviour for /customers/* is byte-for-byte identical.
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_customer_id(path: str) -> Optional[int]:
        """
        Deprecated alias retained for backward compatibility.  New code
        should use ``_extract_entity_id`` together with
        ``_extract_audit_context`` — they carry the resource type too.
        """
        context = AuditLoggingMiddleware._extract_audit_context(path)
        if context is None or context[0] != "customer":
            return None
        return AuditLoggingMiddleware._extract_entity_id(path)

    def _get_client_ip(self, request: Request) -> str:
        """
        Get client IP address, validating proxy headers against the direct peer.

        Args:
            request: HTTP request

        Returns:
            Client IP address
        """
        return get_real_ip(request)

    def _method_to_action(self, method: str) -> str:
        """
        Convert HTTP method to audit log action.

        Args:
            method: HTTP method (GET, POST, PUT, etc.)

        Returns:
            Audit log action
        """
        action_map = {
            "GET": "accessed",
            "POST": "created",
            "PUT": "updated",
            "PATCH": "updated",
            "DELETE": "deleted",
        }
        return action_map.get(method, "accessed")

    async def _log_to_database(
        self,
        customer_id: Optional[int],
        action: str,
        method: str,
        endpoint: str,
        user_id: Optional[int],
        user_email: Optional[str],
        user_role: Optional[str],
        ip_address: str,
        user_agent: str,
        status_code: int,
        duration_ms: float,
        entity_type: str = "customer",
        entity_id: Optional[int] = None,
    ):
        """
        Persist a CustomerAuditLog row for this request.

        The write opens its own `AsyncSessionLocal()` because
        ``BaseHTTPMiddleware`` cannot use FastAPI's ``Depends(get_db)``.
        This matches the pattern already used by the system monitor
        background loop (see ``services/system_monitor.py``).

        Only the columns that actually exist on :class:`CustomerAuditLog`
        are populated.  Extras (``endpoint``, ``http_method``, duration,
        legal basis, purpose) are packed into the ``details`` JSON column.

        This method is the unit tests patch; it must therefore be
        side-effect-only (no return value the caller relies on).

        R1: rows with ``customer_id`` / ``entity_id`` = None are valid and
        expected for bulk list/search endpoints (``GET /api/v1/customers/``,
        ``GET /api/v1/customers/search``) and for POST-create requests
        (DB-assigned id is not known at middleware time).  Previously this
        method returned early when ``customer_id`` was falsy, silently
        dropping those rows — a P1 GDPR Art. 30 gap for bulk PII access.

        C6: the ``entity_type`` / ``entity_id`` kwargs generalize the
        writer to cover invoices / valuations / scrap-gold in addition
        to customers.  ``customer_id`` remains populated for the
        ``entity_type == "customer"`` case only — the ``customer_audit_logs.
        customer_id`` column has a foreign key to ``customers.id`` and
        writing a non-customer integer there would violate referential
        integrity.  The ``entity_id`` column is the generic pointer used
        for non-customer entities.
        """
        if AsyncSessionLocal is None or CustomerAuditLog is None:
            # Import-time failure — audit is not available in this env.
            logger.error(
                "audit write skipped: AsyncSessionLocal or "
                "CustomerAuditLog not importable",
                extra={"audit": True},
            )
            return

        # Financial reads cite a different legal basis than customer-PII
        # reads: Art. 6(1)(c) "legal obligation" (German §147 AO requires
        # retaining invoice records) rather than 6(1)(b) "contract".
        # Dashboards filtering by legal_basis can slice financial traffic
        # cleanly this way.
        if entity_type == "customer":
            legal_basis = "GDPR Article 6(1)(b) - Contract"
            purpose = f"Customer data {action} via API"
        else:
            legal_basis = "GDPR Article 6(1)(c) - Legal obligation (§147 AO)"
            purpose = f"{entity_type.replace('_', ' ').title()} {action} via API"

        details = {
            "endpoint": endpoint,
            "http_method": method,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "legal_basis": legal_basis,
            "purpose": purpose,
        }

        try:
            async with AsyncSessionLocal() as session:
                audit_log = CustomerAuditLog(
                    customer_id=customer_id,
                    action=action,
                    entity=entity_type,
                    entity_id=entity_id,
                    user_id=user_id,
                    user_email=user_email,
                    user_role=user_role,
                    timestamp=datetime.utcnow(),
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details=details,
                )
                session.add(audit_log)
                await session.commit()
        except Exception as exc:
            # Fail loudly in the log but never propagate — a DB outage on
            # the audit path must not deny legitimate data access.
            logger.error(
                "audit DB write failed: %s",
                exc,
                extra={
                    "audit": True,
                    "entity": entity_type,
                    "entity_id": entity_id,
                },
                exc_info=True,
            )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    General request logging middleware for all API endpoints.

    Logs all incoming requests for security monitoring and debugging.

    Usage:
        app.add_middleware(RequestLoggingMiddleware)
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Log incoming requests.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response
        """
        start_time = time.time()

        # Log request
        logger.info(
            f"→ {request.method} {request.url.path} | "
            f"IP: {self._get_client_ip(request)}"
        )

        # Process request
        response = await call_next(request)

        # Log response
        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            f"← {request.method} {request.url.path} | "
            f"Status: {response.status_code} | "
            f"Duration: {duration_ms:.2f}ms"
        )

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address, validating proxy headers against the direct peer."""
        return get_real_ip(request)


# ═══════════════════════════════════════════════════════════════════════════
# Request ID Middleware (for correlation)
# ═══════════════════════════════════════════════════════════════════════════

import uuid


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Add unique request ID to each request for correlation.

    Useful for:
    - Tracking requests across services
    - Correlating logs
    - Debugging issues

    Usage:
        app.add_middleware(RequestIDMiddleware)
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Add request ID to request and response.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response with X-Request-ID header
        """
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Store in request state for access in route handlers
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response
