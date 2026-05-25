# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Goldsmith ERP** is a specialized ERP system for modern goldsmith businesses, built with a containerized architecture using FastAPI (backend) and React (frontend). The system handles order management, material tracking, time tracking with QR/NFC support, and includes ML-based features for deadline prediction.

**Key Technology Stack:**
- Backend: Python 3.11+, FastAPI 0.115+, SQLAlchemy 2.0+ (async), PostgreSQL 15
- Frontend: React 18.3+, TypeScript, Vite 5.4+, Yarn 4.9+
- Infrastructure: Podman (rootless containers), Redis 7 (pub/sub & caching)
- Migrations: Alembic
- Dependency Management: Poetry (backend), Yarn (frontend)

## Working Style

**Decision-Making Hierarchy:** security > correctness > performance > convenience

**Core Principles:**
- Always ask questions when not 100% sure about requirements or approach
- Fail loudly — never swallow exceptions silently. Log structured errors with context.
- Prefer proven patterns over novel approaches
- Every data display should link to its natural next action (alert → fix, recommendation → do)

**Code Review Standards:**
- All database queries must use selectinload() to prevent N+1
- All user input must pass through Pydantic validation
- All service methods must be async and accept AsyncSession as first parameter
- All new models must be registered with audit logging
- All new endpoints must have @require_permission decorator

## Data Privacy Rules (CRITICAL)

These rules are non-negotiable. AI agents MUST follow them in all code generation.

**Customer PII:**
- Names, addresses, phone numbers, email → MUST be encrypted at rest (EncryptedString type)
- NEVER log customer PII in plaintext — use anonymized IDs in log messages
- Customer data MUST be exportable (GDPR Art. 15) and deletable (Art. 17)

**Design IP:**
- Custom jewelry designs, CAD file references → access-controlled (GOLDSMITH or ADMIN only)
- Design files MUST NOT be included in data exports without explicit consent
- Design descriptions in orders are business-confidential

**Financial Data:**
- Pricing, payment info, material costs → visible only to ADMIN and GOLDSMITH roles
- All financial data access MUST be audit-logged
- Scrap gold (Altgold) records are financial data — same protections as pricing

**Insurance Valuations:**
- Valuation data MUST be encrypted at rest
- Access MUST be logged in audit trail
- Exportable only by ADMIN role

**General Rules:**
- Minimum data principle — don't collect data you don't need
- All PII fields must have a retention policy
- Soft-delete with 30-day grace period, then hard delete
- Anonymize audit logs when user requests erasure (replace with "deleted_user_{hash}")

## Tool Selection Matrix

| Issue Type | Primary Tools | Optional Tools |
|-----------|--------------|----------------|
| Backend bug | Serena + Sequential Thinking | Explore Agent |
| Frontend bug | Read/Edit + Browser | Frontend-Design plugin |
| New API endpoint | Serena + TodoWrite | Sequential Thinking |
| New React component | Read/Edit + TodoWrite | Frontend-Design plugin |
| Security issue | Sequential Thinking + Serena | Security-Guidance plugin |
| Database migration | Serena + Bash | Sequential Thinking |
| GDPR feature | Sequential Thinking + Serena | Compliance agent (@anna) |

## Multi-Agent Workflow

### 6-Phase Pipeline
1. **RESEARCH** — parallel read-only agents investigate codebase + web research
2. **PLAN** — orchestrator synthesizes, detects file conflicts, serializes conflicting work
3. **PLAN REVIEW** — security/compliance/architecture reviewers (complex issues only)
4. **IMPLEMENT** — parallel batches, 1-2 agents per issue, orchestrator monitors
5. **CODE REVIEW** — 1 reviewer per implementation, APPROVED or NEEDS_WORK
6. **COMMIT** — fix findings, stage, commit, close issues

### Parallel Safety Rules
**NEVER parallelize:** migrations, `main.py`, `db/models.py`, `types.ts`, `package.json`
**SAFE to parallelize:** independent routers, independent React components, independent test files

### Agent Personas
10 specialized agents available in `.claude/agents/`:
- @henrik (Technical Lead) — architecture, security, infrastructure
- @anna (Compliance Officer) — GDPR, data protection, legal
- @goldsmith (Goldsmith Expert) — domain knowledge, materials, techniques
- @jason (Design Lead) — UI/UX, brand, accessibility
- @maria (Product Lead) — roadmap, prioritization, MVP scope
- @uxresearch (UX Researcher) — user testing, workshop conditions
- @ops (Operations Lead) — KPIs, analytics, efficiency metrics
- @laura (Behavioral Psychologist) — gamification, engagement
- @community (Community Manager) — internal communication, team coordination
- @retention (Retention Strategist) — customer lifecycle, reorder patterns

### Session Handoff Protocol
When pausing mid-feature:
1. Update planning doc with: what's done, what's next, what's blocking
2. Commit the planning doc
3. Next session: read planning doc first, verify assumptions still hold

## Essential Commands

### Container Operations (Podman)

**Start/Stop Services:**
```bash
make start              # Start all services (backend, frontend, db, redis)
make stop               # Stop all services
make restart            # Restart all services
make logs               # View all logs (tail -f)
make logs-backend       # Backend logs only
make logs-frontend      # Frontend logs only
```

**Alternative - Direct podman-compose:**
```bash
podman-compose -f podman-compose.yml up -d
podman-compose -f podman-compose.yml down
podman-compose -f podman-compose.yml logs -f backend
```

**Important:** This project uses Podman (rootless) instead of Docker for enhanced security. All Docker commands work with Podman via aliases (`alias docker=podman`).

### Backend Development

**Run Backend Locally (outside container):**
```bash
cd src
poetry install
poetry run uvicorn goldsmith_erp.main:app --reload --host 0.0.0.0 --port 8000
```

**Database Migrations:**
```bash
# Run migrations
make migrate
# OR
podman-compose exec backend poetry run alembic upgrade head

# Create new migration
make migrate-create MESSAGE="add new feature"
# OR
podman-compose exec backend poetry run alembic revision --autogenerate -m "your message"

# Rollback one migration
podman-compose exec backend poetry run alembic downgrade -1
```

**Access Backend Shell:**
```bash
make shell-backend
# OR
podman-compose exec backend /bin/bash
```

**Database Access:**
```bash
make shell-db
# OR
podman-compose exec db psql -U user -d goldsmith
```

### Frontend Development

**Run Frontend Locally (outside container):**
```bash
cd frontend
yarn install
yarn dev        # Starts Vite dev server on http://localhost:3000
yarn build      # Production build
yarn preview    # Preview production build
```

### Testing & Code Quality

**Backend Tests:**
```bash
make test                    # Run all tests
make test-cov               # Run tests with coverage report
podman-compose exec backend poetry run pytest -v
podman-compose exec backend poetry run pytest --cov=goldsmith_erp
```

**Linting & Formatting:**
```bash
make lint       # Run all linters (black, isort, pylint, mypy)
make format     # Auto-format code with black and isort
make security   # Security scan with bandit
```

**Individual Tools:**
```bash
# Backend
poetry run black src/                    # Format Python code
poetry run isort src/                    # Sort imports
poetry run pylint src/                   # Lint code
poetry run mypy src/                     # Type checking
poetry run bandit -r src/                # Security scan
```

### Architecture & Code Analysis (TrueCourse)

TrueCourse is an architecture/code-intelligence scanner (tree-sitter static rules + optional
LLM rules) that covers **both** our stacks — Python backend and TS/React frontend. It checks 8
categories: Security, Bugs, Architecture, Code Quality, Performance, Reliability, Database, Style.
Claude Code skills are installed in `.claude/skills/truecourse-*` — invoke them, don't shell out
manually: `/truecourse-analyze`, `/truecourse-list`, `/truecourse-fix`, `/truecourse-hooks`.

**Always invoke the CLI via `npx -y truecourse …`** (without `-y` it hangs on npx's "Ok to proceed?"
prompt). `analyze`/`list` require an explicit `--llm` or `--no-llm` flag. **Never pass `--llm`
without first relaying the token estimate to the user and getting approval.**

**Use `--diff`, not full scans, for day-to-day work.** A full scan of this established codebase
returns thousands of violations (mostly `low`/`medium` Code Quality + Style noise) — not
actionable. The diff workflow surfaces only what *your current changes* introduced:

```bash
npx -y truecourse analyze --no-llm          # full scan → refreshes .truecourse/LATEST.json baseline
npx -y truecourse analyze --diff --no-llm   # compare working tree vs baseline (use this while iterating)
npx -y truecourse list --diff               # show only newly-introduced violations
npx -y truecourse list --severity critical,high   # triage the full set by severity
```

**Workflow guidance:**
- **Triage by severity.** Only `critical`/`high` warrant immediate action. Map findings against our
  `security > correctness > performance > convenience` hierarchy before fixing — TrueCourse Security
  findings (SQL injection, hardcoded secrets, unsafe deserialization) take priority.
- **Baseline lives in git.** `.truecourse/LATEST.json` (baseline), `config.json` (rule toggles),
  and `hooks.yaml` (hook policy) are committable. After a full scan **on `main`**, commit
  `LATEST.json` so fresh clones/worktrees and the pre-commit hook have a baseline. Don't commit it
  from feature branches (the large generated JSON conflicts across PRs).
- **Tame noise at the source.** Disable chronically noisy rules/categories rather than ignoring
  output: `npx -y truecourse rules disable <ruleKey>` or `rules categories --disable <category>`
  (persists to `.truecourse/config.json`). Style/Code-Quality are the usual culprits here.
- **Pre-commit hook is optional and slows commits** (runs `analyze --diff` per commit). If enabled
  via `/truecourse-hooks`, keep `block-on: [critical, high]` and `llm: false` so commits stay fast
  and free. Bypass a blocked commit with `git commit --no-verify` only when justified.
- **Don't treat TrueCourse as ground truth.** It complements, not replaces, our review standards
  (selectinload, Pydantic validation, `@require_permission`, audit logging) and the existing
  linters (black, mypy, bandit). Verify each finding against the actual code before acting.

### Build & Cleanup

```bash
make build              # Rebuild all containers (no cache)
make build-backend      # Rebuild backend only
make build-frontend     # Rebuild frontend only
make clean             # Remove all containers, volumes, images (with confirmation)
```

## Architecture & Code Organization

### Backend Structure

```
src/goldsmith_erp/
├── main.py                 # FastAPI application entry point, WebSocket manager
├── api/
│   └── routers/           # API route handlers
│       ├── auth.py        # Authentication (login, token)
│       ├── orders.py      # Order CRUD operations
│       ├── materials.py   # Material inventory management
│       ├── time_tracking.py  # Time entry start/stop/reporting
│       ├── activities.py  # Activity management for time tracking
│       └── users.py       # User management
├── core/
│   ├── config.py         # Settings (Pydantic BaseSettings)
│   ├── security.py       # JWT token creation/validation, password hashing
│   ├── pubsub.py         # Redis pub/sub for real-time updates
│   └── permissions.py    # Authorization logic
├── db/
│   ├── session.py        # Database connection & async session factory
│   ├── models.py         # SQLAlchemy ORM models (database schema)
│   └── seed_data.py      # Sample data seeding
├── models/               # Pydantic schemas for request/response validation
│   ├── user.py
│   ├── order.py
│   ├── material.py
│   ├── time_entry.py
│   └── activity.py
└── services/            # Business logic layer
    ├── order_service.py
    ├── material_service.py
    ├── time_tracking_service.py
    ├── activity_service.py
    └── user_service.py
```

**Key Patterns:**
- **Service Layer:** Business logic is in `services/`. Services handle DB queries, business rules, and event publishing.
- **Router Layer:** API routes in `api/routers/` handle HTTP requests/responses, call services.
- **Models:** SQLAlchemy models in `db/models.py` define database schema. Pydantic models in `models/` define API schemas.
- **Async Everywhere:** All DB operations use async SQLAlchemy (`AsyncSession`).

### Frontend Structure

```
frontend/src/
├── main.tsx              # Application entry point
├── App.tsx               # Root component with routing
├── api/                  # API client layer
│   ├── client.ts         # Axios instance with auth interceptor
│   ├── auth.ts           # Auth API calls
│   ├── orders.ts         # Order API calls
│   ├── materials.ts      # Material API calls
│   └── users.ts          # User API calls
├── components/           # Reusable React components
│   ├── OrderList.tsx
│   └── ProtectedRoute.tsx
├── contexts/             # React Context for state management
│   ├── AuthContext.tsx   # Authentication state
│   └── OrderContext.tsx  # Order data state
├── layouts/
│   └── MainLayout.tsx    # Main app layout wrapper
└── types.ts             # TypeScript type definitions
```

**State Management:** Currently uses React Context. See ARCHITECTURE_REVIEW.md for recommendations to migrate to Zustand for better scalability.

### Database Schema

**Core Models:**
- `users` - User accounts with email, hashed password, role
- `orders` - Orders with status, customer info, delivery date
- `materials` - Material inventory (gold, silver, gemstones)
- `time_entries` - Time tracking entries with start/end time, duration, activity
- `activities` - Predefined activities for time tracking (e.g., "Polishing", "Stone Setting")
- `interruptions` - Interruptions during time tracking
- `order_photos` - Photo documentation for orders

**Important Relationships:**
- Order → Materials (many-to-many via association table)
- TimeEntry → Order (many-to-one)
- TimeEntry → Activity (many-to-one)
- TimeEntry → User (many-to-one)
- TimeEntry → Interruptions (one-to-many)

### Real-time Updates (WebSockets)

The system uses WebSockets for real-time notifications:

1. **Redis Pub/Sub:** Backend publishes events to Redis channels (`order_updates`, `time_tracking_updates`)
2. **WebSocket Manager:** `main.py` manages WebSocket connections and subscribes to Redis
3. **Broadcasting:** Events from Redis are broadcast to all connected WebSocket clients

**Channels:**
- `order_updates` - Order creation, status changes
- `time_tracking_updates` - Time entry start/stop events

## Critical Architecture Notes

### Security Considerations

**CRITICAL:** Review ARCHITECTURE_REVIEW.md before making changes. Key security issues:

1. **SECRET_KEY:** Must be set via environment variable, not hardcoded. Generate with:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```
   Set in `.env` (never commit this file!)

2. **Authentication:** JWT tokens stored in localStorage (frontend) - see ARCHITECTURE_REVIEW.md for recommendation to use HttpOnly cookies instead.

3. **Input Validation:** All user input must be validated via Pydantic models with appropriate constraints (e.g., `Field(gt=0)` for positive integers).

4. **SQL Injection:** Always use SQLAlchemy ORM - never construct raw SQL with user input.

### Database Best Practices

1. **Async Operations:** Always use `async`/`await` with database operations:
   ```python
   async with AsyncSession() as session:
       result = await session.execute(select(Order))
   ```

2. **Eager Loading:** Avoid N+1 queries by using `selectinload()`:
   ```python
   result = await db.execute(
       select(TimeEntryModel)
       .options(
           selectinload(TimeEntryModel.activity),
           selectinload(TimeEntryModel.user),
           selectinload(TimeEntryModel.order)
       )
   )
   ```

3. **Transactions:** Wrap multi-step operations in transactions with proper error handling:
   ```python
   try:
       async with db.begin():
           # Multiple operations
           db.add(obj)
           await publish_event(...)
   except SQLAlchemyError:
       await db.rollback()
       raise
   ```

### Redis Connection Management

**IMPORTANT:** Redis connections must be properly closed to avoid pool exhaustion. Use context managers:

```python
from core.pubsub import get_redis_client

async with get_redis_client() as redis:
    await redis.publish(channel, message)
```

### WebSocket Event Publishing

When publishing events to WebSockets via Redis:

1. Publish AFTER database commit (to ensure consistency)
2. Use JSON serialization for all event payloads
3. Include `action` and relevant entity IDs in event data

Example:
```python
await publish_event(
    "order_updates",
    json.dumps({
        "action": "create",
        "order_id": order.id,
        "status": order.status
    })
)
```

## Development Workflow

### Making Changes to Backend

1. Create new migration if DB schema changes:
   ```bash
   make migrate-create MESSAGE="descriptive message"
   ```

2. Update Pydantic schemas in `models/` to match DB changes

3. Update service layer in `services/` for business logic

4. Update router in `api/routers/` for new endpoints

5. Test changes:
   ```bash
   make test
   make lint
   ```

6. Check API docs: http://localhost:8000/docs

### Making Changes to Frontend

1. Update TypeScript types in `types.ts` to match backend schemas

2. Update API client in `api/` for new endpoints

3. Update components/contexts as needed

4. Build and verify:
   ```bash
   cd frontend
   yarn build
   ```

### Running Full Stack Locally

**Option 1: All in containers (recommended for production-like testing)**
```bash
make start
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

**Option 2: Backend local, services in containers (faster backend iteration)**
```bash
# Start only DB and Redis
podman-compose up -d db redis

# Run backend locally
cd src
poetry run uvicorn goldsmith_erp.main:app --reload

# Run frontend locally
cd frontend
yarn dev
```

## Common Tasks

### Add New API Endpoint

1. Define Pydantic schema in `models/` for request/response
2. Add service function in appropriate `services/` file
3. Add route handler in appropriate `api/routers/` file
4. Import and include router in `main.py` if new router created
5. Test endpoint via Swagger UI at http://localhost:8000/docs

### Add New Database Table

1. Create SQLAlchemy model in `db/models.py`
2. Create Pydantic schemas in `models/`
3. Generate migration:
   ```bash
   make migrate-create MESSAGE="add new_table"
   ```
4. Review generated migration in `alembic/versions/`
5. Apply migration:
   ```bash
   make migrate
   ```

### Debugging

**Backend Logs:**
```bash
make logs-backend
# Look for stack traces, SQL queries (if DEBUG=true)
```

**Database Queries:**
```bash
# Connect to DB
make shell-db

# Check data
SELECT * FROM orders LIMIT 10;
SELECT * FROM time_entries WHERE user_id = 1;
```

**Redis Inspection:**
```bash
podman-compose exec redis redis-cli
> KEYS *
> GET key_name
> MONITOR  # Watch real-time commands
```

## Testing Strategy

Currently, test coverage is minimal (see ARCHITECTURE_REVIEW.md). When writing tests:

1. Use pytest with async support (`pytest-asyncio`)
2. Use in-memory SQLite for test database
3. Mock external dependencies (Redis, S3)
4. Test service layer independently from routers
5. Write integration tests for critical workflows

Example test structure:
```python
@pytest.mark.asyncio
async def test_create_order(db_session, mock_user):
    order_in = OrderCreate(...)
    order = await OrderService.create_order(db_session, order_in)
    assert order.id is not None
```

## Environment Variables

Required variables in `.env`:

- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `SECRET_KEY` - JWT secret (MUST be changed from default!)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Token expiry (default: 10080 = 7 days)
- `BACKEND_CORS_ORIGINS` - Comma-separated allowed origins
- `DEBUG` - Enable debug mode (`true`/`false`)

See `.env.example` for full list with documentation.

## Deployment Notes

**Podman vs Docker:**
- This project uses Podman for rootless, daemonless containers
- All Docker commands work with Podman (100% compatible API)
- For deployment, use `podman-compose.yml` or `podman-pod.yaml` (Kubernetes-style)

**Systemd Integration:**
```bash
# Generate systemd unit file
podman generate systemd --name goldsmith-erp-pod > /etc/systemd/system/goldsmith-erp.service

# Enable on boot
systemctl enable goldsmith-erp
systemctl start goldsmith-erp
```

**Health Checks:**
- Backend health: http://localhost:8000/health
- Database readiness: Check via `podman-compose ps` or `pg_isready`

## Key Documentation Files

Documentation is organized under `docs/`:

```
docs/
├── feedback/                          # User feedback & ideas
│   └── Ideensammlung.md              # Goldsmith domain expert ideas
├── planning/                          # Roadmaps & status
│   ├── IMPLEMENTATION_PLAN.md        # Development roadmap
│   ├── PROJECT_STATUS_AND_STRATEGY.md # Current status & strategy
│   └── progress/
│       └── PHASE_5.2_PROGRESS.md     # Phase tracking
├── technical/                         # Architecture & specs
│   ├── architecture/
│   │   └── ARCHITECTURE_REVIEW.md    # READ THIS FIRST before major changes!
│   ├── infrastructure/
│   │   ├── INSTALLATION.md           # Platform-specific install guide
│   │   └── PODMAN_MIGRATION.md       # Podman migration & best practices
│   └── specs/
│       ├── FEATURE_SPEC_TIME_TRACKING_ML.md  # Time tracking + ML spec
│       ├── GOLDSMITH_WORKSHOP_REQUIREMENTS.md # Domain requirements
│       └── MVP_ANALYSIS.md           # MVP readiness assessment
└── user-guide/                        # German user documentation
    ├── USER_GETTING_STARTED.md       # Onboarding
    ├── USER_ROLES_PERMISSIONS.md     # RBAC reference
    ├── DAILY_WORKFLOWS.md            # Role-based workflows
    ├── TROUBLESHOOTING.md            # Problem solving
    ├── FAQ.md                        # Common questions
    └── features/                     # Feature guides
        ├── FEATURE_ORDER_MANAGEMENT.md
        ├── FEATURE_MATERIAL_MANAGEMENT.md
        ├── FEATURE_TIME_TRACKING.md
        ├── FEATURE_CUSTOMER_MANAGEMENT.md
        └── FEATURE_USER_MANAGEMENT.md
```

- **README.md** - Project overview, installation, quick start (root)

## Important Notes for AI Assistants

1. **Language:** Documentation is in German, code comments may be in German or English. Code itself follows English naming conventions.

2. **Breaking Changes:** Before making architectural changes, review `docs/technical/architecture/ARCHITECTURE_REVIEW.md` - it contains critical security issues that must be addressed first.

3. **Database Migrations:** Always generate and review migrations before applying. Never modify existing migrations - create new ones.

4. **Code Style:**
   - Backend: Black formatter (line length 88), isort for imports
   - Frontend: Follow existing patterns (no Prettier config currently)
   - Type hints required in Python (mypy strict mode)

5. **Commit Conventions:** Use conventional commits format:
   - `feat:` - New feature
   - `fix:` - Bug fix
   - `docs:` - Documentation
   - `refactor:` - Code refactoring
   - `test:` - Tests
   - `chore:` - Maintenance

6. **Security First:** This is a business-critical ERP system. Always consider:
   - Input validation
   - SQL injection prevention
   - Authentication/authorization
   - Sensitive data handling
   - Rate limiting for expensive operations
