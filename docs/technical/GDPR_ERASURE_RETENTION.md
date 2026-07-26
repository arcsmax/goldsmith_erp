# GDPR Art. 17 Erasure vs. §147 AO Retention

Status: authoritative — describes the implemented behaviour as of the
`feat/tier1-gdpr-loop` change (production-readiness.md 2026-07-26, finding
1.3 + issue #24).

This document covers:

1. The **retention policy** — when a customer is hard-deleted vs. anonymised.
2. The **erasure lifecycle** end to end (request → grace period → cleanup).
3. **Installation** of the scheduled cleanup job (systemd timer + alerting).

---

## 1. Policy: §147 AO retention overrides Art. 17 erasure

A data subject's right to erasure (GDPR **Art. 17(1)**) is **not absolute**.
Art. **17(3)(b)** explicitly preserves processing that is required "for
compliance with a legal obligation". In a German goldsmith business the
governing obligation is **§147 AO (Abgabenordnung)**: invoices and the trade
records around them must be retained for **10 years**. GoBD/HGB §257 point the
same way for quotes and valuation certificates.

Therefore, when the 30-day grace period elapses, the customer's disposition
depends on whether they have **retained financial records**:

| Customer has …                              | Disposition                     | Why                                                                 |
| ------------------------------------------- | ------------------------------- | ------------------------------------------------------------------- |
| No invoices, quotes, or valuations          | **Hard-delete** the customer row | Nothing legally blocks removal; child rows go via CASCADE / SET NULL |
| ≥1 invoice, quote, or valuation certificate | **Anonymise in place** (keep row) | §147 AO requires the record be kept; the FK must keep resolving      |

The schema **encodes** this obligation and made the old naive delete
impossible: `invoices.customer_id`, `quotes.customer_id`, and
`valuation_certificates.customer_id` are all `ForeignKey(..., ondelete="RESTRICT")`
and `nullable=False` (`db/models.py:1334, 1466, 2386`). A plain
`DELETE FROM customers` FK-fails for any customer who was ever invoiced —
which is essentially every real customer. The previous cleanup script
swallowed that failure into an `error_count` that nobody ever saw.

### What "anonymise in place" means

`CustomerService.anonymize_customer` (mirroring `UserService.anonymize_user`
for the workforce side) keeps the `customers` row — so the RESTRICT FKs stay
valid — and overwrites every identifying / personal column:

- `first_name` / `last_name` → `[GELÖSCHT]` sentinel (the columns are NOT NULL).
- `email` → `deleted_{id}@anonymized.local` (unique, keeps the NOT NULL +
  UNIQUE `email_hash` blind index collision-free); `email_hash` recomputed.
- `company_name`, `phone`, `mobile`, `street`, `city`, `postal_code`,
  `allergies` (health-adjacent PII), `birthday`, `notes`, `style_profile`,
  `tags`, `preferences`, and the ring/chain/bracelet measurement fields →
  `NULL` / empty.
- `is_active=False`, `is_deleted=True`, `deleted_at=now`,
  `deletion_scheduled_at=NULL` (the schedule is discharged),
  `deletion_reason` records the §147 AO rationale.

The retained **invoice/quote/valuation still exists**, still carries its
financial content for the tax audit, and now points at a customer shell that
holds **no personal data**. Free-text PII that had leaked into those records
(e.g. a name typed into `invoices.notes`) was already `[REDACTED]` at request
time by `CustomerService.scrub_customer_pii`.

> **Design choice — why in-place anonymisation, not a sentinel customer.**
> The two options were (a) create a global "deleted customer" sentinel row and
> repoint every financial FK to it, then delete the real row, or (b) scrub the
> customer's own row in place and keep it. We chose **(b)** because it needs
> the **least new machinery**: no sentinel row to seed (which would need a
> migration — explicitly out of scope), no per-FK repoint registry, and the
> existing `scrub_customer_pii` field-registry already handles the related
> free-text. It also mirrors the precedent already in the codebase —
> `RepairJob` / `Consultation` rows are likewise retained-and-scrubbed rather
> than repointed — so operators and auditors see one consistent pattern.

---

## 2. Erasure lifecycle

```
                 ┌─────────────────────────────────────────────────────────┐
 Admin clicks    │ DELETE /customers/{id}/gdpr-erase  (api/routers/customers)│
 "Löschen"  ───▶ │  • is_active=False, deletion_scheduled_at = now + 30 days │
                 │  • scrub_customer_pii()  → free-text PII → [REDACTED]     │
                 │  • FileErasureService     → PDFs/photos/thumbnails deleted│
                 │  • gdpr_requests row: PENDING → completed / PARTIAL       │
                 └─────────────────────────────────────────────────────────┘
                                     │  (30-day grace period)
                                     ▼
                 ┌─────────────────────────────────────────────────────────┐
 systemd timer   │ python -m goldsmith_erp.jobs.gdpr_cleanup                 │
 (daily 02:30) ─▶│  CustomerService.hard_delete_expired_customers():        │
                 │   for each customer past grace:                          │
                 │    1. FileErasureService (idempotent re-sweep, incl. #24 │
                 │       order-photo thumbnails)                            │
                 │    2. financial records?  yes → anonymize_customer       │
                 │                            no → DELETE customer row       │
                 │    3. gdpr_requests row: erasure_cleanup / completed      │
                 │   per-customer transaction; one failure ≠ whole-run abort │
                 └─────────────────────────────────────────────────────────┘
                                     │ any per-customer failure → exit 1
                                     ▼  OnFailure=
                 ┌─────────────────────────────────────────────────────────┐
                 │ goldsmith-gdpr-cleanup-alert.service                     │
                 │  POST /admin/notify-gdpr-cleanup → WARNING notification   │
                 │  for every active ADMIN (DPO follow-up)                   │
                 └─────────────────────────────────────────────────────────┘
```

**Fail-loud guarantees** (CLAUDE.md "Fail loudly"):

- Each customer is processed in its **own transaction**. A failure is logged
  with structured context (`customer_id` PK **only** — never names/emails;
  PKs are not PII in these logs, consistent with the rest of the GDPR code),
  the transaction is rolled back, and the sweep continues with the next
  customer.
- The job **exits nonzero** if any customer failed. The old inline script
  hid failures in an unread counter; this one surfaces them to systemd, which
  fires the alert.

**Audit trail** (Art. 30): every step writes a row — `customer_audit_logs`
(`gdpr_pii_scrub`, `gdpr_file_erasure`) plus `gdpr_requests`
(`erasure` at request time, `erasure_cleanup` at execution time). Because
`gdpr_requests` has no FK to `customers`, the completion row survives even a
hard-delete.

> **Art. 30 record of processing.** This erasure lifecycle — the customer
> hard-delete/anonymise cleanup job and the customer/employee `gdpr-erase`
> endpoints — is registered as a processing activity (entry **V1.3-002**) in
> the Verarbeitungsverzeichnis:
> [`VERZEICHNIS-VERARBEITUNGSTAETIGKEITEN.md`](../superpowers/plans/qr-barcode-workflow/VERZEICHNIS-VERARBEITUNGSTAETIGKEITEN.md)
> (see also V1.1-004/005/006 for the underlying erasure mechanisms).

---

## 3. Installation — scheduled cleanup + alerting

The job runs **inside** the rootless-podman backend container. The units live
in `deploy/systemd/` and install as **user** units so they share the
operator's rootless podman socket.

```bash
# 1. Copy the units into the user systemd dir.
mkdir -p ~/.config/systemd/user
cp deploy/systemd/goldsmith-gdpr-cleanup.service \
   deploy/systemd/goldsmith-gdpr-cleanup.timer \
   deploy/systemd/goldsmith-gdpr-cleanup-alert.service \
   ~/.config/systemd/user/

# 2. Edit WorkingDirectory in goldsmith-gdpr-cleanup.service to point at the
#    directory that holds podman-compose.yml (default: %h/goldsmith_erp).
#    For a prod deployment set COMPOSE_FILE=podman-compose.prod.yml there too.

# 3. Reload + enable the timer (pulls in the .service on schedule).
systemctl --user daemon-reload
systemctl --user enable --now goldsmith-gdpr-cleanup.timer

# 4. So the timer keeps firing while the operator is logged out:
loginctl enable-linger "$USER"

# 5. Verify.
systemctl --user list-timers goldsmith-gdpr-cleanup.timer
systemctl --user status goldsmith-gdpr-cleanup.service   # after first run

# Run once, on demand (e.g. to verify before enabling the timer):
systemctl --user start goldsmith-gdpr-cleanup.service
# …or directly:
scripts/gdpr-cleanup.sh
```

Notes:

- **Alerting** reuses the same in-app notification path as backup alerting
  (`scripts/backup.sh` → `/admin/notify-backup`). The new endpoint
  `/admin/notify-gdpr-cleanup` (`api/routers/health.py`) is localhost-only,
  takes no PII, and raises a WARNING SYSTEM notification for every active
  ADMIN. If the backend's published port is not `8000`, edit the URL in
  `goldsmith-gdpr-cleanup-alert.service`.
- **Cron alternative**: if systemd is unavailable, schedule the wrapper
  directly and alert on nonzero exit:
  `0 2 * * * /path/to/goldsmith_erp/scripts/gdpr-cleanup.sh >> /var/log/gdpr-cleanup.log 2>&1`.

---

## 4. Backups und Löschung (backups vs. erasure) — production-readiness.md 2.5

### 4.1 The conflict

`scripts/backup.sh` keeps a **tiered** set of dumps (see `apply_retention`):

- **7 daily** dumps,
- **4 weekly** dumps (each Sunday), and
- **3 monthly** dumps (each 1st of month).

The oldest monthly dump can therefore be **up to ~3 months old**. A database
restore replays whatever was in the dump at the time it was taken — so a
customer who was erased or anonymised (§ 1–2 above) **after** that dump was
written will **resurface** in the restored database, personal data and all.
The 30-day erasure grace window is shorter than the ~3-month backup horizon,
so this window of exposure is real and expected — not a bug in the backup
rotation.

### 4.2 Policy: re-run the erasure job after every restore

**After _any_ restore that predates an erasure, re-run the cleanup job.** It is
idempotent (per-customer transactions; already-anonymised rows are handled by
the same disposition logic) and re-applies both the hard-delete and the
in-place anonymisation to the restored rows:

```bash
# From the project root, against the running (prod) stack:
COMPOSE_FILE=podman-compose.prod.yml scripts/gdpr-cleanup.sh
#   …or via the installed user unit (§3):
systemctl --user start goldsmith-gdpr-cleanup.service
```

`scripts/restore.sh` **prints this reminder automatically** as the last thing
it does, pointing back to this section — so an operator following the restore
runbook cannot miss it. The reminder is advisory (an `echo`): it does not run
the job for you, because a restore is often followed by manual verification
before the stack is considered live.

> **Why not scrub the dumps directly?** Rewriting historical `.sql.gz` dumps in
> place would (a) break the integrity check (`gzip -t`) that `backup.sh` relies
> on, (b) risk corrupting the one artifact you restore from in a disaster, and
> (c) still miss any off-site copy already synced by `backup-sync.sh`. Re-applying
> erasure *after* restore is the robust, auditable path — every re-run writes the
> same `customer_audit_logs` / `gdpr_requests` rows as the original erasure.

### 4.3 Retention window vs. the 30-day grace window

The backup retention (~3 months) deliberately **exceeds** the 30-day erasure
grace window. That is an operational disaster-recovery requirement (a fault or
ransomware event discovered weeks later must still be recoverable), not an
oversight. The mismatch is reconciled by policy, not by shortening retention:
the re-run in § 4.2 guarantees that an erasure is re-applied to any older state
that a restore brings back. Shortening backup retention to ≤ 30 days would
weaken disaster recovery and is **not** the chosen trade-off.

### 4.4 Legal basis for keeping the backups themselves — Art. 17(3)

Retaining the backup **files** during their normal rotation window is lawful.
Art. 17 does not require a controller to hunt an erased record out of every
historical backup the moment the request lands; the established position of the
German supervisory authorities is that erasure of backups is discharged on the
**normal backup cycle** — a record erased from the live system is removed from
backups as those backups age out and are overwritten (here: within the 7d/4w/3m
rotation), provided the backups are not restored into production in the interim
without re-applying the erasure (which § 4.2 enforces). During the retention
window the dumps are held under **Art. 17(3)(b)** (data integrity / security of
processing and the legal-obligation carve-out that already governs the §147 AO
financial records) and serve only disaster recovery — they are not used for any
other processing. Once a dump rotates out under `apply_retention`, it is deleted
(`rm -f`), which removes the residual copy for good.
---

## 5. Per-entity retention sweep (`retention_class`) — finding 2.3

The customer-level erasure above disposes of *customers*. A separate weekly
job — `python -m goldsmith_erp.jobs.retention_sweep` — enforces the per-row
statutory retention buckets tagged by the `retention_class` column on the
operational + financial tables (added by the Slice-2 / QR-barcode migrations;
the repository methods that were meant to drive this were deleted in the
pre-V1.1 hotfix and never rebuilt).

### Retention-class map

| Table            | `retention_class`     | Anchor column | Period                    | Legal basis                              | Action                        |
| ---------------- | --------------------- | ------------- | ------------------------- | ---------------------------------------- | ----------------------------- |
| `scan_logs`      | `standard_24m`        | `scanned_at`  | 24 months (rolling)       | Operational log — Datenminimierung Art. 5(1)(e) DSGVO | **Delete** after the window   |
| `time_entries`   | `financial_10y`       | `created_at`  | 10 years (year-end anchor)| HGB §257 / §147 AO                        | **Delete** after the period   |
| `material_usage` | `financial_10y`       | `used_at`     | 10 years (year-end anchor)| HGB §257 / §147 AO                        | **Delete** after the period   |
| `orders`         | `indefinite_business` | —             | indefinite                | Core business record                     | **Excluded** — never expires  |
| `orders`         | `hallmark_10y`        | —             | ≥10 years (floor)         | Feingehaltsgesetz / DIN 8238 evidence    | **Excluded + flagged** (see below) |

**Anchor rationale.** For the financial tables the retention clock is
*year-end-anchored*: §147 AO / HGB §257 retention runs to the end of the
calendar year in which the record arose, so the cutoff is `1 Jan of
(year(now) − 10)`. A row is therefore never a candidate until it is fully past
its statutory 10-year window — conservative by construction, so a euro-relevant
row is **never** deleted early. `created_at` (time_entries) / `used_at`
(material_usage) are the always-present record-creation / consumption
timestamps. `scan_logs` uses a plain 24-month rolling window on `scanned_at`
(the scan event time) — an operational log with no statutory floor.

**Why `orders` is excluded (flagged, not guessed).** `indefinite_business`
(the column default) means nothing ever expires. `hallmark_10y` is a retention
*floor* ("must survive ≥10 years"), not a delete-at-10-years trigger; the order
may still be an indefinite business record afterwards. Deleting an order also
cascades to `material_usage` / `gemstones` / `comments`, touches customer PII +
design-IP, and overlaps the customer-level erasure path — and its 10-year
anchor is itself ambiguous (`created_at` vs `completed_at` vs
`punzierung_verified_at`). This needs an explicit **Anna + Henrik** policy
decision before it is swept.

> **Open policy question (flagged for Anna + Henrik).** For `financial_10y`
> the sweep hard-deletes once the statutory period has fully lapsed (GDPR
> data-minimisation once the retention obligation ends). If the workshop would
> rather *anonymise-in-place* these rows instead (mirroring the customer
> policy in §1), that is a one-line change to the rule's action — raise it
> before enabling execution.

### Safety model

- **DRY-RUN is the default.** Without `--execute` the job only counts + logs
  candidate PKs (PK ids only — never PII) per table and deletes nothing. The
  systemd unit ships in dry-run mode.
- **`--execute` (or `RETENTION_EXECUTE=1`)** performs the deletions, each rule
  in its own transaction. A per-table failure is logged with PK ids and makes
  the job exit nonzero (fail-loud) while other tables still process — the
  `OnFailure=` alert unit then notifies admins in-app.

### Installation — scheduled sweep + alerting

```bash
# 1. Copy the units into the user systemd dir.
mkdir -p ~/.config/systemd/user
cp deploy/systemd/goldsmith-retention-sweep.service \
   deploy/systemd/goldsmith-retention-sweep.timer \
   deploy/systemd/goldsmith-retention-sweep-alert.service \
   ~/.config/systemd/user/

# 2. Edit WorkingDirectory in goldsmith-retention-sweep.service to the project
#    root. LEAVE IT IN DRY-RUN until you have reviewed the candidate logs and
#    have an Anna+Henrik sign-off; then uncomment Environment=RETENTION_EXECUTE=1.

# 3. Reload + enable the weekly timer (Sundays 03:30).
systemctl --user daemon-reload
systemctl --user enable --now goldsmith-retention-sweep.timer
loginctl enable-linger "$USER"

# Run once on demand to review the dry-run candidate counts:
systemctl --user start goldsmith-retention-sweep.service
#   …or directly:  scripts/retention-sweep.sh          # dry-run
#                  RETENTION_EXECUTE=1 scripts/retention-sweep.sh   # execute
```

The alert unit reuses the same localhost-only `/admin/notify-gdpr-cleanup`
endpoint as the Art. 17 cleanup (the retention sweep is a sibling of it); the
`unit` field identifies the source unambiguously and the body carries no PII.

---

## 6. Out-of-band health alerting (email dead-man's-switch) — finding 2.6

In-app health notifications are useless when the backend itself is down. An
external watchdog — `scripts/health-watchdog.sh`, driven by a 5-minute systemd
timer **on the host** (not in the container) — curls `/health` with retries and,
on failure, sends an email via the import-light CLI
`python -m goldsmith_erp.jobs.health_alert`.

Key properties:

- The alert CLI **needs no DB and no running backend** — it only reads the
  SMTP config from `.env` (`SMTP_*`, `EMAIL_NOTIFICATIONS_ENABLED`) and reuses
  `EmailService`. It runs via `poetry run` on the host or via
  `podman run --rm --env-file .env <backend-image>` (set `ALERT_CMD`).
- **No duplicate SMTP creds in the shell** — the recipient is
  `HEALTH_ALERT_EMAIL` (env), falling back to `SMTP_FROM`.
- **If SMTP is unconfigured the CLI logs and exits 0** (documented no-op — a
  workshop may not have SMTP yet). It exits nonzero only when SMTP *is*
  configured but the send fails.
- The watchdog exits nonzero on an outage so `systemctl --user status
  goldsmith-health-watchdog` surfaces it; the email is the out-of-band alert
  (no separate `OnFailure=` unit).

### Installation

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/goldsmith-health-watchdog.service \
   deploy/systemd/goldsmith-health-watchdog.timer \
   ~/.config/systemd/user/
# Edit WorkingDirectory (project root, holds pyproject.toml + .env) and, if
# desired, Environment=HEALTH_ALERT_EMAIL=... in the .service.
systemctl --user daemon-reload
systemctl --user enable --now goldsmith-health-watchdog.timer
loginctl enable-linger "$USER"
systemctl --user list-timers goldsmith-health-watchdog.timer   # verify

# Test the alert path directly (no-op if SMTP unset):
poetry run python -m goldsmith_erp.jobs.health_alert --reason "manual test"
```

Nothing is wired into podman-compose — host-level systemd is the right place,
consistent with the backup and GDPR timers.
