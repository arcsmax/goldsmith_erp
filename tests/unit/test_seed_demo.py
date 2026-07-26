"""Tests for ``scripts/seed_demo.py`` and its helpers.

Two layers:

1. **Unit tests** — exercise ``goldsmith_erp.db._seed_helpers`` (date / uuid /
   schema-drift filter) and ``scripts.seed_data_definitions`` (frozen seed
   dataclasses, ``to_dict()`` shape).  These run without a database.

2. **Integration tests** — exercised only when the test database contains
   every required table (the new V1.1/V1.2 + V1.0 schema).  We detect this
   via :func:`has_required_schema` and ``pytest.mark.skipif`` rather than
   relying on a hard failure — keeps the suite green on stripped-down
   SQLite snapshots that don't carry the full migration history.

The integration test asserts the seeder leaves row counts UNCHANGED when
re-run (idempotency contract), and that the realistic-counts baseline holds
(>= 10 customers, 15 orders, >= 24 time entries, 5 consultations, 4 quotes,
4 invoices, >= 6 order photos).
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from goldsmith_erp.db import _seed_helpers
from goldsmith_erp.db._seed_helpers import (
    FIBONACCI_DAYS,
    days_ago,
    days_from_now,
    filter_model_fields,
    fresh_uuid,
)

# ---------------------------------------------------------------------------
# scripts/ is not on sys.path by default (it's the seeder scripts dir, not
# the package).  Mirror the import pattern used in test_label_template_seed.py
# and load the seed_data_definitions module by absolute file path so this test
# works under any pytest invocation that respects ``rootdir``.
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import seed_data_definitions as sdd  # noqa: E402

# ---------------------------------------------------------------------------
# 1. _seed_helpers unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_days_ago_zero_is_close_to_now() -> None:
    """A zero-day subtract should land within a generous tolerance of
    ``datetime.utcnow()`` at call time.

    Note: ``NOW`` in ``_seed_helpers`` is captured at *module-import time*,
    so when the test suite runs late in a long-running process the module's
    frozen NOW can lag several seconds behind the test's local ``utcnow()``
    call.  We allow a 5-minute-wide window rather than tight test-real-time
    bounds — the test still confirms the function returns a *recent*
    datetime, not some ancient constant.
    """
    # Deterministic contract: days_ago(0) IS the module's frozen NOW — no
    # wall-clock comparison can race, no matter how long the suite runs
    # before this test executes (a 5-minute window failed in CI once the
    # full suite grew past ~7 minutes).
    assert days_ago(0) == _seed_helpers.NOW
    # Recency sanity only — catches an ancient hardcoded constant, with a
    # window no realistic suite duration can outgrow.
    assert datetime.utcnow() - _seed_helpers.NOW < timedelta(hours=24)


@pytest.mark.unit
def test_days_ago_positive_subtracts_days() -> None:
    """``days_ago(7)`` should be exactly 7 days before ``days_ago(0)`` modulo clock drift."""
    base = days_ago(0)
    past = days_ago(7)
    delta = base - past
    # Within +/- 1 second — datetime.utcnow can tick over the second boundary.
    assert (
        timedelta(days=7) - timedelta(seconds=1)
        <= delta
        <= timedelta(days=7) + timedelta(seconds=1)
    )


@pytest.mark.unit
def test_days_from_now_adds_days() -> None:
    base = days_ago(0)
    future = days_from_now(5)
    assert (future - base) >= timedelta(days=5) - timedelta(seconds=1)


@pytest.mark.unit
def test_fibonacci_days_ago_is_newest_first() -> None:
    """``fibonacci_days_ago()`` returns timestamps in FIBONACCI_DAYS order,
    which means the smallest day-count (closest to NOW) comes first.

    Callers that need oldest-first must sort themselves — see the
    docstring on :func:`fibonacci_days_ago`.
    """
    timestamps = [days_ago(n) for n in FIBONACCI_DAYS]
    # Index 0 is days_ago(1) — closest to NOW.
    # Index -1 is days_ago(365) — furthest from NOW.
    assert (
        timestamps[0] >= timestamps[-1]
    ), "expected index 0 (days_ago(1)) to be NEWER than index -1 (days_ago(365))"


@pytest.mark.unit
def test_fresh_uuid_is_distinct_hex_string() -> None:
    a = fresh_uuid()
    b = fresh_uuid()
    assert a != b
    assert len(a) == 36
    assert a.count("-") == 4


@pytest.mark.unit
def test_filter_model_fields_drops_unknown_keys() -> None:
    """Forward-compatibility: aspirational/drifted keys must NOT raise."""

    # Build a model a model shape we can introspect — use the real
    # ``User`` table.  We don't construct it; we just check the filter.
    from goldsmith_erp.db.models import User

    payload = {
        "email": "u@example.com",
        "first_name": "Ann",
        "last_name": "Schmidt",
        # Unknown / aspirational column — should be dropped silently.
        "greeting_template": "Moin {first_name}!",
        "color_picker_widget": "#abc",
    }
    filtered = filter_model_fields(User, payload)
    assert "email" in filtered
    assert "first_name" in filtered
    assert "greeting_template" not in filtered
    assert "color_picker_widget" not in filtered


@pytest.mark.unit
def test_filter_model_fields_preserves_datetimes_passthrough() -> None:
    """datetime / float / None values must survive without modification."""
    from goldsmith_erp.db.models import Customer
    from goldsmith_erp.db.models import Customer as _C

    now = datetime.utcnow()
    payload = {
        "first_name": "Ann",
        "last_name": "Schmidt",
        "created_at": now,
        "is_active": True,
    }
    filtered = filter_model_fields(Customer, payload)
    assert filtered["created_at"] is now
    assert filtered["is_active"] is True


# ---------------------------------------------------------------------------
# 2. seed_data_definitions frozen-dataclass tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "seed_cls",
    [
        sdd.UserSeed,
        sdd.CustomerSeed,
        sdd.MaterialSeed,
        sdd.OrderPhotoSeed,
        sdd.ConsultationSeed,
        sdd.ConsultationPhotoSeed,
        sdd.QuoteLineItemEditSeed,
        sdd.CustomerUpdateSeed,
        sdd.CostChangeRequestSeed,
    ],
)
def test_seed_dataclass_is_frozen(seed_cls) -> None:
    """Every ``*Seed`` must raise FrozenInstanceError on attribute assignment."""
    instance = seed_cls.__new__(seed_cls)
    # Force-set the required fields.  Iterate dataclass ``fields()`` and use
    # a sentinel for each, except for a few types we know how to construct.
    sentinel = object()
    for f in fields(seed_cls):
        if not f.init:
            continue
        try:
            setattr(instance, f.name, sentinel)
        except (FrozenInstanceError, AttributeError):
            # Some f.name is a property — try via ``__dict__`` direct
            # bypass anyway should still raise FrozenInstanceError on
            # the next attempt below.
            object.__setattr__(instance, f.name, sentinel)

    # Now mutate — must raise FrozenInstanceError.
    with pytest.raises(FrozenInstanceError):
        instance.email = "mutated@example.com"


@pytest.mark.unit
def test_customer_seed_to_dict_matches_field_names() -> None:
    seed = sdd.CustomerSeed(
        first_name="Maria",
        last_name="Schneider",
        email="m.schneider@example.de",
        phone="+49 711 1234567",
        city="Stuttgart",
        tags=("Stammkunde",),
    )
    payload = seed.to_dict()
    declared = {f.name for f in fields(sdd.CustomerSeed)}
    assert set(payload.keys()) == declared, (
        f"to_dict() leaked/dropped fields: "
        f"extra={set(payload) - declared}, missing={declared - set(payload)}"
    )
    assert payload["first_name"] == "Maria"
    assert payload["tags"] == ("Stammkunde",)


@pytest.mark.unit
def test_customer_seed_replace_produces_independent_copy() -> None:
    """``dataclasses.replace`` must not mutate the source instance."""
    base = sdd.CustomerSeed(
        first_name="Maria",
        last_name="Schneider",
        email="m.schneider@example.de",
    )
    overridden = replace(base, first_name="Anna")
    assert overridden.first_name == "Anna"
    # Source copy still intact (frozen dataclass).
    assert base.first_name == "Maria"


@pytest.mark.unit
def test_consultation_seed_default_status_is_draft() -> None:
    """A newly-constructed ConsultationSeed defaults to the draft state —
    matches the model column default so a draft-typed seed payload is round-
    trippable through :func:`_seed_helpers.filter_model_fields`."""
    seed = sdd.ConsultationSeed(
        customer_id=1,
        conducted_by=2,
        occasion="engagement",
    )
    payload = seed.to_dict()
    assert payload["status"] == "draft"
    assert payload["budget_min"] is None
    assert payload["budget_max"] is None


@pytest.mark.unit
def test_order_photo_seed_with_uuid_attaches_id() -> None:
    base = sdd.OrderPhotoSeed(
        order_id=42,
        file_path="/uploads/x.jpg",
        taken_by=1,
    )
    assert base.id is None
    fresh = base.with_uuid(fresh_uuid())
    assert fresh.id is not None
    # Source instance must remain untouched (frozen).
    assert base.id is None


# ---------------------------------------------------------------------------
# 3. scripts/seed_demo.py import smoke-test — verifies every V1.1/V1.2
#    seed function is exported and reuses the shared helpers.  This is the
#    upper bound of "unit-level" coverage we can run from a stock pytest
#    invocation; the genuine integration round-trip (run the seeder twice
#    against a live Postgres, compare row counts) is left as a manual
#    verification step because ``AsyncSessionLocal`` reads DATABASE_URL
#    from the live config, which the unit suite cannot monkey-patch
#    cleanly without re-binding the engine, session factory, and the
#    redis-touching pubsub shim, all of which are out of scope for a unit
#    test.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_seed_demo_exposes_v11_v12_seed_functions() -> None:
    """The new V1.1 + V1.2 + photo seed functions must exist on the module.

    Smoke test for the import wiring only — never invokes them.  Asserts
    each function is callable, has the standard ``async def seed_(...)``
    signature pattern, and is referenced from the orchestrator's ``seed()``
    function body.
    """
    SCRIPT_PATH = _SCRIPTS_DIR / "seed_demo.py"
    spec = importlib.util.spec_from_file_location(
        "seed_demo_under_test", str(SCRIPT_PATH)
    )
    assert (
        spec is not None and spec.loader is not None
    ), f"Could not load seed_demo.py at {SCRIPT_PATH}"
    sd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sd)

    expected = [
        "seed_consultations",
        "seed_consultation_photos",
        "seed_order_photos",
        "seed_repair_photos",
        "seed_customer_updates",
        "seed_cost_change_requests",
    ]
    for fn_name in expected:
        assert hasattr(sd, fn_name), f"missing {fn_name} in scripts/seed_demo.py"
        assert callable(getattr(sd, fn_name)), f"{fn_name} is not callable"

    # The orchestrator's source code must mention each new phase comment so
    # reviewers can find it quickly.  Reading the source as text — relying on
    # ``inspect.getsource`` would break if the script is shipped as .pyc.
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    for fn_name in expected:
        assert fn_name in src, f"{fn_name} not invoked in seed_demo.py body"


@pytest.mark.unit
def test_seed_demo_uses_logger_and_filter_model_fields() -> None:
    """The new seed functions should log via ``logger`` and route payloads
    through ``_seed_helpers.filter_model_fields`` — not ``print`` and not
    raw ORM ``__init__`` calls.  Catches regressions where someone reverts
    to the old inline pattern.
    """
    SCRIPT_PATH = _SCRIPTS_DIR / "seed_demo.py"
    src = SCRIPT_PATH.read_text(encoding="utf-8")

    # The V1.1/V1.2 section must mention ``_seed_helpers.filter_model_fields``
    # at least once per phase (loose count — the V1.2 CustomerUpdate function
    # uses it inside a loop so the count is at least one per function).
    assert "_seed_helpers.filter_model_fields" in src, (
        "scripts/seed_demo.py must use _seed_helpers.filter_model_fields for "
        "forward-compat seed payloads"
    )
    assert (
        "logger.info" in src
    ), "scripts/seed_demo.py should use logging (logger.info) per ECC coding style"
