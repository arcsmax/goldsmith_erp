# Goldsmith ERP - Project Status, Strategy & State-of-the-Art Approach

**Analysis Date:** 2026-03-31
**Analyzed By:** 8 parallel deep-analysis agents
**Scope:** Full codebase, all documentation, git history, infrastructure, security

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Project Status](#2-current-project-status)
3. [What We're Working With](#3-what-were-working-with)
4. [Existing Specs & Documentation](#4-existing-specs--documentation)
5. [Critical Findings](#5-critical-findings)
6. [Unmerged Work - Immediate Action Required](#6-unmerged-work--immediate-action-required)
7. [What to Focus on Next](#7-what-to-focus-on-next)
8. [State-of-the-Art Approach](#8-state-of-the-art-approach)
9. [What Documents to Create](#9-what-documents-to-create)
10. [Goldsmith Domain Expert Feedback (Ideensammlung)](#10-goldsmith-domain-expert-feedback-ideensammlung)
11. [Maturity Scorecard](#11-maturity-scorecard)
12. [Recommended Roadmap](#12-recommended-roadmap)

---

## 1. Executive Summary

Goldsmith ERP is a **specialized ERP system for goldsmith businesses** built on a modern stack (FastAPI + React + PostgreSQL + Redis). The project has a **solid foundation** with 55 API endpoints, 13 database models, comprehensive RBAC, and a well-structured frontend. However, **development has been dormant since November 2025** (~4 months), and there is **significant unmerged work** on a branch that includes CRUD pages, 155+ tests, and a security audit.

### Key Numbers

| Metric | Value |
|--------|-------|
| Backend endpoints | 55 across 8 routers |
| Database models | 13 with full relationships |
| Frontend pages | 8 pages, 10 components |
| Frontend API methods | 47 across 7 API modules |
| Test coverage (backend) | ~0% (conftest only) |
| Test coverage (frontend) | 130+ tests (time-tracking focused) |
| Git commits | 99 total (76% AI-generated) |
| Last commit | November 19, 2025 |
| Dormancy period | ~4 months |
| Unmerged branch commits | 25 (includes CRUD, tests, security audit) |

### Bottom Line

The project is **~60% toward a usable MVP** with excellent architecture but critical gaps in testing, some frontend CRUD operations, and production hardening. The most immediate action is **evaluating and merging the unmerged branch** which contains substantial completed work.

---

## 2. Current Project Status

### Phase Completion Overview

| Phase | Description | Status | Completion |
|-------|-------------|--------|------------|
| Phase 1 | Critical bug fixes | COMPLETE | 100% |
| Phase 2 | User & Material Management | COMPLETE | 100% |
| Phase 3 | Frontend Architecture (React Router) | COMPLETE | 100% |
| Phase 4 | Tab-Memory + QR/NFC Scanner | COMPLETE | 100% |
| Phase 5.1 | Time Tracking Backend | COMPLETE | 100% |
| Phase 5.2 | Time Tracking Frontend | 90% COMPLETE | 90% |
| Phase 5.3 | Integration & Testing | NOT STARTED | 0% |
| Phase 6 | Calendar & Planning | NOT STARTED | 0% |
| Phase 7 | Analytics & Reporting | NOT STARTED | 0% |
| Phase 8 | ML Preparation | NOT STARTED | 0% |

### What Works Right Now

**Backend (Fully Functional):**
- Authentication with JWT + HttpOnly cookies + rate limiting
- RBAC with 30 granular permissions across 3 roles (admin/goldsmith/viewer)
- Complete Order CRUD with status management
- Customer CRM with advanced search, filtering, and analytics
- Material inventory with stock management and alerts
- Time tracking with start/stop, interruptions, quality ratings
- 15 predefined activities with usage statistics
- Cost calculation with material + labor + gemstone pricing
- Real-time WebSocket events via Redis pub/sub
- Health checks (Kubernetes-ready: liveness, readiness, startup)
- Structured JSON logging with request tracing

**Frontend (Partially Functional):**
- Login/registration flow
- Dashboard with order stats and low stock alerts
- Order detail page with 6-tab interface
- Time tracking components (ActivityPicker, TimerWidget, QuickActionModal)
- QR/NFC scanner interface with quick actions
- Global timer widget (sticky, always visible)
- API client layer covering all 55 backend endpoints
- 3 React contexts (Auth, Order, TimeTracking)
- 130+ frontend tests (Vitest + MSW)

**Infrastructure:**
- Podman rootless containers (security-first)
- podman-compose + Kubernetes-style pod definitions
- Comprehensive Makefile (30+ targets)
- 6 Alembic migrations
- Database seed data
- Setup automation script

### What Doesn't Work Yet

- **Frontend CRUD buttons** - Create/Edit/Delete for Orders, Materials, and Users pages have buttons but no handlers
- **Location change API** - ScannerPage TODO (console.log only)
- **Frontend role-based routing** - All authenticated users see all nav items
- **Frontend role display** - UserType interface missing role field
- **CI/CD pipeline** - GitHub Actions YAML has syntax error (broken)
- **Container health checks** - Missing curl/wget in container images
- **Metal price API** - Hardcoded at 45 EUR/g (Phase 2.3 TODO)

---

## 3. What We're Working With

### Technology Stack Assessment

| Layer | Technology | Version | Assessment |
|-------|-----------|---------|------------|
| Backend | Python + FastAPI | 3.11+ / 0.115+ | Excellent choice, async-first |
| ORM | SQLAlchemy | 2.0+ (async) | Modern, well-configured |
| Database | PostgreSQL | 15 | Solid, production-grade |
| Cache/PubSub | Redis | 7 | Used for pub/sub only (caching gap) |
| Frontend | React + TypeScript | 18.3+ | Modern, hooks-based |
| Build | Vite | 5.4+ | Fast, well-configured |
| Package Mgr | Yarn 4 / Poetry | Current | Good choices |
| Containers | Podman (rootless) | Latest | Security advantage over Docker |
| Migrations | Alembic | Current | Well-structured |
| Testing | Vitest + MSW (FE), pytest (BE) | Current | Good frameworks, low coverage |

### Architecture Quality

```
                    STRENGTHS                          WEAKNESSES
    +---------------------------------+  +----------------------------------+
    | Clean layered architecture      |  | No caching layer                 |
    | Async everywhere                |  | Near-zero backend test coverage  |
    | RBAC with 30 permissions        |  | Frontend CRUD incomplete         |
    | Redis pub/sub for real-time     |  | No CI/CD (broken pipeline)       |
    | Structured JSON logging         |  | No monitoring/observability      |
    | Transaction safety              |  | Frontend missing role-based UI   |
    | Kubernetes-ready health checks  |  | No form validation library       |
    | Comprehensive API client layer  |  | No code splitting/lazy loading   |
    | German localization throughout  |  | Limited accessibility (ARIA)     |
    +---------------------------------+  +----------------------------------+
```

### Codebase Size

| Area | Files | Lines (approx) |
|------|-------|-----------------|
| Backend Python | 39 files | ~4,500 lines |
| Frontend TypeScript/TSX | 35 files | ~5,300 lines |
| Frontend CSS | 12 files | ~2,200 lines |
| Frontend Tests | 4 files | ~1,425 lines |
| Documentation | 15+ files | ~15,000+ lines |
| Migrations | 6 files | ~600 lines |
| Config/Infra | 10+ files | ~1,500 lines |

### Development History

- **April 2025:** Project inception (6 initial commits, infrastructure struggles)
- **6-month gap** (April - November 2025)
- **November 6-19, 2025:** Intense AI-assisted sprint (~85 commits in 2 weeks)
  - Complete backend built
  - Frontend foundation + time tracking UI
  - RBAC, CRM, cost calculation
  - Testing infrastructure
  - Security audit
- **November 2025 - March 2026:** Dormant (4+ months)

**Contributors:** 76% AI-generated (Claude), 24% human (arcsmax)

---

## 4. Existing Specs & Documentation

### Specs Found

| Document | Size | Purpose | Relevance |
|----------|------|---------|-----------|
| `FEATURE_SPEC_TIME_TRACKING_ML.md` | ~30KB | Comprehensive time tracking + ML spec | HIGH - The primary feature spec |
| `ARCHITECTURE_REVIEW.md` | ~45KB | Full architecture analysis | HIGH - Security & improvement guide |
| `IMPLEMENTATION_PLAN.md` | ~12KB | Development roadmap (8 phases) | HIGH - Current execution plan |
| `MVP_ANALYSIS.md` | ~13KB | MVP definition & readiness | HIGH - Production readiness guide |
| `PHASE_5.2_PROGRESS.md` | ~15KB | Current phase tracking | MEDIUM - Historical progress |
| `GOLDSMITH_WORKSHOP_REQUIREMENTS.md` | ~21KB | Domain requirements | HIGH - Business requirements |
| `CLAUDE.md` | ~16KB | Developer guide | HIGH - How to work with codebase |

### German User Documentation (11 files in `/docs/`)

| Document | Purpose |
|----------|---------|
| `USER_ROLES_PERMISSIONS.md` | Complete RBAC reference with permission matrix |
| `FEATURE_USER_MANAGEMENT.md` | User admin tasks guide |
| `USER_GETTING_STARTED.md` | Onboarding guide |
| `FEATURE_ORDER_MANAGEMENT.md` | Order operations guide |
| `FEATURE_TIME_TRACKING.md` | Time tracking user guide |
| `FEATURE_MATERIAL_MANAGEMENT.md` | Material management guide |
| `FEATURE_CUSTOMER_MANAGEMENT.md` | CRM guide |
| `DAILY_WORKFLOWS.md` | Role-based daily workflows |
| `TROUBLESHOOTING.md` | Problem solving |
| `FAQ.md` | Common questions |

### What the ML Spec Covers (FEATURE_SPEC_TIME_TRACKING_ML.md)

This is the most ambitious spec in the project, defining:

1. **Model 1: Duration Prediction** (XGBoost/LightGBM) - Estimate total hours for new orders
2. **Model 2: Activity Duration** (Random Forest) - Per-activity time prediction
3. **Model 3: Delivery Date Calculator** - Multi-factor deadline calculation
4. **Model 4: Anomaly Detection** (Isolation Forest) - Detect unusual activity durations
5. **Batch Processing Detection** - Identify orders suitable for consolidated work
6. **Worker Specialization Learning** - Individual strength/weakness profiling
7. **Rework Prevention** - Predict conditions leading to rework
8. **Seasonal Adjustment** - Dynamic workload patterns

**ML Status:** None implemented yet. Requires ~100 completed orders for training data. Planned for Phase 5-8 (months away).

---

## 5. Critical Findings

### 5.1 Security Assessment

| Issue | Severity | Status | Notes |
|-------|----------|--------|-------|
| Hardcoded SECRET_KEY | CRITICAL | **FIXED** | Now uses env var with validation |
| Redis connection leak | CRITICAL | **FIXED** | Connection pool + context manager |
| HttpOnly cookies | CRITICAL | **FIXED** | Implemented with secure flags |
| RBAC system | HIGH | **IMPLEMENTED** | 30 permissions, 3 roles |
| Rate limiting (login) | HIGH | **IMPLEMENTED** | 5 attempts/min |
| N+1 queries | HIGH | **PARTIALLY FIXED** | Eager loading added to most services |
| Frontend role enforcement | HIGH | **NOT DONE** | All routes visible to all users |
| Activities router permissions | MEDIUM | **NOT DONE** | Has auth but no @require_permission |
| Token refresh mechanism | MEDIUM | **NOT DONE** | No refresh tokens |
| CSRF protection | MEDIUM | **PARTIAL** | SameSite=lax cookies only |

### 5.2 Infrastructure Issues

| Issue | Severity | Notes |
|-------|----------|-------|
| CI/CD YAML syntax error | CRITICAL | Python setup step malformed, pipeline broken |
| Container health checks fail | HIGH | curl/wget not installed in images |
| Python version mismatch | MEDIUM | CI uses 3.13, project targets 3.11+ |
| No frontend CI tests | MEDIUM | Only backend linting in pipeline |
| No TLS configuration | HIGH | No HTTPS for production |
| No monitoring/alerting | MEDIUM | No Prometheus/Grafana |

### 5.3 Code Quality Gaps

| Gap | Impact | Notes |
|-----|--------|-------|
| Backend test coverage ~0% | CRITICAL | Only conftest.py with fixtures |
| Frontend CRUD not wired | HIGH | Buttons exist but no handlers |
| No ESLint/Prettier | MEDIUM | No frontend code quality tools |
| No tsconfig.json | LOW | Using Vite defaults |
| Duplicate permission enums | LOW | Both core/permissions.py and api/deps.py |
| Mixed language comments | LOW | German/English inconsistency |

---

## 6. Unmerged Work - Immediate Action Required

**Branch:** `claude/analyze-next-steps-01EXbkJ1jRuEWS79Lm9XpSZx`
**Commits behind main:** 0 | **Commits ahead:** 25

### What's on the Unmerged Branch

This branch contains **substantial completed work** that has NOT been merged to main:

1. **Full CRUD Pages:**
   - CustomersPage with create/edit/delete
   - MaterialsPage with full CRUD
   - OrdersPage with full CRUD
   - MetalInventoryPage (new page)

2. **TimeTrackingPage:**
   - Live timer display
   - Charts and analytics
   - Activity breakdown visualization

3. **Dashboard Enhancement:**
   - KPI cards
   - Alerts and deadline warnings
   - Performance metrics

4. **Backend Test Suites (155+ tests):**
   - CustomerService tests (40+)
   - OrderService tests (50+)
   - Auth & User Service tests (65+)
   - MaterialService tests (28)

5. **Performance Optimizations:**
   - useMemo/useCallback patterns
   - Component re-render reduction

6. **Security Audit:**
   - Comprehensive vulnerability assessment
   - Dependency updates and fixes

**RECOMMENDATION:** This branch should be evaluated and merged ASAP. It addresses several critical gaps (CRUD operations, test coverage, security).

---

## 7. What to Focus on Next

### Priority 1: Housekeeping (Week 1)

1. **Evaluate and merge unmerged branch** - Contains 155+ tests, CRUD pages, security fixes
2. **Fix CI/CD pipeline** - YAML syntax error, Python version mismatch
3. **Fix container health checks** - Add curl/wget to Containerfiles
4. **Wire frontend role field** - Add role to UserType, display in UI

### Priority 2: Production Hardening (Weeks 2-3)

1. **Complete frontend RBAC** - Role-based routing, hide unauthorized nav items
2. **Fix activities router permissions** - Add @require_permission decorators
3. **Add token refresh mechanism** - Prevent forced re-login
4. **Implement Redis caching** - Cache hot data (materials, activities, customer top-N)
5. **Add form validation** - Zod or similar for frontend forms
6. **Set up monitoring** - Prometheus metrics + basic Grafana dashboard

### Priority 3: Feature Completion (Weeks 4-6)

1. **Calendar & Planning system** (Phase 6) - Core business requirement
2. **Invoice/billing integration** - Revenue-generating feature
3. **Mobile responsiveness** - Goldsmiths need workbench access
4. **Metal price API integration** - Replace hardcoded 45 EUR/g
5. **Offline capability** - Service worker for workshop use

### Priority 4: ML Foundation (Weeks 7-10)

1. **Data collection pipeline** - Ensure time entries capture all ML features
2. **Feature engineering** - Extract training features from completed orders
3. **Duration prediction model** - First ML model (requires 100+ completed orders)
4. **Anomaly detection** - Alert on unusual activity durations

---

## 8. State-of-the-Art Approach

### What Makes This Project Special

This isn't just another ERP - it's a **craft-industry-specific system** with ML-powered workflow intelligence. The state-of-the-art opportunity lies in combining:

1. **Domain-specific ML** - Models trained on goldsmith workflow data
2. **Real-time craft tracking** - QR/NFC-triggered time capture at the workbench
3. **Predictive operations** - Deadline calculation that accounts for material lead times, worker specialization, seasonal patterns
4. **Workshop intelligence** - Batch detection, rework prevention, capacity optimization

### Recommended Architecture Evolution

```
CURRENT STATE                              TARGET STATE
+------------------+                       +----------------------------------+
| Monolithic       |                       | Modular Monolith (Phase 1)       |
| FastAPI + React  |        ====>          | with clear bounded contexts      |
| Single DB        |                       |                                  |
+------------------+                       | Orders | CRM | TimeTracking | ML |
                                           +----------------------------------+
                                                          |
                                           +----------------------------------+
                                           | Event-Driven Architecture        |
                                           | Redis Streams (not just pub/sub) |
                                           | Event sourcing for audit trail   |
                                           +----------------------------------+
                                                          |
                                           +----------------------------------+
                                           | ML Pipeline (Phase 2)            |
                                           | Feature Store | Model Registry   |
                                           | Online Prediction | A/B Testing  |
                                           +----------------------------------+
```

### Key Technical Recommendations

#### Backend Evolution
1. **Redis Streams** instead of basic pub/sub for reliable event processing
2. **Repository Pattern** to decouple services from ORM details
3. **Event Sourcing** for order lifecycle (enables full audit trail and ML training)
4. **Background Workers** (Celery/ARQ) for ML predictions, PDF generation, email
5. **API Versioning** strategy for future compatibility

#### Frontend Evolution
1. **Zustand** instead of Context API (better performance, devtools, persistence)
2. **React Query / TanStack Query** for server state (caching, refetching, optimistic updates)
3. **Code splitting** with React.lazy + Suspense
4. **PWA capabilities** for offline workshop use
5. **Component library** (Radix UI or Shadcn) for consistency and accessibility

#### ML Pipeline
1. **MLflow** for model registry and experiment tracking
2. **Feature Store** (Feast or custom) for training data management
3. **Online prediction serving** via FastAPI endpoint
4. **A/B testing framework** for model comparison
5. **Continuous retraining** as more order data accumulates

#### DevOps Evolution
1. **Fix CI/CD first** - then add frontend tests, coverage gates, security scanning
2. **GitOps workflow** - Trunk-based development with feature flags
3. **Observability stack** - Prometheus + Grafana + Loki (all containerized)
4. **Load testing** - k6 or Locust for performance baselines
5. **Database backups** - Automated with pg_dump cron + S3 upload

---

## 9. What Documents to Create

### Must-Have (Create Before Development Resumes)

| Document | Purpose | Priority |
|----------|---------|----------|
| **SPEC_V2.md** | Updated comprehensive spec reflecting current state + future vision | CRITICAL |
| **TECHNICAL_DEBT.md** | Tracked list of all debt items with severity and effort estimates | HIGH |
| **TESTING_STRATEGY.md** | What to test, how to test, coverage targets per module | HIGH |
| **API_REFERENCE.md** | Auto-generated OpenAPI docs + custom usage examples | HIGH |
| **DEPLOYMENT_GUIDE.md** | Production deployment checklist (TLS, secrets, monitoring) | HIGH |

### Should-Have (Create During Development)

| Document | Purpose | Priority |
|----------|---------|----------|
| **DATA_MODEL.md** | Visual ERD + field-level documentation | MEDIUM |
| **ML_READINESS_CHECKLIST.md** | What data we need, what we're capturing, gaps | MEDIUM |
| **SECURITY_RUNBOOK.md** | Incident response, secret rotation, access audit | MEDIUM |
| **PERFORMANCE_BASELINE.md** | Current API response times, DB query times | MEDIUM |
| **MOBILE_UX_SPEC.md** | Workshop-specific mobile UI requirements | MEDIUM |

### Nice-to-Have (Create When Stable)

| Document | Purpose | Priority |
|----------|---------|----------|
| **ONBOARDING.md** | New developer setup + architecture walkthrough | LOW |
| **DECISIONS.md** | Architecture Decision Records (ADRs) | LOW |
| **CHANGELOG.md** | User-facing change log per release | LOW |

### What the Detailed Spec (SPEC_V2.md) Should Cover

The user mentioned they will write a more detailed spec. Based on the analysis, that spec should address:

1. **Vision & Goals** - What "done" looks like for V1.0
2. **User Personas** - Admin, Goldsmith, Viewer + customer portal?
3. **Feature Prioritization** - MoSCoW (Must/Should/Could/Won't) for all features
4. **Data Requirements for ML** - Minimum viable dataset, feature list, training triggers
5. **Offline Requirements** - What must work without internet
6. **Integration Points** - Metal price APIs, email/SMS, accounting software
7. **Performance Requirements** - Response times, concurrent users, data volume
8. **Compliance** - GDPR (already started), data retention, audit requirements
9. **Mobile/Tablet Strategy** - PWA vs native, specific workshop UI needs
10. **Multi-tenancy** - Single goldsmith vs supporting multiple workshops

---

## 10. Goldsmith Domain Expert Feedback (Ideensammlung)

A real goldsmith (Anne) provided detailed feature ideas and workflow requirements in `docs/feedback/Ideensammlung.md`. This is **invaluable domain-expert input** that reveals pain points no developer would think of. Every idea below comes directly from workshop experience.

### 10.1 The 7 Modules Requested

#### Module 1: Order Management ("Die Digitale Tuete" - The Digital Dossier)
- **Mandatory field popup** on order creation: alloy, surface finish, ring size, etc.
- No order can be confirmed until all required fields are filled (completeness validation)
- This prevents incomplete orders from entering the production pipeline

#### Module 2: Scrap Gold (Altgold) - HIGHEST DOMAIN VALUE
- **Altgold check** as part of order creation popup: "Scrap gold present? Yes/No"
- **Alloy calculator**: Select alloy (585er = 58.5% pure gold, 750er, 333er), enter weight, auto-calculate fine gold content
- **Multi-item entry**: e.g., "10g 585 yellow gold + 5g 333 white gold" with automatic summation
- **Photo upload** of delivered scrap pieces (documentation + legal protection)
- **Digital signature** on tablet for purchase receipt (legally binding)
- **Auto-generated receipt document** from entered data
- **Accounting integration**: Scrap gold credit flows automatically into final invoice as "Gutschrift Altgold"

> **Why this matters:** Scrap gold is a major cash flow mechanism in goldsmith businesses. Currently it's often a "forgotten item" - manually tracked, improperly credited, and legally undocumented.

#### Module 3: Cost Calculation & Invoicing
- **Pre-calculation (Vorkalkulation)**: Pull current metal/gemstone prices, estimate labor, generate binding offer
- **Digital work sheet (Arbeitszettel)**: Track actual values during production (real metal weight after scrap, actual time)
- **Quote vs. Actual comparison**: System compares estimated (Soll) with actual (Ist) and generates invoice with one click
- **No manual transfer** between quote and invoice - eliminates accounting errors

#### Module 4: Inventory & Procurement (Warenwirtschaft)
- **Gemstone/metal/tool inventory** with images (critical for non-expert staff to identify items)
- **Supplier links**: Each item linked to supplier webshop or order number
- **Stock threshold warnings**: Alert when critical level reached
- **Weekly consolidated procurement list**, grouped by supplier for efficient ordering

#### Module 5: Deadline & Reminder Management
- **Central calendar with traffic light status**:
  - Green: On schedule
  - Yellow: Fitting scheduled / work in progress
  - Red: Deadline critically close (< 2 days)
- **Mandatory deadline fields** on order creation: delivery date + optional fitting (Anprobe) date
- **Automated reminders**:
  - Day before pickup: "Tomorrow: Customer XY, Item: Ring - is the stone already set?"
  - Status-triggered: When "raw setting complete" -> "Fitting for Customer XY now possible - schedule appointment?"

#### Module 6: 360-Degree Customer Profile
- **Measurement Library (Mass-Bibliothek)**: Permanent storage of ring sizes, chain lengths, preferences ("prefers platinum", "allergic to nickel") - eliminates repetitive measuring
- **Birthday tracking** for marketing/gift vouchers
- **Visual customer lifetime history**: Every piece ever ordered, linked with:
  - Original photo of finished unique piece
  - Order document (what was discussed)
  - Invoice as PDF

#### Module 7: Employee Dashboard & Internal Messaging
- **Role-based dashboard views**:
  - Goldsmith: Focus on production (work sheets, current stones, deadlines)
  - Office staff: Focus on administration (order intake, material orders, invoicing)
- **Auto-populated to-do list** from order deadlines, with red indicator for today's deadlines
- **Digital Post-it (order-scoped comments)**: Comments tied to order ID for inter-team communication
  - Example: Goldsmith writes "Customer requested bezel setting instead of prong setting at fitting. Please check surcharge." -> Office staff gets notification, adjusts price without interrupting craftsperson
- **Handoff protocol (Stabuebergabe)**: Status change (e.g., "In Progress" -> "Ready for Setting") auto-notifies the next team member

### 10.2 Implementation Status of Requested Features

| Feature | Status | Notes |
|---------|--------|-------|
| Basic order management | DONE | CRUD exists, but no mandatory field validation popup |
| Customer master data | DONE | CRM fields exist, missing measurement library |
| Material inventory | DONE | Stock tracking + low stock alerts work |
| Gemstone support | DONE | Full gemstone model with attributes |
| Order photos | DONE | OrderPhoto model exists |
| RBAC (role-based access) | DONE | 3 roles, 30 permissions |
| Time tracking & activities | DONE | 15 activities, start/stop, interruptions |
| Scrap percentage in cost calc | DONE | Field exists in Order model |
| Deadline field on orders | DONE | DateTime field exists |
| Customer order history | PARTIAL | Relationship exists, no visual display |
| Status monitoring | PARTIAL | Deadline field but no traffic light UI |
| **Mandatory field validation popup** | NOT DONE | No enforced required fields |
| **Scrap Gold (Altgold) module** | NOT DONE | No dedicated model or workflow |
| **Digital signature** | NOT DONE | No signature capture system |
| **Alloy fine content calculator** | NOT DONE | No alloy calculation logic |
| **Calendar with traffic light** | NOT DONE | No calendar view at all |
| **Automated reminders/notifications** | NOT DONE | No push/email notification system |
| **Fitting (Anprobe) workflow** | NOT DONE | No fitting status |
| **Internal order comments** | NOT DONE | No comment model |
| **Handoff protocol** | NOT DONE | No "Stabuebergabe" button |
| **Role-specific dashboards** | NOT DONE | Generic dashboard for all users |
| **Measurement library** | NOT DONE | No ring_size/chain_length fields |
| **Customer birthday** | NOT DONE | Not in Customer model |
| **Supplier-grouped procurement** | NOT DONE | No procurement module |
| **Auto invoice generation** | NOT DONE | No quote-to-invoice flow |
| **Quote vs. actual comparison** | NOT DONE | No Soll/Ist comparison |
| **Supplier webshop links** | NOT DONE | No supplier linking |
| **Material images** | NOT DONE | No image field on materials |

### 10.3 Key Pain Points Revealed

These are the frustrations behind the feature requests:

1. **Scrap gold gets forgotten** - "Damit dies kein vergessener Posten mehr bleibt" - Major revenue leakage
2. **Repetitive customer measurements** - Ring sizes asked every time instead of stored permanently
3. **Paper notes between team members** - Physical post-its and verbal interruptions for order changes
4. **Unclear deadline urgency** - No visual indication of which orders are critical TODAY
5. **Manual quote-to-invoice transfer** - Error-prone copy/paste between estimate and final bill
6. **Ad-hoc material ordering** - No consolidated procurement, items ordered one by one
7. **Lost customer history** - Previous orders and preferences not easily accessible

### 10.4 Architectural Impact Assessment

| Feature | New DB Entities | Backend Changes | Frontend Changes | Infrastructure |
|---------|----------------|-----------------|------------------|----------------|
| Altgold Module | ScrapGold, ScrapGoldItem | New service + router, alloy calculator | New form, photo upload, signature widget | File storage (S3) |
| Order Comments | OrderComment | New service + router | Comment section in OrderDetail | - |
| Calendar | - | Query endpoints for date ranges | Full calendar component | - |
| Notifications | Notification, NotificationPreference | Notification service, job scheduler | Notification bell, push support | Celery/ARQ, email service |
| Measurement Library | CustomerMeasurement or extend Customer | Extend customer service | Measurement tab in customer profile | - |
| Procurement | Supplier, ProcurementList, ProcurementItem | New service + router | Procurement page | - |
| Digital Signature | SignatureRecord | PDF generation service | Signature canvas widget | PDF library (ReportLab) |
| Invoice Generation | Invoice, InvoiceLineItem | Invoice service, Soll/Ist logic | Invoice page, PDF preview | PDF generation |

### 10.5 Recommended Priority (Domain Expert Features)

**Must-Have for V1.0 (goldsmith won't use the system without these):**
1. Mandatory field validation on order creation
2. Calendar view with traffic light deadlines
3. Order comments system (Digital Post-it)
4. Measurement library in customer profile
5. Role-specific dashboard views

**Should-Have for V1.0 (major business value):**
1. Scrap Gold (Altgold) module (highest domain-unique value)
2. Automated reminders (day before pickup, fitting follow-up)
3. Quote vs. actual comparison
4. Handoff protocol with notifications

**Could-Have for V1.1 (significant but can wait):**
1. Digital signature with PDF receipt
2. Supplier-grouped procurement lists
3. Auto invoice generation
4. 360-degree customer visual history
5. Material images and supplier webshop links

---

## 11. Maturity Scorecard

### Backend Maturity: 8.2/10

| Component | Score | Notes |
|-----------|-------|-------|
| API Design | 9/10 | 55 endpoints, well-structured, comprehensive |
| Business Logic | 8/10 | 7 services, good separation, some TODOs |
| Database | 9/10 | 13 models, proper relationships, migrations |
| Security | 8/10 | JWT + cookies + RBAC, missing refresh tokens |
| Testing | 1/10 | **CRITICAL** - conftest only |
| Logging | 9/10 | Structured JSON, request tracing |
| Error Handling | 7/10 | Inconsistent across modules |
| Performance | 8/10 | Eager loading, missing caching |

### Frontend Maturity: 6.5/10

| Component | Score | Notes |
|-----------|-------|-------|
| Architecture | 9/10 | Clean context + API layer separation |
| TypeScript | 8/10 | 30+ interfaces, minor any gaps |
| Components | 7/10 | Good quality, CRUD operations incomplete |
| State Management | 8/10 | 3 contexts, localStorage persistence |
| Testing | 5/10 | 130 tests but limited scope |
| Accessibility | 3/10 | Missing ARIA, keyboard nav, semantic HTML |
| Performance | 5/10 | No code splitting, lazy loading |
| Code Quality Tools | 2/10 | No ESLint, Prettier, or tsconfig |

### Infrastructure Maturity: 5.8/10

| Component | Score | Notes |
|-----------|-------|-------|
| Containerization | 9/10 | Podman rootless, security-first |
| Dev Workflow | 9/10 | Makefile with 30+ targets |
| Documentation | 9/10 | Excellent installation + migration guides |
| CI/CD | 1/10 | **BROKEN** - syntax error |
| Monitoring | 1/10 | Missing entirely |
| Production Readiness | 3/10 | No TLS, backups, or HA |

### Overall Project Maturity: 6.5/10

**Verdict:** Strong foundation, needs production hardening and feature completion.

---

## 12. Recommended Roadmap

### Phase A: Recovery & Stabilization (1-2 weeks)

**Goal:** Get back to a stable, deployable state after 4 months of dormancy.

- [ ] Review and merge unmerged branch (`claude/analyze-next-steps`)
- [ ] Fix CI/CD pipeline (YAML syntax, Python version)
- [ ] Fix container health checks (install curl/wget)
- [ ] Run full test suite, fix any regressions
- [ ] Update all dependencies (4 months of updates)
- [ ] Create SPEC_V2.md (user's detailed spec)

### Phase B: Production Hardening (2-3 weeks)

**Goal:** Make the system safe for real users with real data.

- [ ] Complete frontend RBAC (role-based routing + UI)
- [ ] Add activities router permission decorators
- [ ] Implement token refresh mechanism
- [ ] Add Redis caching for hot data
- [ ] Set up TLS/HTTPS
- [ ] Add monitoring (Prometheus + Grafana)
- [ ] Reach 70%+ backend test coverage
- [ ] Add ESLint + Prettier to frontend
- [ ] Fix accessibility issues (ARIA, keyboard)

### Phase C: Feature Completion (3-4 weeks)

**Goal:** Deliver a complete MVP that goldsmiths can use daily.

- [ ] Calendar & deadline management system
- [ ] Mobile-responsive design (workshop use)
- [ ] Invoice/billing foundation
- [ ] Metal price API integration
- [ ] Email notifications (order status, deadlines)
- [ ] Offline capability (PWA)

### Phase D: Intelligence Layer (4-6 weeks)

**Goal:** Add ML-powered features that differentiate the product.

- [ ] Data collection pipeline validation
- [ ] Feature engineering for ML models
- [ ] Duration prediction model (when 100+ orders exist)
- [ ] Anomaly detection for activity durations
- [ ] Deadline calculation with confidence intervals
- [ ] Worker specialization profiling

### Phase E: Scale & Polish (Ongoing)

- [ ] Batch processing detection
- [ ] Advanced reporting & analytics
- [ ] Multi-language support
- [ ] Customer portal
- [ ] Advanced calendar (Gantt, capacity planning)
- [ ] Load testing & performance optimization

---

## Appendix: File Structure Reference

```
goldsmith_erp/
+-- src/goldsmith_erp/          # Backend (39 Python files)
|   +-- api/routers/            # 8 routers, 55 endpoints
|   +-- core/                   # Security, config, permissions, pubsub, logging
|   +-- db/                     # Models (13), session, seed data
|   +-- middleware/             # Request logging middleware
|   +-- models/                 # Pydantic schemas (8 modules)
|   +-- services/              # Business logic (7 services, 1,846 lines)
|   +-- main.py                # FastAPI app entry + WebSocket manager
+-- frontend/src/               # Frontend (35+ TypeScript files)
|   +-- api/                   # 7 API clients, 47 methods
|   +-- components/            # 10 reusable components
|   +-- contexts/              # 3 React contexts
|   +-- layouts/               # MainLayout
|   +-- pages/                 # 8 pages
|   +-- styles/                # 12 CSS files
|   +-- test/                  # MSW setup + handlers
|   +-- types.ts               # 300 lines, 30+ interfaces
+-- alembic/versions/          # 6 database migrations
+-- docs/                      # 11 German user documentation files
+-- tests/                     # Backend tests (conftest only on main)
+-- .github/workflows/         # CI/CD (BROKEN)
+-- Containerfile              # Backend container
+-- frontend/Containerfile     # Frontend container
+-- podman-compose.yml         # Container orchestration
+-- podman-pod.yaml            # Kubernetes-style pod definition
+-- Makefile                   # 30+ development targets
```

---

*This analysis was generated by 8 parallel deep-analysis agents examining: architecture review, implementation plan & progress, feature spec, backend codebase, frontend codebase, infrastructure & DevOps, git history, and RBAC & security implementation.*
