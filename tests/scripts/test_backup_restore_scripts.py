"""scripts/backup.sh + scripts/restore.sh: encryption and erasure replay (GDPR-06/07).

No container runtime here, so the tests exercise what runs without one:
syntax (``bash -n``, one file per call: ``bash -n a b`` only checks ``a``),
the ``--dry-run`` plans, the refusal to write unencrypted dumps, key-file
permission checks, a real gpg round trip through the shared helpers, the
sha256 manifest, and (media follow-up) the media-archive restore: sibling
discovery, manifest verification, ``--skip-media``, and a real gpg round
trip of ``restore.sh``'s own ``restore_media_archive()`` (decrypt + extract
+ atomic swap + ``.pre-restore``), extracted verbatim from the script so the
test exercises the real code, not a copy.
"""

from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP = REPO_ROOT / "scripts" / "backup.sh"
RESTORE = REPO_ROOT / "scripts" / "restore.sh"
CRYPTO_LIB = REPO_ROOT / "scripts" / "lib" / "backup-crypto.sh"

HAS_GPG = shutil.which("gpg") is not None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(manifest_path: Path, *files: Path) -> None:
    lines = ["# test manifest (sha256)\n"]
    lines += [f"{_sha256(f)}  {f.name}\n" for f in files]
    manifest_path.write_text("".join(lines), encoding="utf-8")


def _extract_bash_function(script: Path, name: str) -> str:
    """Pull a top-level ``name() { ... }`` function verbatim out of a script,
    so a test can exercise the actual implementation without a full run of
    the surrounding script (which needs podman-compose)."""
    lines = script.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{name}() {{"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
    return "\n".join(lines[start : end + 1])


def _run(script: Path, *args: str, env_file: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "GOLDSMITH_ENV_FILE": str(env_file)}
    return subprocess.run(
        ["bash", str(script), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )


def _env_file(tmp_path: Path, extra: str = "") -> Path:
    env = tmp_path / "env.production"
    env.write_text(f"BACKUP_DIR={tmp_path / 'backups'}\n{extra}", encoding="utf-8")
    return env


def _passphrase(tmp_path: Path, mode: int = 0o600) -> Path:
    key = tmp_path / "backup.pass"
    key.write_text("correct horse battery staple\n", encoding="utf-8")
    key.chmod(mode)
    return key


@pytest.mark.parametrize("script", [BACKUP, RESTORE, CRYPTO_LIB])
def test_scripts_are_valid_bash(script: Path) -> None:
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True)
    assert result.returncode == 0, result.stderr


def test_backup_refuses_unencrypted_without_flag(tmp_path: Path) -> None:
    result = _run(BACKUP, "--dry-run", env_file=_env_file(tmp_path))

    assert result.returncode == 2
    assert "Refusing to write an" in result.stderr


def test_backup_unencrypted_dev_flag_dry_run(tmp_path: Path) -> None:
    result = _run(BACKUP, "--dry-run", "--unencrypted", env_file=_env_file(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "DRY-RUN" in result.stdout
    assert "encryption : none" in result.stdout
    assert not (tmp_path / "backups").exists()  # dry-run writes nothing


def test_backup_dry_run_plans_gpg_file_and_ledger(tmp_path: Path) -> None:
    key = _passphrase(tmp_path)
    env = _env_file(tmp_path, f"BACKUP_PASSPHRASE_FILE={key}\n")

    result = _run(BACKUP, "--dry-run", env_file=env)

    assert result.returncode == 0, result.stderr
    assert "encryption : gpg" in result.stdout
    assert ".sql.gz.gpg" in result.stdout
    assert "erasure-ledger.jsonl" in result.stdout
    assert "correct horse" not in result.stdout + result.stderr


def test_backup_dry_run_prefers_age_when_recipients_set(tmp_path: Path) -> None:
    recipients = tmp_path / "age.pub"
    recipients.write_text("age1examplepublickey\n", encoding="utf-8")
    env = _env_file(tmp_path, f"BACKUP_AGE_RECIPIENTS_FILE={recipients}\n")

    result = _run(BACKUP, "--dry-run", env_file=env)

    assert result.returncode == 0, result.stderr
    assert ".sql.gz.age" in result.stdout


def test_backup_rejects_unknown_encryption(tmp_path: Path) -> None:
    env = _env_file(tmp_path, "BACKUP_ENCRYPTION=rot13\n")

    result = _run(BACKUP, "--dry-run", env_file=env)

    assert result.returncode == 2


def test_restore_rejects_unknown_extension(tmp_path: Path) -> None:
    bogus = tmp_path / "dump.zip"
    bogus.write_bytes(b"x")

    result = _run(RESTORE, "--dry-run", str(bogus), env_file=_env_file(tmp_path))

    assert result.returncode == 1
    assert "Invalid backup file" in result.stderr


def test_restore_dry_run_on_plain_dump(tmp_path: Path) -> None:
    dump = tmp_path / "goldsmith_erp_2026-09-20_030000.sql.gz"
    dump.write_bytes(gzip.compress(b"SELECT 1;\n"))

    result = _run(RESTORE, "--dry-run", str(dump), env_file=_env_file(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "DRY-RUN" in result.stdout
    assert "2026-09-20T03:00:00" in result.stdout


def _gpg_encrypt(tmp_path: Path, key: Path, plaintext: bytes) -> Path:
    """Encrypt with the SAME helper backup.sh uses."""
    out = tmp_path / "goldsmith_erp_2026-09-20_030000.sql.gz.gpg"
    script = (
        f'source "{CRYPTO_LIB}"; BACKUP_PASSPHRASE_FILE="{key}"; '
        "BACKUP_CRYPTO_METHOD=gpg; backup_crypto_encrypt"
    )
    with out.open("wb") as handle:
        subprocess.run(
            ["bash", "-c", script],
            input=gzip.compress(plaintext),
            stdout=handle,
            check=True,
            timeout=60,
        )
    return out


@pytest.mark.skipif(not HAS_GPG, reason="gpg not installed")
def test_gpg_round_trip_and_restore_dry_run(tmp_path: Path) -> None:
    key = _passphrase(tmp_path)
    encrypted = _gpg_encrypt(tmp_path, key, b"CREATE TABLE t (id int);\n")
    assert b"CREATE TABLE" not in encrypted.read_bytes()

    env = _env_file(tmp_path, f"BACKUP_PASSPHRASE_FILE={key}\n")
    result = _run(RESTORE, "--dry-run", str(encrypted), env_file=env)

    assert result.returncode == 0, result.stderr
    assert "Verschlüsselung : gpg" in result.stdout


@pytest.mark.skipif(not HAS_GPG, reason="gpg not installed")
def test_restore_refuses_world_readable_passphrase_file(tmp_path: Path) -> None:
    key = _passphrase(tmp_path)
    encrypted = _gpg_encrypt(tmp_path, key, b"SELECT 1;\n")
    key.chmod(0o644)
    env = _env_file(tmp_path, f"BACKUP_PASSPHRASE_FILE={key}\n")

    result = _run(RESTORE, "--dry-run", str(encrypted), env_file=env)

    assert result.returncode == 1
    assert "chmod 600" in result.stderr


@pytest.mark.skipif(not HAS_GPG, reason="gpg not installed")
def test_restore_fails_with_wrong_passphrase(tmp_path: Path) -> None:
    key = _passphrase(tmp_path)
    encrypted = _gpg_encrypt(tmp_path, key, b"SELECT 1;\n")
    key.write_text("wrong\n", encoding="utf-8")
    env = _env_file(tmp_path, f"BACKUP_PASSPHRASE_FILE={key}\n")

    result = _run(RESTORE, "--dry-run", str(encrypted), env_file=env)

    assert result.returncode == 1


def test_restore_replays_ledger_before_services_start() -> None:
    """The replay must run before `up -d` so no erased person goes live."""
    text = RESTORE.read_text(encoding="utf-8")
    replay_execute = text.index("replay --execute")
    stack_up = text.index("${COMPOSE_CMD} up -d redis")
    assert replay_execute < stack_up
    assert "export --known -" in text  # live ledger saved before the DROP
    assert text.index("export --known -") < text.index("DROP DATABASE")


def test_backup_appends_ledger_outside_rotation() -> None:
    text = BACKUP.read_text(encoding="utf-8")
    assert "gdpr_replay_erasures export --known -" in text
    # Rotation globs only match dump files, never the ledger.
    assert '"${dir}"/goldsmith_erp_*.sql.gz.gpg' in text
    assert "erasure-ledger" not in text.split("apply_retention()")[1].split("}")[0]


def test_backup_dry_run_plans_encrypted_media_archive(tmp_path: Path) -> None:
    # ARCH phase 4: the media root (photos, PDFs) is archived next to the dump.
    key = _passphrase(tmp_path)
    media = tmp_path / "uploads"
    env = _env_file(tmp_path, f"BACKUP_PASSPHRASE_FILE={key}\nMEDIA_DIR={media}\n")

    result = _run(BACKUP, "--dry-run", env_file=env)

    assert result.returncode == 0, result.stderr
    assert f"media dir  : {media}" in result.stdout
    assert "goldsmith_media_" in result.stdout
    assert ".tar.gz.gpg" in result.stdout


def test_backup_media_dir_defaults_to_project_uploads(tmp_path: Path) -> None:
    result = _run(BACKUP, "--dry-run", "--unencrypted", env_file=_env_file(tmp_path))

    assert result.returncode == 0, result.stderr
    assert f"media dir  : {REPO_ROOT / 'uploads'}" in result.stdout


def test_backup_dry_run_plans_manifest(tmp_path: Path) -> None:
    result = _run(BACKUP, "--dry-run", "--unencrypted", env_file=_env_file(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "goldsmith_manifest_" in result.stdout
    assert ".sha256" in result.stdout


def test_backup_writes_and_rotates_manifest_in_source() -> None:
    """No container runtime to actually run a backup, so check the manifest
    is (a) written next to the dump/media files and (b) rotated like them —
    by inspecting the script rather than executing it."""
    text = BACKUP.read_text(encoding="utf-8")
    assert 'MANIFEST_FILE="${BACKUP_DIR}/goldsmith_manifest_${TIMESTAMP}.sha256"' in text
    assert "compute_sha256" in text
    assert '"${dir}"/goldsmith_manifest_*.sha256' in text
    assert 'apply_retention "${BACKUP_DIR}" manifest' in text


# ── Media archive restore (media follow-up) ──────────────────────────────────


def test_restore_skip_media_flag_dry_run(tmp_path: Path) -> None:
    dump = tmp_path / "goldsmith_erp_2026-09-20_030000.sql.gz"
    dump.write_bytes(gzip.compress(b"SELECT 1;\n"))
    media = tmp_path / "goldsmith_media_2026-09-20_030000.tar.gz"
    media.write_bytes(gzip.compress(b"tarball-placeholder"))

    result = _run(RESTORE, "--dry-run", "--skip-media", str(dump), env_file=_env_file(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "übersprungen (--skip-media)" in result.stdout


def test_restore_dry_run_detects_sibling_media_archive(tmp_path: Path) -> None:
    dump = tmp_path / "goldsmith_erp_2026-09-20_030000.sql.gz"
    dump.write_bytes(gzip.compress(b"SELECT 1;\n"))
    media = tmp_path / "goldsmith_media_2026-09-20_030000.tar.gz"
    media.write_bytes(gzip.compress(b"tarball-placeholder"))

    result = _run(RESTORE, "--dry-run", str(dump), env_file=_env_file(tmp_path))

    assert result.returncode == 0, result.stderr
    media_line = next(
        line for line in result.stdout.splitlines() if "Medien-Archiv" in line
    )
    assert "goldsmith_media_2026-09-20_030000.tar.gz" in media_line
    assert "nicht gefunden" not in media_line


def test_restore_dry_run_warns_when_media_archive_missing(tmp_path: Path) -> None:
    dump = tmp_path / "goldsmith_erp_2026-09-20_030000.sql.gz"
    dump.write_bytes(gzip.compress(b"SELECT 1;\n"))
    # No sibling goldsmith_media_* file written.

    result = _run(RESTORE, "--dry-run", str(dump), env_file=_env_file(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "nicht gefunden" in result.stdout
    assert "Kein passendes Medien-Archiv gefunden" in result.stderr


def test_restore_verifies_manifest_when_present(tmp_path: Path) -> None:
    dump = tmp_path / "goldsmith_erp_2026-09-20_030000.sql.gz"
    dump.write_bytes(gzip.compress(b"SELECT 1;\n"))
    media = tmp_path / "goldsmith_media_2026-09-20_030000.tar.gz"
    media.write_bytes(gzip.compress(b"tarball-placeholder"))
    manifest = tmp_path / "goldsmith_manifest_2026-09-20_030000.sha256"
    _write_manifest(manifest, dump, media)

    result = _run(RESTORE, "--dry-run", str(dump), env_file=_env_file(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "Manifest OK: goldsmith_erp_2026-09-20_030000.sql.gz" in result.stdout
    assert "Manifest OK: goldsmith_media_2026-09-20_030000.tar.gz" in result.stdout
    assert "(geprüft)" in result.stdout


def test_restore_aborts_on_manifest_mismatch(tmp_path: Path) -> None:
    dump = tmp_path / "goldsmith_erp_2026-09-20_030000.sql.gz"
    dump.write_bytes(gzip.compress(b"SELECT 1;\n"))
    manifest = tmp_path / "goldsmith_manifest_2026-09-20_030000.sha256"
    manifest.write_text(
        "0" * 64 + "  goldsmith_erp_2026-09-20_030000.sql.gz\n", encoding="utf-8"
    )

    result = _run(RESTORE, "--dry-run", str(dump), env_file=_env_file(tmp_path))

    assert result.returncode == 1
    assert "stimmt nicht mit dem Manifest überein" in result.stderr


def test_restore_warns_when_manifest_missing_entry(tmp_path: Path) -> None:
    dump = tmp_path / "goldsmith_erp_2026-09-20_030000.sql.gz"
    dump.write_bytes(gzip.compress(b"SELECT 1;\n"))
    manifest = tmp_path / "goldsmith_manifest_2026-09-20_030000.sha256"
    manifest.write_text("# manifest without a matching entry\n", encoding="utf-8")

    result = _run(RESTORE, "--dry-run", str(dump), env_file=_env_file(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "Kein Manifest-Eintrag" in result.stderr


def test_restore_warns_when_no_manifest_found(tmp_path: Path) -> None:
    dump = tmp_path / "goldsmith_erp_2026-09-20_030000.sql.gz"
    dump.write_bytes(gzip.compress(b"SELECT 1;\n"))
    # No goldsmith_manifest_* file written at all.

    result = _run(RESTORE, "--dry-run", str(dump), env_file=_env_file(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "Kein Manifest gefunden" in result.stderr
    assert "nicht gefunden" in result.stdout  # dry-run plan line for "Manifest"


@pytest.mark.skipif(not HAS_GPG, reason="gpg not installed")
def test_media_restore_round_trip_gpg(tmp_path: Path) -> None:
    """Real round trip of restore.sh's own restore_media_archive(): a real
    gpg-encrypted tarball is decrypted and extracted, the previous MEDIA_DIR
    is preserved as .pre-restore, and the swap is atomic (temp dir + rename).
    The function body is extracted verbatim from restore.sh so this tests
    the actual implementation, not a reimplementation of it."""
    key = _passphrase(tmp_path)

    media_src = tmp_path / "media_src"
    (media_src / "order_42").mkdir(parents=True)
    (media_src / "order_42" / "photo.jpg").write_bytes(b"binary-photo-data")

    archive = tmp_path / "goldsmith_media_2026-09-20_030000.tar.gz.gpg"
    tar_proc = subprocess.run(
        ["tar", "-C", str(media_src), "-cf", "-", "."],
        capture_output=True,
        check=True,
        timeout=60,
    )
    encrypt_script = (
        f'source "{CRYPTO_LIB}"; BACKUP_PASSPHRASE_FILE="{key}"; '
        "BACKUP_CRYPTO_METHOD=gpg; backup_crypto_encrypt"
    )
    with archive.open("wb") as handle:
        subprocess.run(
            ["bash", "-c", encrypt_script],
            input=gzip.compress(tar_proc.stdout),
            stdout=handle,
            check=True,
            timeout=60,
        )

    dest = tmp_path / "uploads"
    dest.mkdir()
    (dest / "stale.txt").write_text("pre-existing media root", encoding="utf-8")
    stale_pre_restore = tmp_path / "uploads.pre-restore"
    assert not stale_pre_restore.exists()

    func_body = _extract_bash_function(RESTORE, "restore_media_archive")
    driver = (
        f'source "{CRYPTO_LIB}"; METHOD=gpg; BACKUP_PASSPHRASE_FILE="{key}"; '
        f"{func_body}\n"
        f'restore_media_archive "{archive}" "{dest}"'
    )
    result = subprocess.run(
        ["bash", "-c", driver], capture_output=True, text=True, timeout=60
    )

    assert result.returncode == 0, result.stderr
    assert (dest / "order_42" / "photo.jpg").read_bytes() == b"binary-photo-data"
    assert (stale_pre_restore / "stale.txt").read_text(encoding="utf-8") == (
        "pre-existing media root"
    )
    # Atomic: no leftover restore-tmp directories next to the media root.
    assert not list(tmp_path.glob("uploads.restore-tmp.*"))


@pytest.mark.skipif(not HAS_GPG, reason="gpg not installed")
def test_media_restore_round_trip_no_previous_media_dir(tmp_path: Path) -> None:
    """Same real round trip, but MEDIA_DIR does not exist yet (fresh install):
    no .pre-restore should be created, and the restore still succeeds."""
    key = _passphrase(tmp_path)

    media_src = tmp_path / "media_src"
    media_src.mkdir()
    (media_src / "photo.jpg").write_bytes(b"fresh-install-photo")

    archive = tmp_path / "goldsmith_media_2026-09-20_030000.tar.gz.gpg"
    tar_proc = subprocess.run(
        ["tar", "-C", str(media_src), "-cf", "-", "."],
        capture_output=True,
        check=True,
        timeout=60,
    )
    encrypt_script = (
        f'source "{CRYPTO_LIB}"; BACKUP_PASSPHRASE_FILE="{key}"; '
        "BACKUP_CRYPTO_METHOD=gpg; backup_crypto_encrypt"
    )
    with archive.open("wb") as handle:
        subprocess.run(
            ["bash", "-c", encrypt_script],
            input=gzip.compress(tar_proc.stdout),
            stdout=handle,
            check=True,
            timeout=60,
        )

    dest = tmp_path / "uploads-fresh"  # deliberately not created

    func_body = _extract_bash_function(RESTORE, "restore_media_archive")
    driver = (
        f'source "{CRYPTO_LIB}"; METHOD=gpg; BACKUP_PASSPHRASE_FILE="{key}"; '
        f"{func_body}\n"
        f'restore_media_archive "{archive}" "{dest}"'
    )
    result = subprocess.run(
        ["bash", "-c", driver], capture_output=True, text=True, timeout=60
    )

    assert result.returncode == 0, result.stderr
    assert (dest / "photo.jpg").read_bytes() == b"fresh-install-photo"
    assert not (tmp_path / "uploads-fresh.pre-restore").exists()
