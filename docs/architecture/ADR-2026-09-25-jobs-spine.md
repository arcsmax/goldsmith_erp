# ADR 2026-09-25: Jobs spine for orders and repairs

- Status: accepted (ARCH phase 5, ARCH-02)
- Findings: ARCH-02 (Order and RepairJob duplicated; repairs cannot be invoiced),
  docs/review/2026-09-25/01-architecture.md section E, phase "5. Job spine"
- Migration: `alembic/versions/20260925_arch5_jobs_spine.py` (revision `20260925_arch5_jobs`, on top of `20260925_arch4_media`)
- Code: `db/models/jobs.py`, `services/job_service.py`, `services/repair_workflow.py`, `api/routers/jobs.py`

## Context

A workshop has two kinds of work: made-to-order pieces (`orders`) and repairs (`repair_jobs`). They were separate aggregates that shared nothing. Both have a customer, a number, a status machine, a deadline, photos, customer updates and a timeline, and each of these was built twice or not at all for repairs. Invoices required an `order_id`, so a repair, the highest-volume work in a small workshop, could not be invoiced. A kanban board across both kinds had nothing to query.

## Decision

Add a `jobs` supertable (one row per order and per repair) and let the cross-cutting records point at it through `job_id`. For this release the per-kind tables stay the source of truth. The job row is a synchronised projection that the service layer writes.

### Schema

`jobs`:

| column | notes |
|---|---|
| `id` | PK |
| `kind` | `order` / `repair` (String + CHECK, like `media_assets`) |
| `customer_id` | FK customers, SET NULL |
| `number` | unique. `AU-YYYY-NNNN` for orders (new Auftragsnummer), the existing `REP-YYYY-NNNN` for repairs. Both come from `number_sequences` (D-12: gap-free per Europe/Berlin year) |
| `title` | copy of `orders.title` / `repair_jobs.item_description`, whitespace-collapsed, 200 chars. GDPR scrub target `jobs.title` |
| `status` | unified lifecycle (below), String + CHECK |
| `kind_status` | the raw per-kind status, so a board can show the finer stage |
| `deadline` | `orders.deadline` / `repair_jobs.estimated_completion_date` |
| `on_hold_since`, `resume_date` | set while the job is `on_hold`. The free-text hold reason is not copied (minimum data) |
| `is_deleted` | soft-delete mirror |
| `created_at`, `updated_at` | |

New nullable FKs: `orders.job_id`, `repair_jobs.job_id`, `invoices.job_id` (RESTRICT), `customer_updates.job_id`, `media_assets.job_id`, `order_events.job_id`, plus `order_events.repair_job_id` (CASCADE). Repairs now write lifecycle events into `order_events`, with `order_id` NULL.

`invoices.order_id` and `order_events.order_id` become nullable. The partial unique index `uq_invoices_one_active_per_job` enforces one live invoice per job, which also covers repairs. The per-order index stays.

### Status mapping

| job status | order statuses | repair statuses |
|---|---|---|
| `draft` | draft, new (legacy) | |
| `intake` | | received, diagnosed |
| `awaiting_approval` | | quoted |
| `confirmed` | confirmed | approved |
| `in_progress` | in_progress, waiting_for_fitting, fitting_done, ready_for_setting | in_repair |
| `quality_check` | quality_check | quality_check |
| `ready` | completed | ready |
| `delivered` | delivered | picked_up |
| `on_hold` | on_hold | |
| `cancelled` | cancelled | cancelled |

The mapping lives in `services/job_service.py`. The migration keeps a frozen copy, and a test checks that the two agree and that both cover every enum value.

### Sync rules

Services keep the job in sync. There are no DB triggers. Each rule below runs inside the caller's transaction, so the status change, its event and the job row commit or roll back together.

1. **Order created** (`OrderService.create_order` via `order_workflow.record_creation`): the job is created, an `AU` number is drawn, and the creation event gets its `job_id`.
2. **Order status change** (`order_workflow.transition`, the only order status writer): the job status, `kind_status` and hold fields are updated, and the event gets its `job_id`.
3. **Order field edit without a status change** (`OrderService.update_order`): title, deadline and customer are re-copied.
4. **Order soft delete** (`OrderService.delete_order`): `is_deleted` is mirrored.
5. **Quote conversion** (`QuoteService.convert_quote`): a new order gets its job, and carried consultation fields reach it.
6. **Repair intake** (`RepairService.create_repair` via `repair_workflow.record_creation`): the repair number now comes from `number_sequences` (`REP`, seeded from the highest existing number), the job reuses it, and a creation event is written.
7. **Repair status change**: every repair status write (approve, start, quality check, complete, pickup, cancel, and both diagnose steps) goes through `repair_workflow.transition`. It checks the moved `ALLOWED_TRANSITIONS` table, writes the event (`repair_job_id`, `job_id`, no free text) and syncs the job.
8. **Repair soft delete** mirrors `is_deleted`.
9. **Attach points**: `CustomerUpdateService.create_draft`, `MediaService` (order/repair owners), `InvoiceService` (order and repair invoices, Stornorechnungen inherit it) set `job_id` on the new row.

`JobService.sync_order` / `sync_repair` are idempotent upserts. A row without a job (created by old code during a rolling deploy, by the seed script, or by a test fixture) gets one on its next sync. `JobService.count_missing` / `backfill_missing` exist as a health check and a repair tool.

### Features built on the spine in this release

- `POST /repairs/{id}/invoice`: a repair (READY or PICKED_UP, with a customer) is invoiced through the existing `InvoiceService`, with the same numbering, snapshot, §14 UStG elements, seller block and VAT defaults. The net price is the repair's agreed price: `actual_cost`, else `estimated_cost`.
- `GET /jobs`: a paged list of both kinds (filters `kind`, `status` (repeatable), `customer_id`, `q`; sort whitelist without financial fields). This is the data source for a later kanban. `GET /jobs/{id}` and `GET /jobs/{id}/timeline` delegate to the per-kind timeline (orders: the W2-07 merged timeline, repairs: the new repair timeline built from repair events, sent updates and, with DESIGN_VIEW, photos).
- Status report, customer messages and the dashboard carry `job_id`, and the repair status report now shows real repair events instead of a synthetic entry.

### Migration plan

1. Deploy `20260925_arch5_jobs` (additive; backfill in the same transaction). The upgrade log line records the counts: order jobs, repair jobs, repair events, attached rows per table, and the seeded sequences.
2. This release: both per-kind tables remain the write model. Readers may use `jobs` for lists and boards only.
3. Verify after deploy: `JobService.count_missing()` must return zeros.

Downgrade is refused while any repair invoice exists (`invoices.order_id IS NULL`), because invoices are retained records under GoBD. Otherwise it drops the repair events, the new columns and the table, and removes the `AU` / `REP` counters (the old repair code derives numbers from `MAX(repair_number)` again).

### Retiring the per-kind duplication (later releases)

1. **Next release**: move the reads of customer, number, deadline and status in lists, dashboard and notifications to `jobs`. Make `job_id` NOT NULL on `orders`, `repair_jobs`, `invoices` and `order_events` once `count_missing()` is zero in production. Rename `order_events` to `job_events` (with a view for one release).
2. **Release after**: make `jobs` the writer for the shared fields (`customer_id`, `deadline`, hold fields). The per-kind columns become read-only mirrors and are then dropped. `orders` and `repair_jobs` keep only kind-specific data (alloy, hallmark, fitting / bag number, diagnosis, intake checklist). The two status enums collapse into one job lifecycle plus a per-kind production stage (W6-04).
3. Drop the legacy `customer_updates.order_id` / `repair_job_id` and the `media_assets` order/repair owner types in favour of `job_id`, after the frontend addresses jobs.

## Consequences

- Repairs are first-class for billing, feedback and the board. Every future cross-cutting feature targets `job_id` once.
- For one release, a status write costs one extra UPDATE. The shared fields are duplicated, and the sync rules above must be kept on every new write path (review item). A path that bypasses the services leaves the job stale until its next sync.
- New PII surface: `jobs.title`, covered by the GDPR scrub list. Repair events carry no free text.

## Open items

- Price semantics of `repair_jobs.estimated_cost` / `actual_cost` (net vs gross) are not documented anywhere. The invoice treats them as NET, as the task specified. If staff enter consumer prices including VAT, the repair invoice overstates VAT. Confirm with the workshop and, if needed, convert the same way as `order.calculated_price`.
- The frontend has no "Rechnung erstellen" button on the repair page yet (a later item).
- `db/seed_data.py` inserts orders directly. Run `JobService.backfill_missing` after seeding (or on the next sync).
