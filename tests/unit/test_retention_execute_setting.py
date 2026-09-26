"""RETENTION_EXECUTE gating of the retention sweep (GDPR-08, decision D-08).

Dry-run is the default. The setting switches the scheduled run to executing;
``--dry-run`` always wins, ``--execute`` forces deletion.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import pytest

from goldsmith_erp.core.config import Settings
from goldsmith_erp.jobs import retention_sweep
from goldsmith_erp.jobs.retention_sweep import RetentionSweepReport, resolve_execute


def test_setting_defaults_to_false() -> None:
    assert Settings.model_fields["RETENTION_EXECUTE"].default is False


@pytest.mark.parametrize(
    "argv, setting, expected",
    [
        ([], False, False),
        ([], True, True),
        (["--execute"], False, True),
        (["--dry-run"], True, False),
        (["--dry-run"], False, False),
    ],
)
def test_resolve_execute_precedence(
    argv: List[str], setting: bool, expected: bool
) -> None:
    args = retention_sweep._parse_args(argv)
    assert resolve_execute(args, setting) is expected


def test_execute_and_dry_run_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        retention_sweep._parse_args(["--execute", "--dry-run"])


@pytest.mark.parametrize("setting, expected", [(False, False), (True, True)])
def test_main_passes_setting_to_the_sweep(
    monkeypatch: pytest.MonkeyPatch, setting: bool, expected: bool
) -> None:
    seen: List[bool] = []

    async def fake_run(execute: bool) -> RetentionSweepReport:
        seen.append(execute)
        return RetentionSweepReport(executed=execute, now=datetime(2026, 9, 25))

    monkeypatch.setattr(retention_sweep, "_run", fake_run)
    monkeypatch.setattr(retention_sweep, "_retention_execute_setting", lambda: setting)

    assert retention_sweep.main([]) == 0
    assert seen == [expected]


def test_main_exits_one_when_settings_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken() -> bool:
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr(retention_sweep, "_retention_execute_setting", broken)

    assert retention_sweep.main([]) == 1
