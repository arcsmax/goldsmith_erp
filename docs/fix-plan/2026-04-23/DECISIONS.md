# Decisions Log — Week 1 Fix Plan
Running log of product / judgment-call decisions made during fix execution. Every time an implementation question has a non-obvious answer, we record it here so the trail stays auditable.

**Format per decision:**
```
## YYYY-MM-DD — <item ID> — <short title>
**Question:** ...
**Options considered:** ...
**Decision:** ...
**Rationale:** ...
**Decided by:** <user / orchestrator default>
```

---

## 2026-04-23 — (meta) — Scope, branch, testing, decision model

**Question:** How broad is the Week-1 fix effort, where does it land, how are product calls handled, what's the testing bar?

**Decision:**
- **Scope:** Complete Week 1 (Groups A + B + F) from `docs/review/2026-04-23/FIX-PLAN.md`
- **Branch:** `code-review-fixes-2026-04-23` off main `a6a5d73`
- **Product decisions:** stop and ask one-by-one (no batching)
- **Testing:** TDD per fix — failing test before implementation

**Decided by:** user, via AskUserQuestion round on 2026-04-23.

---

## 2026-04-23 — F4 — Defer un-skipping encryption tests

**Question:** Should F4 (un-skip 7 encryption/GDPR tests) be done in Week 1?

**Options considered:**
1. Un-skip now — they'll fail, because encryption infra (EncryptedString TypeDecorator, PII_FIELDS expansion) is a Group-C Week-2 fix
2. Delete as superseded — but we haven't yet verified that any post-Slice-2 encryption tests actually cover the same surface
3. Defer to Week 2, alongside Group C

**Decision:** Option 3 — defer to Week 2. Status `🛑 blocked` on Group C.

**Rationale:** Un-skipping now = red CI with no fix available this week. Deleting blind = risk losing unique coverage. Deferred is the honest state.

**Decided by:** orchestrator default (matches "TDD per fix" — no point testing infra that doesn't exist yet).

---

<!-- Append new decisions below as they come up. -->
