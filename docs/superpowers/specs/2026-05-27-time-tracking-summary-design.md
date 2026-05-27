# Design: Time-Tracking Summary Endpoint

**Date:** 2026-05-27
**Status:** Approved (design), pending spec review
**Author:** Claude (Opus 4.7) + arcsmax

## Problem

The frontend already calls `timeTrackingApi.getSummary({ start_date, end_date })` and
expects a `TimeSummaryStats` payload, but the backend endpoint does not exist. Both
consumers — `DashboardKPIs` ("Stunden (Woche)" KPI) and `TimeSummaryCards`
(Zeiterfassung-Übersicht) — currently degrade gracefully (the call 404s and they show
zeros / hide). This builds the missing `GET /time-tracking/summary` endpoint so those
views light up.

## Contract (fixed by the frontend)

```ts
interface TimeSummaryStats {
  total_hours: number;
  billable_hours: number;
  entries_count: number;
  average_session_minutes: number;
  most_used_activity?: string;
  comparison_previous_period?: number; // percentage change
}
```

## Decisions

1. **Data scope — current user by default, optional `user_id`.**
   - No `user_id` → the logged-in user's own entries (`TIME_VIEW_OWN`).
   - `user_id=N` → that user's entries; allowed if `N == current_user.id`, otherwise
     requires `TIME_VIEW_ALL` (same ownership ladder as `GET /time-tracking/user/{id}`).
   - A workshop-wide "all users" mode is **explicitly deferred** (YAGNI — the frontend
     never requests it; trivial to add later as `?scope=all` gated on `TIME_VIEW_ALL`).

2. **`billable_hours` — per-activity flag.** Add `Activity.is_billable: bool`
   (default `true`). `billable_hours` sums `duration_minutes` only for completed entries
   whose activity has `is_billable = true`. Existing activities migrate to `true` via a
   server default. The flag is set through the **existing** Activity create/update API +
   edit form (one checkbox) — no dedicated management screen (Approach A).

3. **`most_used_activity` — by total time.** The activity name with the greatest
   `SUM(duration_minutes)` in the window (not by frequency). `null`/omitted if no
   completed entries.

## Computation (all over *completed* entries: `end_time IS NOT NULL`, `start_time` within window)

Mirrors the existing `TimeTrackingService.get_total_time_for_order` aggregation style.

| Field | Definition |
|-------|-----------|
| `total_hours` | `SUM(duration_minutes) / 60`, rounded to 2 |
| `billable_hours` | `SUM(duration_minutes)` where `activity.is_billable` is true, `/ 60`, rounded to 2 |
| `entries_count` | `COUNT(id)` |
| `average_session_minutes` | `total_minutes / entries_count` (0 when no entries) |
| `most_used_activity` | activity `name` with `MAX(SUM(duration_minutes))`; `null` if none |
| `comparison_previous_period` | % change of `total_hours` vs the immediately preceding window of equal length `[start - (end - start), start)`; `null` if the prior window has zero hours (avoids divide-by-zero / meaningless ∞) |

Window length for the comparison = `end_date - start_date`. Dates are inclusive of the
day per existing `/user/{id}` filter semantics (uses `datetime` query params).

## Architecture (follows the project's service/router/schema layering)

**Backend**
- `db/models.py` — add `Activity.is_billable = Column(Boolean, nullable=False, server_default=expression.true(), default=True)`.
- Alembic migration — add column with server default `true` so existing rows backfill; non-destructive, reversible (`op.drop_column` on downgrade).
- `models/activity.py` — add `is_billable: bool = True` to `ActivityBase`/read/create/update schemas.
- `models/time_entry.py` — add `TimeSummaryStats` Pydantic schema matching the contract.
- `services/time_tracking_service.py` — `async def get_summary(db, *, user_id, start, end) -> TimeSummaryStats`. Two grouped aggregate queries (current window + prior window) joined to `activities` for the billable filter and the most-used name. Uses `selectinload`/explicit joins; no N+1.
- `api/routers/time_tracking.py` — `GET /summary` with `@require_permission(Permission.TIME_VIEW_OWN)` + ownership ladder; resolves `user_id` default to `current_user.id`.

**Frontend (Approach A, minimal)**
- `types.ts` — add `is_billable: boolean` to `Activity`; `ActivityCreateInput`/`ActivityUpdateInput` accept optional `is_billable`.
- Activity edit form — one "Abrechenbar" checkbox bound to `is_billable`.
- `getSummary` client method already exists (added in the tsc-burndown PR) and already targets `/time-tracking/summary`.

**Seed data** — built-in activities default to `is_billable = true` (same as the column
default). We deliberately do **not** hardcode a billing policy (e.g. "waiting is
non-billable") — billability is a per-workshop decision the goldsmith sets via the
checkbox. This keeps behaviour unsurprising (everything billable until explicitly
changed) and avoids baking one shop's policy into seed data.

## Edge cases

- Empty window → `total_hours=0, billable_hours=0, entries_count=0, average_session_minutes=0, most_used_activity=null, comparison_previous_period=null`.
- Prior window empty but current has data → `comparison_previous_period=null` (not a misleading large %).
- Running entries (`end_time IS NULL`) excluded from all aggregates.
- `start_date > end_date` → 422 (validated).
- Requesting another user's summary without `TIME_VIEW_ALL` → 403.

## Testing (TDD — tests first)

**Service unit tests** (`tests/unit/test_time_tracking_service.py` or similar):
- billable excludes entries whose activity `is_billable=false`
- `most_used_activity` picks the activity with most *time*, not most entries
- `comparison_previous_period` math (e.g. prior 10h, current 12h → +20.0); null when prior empty
- empty window → zeros/nulls
- running entries excluded

**Integration tests** (`tests/integration/test_time_tracking_api.py`):
- own summary 200 + shape
- `user_id` of self 200; of another user without `TIME_VIEW_ALL` → 403; with → 200
- `start_date > end_date` → 422

**Backend regression:** full suite stays green (currently 1122 passed).
**Frontend:** vitest stays 348/348; the dashboard/summary components consume the live shape (covered by existing component tests via MSW — add a `/time-tracking/summary` MSW handler).

## Out of scope

- Workshop-wide "all users" aggregation mode.
- A dedicated billable-activity management screen.
- Historical/trend charts beyond the single previous-period comparison.
