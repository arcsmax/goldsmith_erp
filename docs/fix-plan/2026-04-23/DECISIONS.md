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

## 2026-04-23 — A4 — Compose validator substitution + env-file isolation

**Question:** How to run the A4 acceptance tests when `podman-compose` is not
installed in the executing agent's environment, and how to prevent the repo's
own `.env` from masking the "POSTGRES_PASSWORD unset" test?

**Options considered:**
1. Require podman-compose — blocks CI on environments that only have Docker
2. Fall back to `docker compose` (v2) — identical compose-file YAML validator
   for the two guarantees A4 cares about (required-variable `:?` interpolation
   and port-mapping host_ip). Spec explicitly permits this.
3. Skip the tests if podman-compose is missing — defeats the TDD bar

**Decision:** Option 2 — `scripts/test-compose-validation.sh` prefers
`podman-compose`, falls back to `docker compose`, then `docker-compose`
(classic), then SKIP. Additional nuance: `docker compose` auto-loads `.env`,
which supplies a real POSTGRES_PASSWORD and would silently defeat Test 1.
The script passes `--env-file /dev/null` to the docker-family validators
(podman-compose doesn't need it — it doesn't auto-load `.env` the same way)
so the test measures the compose file on its own.

**Rationale:** The two behaviours A4 enforces — required-variable rejection
and loopback port binding — are pure compose-file syntax, validated identically
by either tool. Coupling the test to the presence of podman-compose buys
nothing and costs portability.

**Port override nuance:** Used the optional pattern from the spec's "Open
questions" section — `${DB_HOST_IP:-127.0.0.1}:${DB_PORT:-5432}:5432` — so a
developer on a remote dev box can opt in to LAN access without editing the
compose file.

**Decided by:** orchestrator default, consistent with spec's escalation clause.

---

<!-- Append new decisions below as they come up. -->
