# Changelog

This project does not yet follow a strict Keep-a-Changelog release cadence
(no tagged releases). This file tracks notable multi-wave efforts; for
day-to-day commits see `git log`.

## 2026-09-25 audit branch (`audit/2026-09-fixes`)

A full 8-report re-audit of the codebase (`docs/review/2026-09-25/`, 212
findings across the eight review docs) produced an 83-item fix plan across
7 waves (`docs/review/2026-09-25/MASTER-FIX-PLAN.md`). Final state on this
branch (see [PROGRESS.md](docs/review/2026-09-25/PROGRESS.md) for the full,
evidence-based account — commits, test counts, and open follow-ups per
item):

- **Findings:** 108 fixed, 47 partial, 57 open of 212 total
  (`docs/review/2026-09-25/FINDINGS-REGISTER.md`).
- **Waves W1–W7:** W1 (stop the bleeding — security, money, GDPR
  correctness) done; W2 (product/domain top-15) done/complete; W3
  (platform) mostly landed; W4 (design system) has its primitive library
  plus every page group migrated, with some follow-ups open; W5
  (operations/CI/compliance docs) mostly untouched this pass, with the
  W5-09 TLS gap open; W6 (target architecture) has its jobs spine done and
  media_assets/models-split partial; W7 (backlog/hygiene) partial, with
  W7-01 through W7-05 still open. Full per-wave detail: MASTER-FIX-PLAN.md
  section 0.
- **Final verified gate on the pushed head:** backend 4408 tests passed,
  frontend 1092 tests passed, lint 0 errors, hex-literal ratchet 2113 → 612,
  `types-check` and `lint-imports` clean.
- Integration branch `audit/2026-09-fixes`; **PR #51 is open as a draft** —
  the review vehicle for this work.

Several product/compliance decisions were made under an explicit,
documented assumption pending sign-off by their real owner (Anne, Max, a
Steuerberater or a lawyer) — see PROGRESS.md section (b), "Decisions taken
during execution". Treat this branch as a release candidate only after
those are confirmed and the remaining open/partial items above are closed.
