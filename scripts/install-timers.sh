#!/usr/bin/env bash
# ==============================================================================
# install-timers.sh — installs the compliance-critical systemd user timers
#
# OPS-07 (docs/review/2026-09-25/06-testing-ci-ops.md §C): the GDPR Art. 17
# cleanup, the weekly retention sweep, and the out-of-band health watchdog
# ship as ready-to-use systemd USER units under deploy/systemd/, but nothing
# in the repo ever installed them — an operator had to hand-run the
# `systemctl --user enable --now ...` sequence documented in each unit's
# header comment, and nothing verified they ever did.
#
# This script does that sequence for all three timers in one idempotent step:
#   1. copy every deploy/systemd/goldsmith-*.{service,timer} into
#      ~/.config/systemd/user/ (or $XDG_CONFIG_HOME/systemd/user), rewriting
#      the placeholder `WorkingDirectory=%h/goldsmith_erp` to this repo's
#      actual root so it works regardless of clone location;
#   2. `systemctl --user daemon-reload`;
#   3. `systemctl --user enable --now` each of the three *.timer units (the
#      oneshot .service/-alert.service units have no [Install] section and
#      are never enabled directly — they only ever run when their timer, or
#      an OnFailure= dependency, triggers them);
#   4. best-effort `loginctl enable-linger` so the timers keep firing while
#      the operator is logged out (a normal state on a workshop machine);
#   5. print `systemctl --user list-timers 'goldsmith-*'` so the result is
#      immediately checkable.
#
# Safe to re-run: copying is a plain overwrite and `systemctl ... enable
# --now` on an already-enabled/active unit is a no-op.
#
# Usage:
#   scripts/install-timers.sh              # install + enable + start
#   scripts/install-timers.sh --status     # same as `make timers-status`
#
# Env overrides:
#   GOLDSMITH_ERP_HOME   repo root to bake into WorkingDirectory=
#                        (default: auto-detected via git, else this script's
#                        parent directory)
#   COMPOSE_FILE         forwarded as a comment only — the unit files already
#                        default to podman-compose.yml; production deploys
#                        should edit the copied unit in
#                        ~/.config/systemd/user/ (or export COMPOSE_FILE in
#                        the unit's [Service] Environment=) to
#                        podman-compose.prod.yml before enabling.
#
# See docs/technical/GDPR_ERASURE_RETENTION.md and
# docs/technical/infrastructure/PRODUCTION_DEPLOYMENT.md (Schritt 7) for the
# full policy background.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_SYSTEMD_DIR="$SCRIPT_DIR/../deploy/systemd"

# --- repo root (baked into WorkingDirectory=) ---------------------------
if [[ -n "${GOLDSMITH_ERP_HOME:-}" ]]; then
    REPO_ROOT="$GOLDSMITH_ERP_HOME"
elif REPO_ROOT="$(cd "$SCRIPT_DIR/.." && git rev-parse --show-toplevel 2>/dev/null)"; then
    :
else
    REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

# --- destination (systemd USER unit directory) ---------------------------
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

# Timers that get enabled directly (have an [Install] section).
TIMER_UNITS=(
    goldsmith-gdpr-cleanup.timer
    goldsmith-retention-sweep.timer
    goldsmith-health-watchdog.timer
)

# Oneshot service units (triggered by a timer, or via OnFailure=) — copied
# so the timers can resolve them, but never enabled themselves.
SERVICE_UNITS=(
    goldsmith-gdpr-cleanup.service
    goldsmith-gdpr-cleanup-alert.service
    goldsmith-retention-sweep.service
    goldsmith-retention-sweep-alert.service
    goldsmith-health-watchdog.service
)

ALL_UNITS=("${TIMER_UNITS[@]}" "${SERVICE_UNITS[@]}")

info() { echo "[install-timers] $*"; }
warn() { echo "[install-timers] WARNUNG: $*" >&2; }
err()  { echo "[install-timers] FEHLER: $*" >&2; }

print_status() {
    if ! command -v systemctl &>/dev/null; then
        err "systemctl nicht gefunden — dieses Skript benötigt Linux mit systemd (User-Session)."
        return 1
    fi
    systemctl --user list-timers 'goldsmith-*' --all
}

if [[ "${1:-}" == "--status" ]]; then
    print_status
    exit $?
fi

if ! command -v systemctl &>/dev/null; then
    err "systemctl nicht gefunden — dieses Skript benötigt Linux mit systemd (User-Session)."
    err "Auf macOS/Entwicklungsrechnern ohne systemd kann es nicht ausgeführt werden."
    exit 1
fi

for unit in "${ALL_UNITS[@]}"; do
    if [[ ! -f "$DEPLOY_SYSTEMD_DIR/$unit" ]]; then
        err "Erwartete Unit-Datei fehlt: deploy/systemd/$unit"
        exit 1
    fi
done

info "Repository-Wurzel: $REPO_ROOT"
info "Ziel: $UNIT_DIR"
mkdir -p "$UNIT_DIR"

for unit in "${ALL_UNITS[@]}"; do
    src="$DEPLOY_SYSTEMD_DIR/$unit"
    dest="$UNIT_DIR/$unit"
    # Rewrite the WorkingDirectory=%h/goldsmith_erp placeholder to the actual
    # repo root; a no-op sed for units that don't have that line (the two
    # -alert.service units).
    sed "s|WorkingDirectory=%h/goldsmith_erp|WorkingDirectory=$REPO_ROOT|" \
        "$src" > "$dest"
    info "installiert: $unit"
done

info "systemctl --user daemon-reload"
systemctl --user daemon-reload

for timer in "${TIMER_UNITS[@]}"; do
    info "aktivieren + starten: $timer"
    systemctl --user enable --now "$timer"
done

if command -v loginctl &>/dev/null; then
    if loginctl enable-linger "$(whoami)" 2>/dev/null; then
        info "loginctl enable-linger gesetzt — Timer laufen auch nach dem Ausloggen weiter."
    else
        warn "loginctl enable-linger fehlgeschlagen (evtl. fehlende Berechtigung)."
        warn "Ohne Linger laufen die Timer nur, solange eine Benutzersitzung aktiv ist."
        warn "Manuell nachholen: loginctl enable-linger \$(whoami)"
    fi
fi

echo ""
info "Fertig. Aktueller Timer-Status:"
print_status
