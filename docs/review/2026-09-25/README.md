# Audit 2026-09-25: Goldsmith ERP (`main` @ 73fff19)

Full audit of the product, architecture, security, correctness, frontend, testing and operations,
GDPR and design, with a fix programme for AI coding agents working in parallel worktrees.

## Reading order

1. [00-SUMMARY.md](00-SUMMARY.md): verdicts, the 12 findings that matter most, scorecards, what to keep, July status, open decisions.
2. [MASTER-FIX-PLAN.md](MASTER-FIX-PLAN.md): how to execute: branching, TDD, adversarial rounds, 83 fix items in 7 waves, Wave 1 hand-off packets, dependencies, review checkpoints, decisions.
3. [FINDINGS-REGISTER.md](FINDINGS-REGISTER.md): one row per finding (212), corrected severity, wave, status, fix item. The tracking artifact; update it as items land.
4. [PROGRESS.md](PROGRESS.md): the dated changelog, decisions taken (and needing sign-off), and the open-follow-ups list — the evidence behind the counts in 00-SUMMARY.md.
5. The eight reviews, for evidence (`path:line`) and full reasoning:

| File | Topic |
|---|---|
| [01-architecture.md](01-architecture.md) | Layering, domain model, real-time, target architecture (ARCH-) |
| [02-security.md](02-security.md) | Route inventory, security findings, dependency audit (SEC-, SEC-F) |
| [03-backend-correctness.md](03-backend-correctness.md) | Money path, time tracking, data model (BE-) |
| [04-frontend-code-and-flows.md](04-frontend-code-and-flows.md) | Frontend code and the five UX flows (FE-) |
| [05-domain-product-fit.md](05-domain-product-fit.md) | Goldsmith workflows, top-15 recommendations, feedback options (DOM-) |
| [06-testing-ci-ops.md](06-testing-ci-ops.md) | Tests, CI, deployment and operations (OPS-) |
| [07-gdpr-privacy.md](07-gdpr-privacy.md) | Privacy rules, encryption, retention, feedback-channel preconditions (GDPR-) |
| [08-design-investigation.md](08-design-investigation.md) | Tokens, components, accessibility, improvement plan (DES- = I-01..I-30) |

Related: `docs/design/UI-UX-PLAYBOOK.md` (design rules; Wave 4 follows its migration plan) and the
previous audit `docs/review/2026-07-26/production-readiness.md` (its verdict is stale). The
[live/](live/) subfolder holds LIVE-VERIFICATION-1.md and LIVE-VERIFICATION-2.md, the two
on-the-ground verification passes (Playwright, real Postgres/Redis) against a running stack.

## Verification method

Eleven audit agents wrote the eight reviews read-only against `main` @ 73fff19. Three adversarial
verifiers then re-opened every CRITICAL and HIGH finding (plus impact-H domain gaps and four design
claims) at the cited lines, reproduced the cheap ones (arithmetic, validation errors, a scratch
pytest, `Settings()` boot, contrast ratios, build exit codes), and tried to refute them: 62 confirmed,
1 partial, 0 refuted. Verifier reports: `.orchestrated-fable/ux-erp-audit-2026-09/verify-*.md`. Each
review ends with a "Verification (2026-09-25)" section; corrected severities (SEC-02 and BE-05 to
CRITICAL, FE-13 to HIGH) override the originals everywhere.
