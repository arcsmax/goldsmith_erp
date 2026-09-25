# ADR 2026-09-25: Single-box deployment, migrate-on-boot

Status: accepted. Findings: ARCH-14, ARCH-16
(docs/review/2026-09-25/01-architecture.md).

## Context

Goldsmith ERP targets one goldsmith workshop at a time, run by a
non-technical operator (see CLAUDE.md, "Deployment context"). The production
stack (`podman-compose.prod.yml`) runs Postgres, Redis, the backend, the
frontend and a Caddy TLS proxy as five containers on one host, with the
backend's boot command applying Alembic migrations and the idempotent
reference seed before starting Uvicorn. No load balancer, no multi-region
deployment, no Kubernetes.

The 2026-09-25 architecture review (ARCH-16) noted this decision had never
been written down, so a future contributor — or a hypothetical SaaS pivot —
would have no record of why, and might "fix" it by re-litigating the choice
under time pressure.

## Decision

**Keep the single box.** One workshop, one Postgres instance, one set of
containers on one machine in the workshop's own LAN. This is deliberate, not
a stopgap:

- The product is explicitly single-tenant per deployment (one workshop's
  data, one admin, a handful of goldsmith/viewer accounts) — there is no
  cross-tenant isolation requirement that would justify the operational
  complexity of a distributed deployment.
- A non-technical operator (per CLAUDE.md) needs `./setup.sh` and
  `make prod-status` to be the entire operational surface. Anything that adds
  more moving parts (service discovery, a job queue broker, multi-node
  Postgres) raises the bar for who can run this system.
- Rootless Podman + Caddy already gets most of the security benefit of a
  more complex deployment (TLS termination, non-root containers, no exposed
  ports beyond 80/443) without the operational cost.

**Keep migrate-on-boot for now, as a known, tracked trade-off, not a silent
gap.** The backend's boot command runs `alembic upgrade head` and the
reference seed before serving traffic. This is acceptable for a single box
with one deployment target, but it has two known weaknesses, tracked as
follow-ups rather than blocking this ADR:

- A failed migration crash-loops the API under `restart: unless-stopped`
  instead of failing once with a clear signal.
- There is no automatic pre-migration backup hook (a human must run
  `make backup-now` — since 2026-09-25, `make update` does this
  automatically; see
  [PRODUCTION_DEPLOYMENT.md, Schritt 8](../technical/infrastructure/PRODUCTION_DEPLOYMENT.md)).

The review's recommended fix — a one-shot `migrate` compose service gated by
`depends_on: condition: service_completed_successfully`, running
`scripts/backup.sh` first — is tracked as Wave 5 item W5-12 (ARCH-12,
ARCH-14) and has not landed as of this ADR; it touches `main.py` and
`podman-compose.prod.yml` service wiring, out of scope for a docs-only pass.

## Alternatives considered

- **Multi-tenant SaaS** (one deployment, many workshops): rejected — no
  workshop asked for this, and it would require tenant isolation work
  (row-level security or schema-per-tenant, a control plane, billing) with
  no current customer.
- **Managed Postgres/Redis** (cloud-hosted): rejected for now — a workshop
  LAN deployment with local backups matches the product direction in
  [VISION_AND_ROADMAP_2026-07.md](../planning/VISION_AND_ROADMAP_2026-07.md)
  (no live customer portal, the workshop owns its own data); revisit if a
  hosted offering is ever built.

## Consequences

- Scaling is vertical (bigger box) or per-workshop (one stack per customer),
  never horizontal within one deployment.
- `--workers 2` on Uvicorn means any in-process singleton (the system
  monitor, the WebSocket hub) must coordinate across workers on the same
  Postgres instance (see the advisory-lock pattern used for the system
  monitor, W1-12) rather than assuming a single process.
- A future SaaS pivot is a new ADR, not a silent architecture change.
