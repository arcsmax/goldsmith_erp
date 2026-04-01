#!/usr/bin/env bash
# setup.sh — Goldsmith ERP first-time production setup
# Idempotent: safe to re-run. Existing .env.production is not overwritten.
# Requires: podman, podman-compose, python3, poetry

set -euo pipefail

# Convenience wrapper so all podman-compose calls use the production env file
COMPOSE_PROD() { podman-compose --env-file .env.production -f podman-compose.prod.yml "$@"; }

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
info() { echo -e "${YELLOW}[INFO]${NC} $*"; }
err()  { echo -e "${RED}[FEHLER]${NC} $*" >&2; }
step() { echo -e "\n${BOLD}==> $*${NC}"; }

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------
step "Abhängigkeiten prüfen"
for cmd in podman podman-compose python3; do
    if ! command -v "$cmd" &>/dev/null; then
        err "Benötigt: $cmd – bitte installieren und erneut ausführen."
        exit 1
    fi
done
ok "Alle Abhängigkeiten gefunden."

# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------
prompt()         { read -r -p "$1 " "$2"; }
prompt_default() {
    # prompt_default "Question" VAR_NAME "default value"
    read -r -p "$1 [${3}]: " _tmpval
    printf -v "$2" '%s' "${_tmpval:-$3}"
}
prompt_password() {
    local _pw1 _pw2
    while true; do
        read -r -s -p "$1: " _pw1; echo
        read -r -s -p "Passwort bestätigen: " _pw2; echo
        if [[ "$_pw1" == "$_pw2" ]]; then
            printf -v "$2" '%s' "$_pw1"
            break
        fi
        echo "Passwörter stimmen nicht überein – bitte erneut versuchen."
    done
}

# ---------------------------------------------------------------------------
# Gather configuration (skip if .env.production already exists)
# ---------------------------------------------------------------------------
ENV_FILE=".env.production"

if [[ -f "$ENV_FILE" ]]; then
    info "$ENV_FILE existiert bereits – Konfigurationsabschnitt wird übersprungen."
    # shellcheck source=/dev/null
    source "$ENV_FILE"
else
    step "Konfiguration eingeben"

    prompt_default "Name der Werkstatt" WORKSHOP_NAME "Goldschmiede"
    prompt         "Admin-E-Mail-Adresse:" ADMIN_EMAIL
    prompt_password "Admin-Passwort (min. 8 Zeichen)" ADMIN_PASSWORD
    prompt         "Admin-Vorname:" ADMIN_FIRST_NAME
    prompt         "Admin-Nachname:" ADMIN_LAST_NAME
    prompt_default "Backup-Ordner" BACKUP_DIR "$HOME/goldsmith-backups/"
    prompt_default "Cloud-Sync-URL (optional, leer lassen)" CLOUD_SYNC_URL ""

    if [[ ${#ADMIN_PASSWORD} -lt 8 ]]; then
        err "Admin-Passwort muss mindestens 8 Zeichen lang sein."
        exit 1
    fi

    # Generate secrets
    step "Sicherheitsschlüssel generieren"
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")
    ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
    ok "Schlüssel generiert."

    # Write .env.production
    step ".env.production erstellen"
    cat > "$ENV_FILE" <<EOF
# Goldsmith ERP – Production Environment
# Generiert am: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# ACHTUNG: Diese Datei enthält geheime Schlüssel. Niemals in Git einchecken!

# Application
WORKSHOP_NAME=${WORKSHOP_NAME}
DEBUG=false
SECRET_KEY=${SECRET_KEY}
ENCRYPTION_KEY=${ENCRYPTION_KEY}
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Database
DB_PASSWORD=${DB_PASSWORD}
POSTGRES_USER=goldsmith
POSTGRES_DB=goldsmith
POSTGRES_HOST=db
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://goldsmith:${DB_PASSWORD}@db:5432/goldsmith

# Redis
REDIS_URL=redis://redis:6379/0
REDIS_HOST=redis
REDIS_PORT=6379

# CORS (adjust to your actual domain/IP)
BACKEND_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Backup
BACKUP_DIR=${BACKUP_DIR}
CLOUD_SYNC_URL=${CLOUD_SYNC_URL}

# Admin user (used only during setup – remove after first run if desired)
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_FIRST_NAME=${ADMIN_FIRST_NAME}
ADMIN_LAST_NAME=${ADMIN_LAST_NAME}
EOF
    chmod 600 "$ENV_FILE"
    ok "$ENV_FILE erstellt (Berechtigungen: 600)."
fi

# Re-source so variables are available for the rest of the script
# shellcheck source=/dev/null
source "$ENV_FILE"

# ---------------------------------------------------------------------------
# Create required directories
# ---------------------------------------------------------------------------
step "Verzeichnisse anlegen"
for dir in "${BACKUP_DIR:-$HOME/goldsmith-backups/}" logs uploads; do
    mkdir -p "$dir"
    ok "Verzeichnis: $dir"
done

# ---------------------------------------------------------------------------
# Build containers
# ---------------------------------------------------------------------------
step "Container bauen"
if ! COMPOSE_PROD build; then
    err "Container-Build fehlgeschlagen."
    exit 1
fi
ok "Container gebaut."

# ---------------------------------------------------------------------------
# Start DB + Redis, wait for healthy, run migrations
# ---------------------------------------------------------------------------
step "Datenbank und Redis starten"
if ! COMPOSE_PROD up -d db redis; then
    err "DB/Redis konnte nicht gestartet werden."
    exit 1
fi

info "Warte auf Datenbank (max. 60 Sekunden)…"
for i in $(seq 1 30); do
    if COMPOSE_PROD exec -T db \
        pg_isready -U "${POSTGRES_USER:-goldsmith}" -d "${POSTGRES_DB:-goldsmith}" &>/dev/null; then
        ok "Datenbank bereit (${i}. Versuch)."
        break
    fi
    if [[ $i -eq 30 ]]; then
        err "Datenbank nicht erreichbar nach 60 Sekunden."
        exit 1
    fi
    sleep 2
done

info "Warte auf Redis…"
for i in $(seq 1 15); do
    if COMPOSE_PROD exec -T redis redis-cli ping &>/dev/null; then
        ok "Redis bereit."
        break
    fi
    if [[ $i -eq 15 ]]; then
        err "Redis nicht erreichbar."
        exit 1
    fi
    sleep 2
done

# Run migrations (needs backend image for alembic + poetry)
step "Datenbankmigrationen ausführen"
if ! COMPOSE_PROD run --rm \
    -e DATABASE_URL="${DATABASE_URL}" \
    backend bash -c "poetry run alembic upgrade head"; then
    err "Migrationen fehlgeschlagen."
    exit 1
fi
ok "Migrationen erfolgreich."

# ---------------------------------------------------------------------------
# Create admin user
# ---------------------------------------------------------------------------
step "Admin-Benutzer anlegen"
# Read admin credentials – either from env vars set during this run or from .env.production
ADMIN_EMAIL="${ADMIN_EMAIL:-}"
ADMIN_FIRST_NAME="${ADMIN_FIRST_NAME:-Admin}"
ADMIN_LAST_NAME="${ADMIN_LAST_NAME:-User}"

if [[ -z "${ADMIN_EMAIL}" ]]; then
    prompt "Admin-E-Mail (für Erstellung übersprungen falls leer):" ADMIN_EMAIL
fi

if [[ -n "${ADMIN_EMAIL}" ]]; then
    # Resolve admin password: either captured during this session or ask again
    if [[ -z "${ADMIN_PASSWORD:-}" ]]; then
        prompt_password "Admin-Passwort" ADMIN_PASSWORD
    fi

    if ! COMPOSE_PROD run --rm \
        -e DATABASE_URL="${DATABASE_URL}" \
        backend python /app/scripts/create-admin.py \
            --email "${ADMIN_EMAIL}" \
            --password "${ADMIN_PASSWORD}" \
            --first-name "${ADMIN_FIRST_NAME}" \
            --last-name "${ADMIN_LAST_NAME}"; then
        err "Admin-Erstellung fehlgeschlagen."
        exit 1
    fi
    ok "Admin-Benutzer bereit."
else
    info "Admin-E-Mail nicht angegeben – Admin-Erstellung übersprungen."
fi

# ---------------------------------------------------------------------------
# Start all services
# ---------------------------------------------------------------------------
step "Alle Dienste starten"
if ! COMPOSE_PROD up -d; then
    err "Dienste konnten nicht gestartet werden."
    exit 1
fi
ok "Alle Dienste laufen."

# ---------------------------------------------------------------------------
# Detect local IP and print access URL
# ---------------------------------------------------------------------------
step "Zugriffs-URL ermitteln"
LOCAL_IP=$(python3 -c "
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    print(s.getsockname()[0])
    s.close()
except Exception:
    print('127.0.0.1')
")
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║   Goldsmith ERP läuft!                               ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Frontend:  ${GREEN}http://${LOCAL_IP}:3000${NC}"
echo -e "  Backend:   ${GREEN}http://${LOCAL_IP}:8000${NC}"
echo -e "  API-Docs:  ${GREEN}http://${LOCAL_IP}:8000/docs${NC}"
echo ""

# ---------------------------------------------------------------------------
# Optional: firewall setup (ufw / firewalld)
# ---------------------------------------------------------------------------
if command -v ufw &>/dev/null; then
    echo -e "${YELLOW}ufw erkannt. Ports 3000 und 8000 für lokales Subnetz freigeben?${NC}"
    read -r -p "[j/N]: " _fw_reply
    if [[ "${_fw_reply,,}" == "j" ]]; then
        SUBNET=$(python3 -c "
import socket, ipaddress
ip = '${LOCAL_IP}'
try:
    iface_ip = ipaddress.ip_interface(ip + '/24')
    print(str(iface_ip.network))
except Exception:
    print('192.168.0.0/24')
")
        sudo ufw allow from "$SUBNET" to any port 3000 proto tcp
        sudo ufw allow from "$SUBNET" to any port 8000 proto tcp
        ok "UFW-Regeln für $SUBNET hinzugefügt."
    fi
elif command -v firewall-cmd &>/dev/null; then
    echo -e "${YELLOW}firewalld erkannt. Ports 3000 und 8000 freigeben?${NC}"
    read -r -p "[j/N]: " _fw_reply
    if [[ "${_fw_reply,,}" == "j" ]]; then
        sudo firewall-cmd --permanent --add-port=3000/tcp
        sudo firewall-cmd --permanent --add-port=8000/tcp
        sudo firewall-cmd --reload
        ok "Firewalld-Regeln hinzugefügt."
    fi
fi

# ---------------------------------------------------------------------------
# Optional: avahi mDNS setup
# ---------------------------------------------------------------------------
if command -v avahi-daemon &>/dev/null; then
    echo ""
    echo -e "${YELLOW}avahi erkannt. mDNS-Dienst einrichten (erreichbar als goldsmith.local)?${NC}"
    read -r -p "[j/N]: " _avahi_reply
    if [[ "${_avahi_reply,,}" == "j" ]]; then
        AVAHI_SERVICE_FILE="/etc/avahi/services/goldsmith-erp.service"
        sudo tee "$AVAHI_SERVICE_FILE" > /dev/null <<AVAHI
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">Goldsmith ERP auf %h</name>
  <service>
    <type>_http._tcp</type>
    <port>3000</port>
    <txt-record>path=/</txt-record>
  </service>
</service-group>
AVAHI
        sudo systemctl reload avahi-daemon 2>/dev/null || sudo service avahi-daemon reload 2>/dev/null || true
        ok "mDNS eingerichtet: http://goldsmith.local:3000"
    fi
fi

echo ""
ok "Setup abgeschlossen."
