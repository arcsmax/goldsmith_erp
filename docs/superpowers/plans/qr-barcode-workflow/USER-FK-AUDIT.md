# User Foreign-Key ON DELETE Clause Audit

**Created:** 2026-04-20
**Owner:** Anna Becker (Compliance) + Henrik (Technical Lead)
**Purpose:** Single-source-of-truth record of every `ForeignKey("users.id")`
declared in `src/goldsmith_erp/db/models.py`, its `ON DELETE` clause,
and the legal/security justification for that clause. Introduced in
response to H9 from the post-wave-5 compliance audit.

**When to update:** every time a new column with an FK to `users(id)` is
added. Row is required on the PR that lands the migration.

---

## Invariant

Hard-deleting a row from `users` must **never** silently cascade to
rows that carry audit meaning. The canonical path for removing a user
is `UserService.anonymize_user(user_id, reason, requested_by)` which
rewrites all FKs in `ANONYMIZABLE_FK_TARGETS` to the sentinel user, not
a DB cascade.

Allowed clauses and when each one is appropriate:

| Clause | When |
|---|---|
| `RESTRICT` | Audit / business-record rows. Hard-delete must be blocked so the anonymisation pipeline is the only egress. Covers `scan_logs.user_id`, every `created_by`, every `verified_by`, etc. |
| `SET NULL` | Audit rows that must **survive** a user delete with the user slot blanked. Used for handoff / measurement / photo rows where the audit value is the event, not the actor. Registered in `ANONYMIZABLE_FK_TARGETS` so the sentinel-rewrite path runs anyway — the `SET NULL` is a belt-and-braces second layer. |
| `CASCADE` | User-owned **ephemera** only (personal notification rows, calendar events). Never for audit, never for financial, never for design-IP columns. Each CASCADE has an explicit justification in this doc. |

---

## Table

The list below matches the FK declarations in `db/models.py` at commit
20260420 (H9 merge).

### RESTRICT — audit & business records (no cascade, no null-ing)

| # | Table.Column | File line | `ondelete` | Registered in `ANONYMIZABLE_FK_TARGETS`? | Justification |
|---|---|---|---|---|---|
| 1 | `customers.deleted_by` | 264 | `RESTRICT` | Yes | Soft-delete audit — who erased this customer. GDPR Art. 30. |
| 2 | `order_comments.user_id` | 545 | `RESTRICT` | Yes | Comment authorship — message integrity requires known author (or sentinel). |
| 3 | `activities.created_by` | 596 | `RESTRICT` | Yes | Time-tracking activity catalog — custom activities are auditable. |
| 4 | `time_entries.user_id` | 618 | `RESTRICT` | Yes | Billable-time ownership. HGB §257 10-year retention. |
| 5 | `location_history.changed_by` | 760 | `RESTRICT` | Yes | Order-location audit trail (who moved the piece). |
| 6 | `order_photos.taken_by` | 781 | `RESTRICT` | Yes | Photo-documentation authorship — quality/evidence trail. |
| 7 | `inventory_adjustments.adjusted_by_user_id` | 1024 | `RESTRICT` | Yes | Inventory shrinkage audit — financial. |
| 8 | `scrap_gold.created_by` | 1056 | `RESTRICT` | Yes | Altgold intake record — financial + eIDAS-relevant. |
| 9 | `invoices.created_by` | 1251 | `RESTRICT` | Yes | Financial — HGB §257 retention. |
| 10 | `quotes.created_by` | 1383 | `RESTRICT` | Yes | Quote-authorship — commercial negotiation trail. |
| 11 | `gdpr_requests.requested_by` | 2172 | `RESTRICT` | Yes | Art. 30 audit of GDPR Art. 17 / 15 requests. |
| 12 | `scan_logs.user_id` | Slice 1 | `RESTRICT` | Yes | QR-scan telemetry — A14.2 DPIA subject. |
| 13 | `barcode_aliases.created_by` | Slice 1 | `RESTRICT` | Yes | Label-registry authorship. |
| 14 | `label_templates.created_by` | Slice 1 | `RESTRICT` | Yes | Template authorship. |
| 15 | `orders.punzierung_verified_by` | Slice 2 | `RESTRICT` | Yes | Feingehaltsgesetz / DIN 8238 — 10-year retention, hallmark audit. |
| 16 | `material_usage.user_id` | Slice 2 | `RESTRICT` | Yes | Financial — who consumed which alloy-override. |

### SET NULL — audit row survives, user slot blanked

The `SET NULL` path is preserved for rows where the business value is
the *event* itself (handoff occurred, photo exists, measurement was
taken). `anonymize_user` rewrites these FKs to the sentinel before the
`SET NULL` trigger could fire; the `SET NULL` is defence-in-depth if
somebody bypasses the service-layer anonymise path.

| # | Table.Column | `ondelete` | In `ANONYMIZABLE_FK_TARGETS`? | Justification for `SET NULL` over `RESTRICT` |
|---|---|---|---|---|
| 17 | `customer_measurements.measured_by` | `SET NULL` | Yes | Measurement events must survive goldsmith turnover. |
| 18 | `order_handoffs.from_user_id` | `SET NULL` | Yes | Handoff event survives; who gave away the order is nulled if sentinel path ever bypassed. |
| 19 | `order_handoffs.to_user_id` | `SET NULL` | Yes | Symmetric to 18. |
| 20 | `repair_jobs.received_by` | `SET NULL` | Yes | Intake event survives. |
| 21 | `repair_photos.taken_by` | `SET NULL` | Yes | Photo must survive — evidence trail. |
| 22 | `order_hallmarks.created_by` | `SET NULL` | Yes | Hallmark record must survive (Feingehaltsgesetz). |
| 23 | `valuation_certificates.created_by` | `SET NULL` | Yes | Insurance certificate must survive. |
| 24 | `customer_audit_logs.user_id` | `SET NULL` | Yes | Audit log row survives — that's the whole point. |
| 25 | `order_status_history.changed_by` | `SET NULL` | Yes | Status-transition event survives. |

### CASCADE — user-owned ephemera only

Each CASCADE is reviewed separately. The invariant: **no audit, no
financial, no design-IP column may cascade**.

| # | Table.Column | `ondelete` | In `ANONYMIZABLE_FK_TARGETS`? | Justification for `CASCADE` |
|---|---|---|---|---|
| 26 | `calendar_events.user_id` | `CASCADE` | **No** (intentional) | Personal calendar entries — auto-cleanup is the user-expected behaviour. Not audit, not financial. |
| 27 | `notifications.user_id` | `CASCADE` | **No** (intentional) | Per-user notification inbox. Ephemeral, not audit. |
| 28 | `notification_preferences.user_id` | `CASCADE` | **No** (intentional) | Per-user UI preferences. Ephemeral, not audit. |

---

## Enforcement checklist (for reviewers)

Every PR that introduces a new `ForeignKey("users.id")` must satisfy:

1. [ ] Explicit `ondelete=` clause (never the plain default form).
2. [ ] This document updated with a new row explaining the choice.
3. [ ] If `RESTRICT` or `SET NULL`: column registered in
       `UserService.ANONYMIZABLE_FK_TARGETS`.
4. [ ] If `CASCADE`: justification documented why the column is
       user-owned ephemera (NOT audit / NOT financial / NOT design-IP).
5. [ ] Integration test in `tests/unit/test_user_fk_ondelete_h9.py`
       proves the hard-delete path raises `IntegrityError` (for
       RESTRICT / SET NULL in the audit class).

---

## References

- `src/goldsmith_erp/services/user_service.py` — `ANONYMIZABLE_FK_TARGETS`
  list (lines 67–102).
- `alembic/versions/20260420_h9_explicit_ondelete_restrict.py` — the
  migration that normalised rows 1–11.
- `docs/superpowers/plans/qr-barcode-workflow/V1.1-POST-WAVE5-COMPLIANCE-AUDIT.md`
  §4 — Anna's audit finding H9.
- `docs/superpowers/plans/qr-barcode-workflow/V1.1-ANONYMIZE-USER-CONTRACT.md`
  — the anonymisation pipeline contract.
