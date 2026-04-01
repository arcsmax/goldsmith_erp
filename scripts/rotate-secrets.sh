#!/usr/bin/env bash
# ==============================================================================
# rotate-secrets.sh — SECRET_KEY rotation for Goldsmith ERP (production)
#
# WICHTIG: Rotiert NUR den SECRET_KEY (JWT-Signing). Der ENCRYPTION_KEY
# wird NICHT rotiert, da sonst alle verschlüsselten Kundendaten (PII)
# unlesbar werden. Für ENCRYPTION_KEY-Rotation ist ein separates
# Datenmigrations-Verfahren erforderlich.
# ==============================================================================
set -euo pipefail

ENV_FILE=".env.production"
COMPOSE_FILE="podman-compose.prod.yml"

# ---------------------------------------------------------------------------
# 1. Prüfe ob .env.production existiert
# ---------------------------------------------------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
    echo "FEHLER: Datei '$ENV_FILE' wurde nicht gefunden." >&2
    echo "Bitte im Projektverzeichnis ausführen und .env.production anlegen." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. Warnung ausgeben
# ---------------------------------------------------------------------------
echo ""
echo "=========================================================="
echo "  SECRET_KEY Rotation — Goldsmith ERP"
echo "=========================================================="
echo ""
echo "WARNUNG: Alle aktiven Sitzungen werden ungültig."
echo "         Benutzer müssen sich erneut anmelden."
echo ""
echo "HINWEIS: Der ENCRYPTION_KEY wird NICHT rotiert."
echo "         Eine Rotation des ENCRYPTION_KEY würde alle"
echo "         verschlüsselten Kundendaten (Namen, Adressen,"
echo "         Telefonnummern) unlesbar machen."
echo ""

# ---------------------------------------------------------------------------
# 3. Bestätigung abfragen
# ---------------------------------------------------------------------------
read -r -p "Fortfahren? (j/n): " CONFIRM

if [[ "$CONFIRM" != "j" && "$CONFIRM" != "J" ]]; then
    echo "Abgebrochen. Keine Änderungen vorgenommen."
    exit 0
fi

echo ""
echo "Generiere neuen SECRET_KEY..."

# ---------------------------------------------------------------------------
# 4. Neuen SECRET_KEY generieren
# ---------------------------------------------------------------------------
NEW_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")

if [[ -z "$NEW_SECRET_KEY" ]]; then
    echo "FEHLER: SECRET_KEY konnte nicht generiert werden." >&2
    exit 1
fi

echo "Neuer SECRET_KEY generiert (${#NEW_SECRET_KEY} Zeichen)."

# ---------------------------------------------------------------------------
# 5. SECRET_KEY in .env.production ersetzen (macOS-kompatibles sed mit .bak)
# ---------------------------------------------------------------------------
# macOS sed requires an extension argument for -i
sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=${NEW_SECRET_KEY}|" "$ENV_FILE"

# Backup-Datei entfernen
rm -f "${ENV_FILE}.bak"

echo "SECRET_KEY in '$ENV_FILE' erfolgreich aktualisiert."

# ---------------------------------------------------------------------------
# 6. Backend neu starten damit der neue Key aktiv wird
# ---------------------------------------------------------------------------
if [[ -f "$COMPOSE_FILE" ]]; then
    echo ""
    echo "Starte Backend neu..."
    podman-compose -f "$COMPOSE_FILE" restart backend
    echo "Backend erfolgreich neugestartet."
else
    echo ""
    echo "HINWEIS: '$COMPOSE_FILE' nicht gefunden."
    echo "Bitte Backend manuell neu starten:"
    echo "  podman-compose -f $COMPOSE_FILE restart backend"
fi

echo ""
echo "=========================================================="
echo "  Rotation abgeschlossen"
echo "=========================================================="
echo ""
echo "NÄCHSTE SCHRITTE:"
echo "  1. Alle Benutzer wurden automatisch abgemeldet."
echo "  2. Benutzer müssen sich mit ihrem Passwort neu anmelden."
echo "  3. Prüfe Backend-Logs: podman-compose -f $COMPOSE_FILE logs -f backend"
echo ""
