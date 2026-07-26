#!/usr/bin/env bash
# ==============================================================================
# gdpr-cleanup.sh — GDPR Art. 17 Löschung nach 30-Tage-Frist
#
# Führt im Backend-Container den Cleanup-Job aus, der alle Kunden endgültig
# verarbeitet, deren Löschfrist (deletion_scheduled_at) abgelaufen ist:
#
#   * Kunden OHNE aufbewahrungspflichtige Finanzunterlagen  → Zeile gelöscht.
#   * Kunden MIT Rechnungen/Kostenvoranschlägen/Wertgutachten (§147 AO,
#     10 Jahre Aufbewahrung) → in-place anonymisiert (Identität gelöscht,
#     Datensatz bleibt für die gesetzliche Aufbewahrung erhalten).
#
# Die eigentliche Logik liegt in ``goldsmith_erp.jobs.gdpr_cleanup`` (per
# ``python -m`` aufgerufen). Dieses Skript ist nur der Container-Wrapper.
#
# Exit-Code:
#   0  → Lauf erfolgreich, keine Fehler.
#   1  → mindestens ein Kunde fehlgeschlagen ODER Backend nicht erreichbar.
#        (Der systemd-Timer löst über OnFailure= die Admin-Benachrichtigung
#         aus — siehe deploy/systemd/.)
#
# Ausführung (empfohlen via systemd-Timer, siehe deploy/systemd/; alternativ
# Cron, täglich nachts):
#   0 2 * * * /path/to/goldsmith_erp/scripts/gdpr-cleanup.sh >> /var/log/gdpr-cleanup.log 2>&1
# ==============================================================================
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-podman-compose.yml}"
COMPOSE_CMD="${COMPOSE_CMD:-podman-compose}"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] GDPR-Cleanup gestartet"

# ---------------------------------------------------------------------------
# Ausführung im Backend-Container
# ---------------------------------------------------------------------------
if ! ${COMPOSE_CMD} -f "$COMPOSE_FILE" ps --services 2>/dev/null | grep -q "^backend$"; then
    echo "FEHLER: Backend-Container läuft nicht." >&2
    echo "Bitte zuerst starten: ${COMPOSE_CMD} -f $COMPOSE_FILE up -d backend" >&2
    exit 1
fi

# ``|| EXIT_CODE=$?`` verhindert, dass ``set -e`` den Lauf vor der
# Protokollzeile abbricht; der Modul-Exit-Code (0/1) wird durchgereicht.
EXIT_CODE=0
${COMPOSE_CMD} -f "$COMPOSE_FILE" exec -T backend \
    python -m goldsmith_erp.jobs.gdpr_cleanup || EXIT_CODE=$?

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] GDPR-Cleanup beendet (Exit-Code: ${EXIT_CODE})"
exit "${EXIT_CODE}"
