# Database Seeding (production vs. demo)

Goldsmith ERP has four seed paths. Only **two** are safe for a real production
database; the other two are development/demo tools and must never touch prod.

| Path | Command | Creates | Prod-safe? |
|------|---------|---------|:----------:|
| **Admin user** | `scripts/create-admin.py` | One ADMIN user (password from `ADMIN_PASSWORD` env) | ✅ Yes |
| **Reference data** | `python -m goldsmith_erp.db.reference_seed` | 15 standard activities + standard materials catalogue | ✅ Yes |
| Demo showcase | `scripts/seed_demo.py` / `make seed-demo` | Fake staff (shared password `demo2026!`), 10 customers, orders, quotes, invoices, consultations, … | ❌ **Demo only** |
| Dev sample data | `goldsmith_erp.db.seed_data` / `make seed` | Sample users/customers/orders (weak dev passwords) | ❌ **Dev only** |

A fresh production install needs exactly two things seeded: **one admin user**
(so someone can log in) and the **reference data** (so time-tracking and
material selection have their standard lookups). Nothing else — no fake staff,
no fake customers, no demo passwords.

## The reference seed (`db/reference_seed.py`)

This is the one seed path wired into the production boot sequence.

**Contract — it NEVER creates:**

- users (no demo staff, no shared passwords)
- customers (no PII)
- orders / quotes / invoices / consultations / repairs (no business data)

**It creates only:**

- the **15 standard goldsmith activities** — the time-tracking catalogue,
  including the V1.3 `is_billable` / `hourly_rate` rubric the estimator reads;
- a **standard materials catalogue** — the common alloys and consumables a
  workshop starts with, at nominal reference prices and **stock 0** (real
  inventory is operational data the workshop enters itself).

**Idempotent — this is the point.** Every row is matched by its natural key
(activity → `name` + `category`, material → `name`) and inserted only when
absent (upsert-or-skip). Re-running is a no-op that reports zero created, so it
is safe to run on **every boot and upgrade**. A defence-in-depth check in the
standalone runner aborts loudly if the seed ever changed the User/Customer row
count — the contract can't silently rot.

The reference seed is also the **single source of truth** for the standard
activity list: `scripts/seed_demo.py` composes on top of it (its
`seed_activities` / `seed_materials` delegate to the reference seed) instead of
re-declaring the list, so the demo and production catalogues can never drift.

## How production uses it

### 1. Automatic on boot (default)

The production backend container runs the reference seed **after migrations,
before serving** (`podman-compose.prod.yml`):

```bash
alembic upgrade head \
  && python -m goldsmith_erp.db.reference_seed \
  && uvicorn goldsmith_erp.main:app ...
```

Because the seed is idempotent, this is safe on every restart — the first boot
populates the catalogue, later boots are no-ops.

### 2. The `SEED_REFERENCE_DATA` gate

The boot step honours the `SEED_REFERENCE_DATA` environment variable
(**default: `true`**). Set it to `false` / `0` / `no` / `off` in
`.env.production` to turn the boot step into a clean no-op exit (e.g. if you
manage reference data manually or restore it from a backup):

```dotenv
# .env.production
SEED_REFERENCE_DATA=true   # default — seed reference data on boot
```

### 3. Manual invocation

Seed on demand against the running production stack:

```bash
make seed-production
# → podman-compose ... exec backend python -m goldsmith_erp.db.reference_seed
```

Or directly inside the backend container:

```bash
python -m goldsmith_erp.db.reference_seed
```

Both read `DATABASE_URL` from the app config like the rest of the backend.

## First-boot production checklist

```bash
# 1. Start the production stack (runs migrations + reference seed automatically)
make prod-start

# 2. Create the first admin user (password from env, never on the command line)
ADMIN_PASSWORD='<strong-password>' \
  podman-compose --env-file .env.production -f podman-compose.prod.yml \
  exec backend poetry run python scripts/create-admin.py \
    --email admin@your-workshop.de --first-name Max --last-name Mustermann

# 3. Log in and go — the 15 activities + material catalogue are already there.
```

Do **not** run `make seed-demo` or `make seed` against a production database:
they create fake users with the shared demo password and fake customer PII.

## See also

- `scripts/create-admin.py` — the prod-safe admin bootstrap.
- `src/goldsmith_erp/db/reference_seed.py` — the reference seed itself.
- `PRODUCTION_TLS.md` — the TLS reverse proxy that fronts the stack.
