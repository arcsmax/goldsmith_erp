# tests/unit/test_worker.py
"""Worker entrypoint (ARCH-04): loop, monitor under leader lock, heartbeat."""

import asyncio
import os
import time

import pytest

from goldsmith_erp import worker
from goldsmith_erp.core.config import settings


async def test_loop_drains_outbox_runs_monitor_once_and_heartbeats(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    heartbeat = tmp_path / "hb"
    monkeypatch.setattr(worker, "HEARTBEAT_PATH", heartbeat)
    monkeypatch.setattr(
        worker, "_touch_heartbeat", lambda path=heartbeat: path.write_text("x")
    )
    monkeypatch.setattr(settings, "OUTBOX_POLL_INTERVAL_SECONDS", 0.01)
    stop = asyncio.Event()
    calls = {"drain": 0, "monitor": 0}

    async def fake_run_once(factory):
        calls["drain"] += 1
        if calls["drain"] >= 3:
            stop.set()
        return 0

    async def fake_cycle(lease):
        calls["monitor"] += 1
        return True

    monkeypatch.setattr(worker.OutboxService, "run_once", staticmethod(fake_run_once))
    monkeypatch.setattr(worker, "run_cycle_if_leader", fake_cycle)

    await asyncio.wait_for(worker.run_worker(stop), timeout=5)

    assert calls["drain"] == 3
    # The monitor interval (5 min) has not elapsed again: exactly one cycle.
    assert calls["monitor"] == 1
    assert worker.heartbeat_is_fresh(heartbeat)


async def test_a_crashing_monitor_does_not_stop_the_loop(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, "_touch_heartbeat", lambda path=None: None)
    monkeypatch.setattr(settings, "OUTBOX_POLL_INTERVAL_SECONDS", 0.01)
    stop = asyncio.Event()
    drains = []

    async def fake_run_once(factory):
        drains.append(1)
        if len(drains) >= 2:
            stop.set()
        return 0

    async def boom(lease):
        raise RuntimeError("monitor broke")

    monkeypatch.setattr(worker.OutboxService, "run_once", staticmethod(fake_run_once))
    monkeypatch.setattr(worker, "run_cycle_if_leader", boom)
    await asyncio.wait_for(worker.run_worker(stop), timeout=5)
    assert len(drains) == 2


def test_healthcheck_reflects_heartbeat_age(tmp_path):
    hb = tmp_path / "hb"
    assert worker.heartbeat_is_fresh(hb) is False
    hb.write_text("x")
    assert worker.heartbeat_is_fresh(hb) is True
    old = time.time() - worker.HEARTBEAT_MAX_AGE_SECONDS - 10
    os.utime(hb, (old, old))
    assert worker.heartbeat_is_fresh(hb) is False


def test_healthcheck_cli_exit_code(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, "HEARTBEAT_PATH", tmp_path / "missing")
    monkeypatch.setattr(
        worker,
        "heartbeat_is_fresh",
        lambda path=None, max_age=None: (tmp_path / "missing").exists(),
    )
    assert worker.main(["--healthcheck"]) == 1
    (tmp_path / "missing").write_text("x")
    assert worker.main(["--healthcheck"]) == 0


async def test_web_startup_skips_monitor_in_worker_mode(monkeypatch):
    from goldsmith_erp import main as main_module

    started = []
    monkeypatch.setattr(
        main_module.asyncio, "create_task", lambda coro: started.append(coro)
    )
    monkeypatch.setattr(settings, "OUTBOX_MODE", "worker")
    await main_module.start_background_tasks()
    assert started == []

    monkeypatch.setattr(settings, "OUTBOX_MODE", "inline")
    await main_module.start_background_tasks()
    assert len(started) == 1
    started[0].close()  # never awaited: avoid the RuntimeWarning


def test_outbox_mode_defaults_follow_debug(monkeypatch):
    monkeypatch.setattr(settings, "OUTBOX_MODE", None)
    monkeypatch.setattr(settings, "DEBUG", True)
    assert settings.outbox_mode == "inline"
    monkeypatch.setattr(settings, "DEBUG", False)
    assert settings.outbox_mode == "worker"
    monkeypatch.setattr(settings, "OUTBOX_MODE", "inline")
    assert settings.outbox_mode == "inline"
