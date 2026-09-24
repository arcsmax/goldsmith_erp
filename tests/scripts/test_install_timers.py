"""scripts/install-timers.sh must stay in sync with deploy/systemd/ (OPS-07).

Static checks only — the script itself requires a Linux systemd user session
to actually run (``systemctl --user ...``), which this test environment does
not have. What we *can* verify without executing it:

  * the script is syntactically valid bash (``bash -n``);
  * every unit filename the script references by name actually exists under
    ``deploy/systemd/`` (catches drift if a unit is renamed/removed there
    without updating the installer, or vice versa);
  * every ``deploy/systemd/*.service``/``*.timer`` file is referenced by the
    script (catches a new unit being added without wiring it into install);
  * only the three ``*.timer`` units are ever passed to
    ``systemctl --user enable`` — the oneshot ``.service``/``-alert.service``
    units have no ``[Install]`` section and must never be enabled directly.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "install-timers.sh"
DEPLOY_SYSTEMD_DIR = REPO_ROOT / "deploy" / "systemd"

EXPECTED_TIMERS = {
    "goldsmith-gdpr-cleanup.timer",
    "goldsmith-retention-sweep.timer",
    "goldsmith-health-watchdog.timer",
}
EXPECTED_SERVICES = {
    "goldsmith-gdpr-cleanup.service",
    "goldsmith-gdpr-cleanup-alert.service",
    "goldsmith-retention-sweep.service",
    "goldsmith-retention-sweep-alert.service",
    "goldsmith-health-watchdog.service",
}


@pytest.fixture(scope="module")
def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _bash_array(text: str, name: str) -> list[str]:
    match = re.search(rf"{name}=\((.*?)\)", text, re.S)
    assert match, f"could not find bash array {name}= in {SCRIPT}"
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


def test_script_exists_and_is_executable() -> None:
    assert SCRIPT.is_file(), f"{SCRIPT} does not exist"
    assert SCRIPT.stat().st_mode & 0o111, f"{SCRIPT} is not executable"


def test_script_is_valid_bash() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"


def test_every_referenced_timer_unit_exists_on_disk(script_text: str) -> None:
    referenced = set(_bash_array(script_text, "TIMER_UNITS"))
    assert referenced == EXPECTED_TIMERS
    for unit in referenced:
        assert (DEPLOY_SYSTEMD_DIR / unit).is_file(), f"missing deploy/systemd/{unit}"


def test_every_referenced_service_unit_exists_on_disk(script_text: str) -> None:
    referenced = set(_bash_array(script_text, "SERVICE_UNITS"))
    assert referenced == EXPECTED_SERVICES
    for unit in referenced:
        assert (DEPLOY_SYSTEMD_DIR / unit).is_file(), f"missing deploy/systemd/{unit}"


def test_every_unit_file_on_disk_is_referenced_by_the_script(script_text: str) -> None:
    """Catches a new unit landing in deploy/systemd/ without being wired in."""
    on_disk = {p.name for p in DEPLOY_SYSTEMD_DIR.glob("goldsmith-*.service")} | {
        p.name for p in DEPLOY_SYSTEMD_DIR.glob("goldsmith-*.timer")
    }
    referenced = set(_bash_array(script_text, "TIMER_UNITS")) | set(
        _bash_array(script_text, "SERVICE_UNITS")
    )
    assert on_disk == referenced, (
        f"deploy/systemd/ and install-timers.sh have drifted: "
        f"on disk but not referenced={on_disk - referenced}, "
        f"referenced but missing on disk={referenced - on_disk}"
    )


def test_only_timer_units_are_enabled(script_text: str) -> None:
    """The oneshot .service/-alert.service units must never be `enable`d
    directly — only their companion .timer (which carries [Install]) may be.
    """
    enable_calls = re.findall(r'enable --now "\$?\{?(\w+)\}?"', script_text)
    assert enable_calls, "expected at least one `systemctl --user enable --now` call"
    service_units = set(_bash_array(script_text, "SERVICE_UNITS"))
    for unit in service_units:
        assert f'enable --now "{unit}"' not in script_text
        assert f"enable --now {unit}" not in script_text
