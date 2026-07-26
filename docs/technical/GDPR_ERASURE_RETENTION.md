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

## 4. Backup interaction (see production-readiness.md 2.5)

Tiered DB dumps (7d/4w/3m) mean an erased/anonymised customer can **resurface
on restore** for up to ~3 months. After **any** restore that predates an
erasure, re-run the cleanup job (`scripts/gdpr-cleanup.sh`) to re-apply the
erasure to the restored rows. Keeping backup retention within the grace window
is the cleaner long-term fix; that is tracked separately.
