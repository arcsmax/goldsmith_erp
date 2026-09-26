"""setup.sh must write a .env.production the backend can boot with (F-1, SEC-03).

Runs ``setup.sh --render-env <file>``, the non-interactive mode that only
renders the production env file, then loads it through ``Settings`` with
DEBUG=false semantics exactly as the production container would.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from goldsmith_erp.core.config import ENV_EXAMPLE_PLACEHOLDER, Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_SH = REPO_ROOT / "setup.sh"
MIN_SECRET_LENGTH = 32
CONFIG_DEFAULT_TOKEN_MINUTES = 30

# Env vars that would outrank the dotenv file inside Settings().
_SETTINGS_ENV_KEYS = (
    "DEBUG",
    "SECRET_KEY",
    "ENCRYPTION_KEY",
    "ANONYMIZATION_SALT",
    "COOKIE_SECURE",
    "BACKEND_CORS_ORIGINS",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "DATABASE_URL",
    "REDIS_URL",
    "TRUSTED_PROXIES",
)


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value
    return values


@pytest.fixture
def rendered_env(tmp_path: Path) -> Path:
    out = tmp_path / ".env.production"
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "WORKSHOP_NAME": "Testwerkstatt",
        "ADMIN_EMAIL": "admin@example.test",
        "ADMIN_FIRST_NAME": "Test",
        "ADMIN_LAST_NAME": "Admin",
        "BACKUP_DIR": str(tmp_path / "backups"),
        "LOCAL_IP": "192.168.1.20",
    }
    result = subprocess.run(  # noqa: S603 - fixed argv, repo-local script
        ["bash", str(SETUP_SH), "--render-env", str(out)],
        cwd=tmp_path,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert out.is_file()
    return out


def test_render_env_contains_every_required_production_secret(rendered_env: Path):
    values = _parse_env_file(rendered_env)

    for key in ("SECRET_KEY", "ENCRYPTION_KEY", "ANONYMIZATION_SALT"):
        assert values.get(key), f"{key} missing from .env.production"
        assert values[key] != ENV_EXAMPLE_PLACEHOLDER
    assert len(values["SECRET_KEY"]) >= MIN_SECRET_LENGTH
    assert len(values["ANONYMIZATION_SALT"]) >= MIN_SECRET_LENGTH
    assert values["SECRET_KEY"] != values["ANONYMIZATION_SALT"]
    Fernet(values["ENCRYPTION_KEY"].encode())  # raises if not a Fernet key
    assert values["DEBUG"] == "false"
    assert values["COOKIE_SECURE"] == "true"


def test_render_env_does_not_override_token_lifetime(rendered_env: Path):
    values = _parse_env_file(rendered_env)

    assert "ACCESS_TOKEN_EXPIRE_MINUTES" not in values


def test_render_env_file_is_private(rendered_env: Path):
    mode = stat.S_IMODE(rendered_env.stat().st_mode)

    assert mode == 0o600


def test_rendered_env_boots_production_settings(rendered_env: Path, monkeypatch):
    for key in _SETTINGS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=rendered_env)

    assert settings.DEBUG is False
    assert settings.COOKIE_SECURE is True
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == CONFIG_DEFAULT_TOKEN_MINUTES
    assert "http://192.168.1.20:3000" in settings.BACKEND_CORS_ORIGINS


def test_render_env_generates_fresh_secrets_each_run(tmp_path: Path):
    outputs = []
    for name in ("a", "b"):
        out = tmp_path / f"{name}.env"
        subprocess.run(  # noqa: S603 - fixed argv, repo-local script
            ["bash", str(SETUP_SH), "--render-env", str(out)],
            cwd=tmp_path,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(tmp_path),
            },
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        outputs.append(_parse_env_file(out))

    assert outputs[0]["SECRET_KEY"] != outputs[1]["SECRET_KEY"]
    assert outputs[0]["ANONYMIZATION_SALT"] != outputs[1]["ANONYMIZATION_SALT"]


def _run_setup(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, repo-local script
        ["bash", str(SETUP_SH), *args],
        cwd=cwd,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cwd)},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_upgrade_env_adds_missing_salt_to_legacy_file(tmp_path: Path):
    legacy = tmp_path / ".env.production"
    legacy.write_text(
        "DEBUG=false\nSECRET_KEY=x\nACCESS_TOKEN_EXPIRE_MINUTES=10080\n",
        encoding="utf-8",
    )

    result = _run_setup(["--upgrade-env", str(legacy)], tmp_path)

    assert result.returncode == 0, result.stderr
    values = _parse_env_file(legacy)
    assert len(values["ANONYMIZATION_SALT"]) >= MIN_SECRET_LENGTH
    assert "ACCESS_TOKEN_EXPIRE_MINUTES" in result.stdout


def test_upgrade_env_never_rotates_existing_salt(tmp_path: Path):
    existing = tmp_path / ".env.production"
    existing.write_text("ANONYMIZATION_SALT=keep-me-forever\n", encoding="utf-8")

    result = _run_setup(["--upgrade-env", str(existing)], tmp_path)

    assert result.returncode == 0, result.stderr
    assert _parse_env_file(existing)["ANONYMIZATION_SALT"] == "keep-me-forever"


def test_env_example_documents_auth_revocation_fail_closed():
    """OPS-15: AUTH_REVOCATION_FAIL_CLOSED is a real security/availability
    toggle (core/config.py) but was the one remaining undocumented knob in
    .env.example, unlike every other security-relevant setting."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "AUTH_REVOCATION_FAIL_CLOSED" in text
    # Documented, not just named: a comment block precedes the line, mirroring
    # every other security-toggle section in this file.
    idx = text.index("AUTH_REVOCATION_FAIL_CLOSED")
    preceding = text[max(0, idx - 400) : idx]
    assert "#" in preceding, "AUTH_REVOCATION_FAIL_CLOSED has no explanatory comment"
