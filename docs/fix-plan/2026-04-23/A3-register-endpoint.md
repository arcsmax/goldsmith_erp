# A3 — Lock down `/users/register`

**Item:** A3 · **Severity:** P0 · **Effort:** S · **Owner:** BE + SEC · **Status:** 🛑 BLOCKED
**Blocked-by:** (1) product decision on registration policy; (2) A2 committed (to share canonical `require_permission`).

## Context

`middleware/auth_required.py:29` whitelists `/api/v1/users/register` as PUBLIC. `api/routers/users.py:19-43` accepts any `(email, password)` with no invitation token, no captcha, no admin approval. 400 "Email already registered" is a free email-enumeration oracle. An outside attacker can spray the endpoint, verify addresses, and create VIEWER accounts on an internal workshop ERP.

## Decision needed from user (before this item unblocks)

The fix depends on what "registration" should become. Options the orchestrator will present:

1. **ADMIN-invitation-only** (recommended, matches CLAUDE.md posture) — remove from PUBLIC_PATHS; only an authenticated ADMIN can call `/users/register` or a renamed `/users` POST to create a user. Add `PATCH /users/{id}/role` guarded by `USER_MANAGE` for role changes.
2. **Invitation-token gate** — keep public URL; require a one-use token (admin pre-generates, emails the invitee). Mid-complexity.
3. **Public with strong rate-limit + captcha** — only if the product intent is "anyone can sign up". Most work, and inconsistent with CLAUDE.md.

## Goal (once decision lands)

The endpoint is no longer anonymously exploitable; the email-enumeration oracle is removed (return 201 regardless of whether the email existed, or return a generic 200 with "if your address is eligible you will receive…" semantics).

## Files (likely, pending decision)

- `src/goldsmith_erp/middleware/auth_required.py` — remove `/users/register` from `PUBLIC_PATHS`.
- `src/goldsmith_erp/api/routers/users.py` — add `@require_permission(Permission.USER_MANAGE)` (or `USER_CREATE`) if admin-only; OR add invitation-token verification.
- `tests/integration/test_auth_flow.py` or new file — assert 401/403 on unauthenticated register; assert enumeration oracle gone.

## Acceptance criteria (once unblocked)

- [ ] Unauthenticated POST to register → 401 (if admin-only) OR 403 (if token-gated and missing).
- [ ] Admin-authenticated POST → 201 as today.
- [ ] Duplicate-email response identical to unknown-email response (no oracle).
- [ ] Existing admin flows still work; `create_user_by_admin` in `user_service.py` remains the backend.

## Next step

Orchestrator will present the decision options to the user via AskUserQuestion when Wave 2 begins, record the choice in `DECISIONS.md`, then expand this spec into the TDD implementation plan.
