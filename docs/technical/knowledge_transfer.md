# Knowledge Transfer: Coffee Lab Lessons for New Projects

**Date:** 2026-03-31
**Purpose:** Complete knowledge extraction from Coffee Lab for reuse in a Goldsmith ERP project
**Method:** 7 parallel research agents covering every aspect of the project

---

## Table of Contents

1. [What Worked, What Didn't](#1-what-worked-what-didnt)
2. [AI Agent System Setup](#2-ai-agent-system-setup)
3. [CLAUDE.md Architecture](#3-claudemd-architecture)
4. [Tech Stack & Licensing](#4-tech-stack--licensing)
5. [Security Concept](#5-security-concept)
6. [UI/UX Design System & Brand Coherence](#6-uiux-design-system--brand-coherence)
7. [Project Structure & Django Patterns](#7-project-structure--django-patterns)
8. [Deployment & DevOps](#8-deployment--devops)
9. [Goldsmith ERP Adaptation Guide](#9-goldsmith-erp-adaptation-guide)

---

## 1. What Worked, What Didn't

### What Worked Extremely Well

**1. HTMX + Alpine.js + Tailwind (No SPA)**
- Server-rendered HTML with HTMX partial swaps = fast dev, no build step, instant feedback
- Alpine.js for micro-interactions (dropdowns, modals, toggles) without React complexity
- Tailwind utility classes = consistent design without naming CSS classes
- Combined bundle: ~14KB vs React's ~48KB+
- Django templates + HTMX = forms just work, no API layer needed

**2. Docker-First Development**
- `docker compose up -d` and entire stack is running
- Consistent across team members (no "works on my machine")
- Production parity: same images, same services
- Celery, Redis, PostgreSQL, Mailpit all containerized

**3. Multi-Agent Orchestration**
- 10 specialized agents cover every domain (design, security, compliance, product, coffee science)
- 6-phase pipeline (Research → Plan → Plan Review → Implement → Code Review → Commit)
- Parallel safety rules prevent file conflicts
- Session handoff protocol enables multi-day work

**4. Service Layer Pattern**
- Business logic in `services/` directory, not in views
- Services are testable without HTTP
- Views become thin: parse request → call service → render response
- Reusable: views, Celery tasks, and admin actions all call same services

**5. Security-by-Default**
- `GlobalLoginRequiredMiddleware` = deny-by-default (whitelist public paths)
- Pre-commit hooks catch secrets and vulnerabilities before they land in git
- `@require_recent_auth` for sensitive actions = sudo mode
- `auditlog.register()` on every model = complete audit trail
- `nh3.clean()` sanitization on every user input

**6. Comprehensive CLAUDE.md**
- 1000+ line development manual that guides AI behavior
- Roaster data privacy rules enforced through AI constraints
- Tool selection matrix (which tool for which issue type)
- Deployment workflow documented step-by-step

### What Didn't Work / Lessons Learned

**1. Missing Edit Views (Create-Only Models)**
- 4 models (RoastBatch, PackagingMaterial, RoasterReminder, WholesaleOrder) have no edit view
- Roasters can't fix mistakes after creation → frustrating UX
- **Lesson:** Always build Create + Edit + Detail for every entity from day one

**2. Hardcoded Grid Layouts Without Mobile Fallback**
- Multiple forms use `grid-cols-2` without `sm:` prefix → broken on mobile
- **Lesson:** Never use `grid-cols-2` or higher without a `grid-cols-1 sm:grid-cols-2` fallback

**3. Disconnected Workflows**
- Stock alerts don't link to reorder actions
- No batch→packaging workflow
- Dashboard recommendations are read-only (not clickable)
- **Lesson:** Every data display should link to its natural next action

**4. Under-Exposed Model Fields**
- RoastBatch has 37 fields but the form only exposes 7 (19%)
- Roasters can't record roast analytics, QC data, or temperatures
- **Lesson:** Audit form coverage vs model fields early and regularly

**5. Touch Targets Too Small**
- Most buttons use `px-4 py-2` (~32x28px), below 44x44px WCAG minimum
- **Lesson:** Define `btn-primary`, `btn-sm`, etc. with minimum 44px height from the start

**6. No Form Validation Feedback on Mobile**
- Django form errors render but aren't prominently visible on small screens
- **Lesson:** Style form errors with prominent colors and position them above the field

**7. Chart Fixed Heights**
- All ApexCharts use fixed pixel heights (256px, 384px), no responsive config
- **Lesson:** Always add `responsive: [{ breakpoint: 640, options: {...} }]` to chart configs

---

## 2. AI Agent System Setup

### 2.1 Agent Directory Structure

```
.claude/
├── agents/                    # 10 specialized agent personas
│   ├── behavioral-psychologist.md   # @laura — Gamification & community psychology
│   ├── coffee-expert.md             # @coffee — Domain expertise (adapt: goldsmith domain)
│   ├── community-manager.md         # @community — User engagement & moderation
│   ├── compliance-officer.md        # @anna — DSGVO/GDPR, legal compliance
│   ├── design-lead.md              # @jason — UI/UX, brand, Tailwind patterns
│   ├── operations-lead.md          # @ops — Finances, KPIs, analytics
│   ├── product-lead.md             # @maria — Vision, roadmap, prioritization
│   ├── retention-strategist.md     # @retention — Habit formation, churn prevention
│   ├── technical-lead.md           # @henrik — Architecture, security, stack decisions
│   └── ux-researcher.md            # @uxresearch — User research, testing
├── hooks/
│   ├── gsd-check-update.js         # Session start hook
│   └── gsd-statusline.js           # Status line display
├── settings.json                    # Plugin config + hooks
└── settings.local.json              # Permission allowlists
```

### 2.2 Agent Persona Template

Each agent file follows this structure:

```markdown
---
name: Agent Name
role: Role Title
description: Brief description
trigger: @alias
---

## Background
[Education, career history — builds credibility for the AI persona]

## Core Responsibilities
[5-8 numbered responsibilities]

## Expertise
[Technical skills and domain knowledge]

## Frameworks Used
[Psychological, business, or technical frameworks the agent applies]

## Mindset & Communication Style
[How the agent thinks and communicates]

## Typical Questions
[Questions this agent asks to guide decisions]

## Documentation Context Path
[Where this agent's reference docs live: `docs/<agent-name>/`]
```

### 2.3 The 10 Agents & What They Do

| Agent | Trigger | Core Value | Adapt For Goldsmith? |
|-------|---------|------------|---------------------|
| Technical Lead | @henrik | Architecture, security, GDPR | YES — same role |
| Compliance Officer | @anna | DSGVO, legal, data protection | YES — same role |
| Design Lead | @jason | UI/UX, brand, accessibility | YES — new brand |
| Product Lead | @maria | Vision, roadmap, prioritization | YES — new domain |
| UX Researcher | @uxresearch | User research, testing | YES — same role |
| Operations Lead | @ops | Finances, KPIs, analytics | YES — same role |
| Coffee Expert | @coffee | Domain knowledge | REPLACE — Goldsmith Expert |
| Behavioral Psychologist | @laura | Gamification, engagement | MAYBE — if gamification needed |
| Community Manager | @community | Social features, moderation | MAYBE — if community features |
| Retention Strategist | @retention | Churn, habit formation | MAYBE — if SaaS model |

### 2.4 Plugin Configuration (settings.json)

```json
{
  "enabledPlugins": {
    "frontend-design@claude-plugins-official": true,
    "security-guidance@claude-plugins-official": true,
    "code-review@claude-plugins-official": true,
    "commit-commands@claude-plugins-official": true,
    "pyright-lsp@claude-plugins-official": true
  },
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "node .claude/hooks/gsd-check-update.js"
      }]
    }]
  }
}
```

### 2.5 Multi-Agent Orchestration Pattern

**6-Phase Pipeline:**
```
Phase 1: RESEARCH (parallel, read-only agents)
    → Explore agents investigate codebase
    → General-purpose agents do web research

Phase 2: PLAN (orchestrator synthesizes)
    → File conflict detection
    → Serialize conflicting, parallelize safe
    → Save plan to docs/plans/

Phase 3: PLAN REVIEW (complex issues only)
    → Security reviewer
    → Compliance reviewer
    → Architecture reviewer

Phase 4: IMPLEMENT (parallel batches)
    → 1-2 agents per issue
    → Orchestrator monitors

Phase 5: CODE REVIEW (parallel)
    → 1 reviewer per implementation
    → APPROVED or NEEDS_WORK

Phase 6: COMMIT
    → Fix findings, stage files, commit, close issues
```

**Parallel Safety Rules:**
- NEVER parallelize: migrations, settings, middleware, urls.py
- SAFE to parallelize: templates in different apps, views in different apps, independent tests
- Orchestrator maintains "files being modified" list

**Key Constraint:** Subagents cannot spawn other subagents. Only the main conversation spawns agents.

---

## 3. CLAUDE.md Architecture

### 3.1 Structure (1000+ lines)

```markdown
# CLAUDE.md Sections:

1. Working Style — "Always ask questions when not 100% sure"
2. Data Privacy Rules — CRITICAL constraints (adapt per domain)
3. Project Overview — What the product is
4. Tech Stack — Technology matrix table
5. Development Commands — Docker commands, CSS build, testing
6. Services — docker-compose service table (port, purpose)
7. Architecture — Domain concepts, data models, patterns
8. Project Structure — Directory tree
9. Key Documentation — Cross-references to 50+ docs
10. Infrastructure — Hosting, scaling path
11. Internationalization — i18n workflow
12. Environment Variables — .env.example reference
13. Security — Stack, developer requirements, commands
14. Admin — Django Unfold sidebar navigation rules
15. GitHub Issue Workflow — Tool selection per issue type
16. Multi-Agent Workflow — 6-phase pipeline, safety rules, roles
17. Deployment Workflow — Local → Docker → GitHub → Server
```

### 3.2 Key Patterns to Replicate

**Privacy Rules Section:**
```markdown
## Data Privacy Rules (CRITICAL)
[Domain-specific rules that AI must NEVER violate]
- Rule 1: [Who can see what data]
- Rule 2: [What goes in exports]
- ...
```

**Tool Selection Matrix:**
```markdown
| Issue Type | Required Tools | Optional Tools |
|-----------|---------------|----------------|
| Backend   | Serena, TodoWrite | Sequential Thinking |
| Frontend  | Read/Edit, TodoWrite | Frontend-Design |
| Bug       | Sequential Thinking, Serena | Explore Agent |
```

**Session Handoff Protocol:**
```markdown
When pausing mid-feature:
1. Update planning doc with: done, next, blockers
2. Commit the planning doc
3. Next session: read planning doc first
```

---

## 4. Tech Stack & Licensing

### 4.1 Core Stack (All Open Source, Commercially Free)

| Layer | Technology | License | Why Chosen |
|-------|-----------|---------|-----------|
| Backend | Django 5.x | BSD | Admin UI, mature, Python ecosystem |
| Database | PostgreSQL 16 | PostgreSQL License | JSONB, ACID, complex queries |
| Cache/Queue | Redis 7 | BSD | Dual-purpose: cache + Celery broker |
| Task Queue | Celery + Beat | BSD | Distributed tasks, scheduled jobs |
| Web Server | Gunicorn | MIT | Simple, Docker-friendly, performant |
| Frontend | HTMX + Alpine.js | BSD / MIT | 14KB total, no SPA overhead |
| Styling | Tailwind CSS v4 | MIT | Utility-first, responsive, dark mode |
| Charts | ApexCharts | MIT | Radar charts, responsive, dark mode |
| Admin | Django Unfold | MIT | Modern admin UI |
| Auth | django-allauth | MIT | Email + OAuth + MFA |
| Hosting | Hetzner Cloud | N/A | GDPR, German servers, ~25€/month |
| Container | Docker + Compose | Apache 2.0 | Consistency, isolation |
| Email | Brevo (Sendinblue) | N/A (SaaS) | EU-hosted, GDPR compliant |

### 4.2 Security Stack

| Package | License | Purpose |
|---------|---------|---------|
| django-csp | MIT | Content Security Policy headers |
| django-axes | MIT | Brute-force protection (5 attempts / 15 min) |
| django-auditlog | MIT | Admin action audit trail |
| django-permissions-policy | MIT | Permissions-Policy headers |
| nh3 | MIT | XSS sanitization (replaces bleach) |
| django-ratelimit | BSD | View-level rate limiting |
| fido2 | BSD | WebAuthn/Passkey MFA |

### 4.3 Frontend Runtime (Vendored, No Bundler)

| Library | Size | License | Purpose |
|---------|------|---------|---------|
| HTMX | ~9KB | BSD | AJAX without JavaScript |
| Alpine.js | ~5KB | MIT | Reactive micro-interactions |
| ApexCharts | ~14KB | MIT | Data visualization |
| driver.js | ~8KB | MIT | Onboarding tours |
| qr-scanner | ~5KB | Apache 2.0 | QR code scanning |

### 4.4 Why This Stack (Not React/Vue/Next.js)

| Factor | HTMX+Alpine+Tailwind | React+Next.js |
|--------|---------------------|---------------|
| Bundle size | ~14KB | ~48KB+ |
| Build step | CSS only (npm run build:css) | Full webpack/turbopack |
| Server rendering | Native (Django templates) | SSR config needed |
| Learning curve | HTML + attributes | JSX + hooks + state mgmt |
| SEO | Built-in | Requires SSR/SSG config |
| Form handling | Django forms just work | API layer + form libraries |
| Real-time | HTMX polling or SSE | WebSockets + state sync |
| Team size | Solo dev friendly | Better for large teams |

**Verdict:** HTMX stack is ideal for solo/small team building server-rendered apps. Choose React only if you need complex client-side state, real-time collaboration, or mobile app sharing code.

---

## 5. Security Concept

### 5.1 Defense-in-Depth Architecture

```
Layer 1: Network — Cloudflare WAF / UFW firewall / Tailscale VPN
Layer 2: Transport — TLS 1.3 (Let's Encrypt or self-signed)
Layer 3: Application — CSP headers, CSRF, session security
Layer 4: Authentication — MFA (TOTP + WebAuthn), sudo mode
Layer 5: Authorization — Role-based (@roaster_required, @require_min_role)
Layer 6: Input — nh3 sanitization, Django ORM (no raw SQL)
Layer 7: Data — Field-level encryption (Art. 9), soft delete
Layer 8: Audit — django-auditlog, security event logging
Layer 9: CI/CD — Pre-commit hooks (Gitleaks, Bandit, Ruff)
```

### 5.2 Authentication Flow

```
User → Login → django-allauth (email/Google OAuth)
         ↓
     MFA Check → TOTP or WebAuthn (mandatory for "Röster" group)
         ↓
     Session → Redis (30-min TTL)
         ↓
     Sensitive Action → @require_recent_auth (15-min password freshness)
```

### 5.3 Middleware Stack

```python
# Deny-by-default: everything requires login except whitelisted paths
GlobalLoginRequiredMiddleware:
    PUBLIC_PATH_PREFIXES = ["/accounts/", "/admin/", "/static/", ...]

# MFA enforcement for roaster group
MFAEnforcementMiddleware:
    if user.groups.filter(name="Röster") and not user.has_mfa:
        redirect to MFA setup

# HTMX-aware redirects
HtmxRedirectMiddleware:
    if request.htmx:
        return HX-Redirect header instead of 302
```

### 5.4 Developer Security Requirements

1. **Sanitize user input** with `nh3.clean(text, tags=set())`
2. **Use Django ORM** — never raw SQL queries
3. **Protect sensitive actions** with `@require_recent_auth`
4. **Register new models** with `auditlog.register(Model)`
5. **Run pre-commit hooks** before pushing

### 5.5 GDPR/DSGVO Implementation

| Requirement | Implementation |
|------------|---------------|
| Art. 15 Data Access | JSON export of all user data |
| Art. 17 Right to Erasure | 30-day soft delete, then hard delete |
| Art. 20 Data Portability | JSON export endpoint |
| Art. 25 Privacy by Design | K-anonymity (min 5 users), data minimization |
| Art. 28 Processor Agreements | DPA with all third parties |
| Art. 30 Processing Records | ROPA with 59 activities documented |
| Art. 32 Security | Encryption at rest, TLS, MFA, audit logs |
| Art. 33/34 Breach Notification | Incident response plan (72-hour rule) |
| Art. 35 DPIA | Impact assessment for ML profiling |

### 5.6 Pre-Commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: gitleaks     # Secret detection
  - repo: bandit       # Python security analysis
  - repo: ruff         # Code quality + formatting
  - repo: djlint       # Django template linting
  - repo: trim/fix     # Trailing whitespace, EOF
```

---

## 6. UI/UX Design System & Brand Coherence

### 6.1 Design Philosophy

**Glass Morphism Design Language:**
- Cards: `bg-white/85 dark:bg-stone-800/85 backdrop-blur-xs`
- Coffee-tinted shadows: `rgba(111, 78, 55, ...)` instead of black
- Rounded everything: `rounded-xl` (cards), `rounded-lg` (buttons, inputs)
- Subtle borders: `border border-brand-cta-100 dark:border-stone-700`

**Typography Hierarchy:**
- Headings: Serif font (Playfair Display) — warm, premium feel
- Body: Sans-serif (Inter) — clean, readable
- Icons: Material Symbols Outlined — self-hosted for GDPR

### 6.2 Color System (Adapt Brand Colors Per Project)

```css
/* Coffee Lab brand — replace with goldsmith brand */
@theme {
  --color-brand-cta-*:      /* Primary action color (orange in CL) */
  --color-brand-espresso-*:  /* Dark/sidebar color (brown in CL) */
  --color-brand-cream-*:     /* Page background (off-white in CL) */
  --color-brand-gold-*:      /* Accent/warning (gold in CL) */
  --color-brand-coffee-*:    /* Secondary accent (warm brown in CL) */
}

/* Semantic tokens (don't change names, change values) */
--background-color-page: var(--color-brand-cream-100);
--text-color-primary: var(--color-brand-espresso-800);
--text-color-link: var(--color-brand-cta-600);
--border-color-focus: var(--color-brand-cta-500);
--ring-color-focus: var(--color-brand-cta-500);
```

### 6.3 Component Library (Reusable @utility Classes)

**Buttons:**
```css
@utility btn-primary {}      /* px-6 py-3 bg-brand-cta-600 text-white rounded-lg */
@utility btn-primary-md {}   /* px-5 py-2.5 (medium) */
@utility btn-primary-sm {}   /* px-4 py-2 (small) */
@utility btn-secondary {}    /* Outline with brand-coffee border */
@utility btn-danger {}       /* bg-red-600 */
@utility btn-ghost {}        /* Link-style, no background */
```

**Cards:**
```css
@utility card {}             /* Glass morphism card with hover */
@utility card-static {}      /* No hover effect */
@utility card-interactive {} /* Enhanced hover with scale */
@utility card-compact {}     /* Smaller, no shadow */
@utility stat-card {}        /* KPI card with @container query */
```

**Typography:**
```css
@utility page-title {}       /* text-2xl font-bold font-heading */
@utility section-title {}    /* text-xl font-bold font-heading mb-4 */
@utility card-title {}       /* text-lg font-semibold font-heading mb-4 */
@utility subtitle {}         /* text-sm text-stone-600 */
@utility stat-number {}      /* text-2xl font-bold */
```

**Inputs:**
```css
@utility input {}            /* px-3 py-2 text-sm border rounded-lg focus:ring-2 */
@utility select {}           /* Same as input with dropdown styling */
@utility textarea {}         /* Multi-line variant */
@utility checkbox {}         /* h-5 w-5 brand-cta colored */
```

### 6.4 Dark Mode Strategy

- Implementation: `.dark` class on `<html>`, toggled via Alpine.js + localStorage
- FOUC prevention: inline `<script>` in `<head>` sets class before paint
- Pattern: Always pair light/dark classes: `bg-white dark:bg-stone-800`
- Charts: MutationObserver watches `.dark` class, auto-updates ApexCharts

### 6.5 Responsive Breakpoint Strategy

| Breakpoint | Width | Usage |
|-----------|-------|-------|
| Base | <640px | Mobile default, stacked layouts |
| `sm:` | >=640px | Inline text, 2-col forms |
| `md:` | >=768px | Grid layouts (2-3 cols) |
| `lg:` | >=1024px | Sidebar visible, full desktop |
| `xl:` | >=1280px | Wide layouts |

**Critical rule:** `lg:` is the sidebar breakpoint. Mobile nav shown below `lg:`, sidebar shown at `lg:` and above.

### 6.6 UX Patterns

**HTMX Interaction Pattern:**
```html
<button hx-post="{% url 'action' pk %}"
        hx-target="#element-{{ pk }}"
        hx-swap="outerHTML"
        hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
  Action
</button>
```

**Alpine.js Confirmation Pattern:**
```html
<div x-data="{ confirm: false }">
  <button x-show="!confirm" @click="confirm = true">Delete</button>
  <div x-show="confirm" x-transition>
    <span>Sure?</span>
    <button @click="confirm = false">Cancel</button>
    <button hx-post="..." hx-swap="outerHTML">Yes, delete</button>
  </div>
</div>
```

**Modal Component (Reusable):**
- Alpine.js + `x-teleport="body"` (avoids stacking context issues)
- Focus trap: `x-trap.noscroll`
- Backdrop: `bg-black/60 backdrop-blur-xs`
- Escape key + click-outside to close

**Toast/Message System:**
- Fixed position: `top-4 right-4 z-[9998]`
- Auto-dismiss: 5s for success, persistent for errors
- Progress bar countdown animation

---

## 7. Project Structure & Django Patterns

### 7.1 Directory Organization

```
project_root/
├── apps/                    # Django apps (one per domain)
│   ├── accounts/           # Auth, profiles, MFA, soft-delete
│   ├── <domain>/           # Core business logic app
│   │   ├── models/         # Split by subdomain
│   │   ├── services/       # Business logic (not in views!)
│   │   ├── views/          # Split by subdomain
│   │   ├── urls.py         # Namespaced URLs
│   │   ├── forms.py        # Django forms
│   │   ├── tasks.py        # Celery tasks
│   │   ├── constants.py    # App constants
│   │   ├── admin.py        # Admin customization
│   │   ├── tests/          # Test suite
│   │   └── management/commands/  # Django management commands
│   └── ...
├── project_name/           # Django project settings
│   ├── settings/
│   │   ├── base.py         # Shared config
│   │   ├── development.py  # Dev overrides
│   │   └── production.py   # Prod overrides
│   ├── middleware.py        # Custom middleware
│   ├── encryption.py       # Field-level encryption
│   ├── celery.py           # Celery config
│   └── urls.py             # Root URL config
├── templates/              # All HTML templates
├── static/                 # CSS, JS, images, fonts
├── docs/                   # Extensive documentation
├── scripts/                # Bash automation
├── locale/                 # i18n translations
├── .claude/                # AI agent configuration
├── .github/workflows/      # CI/CD
├── docker-compose.yml      # Development
├── docker-compose.prod.yml # Production
└── Dockerfile              # Multi-stage build
```

### 7.2 Key Patterns

**Service Layer:**
```python
# apps/domain/services/order_service.py
class OrderService:
    @staticmethod
    def create_order(customer, items, user):
        """Business logic separate from HTTP layer."""
        with transaction.atomic():
            order = Order.objects.create(customer=customer, created_by=user)
            for item in items:
                OrderItem.objects.create(order=order, **item)
            AuditLog.objects.create(action="order_created", ...)
        return order
```

**Decorator-Based Access Control:**
```python
@login_required
@roaster_required          # Checks user has roaster assignment
@require_min_role("editor") # Minimum permission level
@require_recent_auth       # Sudo mode (15-min freshness)
def sensitive_view(request):
    roaster = request.managed_roaster  # Added by decorator
    ...
```

**Soft Delete Pattern:**
```python
class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

class MyModel(models.Model):
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True)
    objects = SoftDeleteManager()       # Default: excludes deleted
    all_objects = models.Manager()      # Includes deleted
```

**State Machine Pattern:**
```python
ALLOWED_TRANSITIONS = {
    "DRAFT": ["CONFIRMED", "CANCELLED"],
    "CONFIRMED": ["IN_PRODUCTION", "CANCELLED"],
    "IN_PRODUCTION": ["READY", "ON_HOLD"],
    ...
}

def transition(obj, to_state, user):
    if to_state not in ALLOWED_TRANSITIONS.get(obj.status, []):
        raise ValidationError("Invalid transition")
    obj.status = to_state
    obj.save()
    TransitionLog.objects.create(obj=obj, from_state=..., to_state=to_state, user=user)
```

**Singleton Settings Model:**
```python
class SiteSettings(models.Model):
    class Meta:
        verbose_name_plural = "Site Settings"

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
```

### 7.3 i18n Setup (German Primary)

```python
# settings
LANGUAGE_CODE = "de"
LANGUAGES = [("de", "Deutsch"), ("en", "English")]
USE_I18N = True
PREFIX_DEFAULT_LANGUAGE = False  # No /de/ prefix for default

# In templates
{% load i18n %}
<h1>{% trans "Willkommen" %}</h1>

# In Python
from django.utils.translation import gettext as _
message = _("Aufgabe erstellt.")

# Extract & compile
python manage.py makemessages -l de -l en
python manage.py compilemessages
```

---

## 8. Deployment & DevOps

### 8.1 Docker Architecture

**Development (docker-compose.yml):**
- Volume mounts for live reload (Python auto-reloads, templates/static mounted)
- Mailpit for email testing
- Flower for Celery monitoring

**Production (docker-compose.prod.yml):**
- NO volume mounts — code baked into Docker image
- Must `build` then `up -d` for ANY code change (restart only picks up env var changes)
- Non-root user (appuser:1000)
- Resource limits on all containers
- `cap_drop: ALL` + `no-new-privileges` on workers

### 8.2 Multi-Stage Dockerfile

```dockerfile
# Stage 1: CSS Build (Node)
FROM node:20-slim AS css-builder
# npm ci + tailwindcss build

# Stage 2: Python Dependencies
FROM python:3.11-slim AS deps
# uv install (fast, reliable)

# Stage 3: Runtime
FROM python:3.11-slim
# Non-root user, minimal system deps
# COPY from css-builder and deps stages
```

### 8.3 Deployment Flow

```
Local: git commit + push to GitHub
  → CI: lint + test + security scan
  → Server: ssh + git pull + docker compose build + up -d + migrate
```

### 8.4 Backup Strategy (3-2-1-1-0)

- 3 copies (live DB + server backup + offsite)
- 2 media types (SSD + external)
- 1 offsite (Hetzner Storage Box or S3)
- 1 immutable (append-only SSH)
- 0 errors on restore tests

### 8.5 Critical Lessons

1. **Cookie security on HTTP:** SESSION_COOKIE_SECURE must be False for HTTP testing
2. **Redis password:** Must match in 3 places (.env, compose, connection strings)
3. **Django Site model:** Update from "example.com" to actual domain
4. **Production rebuild:** `restart` does NOT pick up code changes — must `build`
5. **Git permissions:** `sudo chown -R user:user /opt/project` if permission errors

---

## 9. Goldsmith ERP Adaptation Guide

### 9.1 What to Keep As-Is

- Django + HTMX + Alpine.js + Tailwind stack
- Docker development and production setup
- Multi-stage Dockerfile pattern
- Service layer architecture
- Security concept (middleware, decorators, audit logging, pre-commit)
- CLAUDE.md structure and multi-agent workflow
- Plugin configuration (settings.json)
- CI/CD pipeline (lint, test, security scan)
- GDPR implementation patterns

### 9.2 What to Adapt

**Brand Colors:**
```css
/* Replace coffee brand with goldsmith brand */
brand-cta:      /* Gold/amber for CTA — fitting for goldsmith */
brand-primary:  /* Deep charcoal or navy for primary surfaces */
brand-cream:    /* Warm ivory for page background */
brand-accent:   /* Rose gold or copper for accents */
```

**Domain Agent:**
Replace `coffee-expert.md` with `goldsmith-expert.md`:
- Precious metals knowledge (gold, silver, platinum, palladium)
- Gemstone expertise (diamonds, rubies, emeralds, sapphires)
- Hallmarking and assay standards
- Jewelry manufacturing techniques
- Material cost tracking (spot prices)

**Privacy Rules:**
Replace roaster data rules with goldsmith-specific:
- Customer PII protection (names, addresses, custom orders)
- Financial data (payment info, pricing)
- Design IP (custom designs, CAD files)
- Insurance valuation data

### 9.3 New Project Checklist

```
1. [ ] Create repository
2. [ ] Copy Dockerfile, docker-compose.yml, docker-compose.prod.yml
3. [ ] Set up Django project with settings/ split (base, dev, prod)
4. [ ] Install security stack (CSP, axes, auditlog, nh3)
5. [ ] Set up GlobalLoginRequiredMiddleware
6. [ ] Create .claude/ directory with:
   - [ ] settings.json (plugins)
   - [ ] agents/ (adapted personas)
   - [ ] hooks/ (statusline, session start)
7. [ ] Write CLAUDE.md with:
   - [ ] Working style
   - [ ] Privacy rules (domain-specific)
   - [ ] Tech stack table
   - [ ] Development commands
   - [ ] Architecture overview
   - [ ] Issue workflow
   - [ ] Multi-agent pipeline
   - [ ] Deployment workflow
8. [ ] Set up Tailwind v4 with custom brand colors
9. [ ] Create base template with sidebar + mobile nav
10. [ ] Set up pre-commit hooks
11. [ ] Create first Django app with service layer pattern
12. [ ] Set up Celery + Redis
13. [ ] Write initial tests
14. [ ] Set up CI/CD (GitHub Actions)
15. [ ] Deploy to Hetzner with docker-compose.prod.yml
```

### 9.4 Avoid These Mistakes From Day One

1. **Always build Create + Edit + Detail** for every entity
2. **Always use `grid-cols-1 sm:grid-cols-2`** (never bare `grid-cols-2`)
3. **Define button sizes** with min 44px touch targets from the start
4. **Every data display links to its next action** (alert → fix, recommendation → do)
5. **Audit form fields vs model fields** regularly
6. **Add `responsive` config to all charts** from day one
7. **Build workflow connections** (entity A detail → create entity B pre-filled)
8. **Use `overflow-x-auto`** on every table from the start

---

*Knowledge transfer document generated 2026-03-31 from 7 parallel research agents analyzing: agent system, security, UI/UX, tech stack, project patterns, CLAUDE.md workflow, and deployment.*
*Companion documents: `2026-03-31-roaster-portal-mobile-optimization.md`, `2026-03-31-roaster-portal-logic-audit.md`, `2026-03-31-roastery-software-industry-research.md`*
