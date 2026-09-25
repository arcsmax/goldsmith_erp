"""LV-17: a disk-usage *warning* (>= 80 %) must not flip GET /health to
"degraded" on its own — only a *critical* disk usage (configurable via
``settings.HEALTH_DISK_CRITICAL_PERCENT``, default 95 %) may flip the
overall status (to "unhealthy", same as a down database/redis).

Before this fix, ``get_full_health`` folded the disk component's "warning"
status into the same generic "any warning -> degraded" branch, so a
workshop server sitting at 80-94 % disk usage (routine, not urgent) reported
"degraded" on every health probe.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from goldsmith_erp.core.config import settings
from goldsmith_erp.services.system_health_service import SystemHealthService


class _FakeUsage:
    def __init__(self, total: int, used: int, free: int) -> None:
        self.total = total
        self.used = used
        self.free = free


def _disk_usage_at(percent: float) -> _FakeUsage:
    total = 100_000_000_000  # 100 GB
    used = int(total * percent / 100)
    return _FakeUsage(total=total, used=used, free=total - used)


def test_check_disk_reports_warning_at_80_percent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("shutil.disk_usage", lambda path: _disk_usage_at(82.0))
    result = SystemHealthService.check_disk()
    assert result["status"] == "warning"


def test_check_disk_reports_critical_at_default_threshold(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "HEALTH_DISK_CRITICAL_PERCENT", 95.0)
    monkeypatch.setattr("shutil.disk_usage", lambda path: _disk_usage_at(96.0))
    result = SystemHealthService.check_disk()
    assert result["status"] == "critical"


def test_check_disk_critical_threshold_is_configurable(
    monkeypatch: pytest.MonkeyPatch,
):
    """A lower configured threshold flags a usage the default would not."""
    monkeypatch.setattr(settings, "HEALTH_DISK_CRITICAL_PERCENT", 90.0)
    monkeypatch.setattr("shutil.disk_usage", lambda path: _disk_usage_at(91.0))
    result = SystemHealthService.check_disk()
    assert result["status"] == "critical"


@pytest.mark.asyncio
async def test_overall_health_stays_healthy_when_only_disk_warns(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        SystemHealthService,
        "check_database",
        AsyncMock(return_value={"status": "up", "latency_ms": 1.0}),
    )
    monkeypatch.setattr(
        SystemHealthService,
        "check_redis",
        AsyncMock(
            return_value={
                "status": "up",
                "latency_ms": 1.0,
                "used_memory_mb": 1.0,
            }
        ),
    )
    monkeypatch.setattr(
        SystemHealthService,
        "check_disk",
        lambda: {
            "status": "warning",
            "free_gb": 10.0,
            "total_gb": 100.0,
            "used_percent": 82.0,
        },
    )
    health = await SystemHealthService.get_full_health(db=None)
    assert health["status"] == "healthy"
    assert health["components"]["disk"]["status"] == "warning"


@pytest.mark.asyncio
async def test_overall_health_is_unhealthy_when_disk_is_critical(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        SystemHealthService,
        "check_database",
        AsyncMock(return_value={"status": "up", "latency_ms": 1.0}),
    )
    monkeypatch.setattr(
        SystemHealthService,
        "check_redis",
        AsyncMock(
            return_value={
                "status": "up",
                "latency_ms": 1.0,
                "used_memory_mb": 1.0,
            }
        ),
    )
    monkeypatch.setattr(
        SystemHealthService,
        "check_disk",
        lambda: {
            "status": "critical",
            "free_gb": 1.0,
            "total_gb": 100.0,
            "used_percent": 97.0,
        },
    )
    health = await SystemHealthService.get_full_health(db=None)
    assert health["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_overall_health_degraded_still_possible_for_non_disk_warning(
    monkeypatch: pytest.MonkeyPatch,
):
    """A hypothetical non-disk "warning" component still degrades overall
    status; only disk's routine warning is exempted."""
    monkeypatch.setattr(
        SystemHealthService,
        "check_database",
        AsyncMock(return_value={"status": "warning", "latency_ms": 1.0}),
    )
    monkeypatch.setattr(
        SystemHealthService,
        "check_redis",
        AsyncMock(
            return_value={
                "status": "up",
                "latency_ms": 1.0,
                "used_memory_mb": 1.0,
            }
        ),
    )
    monkeypatch.setattr(
        SystemHealthService,
        "check_disk",
        lambda: {
            "status": "ok",
            "free_gb": 50.0,
            "total_gb": 100.0,
            "used_percent": 30.0,
        },
    )
    health = await SystemHealthService.get_full_health(db=None)
    assert health["status"] == "degraded"
