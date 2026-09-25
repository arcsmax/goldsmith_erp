# ADR 2026-09-25: Transactional outbox and worker process

Status: accepted (W6, architecture review 2026-09-25, phase "3. Outbox + comms")
Findings: ARCH-04 (background work in the web process, inline SMTP), ARCH-05
(customer communication), ARCH-12 (failed deliveries not visible)

## Context

Customer mail (Kundeninfo, automated pickup and fitting mails, the §649
cost-change notice, the Kostenvoranschlag PDF) was sent inline through
`aiosmtplib` inside the request or the monitor scan. A slow or unreachable
SMTP server blocked the request. Nothing retried a failure except a manual
resend. `uvicorn --workers 2` also started `system_monitor_loop` in each
worker. The advisory leader lock (`core/leader_lock.py`) stopped the scans
from running twice, but the loop still lived in the web process.

## Decision

1. **`outbox_messages` table** (migration `20260925_w6_outbox`): `id, kind,
   payload JSON, dedupe_key UNIQUE NULL, status pending|sent|failed|dead,
   attempts, next_attempt_at, last_error, created_at, sent_at`. `status` is a
   string with a CHECK constraint, not a PG enum, so a new state needs no
   `ALTER TYPE`. `payload` carries ids only. The worker re-reads the business
   rows when it sends, so PII stays in its encrypted tables, and an erasure
   or an Art. 21 objection made while a mail is queued is respected.
2. **Enqueue in the same transaction as the business write.**
   `CustomerMessageService.send_update` enqueues inside the transaction that
   claims the `CustomerUpdate` (DRAFT/SEND_FAILED to SENT).
   `QuoteService.send_quote` enqueues inside the transaction that sets the
   quote to SENT. If the transaction rolls back, the message is gone too.
3. **Two modes**, `OUTBOX_MODE`:
   - `inline`: the old behaviour. SMTP runs in the request and no outbox row
     is written. This is the default when `DEBUG=true` (dev, tests).
   - `worker`: the default when `DEBUG=false` (production). The request only
     enqueues. `python -m goldsmith_erp.worker` sends.
4. **Worker** (`src/goldsmith_erp/worker.py`, same image as the backend,
   compose service `worker`):
   - every `OUTBOX_POLL_INTERVAL_SECONDS` it leases up to `OUTBOX_BATCH_SIZE`
     due rows with `SELECT … FOR UPDATE SKIP LOCKED` (a plain SELECT on
     SQLite). Leasing increments `attempts` and pushes `next_attempt_at`
     forward by `OUTBOX_LEASE_SECONDS`, then commits. A worker that dies in
     the middle of a send leaves the row, and another run retries it after
     the lease expires;
   - success sets `sent`. A failure sets `failed` with exponential backoff
     (`BASE * 2^(attempts-1)`, capped at `OUTBOX_BACKOFF_MAX_SECONDS`). After
     `OUTBOX_MAX_ATTEMPTS` the row is `dead` and the kind's `on_dead` hook
     runs;
   - it runs the system monitor cycle every 5 minutes under the existing
     advisory leader lock. With `OUTBOX_MODE=worker` the web process starts
     no loops at all (`main.py` startup);
   - it writes a heartbeat file, and `--healthcheck` exits 0 while the
     heartbeat is younger than 120 s. `--once` drains one batch and exits.
5. **Kinds and their failure outcomes**
   | kind | sent by | queued state shown to staff | on dead |
   |---|---|---|---|
   | `customer_update` | `deliver_queued_update` | row SENT, `delivery_method` NULL; API `delivered=true, reason="queued"` | row becomes SEND_FAILED, sender gets the in-app notice (same as an inline failure) |
   | `quote_email` | `deliver_queued_quote` | quote SENT, delivery record SENT with `delivery_method` NULL (no "delivered" timestamp yet) | record becomes SEND_FAILED and the quote goes back to DRAFT |
   Handlers are idempotent: a row whose record already has
   `delivery_method=EMAIL` is not mailed again.
6. **Logs and errors carry no PII.** Log lines hold `outbox_id`, `kind`,
   `attempts` and the business ids. `last_error` holds a code
   (`delivery_failed`, `unknown_kind`) or an exception class name, never the
   exception text, because SMTP errors can contain addresses.

Delivery is at least once. If SMTP accepts a mail and the worker then dies
before it commits `sent`, the mail is sent again after the lease expires.
The per-row idempotency check covers the usual resend paths but cannot catch
this particular crash window. We accept that: a rare duplicate is better
than a lost mail.

## Alternatives considered

- **Celery or arq on Redis.** Rejected: another stateful dependency, with
  weaker durability than the PostgreSQL we already back up (review E, "no
  broker").
- **systemd timers for the monitor.** Still an option later. Keeping the
  monitor in the worker means one process to watch and no change to the
  host.

## Operations runbook

**Is the worker running?**
```bash
podman-compose -f podman-compose.prod.yml ps worker          # healthy?
podman-compose -f podman-compose.prod.yml logs --tail=100 worker
```
Look for `Worker started` (with `outbox_mode`) and `Outbox sent` / `Outbox
failed` / `Outbox message dead-lettered` lines.

**What is in the queue?** Admin UI: *System → Nachrichten-Warteschlange*
lists failed and dead messages with their error code. The API is
`GET /api/v1/admin/outbox?status=dead`. Using SQL:
```sql
SELECT status, count(*) FROM outbox_messages GROUP BY status;
SELECT id, kind, attempts, last_error, next_attempt_at
  FROM outbox_messages WHERE status IN ('failed','dead') ORDER BY id DESC;
```

**Retry.** Fix the cause first (SMTP settings under *System → E-Mail*, or the
customer's address). Then click *Nachricht erneut senden* in the panel, or
call `POST /api/v1/admin/outbox/{id}/retry`. The retry resets `attempts` to 0
and sets `pending`, the worker sends on its next poll, and the audit
middleware records the request. Only `failed` and `dead` rows can be
retried (anything else returns 409). To send right away without waiting for
the poll:
```bash
podman-compose -f podman-compose.prod.yml exec worker \
  bash -c "cd /app/src && python -m goldsmith_erp.worker --once"
```

**Stuck `pending` rows with `next_attempt_at` in the future** are leased
rows. They become due again once `OUTBOX_LEASE_SECONDS` (default 300 s) has
passed. If they stay stuck, the worker is not running.

**Switch back to inline** (emergency): set `OUTBOX_MODE=inline` for the
backend and restart it. Drain the queue first, or keep the worker running,
so that already queued mail still goes out.

**Retention.** `sent` rows hold only ids and can be deleted after 90 days
(not automated yet, open item): `DELETE FROM outbox_messages WHERE status =
'sent' AND sent_at < now() - interval '90 days';`

## Consequences

- The request path no longer depends on SMTP latency in production.
- Staff see "versendet" right away. A final failure still reaches them
  through the existing SEND_FAILED notice.
- There is one more container, with a 256 MB limit, built from the same
  image.
- Not yet on the outbox: PDF rendering and thumbnails (review phase 3), and
  WebSocket publishes (ARCH-11 treats those as hints, so no outbox is needed).
  There is no invoice email path in the codebase today. When one is added it
  should use `OutboxService.enqueue` in the same way.
