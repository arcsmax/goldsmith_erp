# Changelog

This project does not yet follow a strict Keep-a-Changelog release cadence
(no tagged releases). This file tracks notable multi-wave efforts; for
day-to-day commits see `git log`.

## 2026-09-25 audit branch (`audit/2026-09-fixes`)

A full 8-report re-audit of the codebase (`docs/review/2026-09-25/`, 212
findings) produced an 83-item fix plan across 7 waves
(`docs/review/2026-09-25/MASTER-FIX-PLAN.md`). Status as of this entry (see
[PROGRESS.md](docs/review/2026-09-25/PROGRESS.md) for the full, evidence-based
account — commits, test counts, and open follow-ups per item):

- **Wave 1 (Stop the bleeding — security, money, GDPR correctness):**
  functionally complete, 20/20 items landed (9 partial, each with a
  documented remainder). Highlights: placeholder `SECRET_KEY`/salt rejected
  in production; hardened `setup.sh` → `.env.production` path with security
  headers and a real client-IP rate-limit key; a role-projection sweep so
  VIEWER no longer receives financial/design data; a consent store gating
  health/allergy data; invoice status locked to explicit actions with an
  immutable snapshot at send time; invoices bill the agreed price instead of
  double-charging VAT; Altgold valued and credited correctly; one customer
  email per real event instead of a notification-storm; a single running
  timer per user; EXIF-stripped, bomb-bounded photo uploads; credential
  changes now require the current password.
- **Wave 2 (product/domain top-15):** partial — live realtime fan-out and a
  corrected metal-price feed landed early; order photo upload and scanner
  deep-links, the "Heute" dashboard (overdue-first, customer-pending lanes),
  repair customer-updates, quote "Versenden" plus consultation-to-quote-to-
  order data carry-through, and the order lifecycle/status-history/5-tab
  order page have since landed on top of Wave 1. Not yet started as of this
  entry: §14 UStG invoice numbering/Storno (W2-04), gemstone/order-type
  intake (W2-06), hallmark vocabulary gating (W2-09), customers without email
  (W2-10), the handover-report PDF (W2-11), repair-intake UX (W2-12),
  interruption-aware time tracking (W2-14), and the Altgold Ankaufsbuch
  (W2-16) — see MASTER-FIX-PLAN.md's Wave 2 table and PROGRESS.md for the
  authoritative, evidence-based item-by-item state; this file summarises, it
  does not replace that record.
- **Waves 3–7 (platform, design system, ops/CI/compliance docs, target
  architecture, backlog):** the critical/high Dependabot backlog was cleared
  (W5-01), and CI caching, advisory dependency/security audits, ruff, a
  nightly heavy-E2E job, frontend coverage tooling, the compliance systemd
  timer installer, encrypted backups with erasure-ledger replay, the
  retention sweep, a completed Art. 15 export, and the Art. 30/TOMs/Art. 13/
  breach-runbook compliance documents have landed. A generated OpenAPI
  contract, a `DomainError`/`Page[T]` API envelope, and the initial design
  tokens (Wave 4) have also landed. This pass additionally closed the
  documentation-only remainder of Wave 5/7 (OPS-08, OPS-14, ARCH-16, SEC-F8,
  SEC-F10 — see the commits following this entry). Remaining Wave 5/7 items
  that touch application code are tracked in MASTER-FIX-PLAN.md's item
  tables.

Several product/compliance decisions were made under an explicit,
documented assumption pending sign-off by their real owner (Anne, Max, a
Steuerberater or a lawyer) — see PROGRESS.md section (b), "Decisions taken
during execution". Treat this branch as a release candidate only after
those are confirmed and the H-severity pre-go-live follow-ups (PG-only
verification, the `Order.price` NET-semantics data review, the W1-17
open-timer migration pre-check) are closed.
