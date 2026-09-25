#!/usr/bin/env bash
# scripts/lib/backup-crypto.sh — shared encryption helpers for backup.sh and
# restore.sh (GDPR-06, Art. 32 Abs. 1 lit. a DSGVO).
#
# Sourced, never executed. Keys are always read from FILES named in
# .env.production, never passed as a password on the command line (a
# command-line secret is visible in `ps` and in shell history).
#
# Configuration (.env.production):
#   BACKUP_ENCRYPTION            age | gpg          (default: auto-detect below)
#   BACKUP_AGE_RECIPIENTS_FILE   age public key(s) — needed to ENCRYPT
#   BACKUP_AGE_IDENTITY_FILE     age private key — needed to DECRYPT/verify;
#                                keep it OFF the server (Anne's safe, USB key)
#   BACKUP_PASSPHRASE_FILE       gpg symmetric passphrase file (chmod 600)
#
# Auto-detect: age when BACKUP_AGE_RECIPIENTS_FILE is set, else gpg when
# BACKUP_PASSPHRASE_FILE is set, else "none" (the caller refuses to run
# unless the operator passed --unencrypted explicitly).

# Resolve the configured method into BACKUP_CRYPTO_METHOD (age|gpg|none).
backup_crypto_resolve_method() {
    local requested="${BACKUP_ENCRYPTION:-}"
    if [[ -z "${requested}" ]]; then
        if [[ -n "${BACKUP_AGE_RECIPIENTS_FILE:-}" ]]; then
            requested="age"
        elif [[ -n "${BACKUP_PASSPHRASE_FILE:-}" ]]; then
            requested="gpg"
        else
            requested="none"
        fi
    fi
    case "${requested}" in
        age|gpg|none) BACKUP_CRYPTO_METHOD="${requested}" ;;
        *)
            echo "ERROR: BACKUP_ENCRYPTION must be 'age' or 'gpg', got '${requested}'" >&2
            return 1
            ;;
    esac
}

# File-name suffix for the resolved method.
backup_crypto_suffix() {
    case "${BACKUP_CRYPTO_METHOD}" in
        age) echo ".age" ;;
        gpg) echo ".gpg" ;;
        *)   echo "" ;;
    esac
}

# Fail if a secret key file is missing, unreadable, or group/world-readable.
backup_crypto_require_private_file() {
    local label="$1" path="$2"
    if [[ -z "${path}" ]]; then
        echo "ERROR: ${label} is not set in .env.production" >&2
        return 1
    fi
    if [[ ! -r "${path}" ]]; then
        echo "ERROR: ${label} (${path}) does not exist or is not readable" >&2
        return 1
    fi
    local mode
    mode="$(stat -c '%a' "${path}" 2>/dev/null || stat -f '%Lp' "${path}")"
    if [[ "${mode: -2}" != "00" ]]; then
        echo "ERROR: ${label} (${path}) has mode ${mode}; run: chmod 600 ${path}" >&2
        return 1
    fi
}

# Check that the tool and the key needed to ENCRYPT are present.
backup_crypto_check_encrypt() {
    case "${BACKUP_CRYPTO_METHOD}" in
        age)
            command -v age >/dev/null 2>&1 \
                || { echo "ERROR: 'age' is not installed" >&2; return 1; }
            if [[ ! -r "${BACKUP_AGE_RECIPIENTS_FILE:-}" ]]; then
                echo "ERROR: BACKUP_AGE_RECIPIENTS_FILE is not a readable file" >&2
                return 1
            fi
            ;;
        gpg)
            command -v gpg >/dev/null 2>&1 \
                || { echo "ERROR: 'gpg' is not installed" >&2; return 1; }
            backup_crypto_require_private_file \
                BACKUP_PASSPHRASE_FILE "${BACKUP_PASSPHRASE_FILE:-}"
            ;;
    esac
}

# Check that the tool and the key needed to DECRYPT are present.
backup_crypto_check_decrypt() {
    local method="$1"
    case "${method}" in
        age)
            command -v age >/dev/null 2>&1 \
                || { echo "ERROR: 'age' is not installed" >&2; return 1; }
            backup_crypto_require_private_file \
                BACKUP_AGE_IDENTITY_FILE "${BACKUP_AGE_IDENTITY_FILE:-}"
            ;;
        gpg)
            command -v gpg >/dev/null 2>&1 \
                || { echo "ERROR: 'gpg' is not installed" >&2; return 1; }
            backup_crypto_require_private_file \
                BACKUP_PASSPHRASE_FILE "${BACKUP_PASSPHRASE_FILE:-}"
            ;;
    esac
}

# stdin → encrypted stdout.
backup_crypto_encrypt() {
    case "${BACKUP_CRYPTO_METHOD}" in
        age) age --encrypt -R "${BACKUP_AGE_RECIPIENTS_FILE}" ;;
        gpg) gpg --batch --yes --quiet --pinentry-mode loopback \
                 --passphrase-file "${BACKUP_PASSPHRASE_FILE}" \
                 --symmetric --cipher-algo AES256 --output - ;;
        *)   cat ;;
    esac
}

# Encrypted file ($2) → decrypted stdout, for method $1.
backup_crypto_decrypt() {
    local method="$1" file="$2"
    case "${method}" in
        age) age --decrypt -i "${BACKUP_AGE_IDENTITY_FILE}" "${file}" ;;
        gpg) gpg --batch --quiet --pinentry-mode loopback \
                 --passphrase-file "${BACKUP_PASSPHRASE_FILE}" \
                 --decrypt "${file}" ;;
        *)   cat "${file}" ;;
    esac
}

# Method implied by a backup file name.
backup_crypto_method_for_file() {
    case "$1" in
        *.sql.gz.age) echo "age" ;;
        *.sql.gz.gpg) echo "gpg" ;;
        *.sql.gz)     echo "none" ;;
        *)            echo "unknown" ;;
    esac
}
