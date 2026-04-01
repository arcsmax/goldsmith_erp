#!/usr/bin/env bash
# ==============================================================================
# gdpr-cleanup.sh — GDPR Art. 17 Hard-Delete nach 30-Tage-Frist
#
# Führt im Backend-Container ein Python-Skript aus, das alle Kunden
# endgültig löscht, deren Löschfrist (deletion_scheduled_at + 30 Tage)
# abgelaufen ist.
#
# Ausführung (empfohlen via Cron, täglich nachts):
#   0 2 * * * /path/to/goldsmith_erp/scripts/gdpr-cleanup.sh >> /var/log/gdpr-cleanup.log 2>&1
# ==============================================================================
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-podman-compose.yml}"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] GDPR-Cleanup gestartet"

# ---------------------------------------------------------------------------
# Python-Inline-Skript für den Hard-Delete
# ---------------------------------------------------------------------------
PYTHON_SCRIPT='
import asyncio
import sys
import logging
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("gdpr_cleanup")


async def run_cleanup():
    """Hard-delete customers past their 30-day grace period."""
    try:
        from goldsmith_erp.db.session import AsyncSessionLocal
        from goldsmith_erp.db.models import Customer
        from sqlalchemy import select, and_
    except ImportError as exc:
        logger.error("Import error: %s", exc)
        sys.exit(1)

    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        # Find customers past the grace period
        result = await db.execute(
            select(Customer).where(
                and_(
                    Customer.is_active == False,
                    Customer.deletion_scheduled_at != None,
                    Customer.deletion_scheduled_at <= now,
                )
            )
        )
        customers_to_delete = result.scalars().all()

        if not customers_to_delete:
            logger.info("Keine Kunden zur endgültigen Löschung gefunden.")
            return

        deleted_count = 0
        error_count = 0

        for customer in customers_to_delete:
            customer_id = customer.id
            try:
                await db.delete(customer)
                deleted_count += 1
                logger.info(
                    "GDPR hard-delete: Kunde %s endgültig gelöscht "
                    "(Löschfrist war: %s)",
                    customer_id,
                    customer.deletion_scheduled_at,
                )
            except Exception as exc:
                error_count += 1
                logger.error(
                    "Fehler beim Löschen von Kunde %s: %s",
                    customer_id,
                    exc,
                )

        await db.commit()

        logger.info(
            "GDPR-Cleanup abgeschlossen: %d gelöscht, %d Fehler",
            deleted_count,
            error_count,
        )

        if error_count > 0:
            sys.exit(1)


asyncio.run(run_cleanup())
'

# ---------------------------------------------------------------------------
# Ausführung im Backend-Container
# ---------------------------------------------------------------------------
if podman-compose -f "$COMPOSE_FILE" ps --services 2>/dev/null | grep -q "^backend$"; then
    podman-compose -f "$COMPOSE_FILE" exec -T backend python3 -c "$PYTHON_SCRIPT"
    EXIT_CODE=$?
else
    echo "FEHLER: Backend-Container läuft nicht." >&2
    echo "Bitte zuerst starten: podman-compose -f $COMPOSE_FILE up -d backend" >&2
    exit 1
fi

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] GDPR-Cleanup beendet (Exit-Code: $EXIT_CODE)"
exit $EXIT_CODE
