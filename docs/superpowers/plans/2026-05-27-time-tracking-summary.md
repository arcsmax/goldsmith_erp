# Time-Tracking Summary Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `GET /time-tracking/summary` returning `TimeSummaryStats` for a date window, with a per-activity `is_billable` flag (sensible category defaults) driving billable hours.

**Architecture:** Add an `Activity.is_billable` column (Alembic migration backfills sensible category defaults). A new `TimeTrackingService.get_summary` aggregates *completed* time entries over the window (and the preceding equal-length window for the % comparison), joining `activities` for the billable filter and most-used name. A thin router endpoint applies the existing `TIME_VIEW_OWN` + ownership ladder. Backend-only; the frontend `getSummary` consumer already exists on the open tsc-burndown PR.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, PostgreSQL, pytest/pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-05-27-time-tracking-summary-design.md`

---

## File Structure

- **Modify** `src/goldsmith_erp/db/models.py` — add `is_billable` column to `Activity` ORM (~line 658).
- **Create** `alembic/versions/20260527_d1_activity_is_billable.py` — add column + category backfill.
- **Modify** `src/goldsmith_erp/models/activity.py` — add `is_billable` to `ActivityBase` + `ActivityUpdate`.
- **Modify** `src/goldsmith_erp/models/time_entry.py` — add `TimeSummaryStats` schema.
- **Modify** `src/goldsmith_erp/db/seed_data.py` — category-based `is_billable` on seeded activities.
- **Modify** `src/goldsmith_erp/services/time_tracking_service.py` — add `get_summary` + `case` import + `Activity` import.
- **Modify** `src/goldsmith_erp/api/routers/time_tracking.py` — add `GET /summary` **before** the `/{entry_id}` route.
- **Create** `tests/unit/test_time_tracking_summary.py` — service aggregation tests.
- **Create** `tests/integration/test_time_tracking_summary_api.py` — endpoint permission/shape/validation tests.

> **Deferred (not in this plan):** frontend `Activity.is_billable` type sync + an activity-management UI to toggle the flag — no such form exists today, and the frontend changes would conflict with the open PR #4. The category defaults (seed + migration) deliver billable hours without it.

---

### Task 1: Add `Activity.is_billable` column + migration

**Files:**
- Modify: `src/goldsmith_erp/db/models.py` (import line 3; `Activity` class ~648-668)
- Create: `alembic/versions/20260527_d1_activity_is_billable.py`

- [ ] **Step 1: Add `text` to the sqlalchemy import in `db/models.py`**

Change line 3 from:
```python
from sqlalchemy import Boolean, Column, DateTime
```
to:
```python
from sqlalchemy import Boolean, Column, DateTime, text
```

- [ ] **Step 2: Add the `is_billable` column to the `Activity` ORM model**

In `class Activity(Base)`, immediately after the `is_custom` column, add:
```python
    is_billable = Column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )  # fabrication billable; administration/waiting non-billable by default
```

- [ ] **Step 3: Write the Alembic migration**

Create `alembic/versions/20260527_d1_activity_is_billable.py`:
```python
"""D1 — Add Activity.is_billable with sensible category defaults.

Adds a per-activity billable flag used by GET /time-tracking/summary to
compute billable_hours. New column defaults to true (server_default) so
existing rows backfill non-destructively; a follow-up UPDATE applies the
sensible workshop default — administration and waiting activities are
non-billable, fabrication stays billable.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260527_d1_activity_billable"
down_revision: Union[str, None] = "20260424_c3_val_enc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column(
            "is_billable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    # Sensible defaults: overhead categories are non-billable.
    op.execute(
        "UPDATE activities SET is_billable = false "
        "WHERE category IN ('administration', 'waiting')"
    )


def downgrade() -> None:
    op.drop_column("activities", "is_billable")
```

- [ ] **Step 4: Apply the migration and verify the column + backfill**

Run:
```bash
poetry run alembic upgrade head
poetry run python -c "import asyncio; from sqlalchemy import text; from goldsmith_erp.db.session import async_session_factory
async def main():
    async with async_session_factory() as s:
        rows = (await s.execute(text('SELECT category, bool_and(is_billable) FROM activities GROUP BY category ORDER BY category'))).all()
        print(rows)
asyncio.run(main())"
```
Expected: column exists; output shows `administration` and `waiting` → `False`, `fabrication` → `True` (or no rows if DB unseeded — acceptable). If the local DB isn't running, at minimum `alembic upgrade head` must succeed.

> If `async_session_factory` is named differently, check `src/goldsmith_erp/db/session.py` for the session factory export and adjust the verification snippet — the migration itself is the deliverable.

- [ ] **Step 5: Commit**

```bash
git add src/goldsmith_erp/db/models.py alembic/versions/20260527_d1_activity_is_billable.py
git commit -m "feat(activity): add is_billable column with category-default backfill"
```

---

### Task 2: Add `is_billable` to Activity Pydantic schemas

**Files:**
- Modify: `src/goldsmith_erp/models/activity.py` (`ActivityBase` ~6-40; `ActivityUpdate` ~50-90)

`ActivityRead` and `ActivityCreate` both inherit `ActivityBase`, so adding the field to the base covers create + read.

- [ ] **Step 1: Add `is_billable` to `ActivityBase`**

After the `color` field in `class ActivityBase`, add:
```python
    is_billable: bool = Field(
        default=True,
        description="Whether time on this activity counts toward billable hours",
    )
```

- [ ] **Step 2: Add optional `is_billable` to `ActivityUpdate`**

After the `color` field in `class ActivityUpdate`, add:
```python
    is_billable: Optional[bool] = Field(
        None,
        description="Whether time on this activity counts toward billable hours",
    )
```

- [ ] **Step 3: Verify schemas import/instantiate**

Run:
```bash
poetry run python -c "from goldsmith_erp.models.activity import ActivityBase, ActivityRead, ActivityUpdate; print(ActivityBase(name='x', category='fabrication').is_billable, ActivityUpdate().is_billable)"
```
Expected: `True None`

- [ ] **Step 4: Commit**

```bash
git add src/goldsmith_erp/models/activity.py
git commit -m "feat(activity): expose is_billable on Activity schemas"
```

---

### Task 3: Category-based `is_billable` in seed data

**Files:**
- Modify: `src/goldsmith_erp/db/seed_data.py` (`seed_activities` ~360-385)

- [ ] **Step 1: Set `is_billable` from category when inserting seeded activities**

In `seed_activities`, change the `Activity(...)` construction to add:
```python
        activity = Activity(
            name=data["name"],
            category=data["category"],
            icon=data["icon"],
            color=data["color"],
            usage_count=0,
            is_custom=False,
            is_billable=data["category"] == "fabrication",
            created_at=datetime.utcnow(),
        )
```

- [ ] **Step 2: Verify seed module imports cleanly**

Run:
```bash
poetry run python -c "import goldsmith_erp.db.seed_data; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/goldsmith_erp/db/seed_data.py
git commit -m "feat(seed): set activity is_billable from category (fabrication billable)"
```

---

### Task 4: Add `TimeSummaryStats` schema

**Files:**
- Modify: `src/goldsmith_erp/models/time_entry.py` (append after `TimeEntryWithDetails` ~168)

- [ ] **Step 1: Append the schema**

At the end of `src/goldsmith_erp/models/time_entry.py`, add:
```python
class TimeSummaryStats(BaseModel):
    """Aggregated time-tracking summary for a date window.

    Matches the frontend `TimeSummaryStats` contract (frontend/src/types.ts).
    """
    total_hours: float
    billable_hours: float
    entries_count: int
    average_session_minutes: float
    most_used_activity: Optional[str] = None
    comparison_previous_period: Optional[float] = None  # % change vs prior window
```

> Confirm `Optional` is already imported at the top of the file (it is used by `TimeEntryUpdate`). If not, add `from typing import Optional`.

- [ ] **Step 2: Verify**

Run:
```bash
poetry run python -c "from goldsmith_erp.models.time_entry import TimeSummaryStats; print(TimeSummaryStats(total_hours=0, billable_hours=0, entries_count=0, average_session_minutes=0))"
```
Expected: prints a model instance with `most_used_activity=None comparison_previous_period=None`.

- [ ] **Step 3: Commit**

```bash
git add src/goldsmith_erp/models/time_entry.py
git commit -m "feat(time-tracking): add TimeSummaryStats schema"
```

---

### Task 5: Service `get_summary` (TDD)

**Files:**
- Test: `tests/unit/test_time_tracking_summary.py` (create)
- Modify: `src/goldsmith_erp/services/time_tracking_service.py` (imports line 6 + line 14-20; append method to `TimeTrackingService`)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_time_tracking_summary.py`:
```python
"""Unit tests for TimeTrackingService.get_summary aggregation."""
import pytest
from datetime import datetime, timedelta

from goldsmith_erp.db.models import Activity, TimeEntry as TimeEntryModel
from goldsmith_erp.services.time_tracking_service import TimeTrackingService


async def _activity(db, name, category, is_billable):
    a = Activity(name=name, category=category, icon="🔨", color="#FF6B6B",
                 usage_count=0, is_custom=False, is_billable=is_billable)
    db.add(a)
    await db.flush()
    return a


async def _entry(db, *, user_id, order_id, activity_id, start, minutes):
    e = TimeEntryModel(
        order_id=order_id, user_id=user_id, activity_id=activity_id,
        start_time=start, end_time=start + timedelta(minutes=minutes),
        duration_minutes=minutes,
    )
    db.add(e)
    await db.flush()
    return e


@pytest.mark.asyncio
class TestGetSummary:
    async def test_empty_window_returns_zeros(self, db_session, sample_user):
        now = datetime(2026, 5, 20, 9, 0, 0)
        result = await TimeTrackingService.get_summary(
            db_session, user_id=sample_user.id, start=now, end=now + timedelta(days=7)
        )
        assert result.total_hours == 0
        assert result.billable_hours == 0
        assert result.entries_count == 0
        assert result.average_session_minutes == 0
        assert result.most_used_activity is None
        assert result.comparison_previous_period is None

    async def test_billable_excludes_non_billable_activity(self, db_session, sample_user, sample_order):
        start = datetime(2026, 5, 12, 9, 0, 0)
        end = start + timedelta(days=7)
        bill = await _activity(db_session, "Polieren", "fabrication", True)
        nonbill = await _activity(db_session, "Pause", "waiting", False)
        await _entry(db_session, user_id=sample_user.id, order_id=sample_order.id,
                     activity_id=bill.id, start=start + timedelta(hours=1), minutes=120)
        await _entry(db_session, user_id=sample_user.id, order_id=sample_order.id,
                     activity_id=nonbill.id, start=start + timedelta(hours=4), minutes=60)
        result = await TimeTrackingService.get_summary(
            db_session, user_id=sample_user.id, start=start, end=end
        )
        assert result.total_hours == 3.0       # 120 + 60 min
        assert result.billable_hours == 2.0     # only the fabrication 120 min
        assert result.entries_count == 2
        assert result.average_session_minutes == 90.0

    async def test_most_used_activity_is_by_total_time(self, db_session, sample_user, sample_order):
        start = datetime(2026, 5, 12, 9, 0, 0)
        end = start + timedelta(days=7)
        a_long = await _activity(db_session, "Fassen", "fabrication", True)
        a_freq = await _activity(db_session, "Löten", "fabrication", True)
        # a_freq appears more often but a_long has more total minutes
        await _entry(db_session, user_id=sample_user.id, order_id=sample_order.id,
                     activity_id=a_long.id, start=start + timedelta(hours=1), minutes=200)
        for h in (3, 5, 7):
            await _entry(db_session, user_id=sample_user.id, order_id=sample_order.id,
                         activity_id=a_freq.id, start=start + timedelta(hours=h), minutes=30)
        result = await TimeTrackingService.get_summary(
            db_session, user_id=sample_user.id, start=start, end=end
        )
        assert result.most_used_activity == "Fassen"

    async def test_comparison_percentage_vs_prior_window(self, db_session, sample_user, sample_order):
        start = datetime(2026, 5, 12, 9, 0, 0)   # window length 7 days
        end = start + timedelta(days=7)
        act = await _activity(db_session, "Polieren", "fabrication", True)
        # prior window: 10 hours (600 min)
        await _entry(db_session, user_id=sample_user.id, order_id=sample_order.id,
                     activity_id=act.id, start=start - timedelta(days=3), minutes=600)
        # current window: 12 hours (720 min) -> +20%
        await _entry(db_session, user_id=sample_user.id, order_id=sample_order.id,
                     activity_id=act.id, start=start + timedelta(days=1), minutes=720)
        result = await TimeTrackingService.get_summary(
            db_session, user_id=sample_user.id, start=start, end=end
        )
        assert result.comparison_previous_period == 20.0

    async def test_running_entries_excluded(self, db_session, sample_user, sample_order):
        start = datetime(2026, 5, 12, 9, 0, 0)
        end = start + timedelta(days=7)
        act = await _activity(db_session, "Polieren", "fabrication", True)
        running = TimeEntryModel(
            order_id=sample_order.id, user_id=sample_user.id, activity_id=act.id,
            start_time=start + timedelta(hours=1), end_time=None, duration_minutes=None,
        )
        db_session.add(running)
        await db_session.flush()
        result = await TimeTrackingService.get_summary(
            db_session, user_id=sample_user.id, start=start, end=end
        )
        assert result.entries_count == 0
        assert result.total_hours == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/unit/test_time_tracking_summary.py -v`
Expected: FAIL — `AttributeError: type object 'TimeTrackingService' has no attribute 'get_summary'`.

- [ ] **Step 3: Add the `case` import and `Activity` import to the service**

In `src/goldsmith_erp/services/time_tracking_service.py`, change line 6 from:
```python
from sqlalchemy import update, delete, and_, func
```
to:
```python
from sqlalchemy import update, delete, and_, func, case
```

Then ensure `Activity` is imported from `goldsmith_erp.db.models` in the `from goldsmith_erp.db.models import (...)` block (lines ~14-20). Add `Activity` to that import list if absent (it imports `TimeEntry as TimeEntryModel` there; check the exact aliases and add `Activity` on its own line).

And ensure `TimeSummaryStats` is importable: in the `from goldsmith_erp.models.time_entry import (...)` block (~line 21-26), add `TimeSummaryStats`.

- [ ] **Step 4: Implement `get_summary`**

Append this method to `class TimeTrackingService` (alongside `get_total_time_for_order`):
```python
    @staticmethod
    async def get_summary(
        db: AsyncSession,
        *,
        user_id: int,
        start: datetime,
        end: datetime,
    ) -> TimeSummaryStats:
        """Aggregate a user's completed time entries within [start, end).

        Billable hours count only entries whose activity.is_billable is True.
        comparison_previous_period is the % change in total hours vs the
        immediately preceding window of equal length; None when that prior
        window has zero hours.
        """
        window = end - start
        prev_start = start - window

        current_filter = and_(
            TimeEntryModel.user_id == user_id,
            TimeEntryModel.end_time.isnot(None),
            TimeEntryModel.start_time >= start,
            TimeEntryModel.start_time < end,
        )

        totals = (
            await db.execute(
                select(
                    func.coalesce(func.sum(TimeEntryModel.duration_minutes), 0).label("total"),
                    func.count(TimeEntryModel.id).label("count"),
                    func.coalesce(
                        func.sum(
                            case(
                                (Activity.is_billable.is_(True), TimeEntryModel.duration_minutes),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("billable"),
                )
                .join(Activity, TimeEntryModel.activity_id == Activity.id)
                .filter(current_filter)
            )
        ).one()

        total_minutes = totals.total or 0
        entries_count = totals.count or 0
        billable_minutes = totals.billable or 0

        most_used_row = (
            await db.execute(
                select(Activity.name)
                .join(TimeEntryModel, TimeEntryModel.activity_id == Activity.id)
                .filter(current_filter)
                .group_by(Activity.id, Activity.name)
                .order_by(func.sum(TimeEntryModel.duration_minutes).desc())
                .limit(1)
            )
        ).first()
        most_used_activity = most_used_row[0] if most_used_row else None

        prev_minutes = (
            await db.execute(
                select(func.coalesce(func.sum(TimeEntryModel.duration_minutes), 0)).filter(
                    and_(
                        TimeEntryModel.user_id == user_id,
                        TimeEntryModel.end_time.isnot(None),
                        TimeEntryModel.start_time >= prev_start,
                        TimeEntryModel.start_time < start,
                    )
                )
            )
        ).scalar() or 0

        average_session_minutes = (
            round(total_minutes / entries_count, 1) if entries_count else 0
        )
        comparison = (
            round(((total_minutes - prev_minutes) / prev_minutes) * 100, 1)
            if prev_minutes > 0
            else None
        )

        return TimeSummaryStats(
            total_hours=round(total_minutes / 60, 2),
            billable_hours=round(billable_minutes / 60, 2),
            entries_count=entries_count,
            average_session_minutes=average_session_minutes,
            most_used_activity=most_used_activity,
            comparison_previous_period=comparison,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run pytest tests/unit/test_time_tracking_summary.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_time_tracking_summary.py src/goldsmith_erp/services/time_tracking_service.py
git commit -m "feat(time-tracking): add get_summary service aggregation"
```

---

### Task 6: Router `GET /summary` (TDD)

**Files:**
- Test: `tests/integration/test_time_tracking_summary_api.py` (create)
- Modify: `src/goldsmith_erp/api/routers/time_tracking.py` (imports ~14-20; add route **before** `@router.get("/{entry_id}")` at ~line 154)

- [ ] **Step 1: Write the failing integration tests**

Create `tests/integration/test_time_tracking_summary_api.py`:
```python
"""Integration tests for GET /api/v1/time-tracking/summary."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

PARAMS = "start_date=2026-05-12T00:00:00&end_date=2026-05-19T00:00:00"


class TestTimeTrackingSummaryEndpoint:
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/time-tracking/summary?{PARAMS}")
        assert resp.status_code == 401

    async def test_viewer_gets_own_summary_shape(
        self, client: AsyncClient, viewer_auth_headers
    ):
        resp = await client.get(
            f"/api/v1/time-tracking/summary?{PARAMS}", headers=viewer_auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {
            "total_hours", "billable_hours", "entries_count",
            "average_session_minutes", "most_used_activity",
            "comparison_previous_period",
        }
        assert body["entries_count"] == 0  # viewer has no entries

    async def test_viewer_cannot_query_other_user(
        self, client: AsyncClient, viewer_auth_headers, admin_user
    ):
        resp = await client.get(
            f"/api/v1/time-tracking/summary?{PARAMS}&user_id={admin_user.id}",
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    async def test_admin_can_query_other_user(
        self, client: AsyncClient, admin_auth_headers, viewer_user
    ):
        resp = await client.get(
            f"/api/v1/time-tracking/summary?{PARAMS}&user_id={viewer_user.id}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200

    async def test_invalid_date_range_returns_422(
        self, client: AsyncClient, viewer_auth_headers
    ):
        resp = await client.get(
            "/api/v1/time-tracking/summary"
            "?start_date=2026-05-19T00:00:00&end_date=2026-05-12T00:00:00",
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 422
```

> `viewer_auth_headers`, `viewer_user`, `admin_auth_headers`, `admin_user` live in `tests/integration/conftest.py`. VIEWER has `TIME_VIEW_OWN` but not `TIME_VIEW_ALL`; ADMIN has both.

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/integration/test_time_tracking_summary_api.py -v`
Expected: FAIL — the `/summary` path is captured by `GET /{entry_id}` (404/422 mismatch) or route missing.

- [ ] **Step 3: Add `TimeSummaryStats` to the router imports**

In `src/goldsmith_erp/api/routers/time_tracking.py`, add `TimeSummaryStats` to the `from goldsmith_erp.models.time_entry import (...)` block (~lines 14-20).

- [ ] **Step 4: Add the `/summary` route BEFORE `/{entry_id}`**

Insert this **immediately before** the `@router.get("/{entry_id}", ...)` declaration (~line 154). Order matters — a `/{entry_id}` path param would otherwise capture the literal `summary`:
```python
@router.get("/summary", response_model=TimeSummaryStats)
@require_permission(Permission.TIME_VIEW_OWN)
async def get_time_tracking_summary(
    start_date: datetime = Query(..., description="Window start (inclusive)"),
    end_date: datetime = Query(..., description="Window end (exclusive)"),
    user_id: Optional[int] = Query(
        None, description="Target user; defaults to the current user"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregated time-tracking summary for a date window.

    Defaults to the current user's own data. Querying another user's summary
    requires TIME_VIEW_ALL (same ownership ladder as GET /user/{user_id}).
    """
    if start_date > end_date:
        raise HTTPException(
            status_code=422, detail="start_date must be on or before end_date"
        )

    target_user_id = user_id if user_id is not None else current_user.id
    if not check_ownership_or_permission(
        target_user_id, current_user, Permission.TIME_VIEW_ALL
    ):
        raise HTTPException(
            status_code=403,
            detail="Permission denied: you can only view your own summary or need TIME_VIEW_ALL",
        )

    return await TimeTrackingService.get_summary(
        db, user_id=target_user_id, start=start_date, end=end_date
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run pytest tests/integration/test_time_tracking_summary_api.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_time_tracking_summary_api.py src/goldsmith_erp/api/routers/time_tracking.py
git commit -m "feat(time-tracking): add GET /summary endpoint"
```

---

### Task 7: Full-suite regression

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `poetry run pytest -q`
Expected: all pass (was 1122 passed, 4 skipped, 1 xfailed + the new summary tests).

- [ ] **Step 2: Run linters on touched files**

Run: `poetry run black --check src/ tests/ && poetry run mypy src/goldsmith_erp/services/time_tracking_service.py src/goldsmith_erp/api/routers/time_tracking.py`
Expected: clean (run `poetry run black src/ tests/` to fix formatting if needed, then re-commit).

- [ ] **Step 3: Commit any formatting fixes**

```bash
git add -A && git commit -m "style: black formatting for summary endpoint" || echo "nothing to format"
```

---

## Self-Review

- **Spec coverage:** Decision 1 (scope/permissions) → Task 6. Decision 2 (`is_billable` + category defaults) → Tasks 1-3. Decision 3 (most-used by time) → Task 5 test + impl. `TimeSummaryStats` contract → Task 4. All computation rows → Task 5. Edge cases (empty window, prior empty, running excluded, bad dates, 403) → Tasks 5-6 tests. ✓
- **Deferred items** (frontend type sync, management UI, all-users mode) match the spec's "Out of scope". ✓
- **Type consistency:** `get_summary(db, *, user_id, start, end) -> TimeSummaryStats` used identically in service impl, unit tests, and router. `TimeSummaryStats` fields match the frontend contract and the router `response_model`. `is_billable` column/schema/seed names align. ✓
- **Route ordering** (`/summary` before `/{entry_id}`) explicitly called out — the one easy-to-miss FastAPI gotcha. ✓
