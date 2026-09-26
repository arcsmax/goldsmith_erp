# Review 02 — Security Audit (2026-09-24, `main` @ 73fff19)

## Header

**Question answered:** Is Goldsmith ERP secure enough to hold real customer PII, financial data and
design IP on a single-workshop LAN?

**Scope:** backend `src/goldsmith_erp` (auth, RBAC, all 34 routers, middleware, config, encryption,
uploads, labels, logging, portal), frontend `frontend/src` (XSS sinks, token storage, redirects),
deployment (`podman-compose.prod.yml`, `podman-compose.yml`, `deploy/Caddyfile`,
`frontend/nginx.conf`, `frontend/Containerfile.prod`, `Containerfile`, `setup.sh`, backup scripts),
dependencies (yarn, pip-audit, Dependabot).

**Method:** static review only. Every finding below was checked against the current code; line numbers
are from `main` @ `73fff19`. No exploitation was attempted, and no services were started. A route inventory was
built with an AST script over `api/routers/*.py` (it catches decorator guards, `Depends(...)` guards and
the `require_permission_dep as require_permission` alias), then checked by hand.

**Commands run (exit codes):**

| Command | Exit | Note |
|---|---|---|
| `git log --oneline -30` | 0 | fixes for 2.1/2.2/2.7/2.8/2.9/2.10/1.5/1.7-tier1 present |
| AST route-inventory script (scratchpad `inv.py`) | 0 | 243 route handlers found |
| `cd frontend && yarn npm audit --severity high --recursive` | 1 | 1 = advisories found (15 high rows) |
| `poetry run pip-audit` (project venv) | 1 | 1 = 15 vulns in 6 packages |
| `gh api repos/{owner}/{repo}/dependabot/alerts --paginate` | 0 | 1 critical / 20 high / 14 medium open (incl. `docs/architecture/likec4`) |
| grep sweeps (raw SQL, secrets, XSS sinks, PII logging, `Image.open`, `joblib`, `subprocess`) | 0 | results cited inline |

---

## A. Status of prior security findings

Sources: `docs/review/2026-04-23/03-security-audit.md` (03), `docs/review/2026-04-23/07-dependencies-cves.md` (07),
`docs/review/2026-07-26/production-readiness.md` (PR).

| Source + id | Status | Evidence |
|---|---|---|
| PR 1.1 No TLS / reverse proxy, `COOKIE_SECURE` no validator | **FIXED** (with gaps) | Caddy `tls internal` service `podman-compose.prod.yml:152-160`, backend/frontend `expose:` only (`:91`, `:132`); validator `core/config.py:249-271`. Gaps: no HSTS / security headers on the SPA (SEC-06); `setup.sh` prod env cannot boot (F-1) |
| PR 1.5 VIEWER reads scrap-gold values | **FIXED** | `SCRAP_GOLD_VIEW` on every scrap-gold GET (`api/routers/scrap_gold.py:66,244,315,334`); not granted to VIEWER (`core/permissions.py:240-265`). The same class of leak remains elsewhere (SEC-01) |
| PR 1.7 Dependabot 1 crit + 34 high | **PARTIAL** | Now 1 critical + 20 high (section D). Prior runtime P0s fixed: axios 1.18.1, pillow 12.3.0, python-multipart 0.0.32, urllib3 2.7.0, starlette 1.3.1 (`poetry.lock`, `frontend/yarn.lock`) |
| PR 2.1 No token revocation, 8-day JWT | **PARTIAL** | Code fixed: `jti`+`iat` (`core/security.py:48-58`), Redis blocklist + invalid-before (`core/token_revocation.py`), checked in `api/deps.py:82` and `/refresh` (`auth.py:213`), default 30 min (`core/config.py:39`). But `setup.sh:139` writes `ACCESS_TOKEN_EXPIRE_MINUTES=10080` and `.env.example:29` writes `11520`, so a deployed system still has 7-8 day tokens (SEC-03). Revocation fails open (`token_revocation.py:126-133`); the WebSocket skips it (SEC-12) |
| PR 2.2 Financial reads unaudited | **PARTIAL** | materials/time-tracking/users/photos/measurements added (`middleware/audit_logging.py:173-200`); orders/activities audit at service layer (commit 58a67d1). Still no DB audit row for quotes, repairs (costs), metal-inventory, metal-prices, analytics. Analytics only writes a `logger.info` line (`api/routers/analytics.py:27-45`). See SEC-15 |
| PR 2.7 `/docs` public | **FIXED** | `main.py:123-129` (`openapi_url=None` when `DEBUG=False`), `middleware/auth_required.py:22-27` |
| PR 2.8 `camera=()` | **FIXED** | `middleware/security_headers.py:33-35` |
| PR 2.9 CORS wildcard guard | **FIXED** | `core/config.py:273-297` |
| PR 2.10 IP-only rate limiting | **PARTIAL / REGRESSED IN PROD TOPOLOGY** | `(ip, username)` + per-IP ceiling (`auth.py:39-72`). But the key is `slowapi.get_remote_address` = TCP peer, and in prod that peer is always the nginx container (SEC-04). Other mutating endpoints are still not limited |
| 03 P0 `/users/register` public | **FIXED** | removed from `PUBLIC_PATHS` (`auth_required.py:30-41`); handler needs `USER_CREATE` (`users.py:42`) |
| 03 P0 duplicate Permission enums | **FIXED** | `api/deps.py` has no Permission; alias factory `core/permissions.py:332-374` |
| 03 P0 weak compose DB password / DB on 0.0.0.0 | **FIXED** (DB) / **OPEN** (Redis) | `podman-compose.yml:13,21` (`:?` + `127.0.0.1`). Redis still `0.0.0.0:6379`, no auth (`podman-compose.yml:37-38`) (SEC-08) |
| 03 P1 WebSocket `?token=` fallback | **OPEN** | `main.py:288-290` |
| 03 P1 Portal numeric-ID enumeration | **OPEN** | `customer_portal.py:322-336`, limit `10/minute` (`:375`) (SEC-10) |
| 03 P1 Unbounded `limit` | **OPEN** | `activities.py:51`, `comments.py:27`, `materials.py:66`, `orders.py:95`, `users.py:164`, `time_tracking.py:99,127` (SEC-16) |
| 03 P1 AuditLoggingMiddleware not registered | **FIXED** | `main.py:148-150` |
| 03 P1 7-day tokens / no revocation | **PARTIAL** | see PR 2.1 |
| 03 P1 `delete_cookie` flags | **OPEN** (low) | `auth.py:162` |
| 03 P1 Permissions-Policy camera | **FIXED** | see PR 2.8 |
| 03 P1 docs public | **FIXED** | see PR 2.7 |
| 03 P1 No role-assignment endpoint | **OPEN** (functional) | `UserUpdate` has no `role` (`models/user.py:119-160`); DB default VIEWER (`db/models.py:191`). Only `scripts/create-admin.py:73` sets a role |
| 03 P2 CSP gaps (`ws:`/`wss:` any host, no `base-uri`/`form-action`, no HSTS) | **OPEN** | `security_headers.py:16-24`. The SPA document gets **no** headers at all (SEC-06) |
| 03 P2 `logo_url` unrestricted scheme | **OPEN** (low) | `theme.py:85-89` |
| 03 P2 photo path traversal guard | **FIXED** | `services/image_validation.py` `resolve_within_root` |
| 03 P2 `is_active` not checked in middleware | **MITIGATED** | every non-public route resolves `get_current_user` (inventory, B) |
| 03 P2 timing leak in portal / email length | **OPEN** (low) | not re-derived |
| 03 open-q `auth/mfa` dead public prefix | **OPEN** (low) | `auth_required.py:48` |
| 03 open-q `.dockerignore` lacks `.env` | **MOOT** | backend `Containerfile:28-33` copies only `pyproject/poetry.lock/README/src/alembic` |
| 07 axios / react-router / vite P0-P1 | **FIXED** | axios 1.18.1, react-router 7.15.1, vite 7.3.6. New react-router advisories exist (D) |
| 07 urllib3 / pillow / python-multipart P1 | **FIXED** | see PR 1.7 |
| 07 python-jose + ecdsa (unmaintained, Minerva) | **OPEN** | `pyproject.toml:29`; imported in `core/security.py:5`, `auth.py:6`, `deps.py:5`, `main.py:11`. HS256 only, so ecdsa is not reachable |
| 07 passlib abandoned, pins bcrypt 4 | **OPEN** | `pyproject.toml:23`, bcrypt 4.3.0 |
| 07 Redis `7-alpine` unpinned (7.4 EOL 2026-11-30) | **OPEN** | `podman-compose.prod.yml:39` |
| 07 Poetry unpinned in Containerfile | **OPEN** (not re-verified in depth) | `Containerfile:24` |
| PR 2.12 plaintext signature/financial columns | **OPEN** | SEC-14 |

---

## B. Route authorization inventory

**Totals:** 243 route handlers across 34 router modules.

| Guard type | Count |
|---|---|
| `@require_permission(...)` decorator + `Depends(get_current_user)` | 179 |
| `Depends(require_permission_dep(...))` (aliased as `require_permission` in customers, measurements, metal_inventory, metal_prices, metal_types) | 39 |
| `Depends(get_current_admin_user)` | 9 |
| Authenticated, self-scoped only (`/users/me` GET/PUT) | 2 |
| **Intentionally public** (middleware whitelist) | 6: `POST /login/access-token`, `POST /logout`, `POST /refresh`, `POST /portal/lookup`, `GET /portal/status/{token}`, `GET /theme`, plus `GET /health` |
| Middleware-authenticated only, no role check | 7 in `health.py`: `/health/detailed`, `/liveness`, `/readiness`, `/startup`, `/version`, and `POST /admin/notify-backup` + `/admin/notify-gdpr-cleanup` (`health.py:292,368`; these also require `client.host` to be loopback) |

Every decorated route also resolves `get_current_user`; the inventory found zero decorated routes without
it. That dependency does the revocation check, so no REST route accepts a revoked token. The only
authenticated surface that skips revocation is the WebSocket (SEC-12).

**Unguarded mutating routes:** none. The two `notify-*` POSTs need a valid JWT from the middleware and a
loopback peer, so no user can reach them in the prod topology. See F-4 for the functional side effect.

**Under-guarded routes (the permission is too broad for the data returned).** VIEWER holds `ORDER_VIEW`,
`MATERIAL_VIEW`, `CUSTOMER_VIEW`, `REPORTS_VIEW`, `REPAIR_VIEW` (`core/permissions.py:240-265`):

| Route | Guard | Data returned that CLAUDE.md reserves for ADMIN/GOLDSMITH |
|---|---|---|
| `GET /orders/{id}/comparison` (`analytics.py:71`) | REPORTS_VIEW | `material_cost`, `total_price` (`models/comparison.py:101-105`). The docstring says "ADMIN und GOLDSMITH" |
| `GET /analytics/workshop-stats` (`analytics.py:114`) | REPORTS_VIEW | cost deviations |
| `GET /repairs/{id}` (`repairs.py:92`) | REPAIR_VIEW | `estimated_cost`, `actual_cost`, `estimated_value` (`models/repair.py:228-246`). The schema docstring claims "router enforces GOLDSMITH/ADMIN", but the router does not |
| `GET /materials/`, `/materials/{id}`, `/materials/purchase-list` (`materials.py:64,114,162`) | MATERIAL_VIEW | `unit_price` |
| `GET /materials/analytics/stock-value` (`materials.py:446`) | MATERIAL_VIEW | total stock value in EUR |
| `GET /metal-inventory/purchases[/{id}]` (`metal_inventory.py:100,154`) | MATERIAL_VIEW | `price_total`, `price_per_gram`, `remaining_value` (`models/metal_inventory.py:54,116,124`) |
| `GET /metal-inventory/usage` (`metal_inventory.py:335`) | ORDER_VIEW | `cost_at_time`, `price_per_gram_at_time` (`models/metal_inventory.py:301-302`) |
| `GET /metal-inventory/statistics` (`metal_inventory.py:385`) | MATERIAL_VIEW | `total_value`, `average_price_per_gram` |
| `GET /customers/top?by=revenue`, `GET /customers/{id}/stats` (`customers.py:109,163`) | CUSTOMER_VIEW | `total_spent` per customer (`services/customer_service.py:758-767,843`) |
| `GET /orders/{id}` description + `GET /orders/{id}/photos`, `/photos/{id}/file` (`photos.py:115,138,181`) | ORDER_VIEW | design IP (order description, design photos) |
| `GET /valuations/{id}/pdf` (`valuations.py:298`) | VALUATION_VIEW | GOLDSMITH can export valuation PDFs; CLAUDE.md says "Exportable only by ADMIN". The deviation is deliberate and documented at `valuations.py:12-15` |

**Object-level authorization (IDOR):** this is a single-tenant workshop, so row-level ownership only
matters for per-user data. Notifications, handoffs, time-entry reads (`time_tracking.py:134,183`) and
scan-driven time mutations (`services/time_tracking_service.py:605,760,845`) are scoped to the owner.
Owner checks are missing on `POST /time-tracking/{id}/stop`, `PUT /time-tracking/{id}` and
`POST /time-tracking/{id}/interruptions` (SEC-13). UUID ids reduce the practical risk.

---

## C. New findings

Severity uses CVSS-style reasoning: attack vector LAN/adjacent, privileges needed, and impact on C/I/A.
Several findings are **policy-critical** because they break a non-negotiable CLAUDE.md data-privacy rule
even where the CVSS-style impact is moderate. This is noted per item.

### SEC-01 — HIGH — VIEWER role reads financial data on 11 endpoints that bypass the order projection

- **Evidence:** see the table in section B. Example, `api/routers/analytics.py:70-81`:
  ```python
  @require_permission(Permission.REPORTS_VIEW)
  async def get_order_comparison(...):
      """... Zugriffsrechte: ADMIN und GOLDSMITH (REPORTS_VIEW)."""
  ```
  `REPORTS_VIEW` is granted to VIEWER at `core/permissions.py:246`. `RepairJobRead` returns
  `estimated_cost/actual_cost/estimated_value` to anyone holding `REPAIR_VIEW` (`repairs.py:92-104`).
  The C5 fix only strips financial fields from `/orders*` (`orders.py:44-82`).
- **Attack scenario:** a front-desk or apprentice VIEWER account (or anyone who picks up that
  session on a shared tablet) opens `/api/v1/orders/42/comparison` or `/api/v1/metal-inventory/purchases`.
  They get calculated vs. final prices, material purchase prices and customer lifetime revenue. That is
  exactly the scrap-gold issue (PR 1.5) in more places.
- **Fix:** add `FINANCIAL_VIEW` (or reuse `INVOICE_VIEW`) for `analytics/*`, `metal-inventory/purchases|usage|statistics`,
  `materials/analytics/stock-value` and `customers/top?by=revenue`. Role-project `unit_price`
  (materials), repair costs and `total_spent` the same way `_financial_excludes_for_user` does. Add
  one parametrised test that walks every GET route as VIEWER and asserts no key from a
  financial-field denylist appears in the response.
- **Effort:** M. **Confidence:** high. **Interim mitigation:** create no VIEWER accounts.

### SEC-02 — HIGH (config-dependent) — `.env.example` SECRET_KEY placeholder is accepted in production, which allows admin JWT forgery

- **Evidence:** `core/config.py:393-400`:
  ```python
  if v == "CHANGE_THIS_TO_A_SECURE_RANDOM_STRING_AT_LEAST_32_CHARS":
      logging.getLogger(__name__).warning(...)
      return v
  ```
  This runs regardless of `DEBUG`. The same public string is at `.env.example:26`. README, `docs/DEPLOYMENT.md:105`
  and `INSTALLATION.md:225,454,643` all say `cp .env.example .env`. `ANONYMIZATION_SALT` has the same
  placeholder (`.env.example:130`) and no placeholder check at all (`config.py:226-247`).
- **Attack scenario:** an operator sets up by hand (likely, because the `setup.sh` path does not boot,
  see F-1). They copy `.env.example`, set `DEBUG=false` and supply `ENCRYPTION_KEY`, and the backend
  boots with a signing key published on GitHub. Anyone on the LAN can mint
  `{"sub":"1","exp":...,"jti":"x","iat":...}` with HS256 and act as the first user (the admin),
  including GDPR export of all customers. Revocation does not help, because the token is newly minted.
- **Fix:** in `validate_secret_key`, hard-reject the placeholder when `DEBUG=False`. The validator
  cannot see `DEBUG` in field order, so do it in a `model_validator(mode="after")`. Add the same
  check for `ANONYMIZATION_SALT`. Add a test for each.
- **Effort:** S. **Confidence:** high on code, medium on likelihood.

### SEC-03 — MEDIUM — Deployed token lifetime is still 7-8 days; the 30-minute fix is overridden by the shipped env files

- **Evidence:** `setup.sh:139` writes `ACCESS_TOKEN_EXPIRE_MINUTES=10080`. `.env.example:28-29` writes `11520`
  with the comment "default: 8 days". The code default is 30 (`core/config.py:39`). Revocation fails open
  if Redis is down (`core/token_revocation.py:126-133`, `AUTH_REVOCATION_FAIL_CLOSED=False` at `config.py:48`).
- **Attack scenario:** a token captured from a shared workshop device, a browser profile or a backup
  of browser state stays valid for 7 days. If Redis restarts (allkeys-lru, 64 MB,
  `podman-compose.prod.yml:41`) the blocklist can be evicted or lost, and logged-out tokens work again.
- **Fix:** drop the line from `setup.sh` (or set 30), and fix `.env.example`. Use `noeviction` for
  Redis, or keep the auth keys in a separate DB/instance so LRU cannot evict revocation entries.
  Consider `AUTH_REVOCATION_FAIL_CLOSED=true` in prod.
- **Effort:** S. **Confidence:** high.

### SEC-04 — MEDIUM — In the prod topology all rate limits key on the nginx container IP: global lockout and login DoS

- **Evidence:** `auth.py:30,57` and `customer_portal.py:43` use `slowapi.util.get_remote_address`
  (= `request.client.host`). Prod traffic is Caddy → nginx → backend (`deploy/Caddyfile:44`,
  `frontend/nginx.conf` `/api/` block). Uvicorn runs without `--forwarded-allow-ips` / `FORWARDED_ALLOW_IPS`
  (`podman-compose.prod.yml:79-82`; grep found none), so it only trusts `127.0.0.1`. Every request
  therefore appears to come from the nginx container IP. The anti-spoof `get_real_ip` helper exists
  (`middleware/rate_limiting.py:41-63`), but the limiters do not use it. The limiter storage is
  in-memory and per worker (`--workers 2`), so the effective limits are also doubled.
- **Attack scenario:** anyone on the workshop Wi-Fi sends 5 wrong passwords per minute for
  `anne@...`. The `(ip, username)` bucket is really `(nginx, username)`, so Anne cannot log in from
  any device. 20 requests/minute of random logins block every login in the workshop. The same applies
  to the portal (10/min global).
- **Fix:** pass `--proxy-headers --forwarded-allow-ips=<compose subnet>` (or set `FORWARDED_ALLOW_IPS`)
  and switch key functions to `get_real_ip`. Point slowapi at Redis (`storage_uri=settings.REDIS_URL`).
  Also add `limit_req` in nginx for `/api/v1/login`.
- **Effort:** S. **Confidence:** high (static; not runtime-verified).

### SEC-05 — MEDIUM (policy-critical) — Customer PII written to logs through request URLs

- **Evidence:** `middleware/logging.py:41-48,63-70,79-86` logs `"url": str(request.url)` (query string
  included) on every request, both incoming and completed. The frontend sends customer search terms as
  query params (`frontend/src/api/customers.ts:38` → `GET /customers/search?q=...`, `customers.py:83-86`).
  Repair/scanner searches do the same (`repairs.py:69`, `scanner.py:296`).
- **Attack scenario:** anyone who can read container logs (`podman logs`, json-file under the user's
  storage, or support bundles shared for debugging) gets customer names, emails and phone numbers in
  plaintext. That contradicts "NEVER log customer PII in plaintext", and GDPR erasure does not reach it.
- **Fix:** log `request.url.path` plus a redacted/allow-listed set of query keys. Add a test that
  searches for a sentinel name and asserts it is absent from captured logs.
- **Effort:** S. **Confidence:** high.

### SEC-06 — MEDIUM — The SPA document is served with no security headers (no CSP, no frame protection, no HSTS)

- **Evidence:** `frontend/nginx.conf` sets only `Cache-Control` (lines 37, 44). `deploy/Caddyfile` sets
  no headers. `SecurityHeadersMiddleware` (`middleware/security_headers.py`) only decorates backend
  (`/api`, `/uploads`, `/ws`) responses. `index.html:4-11` has an inline script, which is why a CSP was
  never applied to the document.
- **Attack scenario:** any other page reachable by workshop browsers (a second LAN service, or a
  phishing page) can frame `https://<erp>/` and clickjack the admin UI, for example "Kunde löschen"
  or GDPR erase. The React app also has no CSP backstop, so a `javascript:` URL in `material.webshop_url`
  (unvalidated, `models/material.py:41-43`, rendered at `MaterialsPage.tsx:83,411,426`) runs when
  clicked. React 18 only warns about these URLs and still renders them.
- **Fix:** in `nginx.conf` `server{}`, add `add_header ... always` for `Content-Security-Policy`
  (`default-src 'self'; script-src 'self' 'sha256-<inline theme script>'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; connect-src 'self'`),
  `X-Frame-Options DENY`, `X-Content-Type-Options nosniff`, `Referrer-Policy`, and
  `Strict-Transport-Security` (or set it in Caddy `header`). Validate `webshop_url`/`logo_url` to `^https?://`.
- **Effort:** S. **Confidence:** high.

### SEC-07 — MEDIUM — Stored HTML injection in printable labels (unescaped `order.title`, `repair.item_description`, customer name)

- **Evidence:** `services/label_service.py:278-282,346-350` builds HTML with f-strings, for example
  `<div class="label-title">{order.title}</div>`. The only filter on `title` is a SQL-keyword blocklist
  (`models/order.py:49-76`), and `item_description` is only stripped (`models/repair.py:157-163`). The
  pages are served same-origin via `GET /orders/{id}/label` (`orders.py:333-362`) and `GET /repairs/{id}/label`.
- **Attack scenario:** a GOLDSMITH, or a CSV import, sets an order title to
  `<form action=/api/v1/...><input ...><button>Drucken</button></form>` or a `<meta http-equiv=refresh>`
  to a credential-phishing page, and the admin opens the label. Today the backend CSP `script-src 'self'`
  (`security_headers.py:18`) blocks inline script and event handlers, so this is HTML/CSS injection
  rather than XSS. Any relaxation of that CSP turns it into same-origin stored XSS against the admin.
  The same CSP also blocks the label's own `window.print()` script (`label_service.py:187-192`), a
  functional bug that will push someone to add `'unsafe-inline'`.
- **Fix:** wrap every interpolated value in `html.escape()`, or render through the existing Jinja env
  with `autoescape=True`. Move the print script to a static `/static/label-print.js`, or use a CSP hash.
- **Effort:** S. **Confidence:** high (injection), medium (exploitability).

### SEC-08 — HIGH (only if the dev stack is used with real data) — Dev compose exposes unauthenticated Redis and plain-HTTP backend to the LAN

- **Evidence:** `podman-compose.yml:37-38` publishes `"${REDIS_EXT_PORT:-6379}:6379"` (all interfaces,
  no `requirepass`). Backend: `:69-70` publishes `8000:8000` and `:79` sets `DEBUG=${DEBUG:-true}`, which
  turns every prod validator (ENCRYPTION_KEY, COOKIE_SECURE, CORS, SALT) into a warning and publishes
  `/docs`. `docker-compose.yml:25-26,41-42` is the same. README lines 113-140 label this the quick start.
- **Attack scenario:** a laptop on the workshop Wi-Fi runs `redis-cli -h <box>` and can
  `DEL auth:jti:blocklist:*` (un-revoke stolen tokens), rewrite `cache:*` entries for materials,
  activity hourly rates and metal prices (`core/cache.py` users: `material_service.py:11`,
  `activity_service.py:9`, `metal_price_service.py:31`), which silently corrupts quotes and estimates,
  `KEYS portal_token:*`, or publish forged `order_updates` to every WebSocket client. Credentials and
  cookies also cross the LAN unencrypted.
- **Fix:** bind dev Redis/backend/frontend to `127.0.0.1` by default. Add a boot-time refusal to run
  with `DEBUG=true` when the customers table has more than N rows, or when not on loopback. State plainly
  in README that the dev stack must never hold real data.
- **Effort:** S. **Confidence:** high (config); likelihood depends on how Anne's box is actually run.

### SEC-09 — MEDIUM (policy-critical) — Design IP visible to VIEWER

- **Evidence:** `orders.py:44-66` strips only price fields, so `description` (design description,
  "business-confidential" per CLAUDE.md) is returned to VIEWER. Order photos and files are gated by `ORDER_VIEW`
  (`photos.py:115,138,181`). CLAUDE.md: "Custom jewelry designs ... access-controlled (GOLDSMITH or ADMIN only)".
- **Attack scenario:** a VIEWER downloads all design photos of commissioned pieces via
  `/api/v1/photos/{id}/file` by iterating ids.
- **Fix:** add a `DESIGN_VIEW` permission (ADMIN, GOLDSMITH) for photo file/thumbnail and `description`,
  and project `description` out for other roles.
- **Effort:** S-M. **Confidence:** high.

### SEC-10 — LOW-MEDIUM — Public customer portal is still mounted although the product decision is "no live portal"

- **Evidence:** `main.py:259-263` mounts it, and it is whitelisted at `auth_required.py:57-60`. The lookup accepts the numeric
  auto-increment order id plus email (`customer_portal.py:322-336`) and returns `order.title` /
  the first 60 characters of `repair.item_description` (`:219, :258`), which can carry design detail. The rate limit is effectively global (SEC-04).
- **Attack scenario:** on the LAN (it is not internet-exposed behind Caddy), someone who knows a
  customer's email can walk order ids 1..N at about 10 per minute and confirm which orders belong to
  that customer, along with their titles.
- **Fix:** put the router behind `settings.PORTAL_ENABLED=False` (default) until V-next. When enabled, use opaque
  public references and per-reference failure counters.
- **Effort:** S. **Confidence:** high.

### SEC-11 — MEDIUM — `PUT /users/me` changes email and password without re-authentication

- **Evidence:** `users.py:90-124` accepts `UserUpdate.email`/`password` (`models/user.py:119-131`) with
  no `current_password` check. Changing the password then revokes every other session of that user (`:123-124`).
- **Attack scenario:** a colleague finds Anne's session open on the shared bench tablet. One request
  sets a new email and password, logs Anne out everywhere, and takes the ADMIN account permanently.
  Recovery needs DB access.
- **Fix:** require `current_password` for any email or password change (verify with bcrypt). Audit-log
  the event, and email the old address.
- **Effort:** S. **Confidence:** high.

### SEC-12 — LOW — WebSocket auth skips revocation and `is_active`, and still accepts `?token=`

- **Evidence:** `main.py:286-298` only does `jwt.decode`, with no `is_token_revoked` and no user
  lookup. The query-param fallback is at `:289-290` (the frontend never uses it).
- **Attack scenario:** a deactivated or logged-out user keeps receiving the `order_updates` stream
  (order ids, statuses, locations, `services/order_service.py:222-235,654-662`) until the token
  expires, which is up to 7 days (SEC-03).
- **Fix:** reuse `get_current_user` logic (revocation + active check) in `_authenticate_websocket`,
  drop the query-token path, and check `Origin` against `BACKEND_CORS_ORIGINS`.
- **Effort:** S. **Confidence:** high.

### SEC-13 — LOW — Time-entry mutations lack an owner check

- **Evidence:** `time_tracking.py:60-81` (stop), `:210-222` (PUT, TIME_EDIT held by GOLDSMITH) and
  `:239-254` (interruptions) call the service without ownership. `stop_time_entry`/`update_time_entry`
  (`services/time_tracking_service.py:143-160,428-436`) look up by id only.
- **Attack scenario:** a goldsmith who learns a colleague's entry UUID (from a shared screen or
  export) edits their hours, which changes labor cost and the estimator corpus.
- **Fix:** enforce `entry.user_id == current_user.id or has_permission(TIME_VIEW_ALL/ADMIN)` in the
  three handlers.
- **Effort:** S. **Confidence:** high (UUID ids keep exploitability low).

### SEC-14 — MEDIUM — Data-at-rest gaps: plaintext signatures and financial columns, unencrypted backups

- **Evidence:** plaintext `ScrapGold.signature_data` (`db/models.py:1157`), `Quote.customer_signature_data`
  (`:1494`), `Customer.notes`/`birthday` (`:268,287`), and `CustomerUpdate.body` (`:2704`, contains customer
  names). Scrap-gold values are also plaintext (PR 2.12 still open). `scripts/backup.sh:69-71` writes
  `pg_dump | gzip` with no encryption and default umask. `scripts/backup-sync.sh:58-64` PUTs that file
  to `BACKUP_CLOUD_URL` without client-side encryption. There is no key rotation path for
  `ENCRYPTION_KEY` (no MultiFernet, and the blind index is derived from the same key,
  `core/encryption.py:104-124`; `rotate-secrets.sh:5-7` explicitly skips it).
- **Attack scenario:** someone with the backup directory (USB copy, cloud bucket, stolen NAS) gets
  handwritten customer signatures, customer notes and message bodies in clear. They do not need
  `ENCRYPTION_KEY`.
- **Fix:** encrypt the signature columns and `Customer.notes`/`CustomerUpdate.body` (EncryptedString,
  migration). Pipe backups through `age -r <pubkey>` (key held off-box), `chmod 600`. Document a
  MultiFernet rotation plan with a separate `BLIND_INDEX_KEY`.
- **Effort:** M. **Confidence:** high.

### SEC-15 — LOW — Remaining audit-log gaps for financial reads

- **Evidence:** quotes, repairs, metal-inventory, metal-prices and analytics are not in `_RESOURCE_ROUTES`
  (`middleware/audit_logging.py:121-200`). Analytics "audit" is a `logger.info` only (`analytics.py:27-45`).
- **Fix:** register the families, or call `write_financial_audit_row` in those handlers.
- **Effort:** S. **Confidence:** high.

### SEC-16 — LOW — Unbounded `limit` on 7 authenticated list endpoints (prior P1, still open)

- **Evidence:** section A row. Example `orders.py:95` `limit: int = 100` with no `le=`.
- **Attack scenario:** an authenticated user requests `?limit=10000000` and the 512 MB backend is OOM-killed (restart loop).
- **Fix:** `Query(100, ge=1, le=500)`. **Effort:** S. **Confidence:** high.

### SEC-17 — LOW — Login timing oracle for account enumeration

- **Evidence:** `auth.py:86-93` returns before any bcrypt call when the email is unknown. Known
  users pay about 250 ms of bcrypt (`:95`).
- **Fix:** verify against a static dummy hash when the user is missing. **Effort:** S. **Confidence:** high.

### SEC-18 — LOW — Image decompression bomb headroom vs 512 MB container

- **Evidence:** uploads are capped at 8 MB (`image_validation.py:97-103`), but `Image.open` →
  `convert("RGB")` / `resize` (`:166-180`) uses the Pillow default `MAX_IMAGE_PIXELS` (about 89 Mpx
  warns, about 179 Mpx errors). A roughly 150 Mpx PNG fits in 8 MB and decodes to about 450 MB, near
  the backend limit (`podman-compose.prod.yml:114`). Decoding also runs synchronously on the event loop.
- **Fix:** set `Image.MAX_IMAGE_PIXELS = 40_000_000` and treat `DecompressionBombWarning` as an error.
  Run thumbnailing in `run_in_threadpool`.
- **Effort:** S. **Confidence:** medium (unverified at runtime).

**Verified clean (no finding):** no raw SQL with user input (only constant `text()` in health checks and
server defaults); JWT alg pinned to HS256 in all decode sites; no `dangerouslySetInnerHTML`/`innerHTML`
in `frontend/src`; no token in `localStorage` (only `user` metadata); login returns no token body;
magic-byte upload validation with path-anchored serving; CSV import is ADMIN-only with a 5 MB cap;
CSV exports carry no user free text (`accounting_export_service.py:186,248`); email Jinja uses
`autoescape=True` (`email_service.py:110`); `joblib.load` only reads a server-side model dir (no
upload path); backup trigger uses `create_subprocess_exec` with a fixed script list; no hardcoded
secrets in `src`/`frontend/src`/`scripts` (only a doc example in `create-admin.py:6` and dev fallback
`restore.sh:39`); containers run non-root with `no-new-privileges`; prod DB/Redis/backend not published.

---

## D. Dependency audit results

```text
$ cd frontend && yarn npm audit --severity high --recursive   # exit 1
 brace-expansion x3  (DoS)                         via minimatch 5.1.9/10.2.5      build/dev
 browserslist x2     (OOM / prototype write)       via @babel/helper-compilation-targets  build
 fast-uri x5         (host confusion / SSRF)       via ajv 8.18.0 (workbox-build)  build
 lodash 4.17.23      (_.template code injection)   via workbox-build 7.4.0         build
 nanoid x2           (infinite loop)               via postcss                      build
 postcss 8.5.15      (source-map path traversal)   via vite 7.3.6                   build/dev
 react-router 7.15.1 GHSA-chx6-hx7r-mcp5 DoS via route matching  (<7.18.0)          RUNTIME (client)
 react-router 7.15.1 GHSA-qwww-vcr4-c8h2 RSC-mode CSRF bypass    (<7.18.2)          RUNTIME, RSC not used

$ poetry run pip-audit   # exit 1
Found 15 known vulnerabilities in 6 packages
anyio        4.11.0  CVE-2026-63374, CVE-2026-64847      fix 4.14.2
click        8.3.0   PYSEC-2026-2132                     fix 8.3.3
cryptography 48.0.1  PYSEC-2026-3552/3553/3554           fix 49.0.0 / 50.0.0
ecdsa        0.19.2  PYSEC-2026-1325 (Minerva)           no fix
pip          26.1.2  PYSEC-2026-3721                     fix 26.2
pytest       8.4.2   PYSEC-2026-1845                     fix 9.0.3

$ gh api .../dependabot/alerts   # exit 0 — open: 1 critical, 20 high, 14 medium
critical pip anyio  "TLSStream IDNA 2003 host name encoding enables potential TLS certificate spoofing" (<4.14.2)
high     pip cryptography "PKCS#7 EnvelopedData decryption ... Bleichenbacher oracle" (>=44,<50)
high     pip ecdsa "Minerva timing attack on P-256" (no patch)
high     npm react-router (x2), fast-uri (x5), nanoid (x2), browserslist, lodash, postcss  (frontend/yarn.lock)
high     npm browserslist, playwright, postcss, vite  (docs/architecture/likec4/package-lock.json — docs tooling)
```

**Summary:**
- **Runtime-reachable and worth bumping now:** `anyio` → 4.14.2. It is used by httpx for outbound TLS in
  `metal_price_service.py:234`; the host is a fixed ASCII name, so practical exploitability is low,
  but it is the only critical and the bump is trivial. `react-router-dom` → ≥7.18.2 (client-side
  DoS only, SPA mode). `cryptography` → 50 (the PKCS#7 path is not used; this is hygiene).
- **Not reachable:** `ecdsa` comes in through `python-jose[cryptography]`, and the app only signs HS256.
  Remove python-jose, migrate the four imports to `pyjwt` (already a dependency, 2.13.0), and ecdsa
  goes with it. `passlib` is still abandoned and holds bcrypt at 4.x.
- **Build/dev only:** every other frontend high (workbox-build, babel, vite/postcss) and pytest/pip/click.
  Fix with `yarn up` / `yarn dedupe` in a routine pass. The likec4 docs lockfile accounts for 4 of the
  highs and could be deleted or `.github/dependabot.yml`-ignored.
- Compared with 2026-07-26 (1 crit + 34 high), the Tier-1 bump landed. No dependency blocks go-live.

---

## E. Overall verdict

**Not yet, but close: days of work, not weeks.** The foundations are real and verified: deny-by-default
middleware, pinned-alg JWT in HttpOnly SameSite=Strict cookies, revocation, 227/243 routes behind an
explicit permission plus 2 self-scoped, Fernet encryption with blind index on customer PII and valuations,
a TLS reverse proxy in the prod compose with nothing else published, magic-byte uploads with
path anchoring, no SQLi/XSS sinks, and fail-fast prod validators. No finding gives an unauthenticated
remote attacker access in the intended prod deployment.

What stops "real customer data on the LAN today" is a set of deployment-wiring and policy gaps:

**Minimum fixes before real data (all S effort except the first):**
1. **SEC-01 + SEC-09:** close the VIEWER financial and design-IP leaks. The interim alternative is to
   create no VIEWER accounts and document that.
2. **SEC-02:** reject the placeholder SECRET_KEY/ANONYMIZATION_SALT when `DEBUG=False`.
3. **F-1 + SEC-03:** make `setup.sh` produce a bootable `.env.production` (add `ANONYMIZATION_SALT`,
   drop `ACCESS_TOKEN_EXPIRE_MINUTES=10080`), so the hardened path is the one actually used.
4. **SEC-04:** trust the proxy chain and key the limiters on the real client IP.
5. **SEC-05:** stop logging query strings.
6. **SEC-06 + SEC-07:** security headers on the SPA in nginx; escape label HTML.
7. **SEC-11:** require the current password for credential changes.
8. **Operational rule (SEC-08):** real data only ever on `podman-compose.prod.yml`; never the dev stack.

Everything else (SEC-10, 12-18, dependency hygiene) belongs in the first-weeks backlog.

---

## F. Things the user might have missed

1. **F-1: the production install path cannot boot.** `setup.sh:130-176` writes `.env.production` without
   `ANONYMIZATION_SALT`, and `core/config.py:236-241` raises when it is unset and `DEBUG=False`. No doc
   mentions it (`grep` in `docs/technical/infrastructure/*.md` is empty). Static finding, not run.
   Operators hitting this will hand-edit env files, which is exactly the SEC-02 trap.
2. **F-2: uploads larger than 1 MB will fail in prod.** `frontend/nginx.conf` sets no `client_max_body_size`
   (nginx default 1 m), but photos allow 8 MB and materials 10 MB. Users will see 413 errors, and the
   likely "quick fix" is a proxy change that someone might make carelessly.
3. **F-3: the label print script is blocked by the app's own CSP** (SEC-07). Expect pressure to add
   `'unsafe-inline'`. Fix the escaping first.
4. **F-4: backup and GDPR-failure notifications never arrive.** `backup.sh:51-55` curls
   `http://localhost:8000/...` without a JWT (middleware returns 401) and from the host, where the backend
   is `expose`-only. The backend Containerfile also does not copy `scripts/`, so `POST /admin/trigger-backup`
   always returns "backup script not found" (`health.py:246-262`). `setup.sh` writes `CLOUD_SYNC_URL`
   but `backup.sh`/`backup-sync.sh` read `BACKUP_CLOUD_URL`, so off-site sync is silently off.
5. **F-5: `PUT /admin/email-config` mutates `settings` in one worker only** (`admin_email.py:129-136`,
   `--workers 2`). SMTP changes apply at random and are lost on restart. This is a correctness issue,
   and a security one for audit trails.
6. **F-6: there is no way to assign roles through the API.** New users default to VIEWER
   (`db/models.py:191`), so either everyone is promoted by SQL (bypassing audit) or VIEWER accounts
   exist and SEC-01 applies. Check the live DB for how roles were actually set.
7. **F-7: Caddy `tls internal` + `on_demand`** is fine on LAN, but the root-CA key lives in the
   `caddy_data` volume. Include it in the backup and restore plan, or every device must re-trust it after
   a rebuild.
8. **F-8: SameSite=Strict on an IP-addressed site** treats any other service on the same host IP
   (different port) as same-site. Do not co-host other web apps on the ERP box.
9. **F-9: original photos keep EXIF/GPS.** Only the email variant strips it (`image_validation.py:185-195`).
10. **F-10: demo seed accounts use the known password `demo2026!`** (`scripts/seed_demo.py:165-183`). If
    the running demo DB is ever promoted to real use, rotate or delete those accounts first.

---

## Verification (2026-09-25)

Verifier: `.orchestrated-fable/ux-erp-audit-2026-09/verify-security-gdpr.md` (adversarial, read-only, HEAD `73fff19`; SEC-02 live-executed with `Settings()`). No finding dropped or downgraded.

| ID | Title (short) | Claimed | Verdict | Corrected severity | Verifier note |
|---|---|---|---|---|---|
| SEC-01 | VIEWER reads financial data on 11+ endpoints | HIGH | CONFIRMED | HIGH | The order projection (`_FINANCIAL_FIELDS`, 7/7 tests pass) is the only endpoint family with one; `GET /repairs/{id}` has no field-stripping path at all; no global response hook exists |
| SEC-02 | SECRET_KEY placeholder accepted in production: admin JWT forgery | HIGH (config-dependent) | CONFIRMED | **CRITICAL** | Live-verified: `Settings(SECRET_KEY=<placeholder>, DEBUG=False, ...)` boots and only logs a warning. Reachable by following the documented setup and skipping one step |
| SEC-08 | Dev compose exposes unauthenticated Redis and plain-HTTP backend | HIGH (conditional) | CONFIRMED | HIGH | Both compose files; `db:` binds 127.0.0.1 with a comment, so the Redis/backend omission looks like an inconsistency, not a choice |

**New while verifying:** `ANONYMIZATION_SALT` set to the same placeholder with `DEBUG=False` boots with **no warning at all** (command 6). Folded into SEC-02; fix both in one patch (plan item W1-01).

The F-items (F-1 to F-10) and MEDIUM/LOW findings were outside the verifier's scope. In the register, F-1, F-2, F-4 to F-8 and F-10 are tracked as SEC-F1 and so on; F-3 is folded into SEC-07 and F-9 into GDPR-19.
