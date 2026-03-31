# Branch Triage: Selective Merge Plan

**Branch:** `origin/claude/goldsmith-erp-analysis-011CUrFXzYqpBrcBm8yFhc4h`
**Date:** 2026-03-31
**Strategy:** Selective cherry-pick (NOT full merge)

## Why Not Full Merge?

The branch makes sweeping changes that would be destructive to main:
- Deletes Containerfile, Makefile, podman-compose.yml, podman-pod.yaml, setup-podman.sh
- Deletes the entire `.claude/` directory (agents, hooks, settings)
- Downgrades all Python dependencies (pytest 8→7, black 24→23, pylint 3→2, etc.)
- Rewrites all 10 Alembic migrations into 3 new clean ones (destroys history)
- Removes many routers (activities, comments, health, metal_inventory, scrap_gold, time_tracking, users)
- Removes many services, models, and utility files from main
- Breaks CI/CD YAML (removes frontend job, downgrades actions versions)
- Deletes entire docs tree (feedback/, planning/, technical/, user-guide/) and replaces with flat structure
- Removes frontend tests, contexts, and ~60 components/pages

## KEEP (cherry-pick these new files)

### New Middleware
- `src/goldsmith_erp/middleware/audit_logging.py` (384 lines) — new, added by branch
- `src/goldsmith_erp/middleware/rate_limiting.py` (396 lines) — new, added by branch
- `src/goldsmith_erp/middleware/security_headers.py` — modified/expanded on branch

### New Repository Pattern
- `src/goldsmith_erp/db/repositories/__init__.py`
- `src/goldsmith_erp/db/repositories/base.py`
- `src/goldsmith_erp/db/repositories/customer.py` (724 lines)
- `src/goldsmith_erp/db/repositories/material.py` (220 lines)
- `src/goldsmith_erp/db/repositories/order.py` (808 lines)

### New Customer Module
- `src/goldsmith_erp/api/routers/customers.py` — modified on branch (substantial rewrite)
- `src/goldsmith_erp/models/customer.py` (563 lines) — modified on branch
- `src/goldsmith_erp/services/customer_service.py` (1001 lines) — modified on branch

### New Core
- `src/goldsmith_erp/core/encryption.py` — new, added by branch

### New Tests
- `tests/test_customer_gdpr.py` (363 lines) — new, added by branch
- `tests/test_customer_repository.py` (392 lines) — new, added by branch
- `tests/test_basic_setup.py` (140 lines) — new, added by branch

### New Scripts
- `scripts/seed_data.py` (689 lines) — new, added by branch
- `scripts/migrate_users_to_customers.py` (413 lines) — new, added by branch

### New Documentation (flat structure — store under docs/superpowers/specs/ or similar)
- `docs/ARCHITECTURE.md` (1266 lines)
- `docs/GDPR_COMPLIANCE.md` (1029 lines)
- `docs/TESTING.md` (579 lines)
- `docs/WORKFLOWS.md` (875 lines)
- `docs/DEPLOYMENT.md` (602 lines)
- `docs/DEPLOYMENT_LOCAL.md` (512 lines)
- `docs/ROADMAP.md` (1097 lines)

### New Frontend Layout Components
- `frontend/src/components/layout/Header.tsx` + `Header.css`
- `frontend/src/components/layout/MainLayout.tsx` + `MainLayout.css`
- `frontend/src/components/layout/Sidebar.tsx` + `Sidebar.css`

### New Frontend Store
- `frontend/src/store/authStore.ts` — Zustand-based auth store (replaces Context)

### New Frontend Pages (Customer CRUD)
- `frontend/src/pages/customers/CustomerList.tsx` + `CustomerList.css`
- `frontend/src/pages/customers/CustomerDetail.tsx` + `CustomerDetail.css`
- `frontend/src/pages/customers/CustomerForm.tsx` + `CustomerForm.css`
- `frontend/src/pages/customers/ConsentManagement.tsx` + `ConsentManagement.css`

### New Frontend Pages (Material CRUD)
- `frontend/src/pages/materials/MaterialList.tsx` + `MaterialList.css`
- `frontend/src/pages/materials/MaterialDetail.tsx` + `MaterialDetail.css`
- `frontend/src/pages/materials/MaterialForm.tsx` + `MaterialForm.css`

### New Frontend API Client
- `frontend/src/lib/api/client.ts`
- `frontend/src/lib/api/auth.ts`
- `frontend/src/lib/api/customers.ts`
- `frontend/src/lib/api/materials.ts`

### New Frontend Pages (simplified replacements)
- `frontend/src/pages/Dashboard.tsx` + `Dashboard.css`
- `frontend/src/pages/Login.tsx`

### Misc Frontend Additions
- `frontend/.env.example`
- `frontend/src/vite-env.d.ts`
- `frontend/tsconfig.json`
- `frontend/tsconfig.node.json`
- `pytest.ini`

## SKIP (keep main's versions)

### Infrastructure (branch deletes these — main needs them)
- `Containerfile` — branch deletes
- `Makefile` — branch deletes
- `podman-compose.yml` — branch deletes
- `podman-pod.yaml` — branch deletes
- `setup-podman.sh` — branch deletes

### Claude Configuration (branch deletes these)
- `.claude/agents/` — branch deletes all 10 agent definitions
- `.claude/hooks/` — branch deletes session-start.js and statusline.js
- `.claude/settings.json` — branch deletes
- `CLAUDE.md` — branch deletes (keep main's version)

### Dependencies (branch downgrades these)
- `pyproject.toml` — keep main's dependency versions
- `poetry.lock` — keep main's lock file

### CI/CD (branch version is broken)
- `.github/workflows/ci.yml` — already rewritten in Task A1.1; branch version removes frontend job

### Migrations (branch rewrites history — too risky)
- `alembic/versions/001_initial_schema.py` — branch replacement, skip
- `alembic/versions/002_gdpr_compliance.py` — branch replacement, skip
- `alembic/versions/003_order_management.py` — branch replacement, skip
- Keep all existing migration files in `alembic/versions/`

### Security config (branch deletes)
- `.gitleaks.toml` — branch deletes; keep for secret scanning
- `.pre-commit-config.yaml` — branch deletes; keep for hooks

### Committed secrets
- `.env` — branch adds a `.env` file (contains secrets, NEVER commit); skip entirely

### Existing docs tree (branch wipes and replaces)
- `docs/feedback/` — keep all files
- `docs/planning/` — keep all files
- `docs/technical/` — keep all files
- `docs/user-guide/` — keep all files
- `docs/INDEX.md` — keep

### Phase-specific docs from branch (historical, redundant given main's docs)
- `docs/PHASE_1.6_COMPLETE.md`
- `docs/PHASE_1.7_COMPLETE.md`
- `docs/PHASE_1.8_PLAN.md`
- `docs/PHASE_1.8_TESTING_PLAN.md`
- `docs/CURRENT_STATE.md`
- `docs/IMPLEMENTATION_PLAN.md` (branch version — conflicts with existing)

### Frontend files that branch deletes from main (DO NOT remove from main)
- `frontend/src/api/` — all files (activities, auth, calendar, client, comments, customers, materials, metal-inventory, orders, scrap-gold, time-tracking, users)
- `frontend/src/components/` — ActivityPicker, CommentsTab, CustomerFormModal, LocationPicker, QuickActionModal, ThemeToggle, TimeTrackingTab, TimerWidget, dashboard/*, materials/*, orders/*, scrap-gold/*, time-tracking/*
- `frontend/src/contexts/` — AuthContext, OrderContext, ThemeContext, TimeTrackingContext
- `frontend/src/layouts/MainLayout.tsx`
- `frontend/src/pages/` — CalendarPage, CustomersPage, DashboardPage, LoginPage, MaterialsPage, MetalInventoryPage, OrderDetailPage, OrdersPage, RegisterPage, ScannerPage, TimeTrackingPage, UsersPage
- `frontend/src/styles/` — all existing style files
- `frontend/src/test/` — mocks, setup
- `frontend/src/utils/` — dateHelpers, formatters

## REVIEW (merge carefully, case by case)

### Core backend files with significant changes
- `src/goldsmith_erp/main.py` — branch reorganizes router imports; review for new customer router registration
- `src/goldsmith_erp/db/models.py` — branch refactors model definitions; review for Customer model additions
- `src/goldsmith_erp/db/session.py` — minor changes; review for async session improvements
- `src/goldsmith_erp/core/config.py` — may have new env vars for GDPR/encryption features
- `src/goldsmith_erp/api/deps.py` — may have new dependency functions
- `src/goldsmith_erp/api/routers/__init__.py` — router registration changes
- `src/goldsmith_erp/core/pubsub.py` — minor changes; review for correctness
- `src/goldsmith_erp/middleware/__init__.py` — may register new middleware

### Backend services with modifications
- `src/goldsmith_erp/services/material_service.py` — may have improvements worth extracting
- `src/goldsmith_erp/services/order_service.py` — may have improvements worth extracting

### Frontend modified files (not deleted, but changed)
- `frontend/src/App.tsx` — routing restructured for new pages; review carefully
- `frontend/src/main.tsx` — entry point changes; review for store initialization
- `frontend/src/types.ts` — type additions for customer/material CRUD
- `frontend/src/components/ProtectedRoute.tsx` — may use new auth store
- `frontend/src/index.css` — global style changes
- `frontend/vite.config.ts` — build config changes
- `frontend/package.json` — dependency additions (Zustand, etc.)
- `frontend/yarn.lock` — updated for new deps

### Configuration
- `.env.example` — branch may add new environment variables needed for encryption/GDPR
- `tests/conftest.py` — branch refactors test fixtures; review for improvements
- `docker-compose.yml` — branch modifies service definitions; verify compatibility
- `alembic/env.py` — minor changes to migration environment
- `.gitignore` — branch modifies; review for new entries

### README.md
- Branch rewrites README significantly; review for any useful additions to incorporate
