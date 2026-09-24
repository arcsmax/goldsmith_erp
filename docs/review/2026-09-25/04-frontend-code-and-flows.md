# Review 04: Frontend code quality, correctness, UX-flow mechanics (2026-09-24)

**Scope:** `frontend/` at HEAD `73fff19` (main). App shell, data layer, types, forms, all 23 page files, components, tests, build/PWA, and the five product flows (a)-(e). The visual/design-system audit is out of scope (separate agent).
**Method:** static read of the code with every claim checked at file:line. I cross-checked against the backend (`src/goldsmith_erp/…`) wherever a frontend behaviour depends on a backend contract. I also scripted a field diff of 10 frontend interfaces against their Pydantic read schemas. No repo files were edited. The only side effect is `frontend/dist/` from the build (gitignored).

**Stack correction:** the brief says Vite 5. Actual versions: **Vite ^7.3.5, Vitest ^4.0.10, Tailwind 4 (`@tailwindcss/vite`), MSW 2, happy-dom** (`frontend/package.json`).

## Commands run

| Command | Exit | Notes |
|---|---|---|
| `cd frontend && yarn tsc --noEmit -p tsconfig.json` | **0** | 3.8 s, 0 errors |
| `yarn vitest run --reporter=dot` | **0** | 48 files, **485/485 passed**, 5.2 s. One `act()` warning in ScannerContext.test |
| `yarn build` | **127** | `Command not found: vite`. Yarn 4 install-state drift in this checkout (`frontend/.yarn/install-state.gz` is modified per git status). `node_modules/.bin/vite` exists |
| `node node_modules/vite/bin/vite.js build` (same build, bypassing yarn's bin resolution) | **0** | 1.8 s. PWA: precache 66 entries / 1591.5 KiB |

## Counts

| Metric | Value | How |
|---|---|---|
| Page files | 23 (22 routed + dormant `RegisterPage.tsx`), incl. `pages/admin/ScanAdoptionDashboard.tsx` | `ls src/pages` |
| Components (non-test .tsx) | 71 | `ls src/components/**/*.tsx` |
| Vitest files / tests | 48 / 485 | vitest output |
| Playwright specs | 6 (51 `test(` calls); **CI runs only `smoke` + `auth`** (`.github/workflows/ci.yml:340`) | |
| `any` (`: any\|as any\|<any>`) | 142 total, **105 in non-test code** | grep |
| `@ts-ignore` / `@ts-expect-error` | 0 | grep |
| `catch (err: any)` style | 76 | grep |
| `[loading/isLoading, set…] = useState` | 54 hand-rolled loading flags | grep |
| `useEffect(` in .tsx | 130; 69 with `}, []);` | grep |
| AbortController / request cancellation | **0 real usages** | grep (3 hits are unrelated comments) |
| `eslint-disable` directives | 14, **but no ESLint config exists** (no `.eslintrc*`/`eslint.config.*`, no eslint in `package.json`) | ls, grep |
| `onClick` lines not on button/a/Link (brief's metric) | 310 (noisy); real non-interactive elements with `onClick`: 22, of which about 20 are overlay/stopPropagation wrappers | grep |
| `window.prompt` / `window.confirm` | 3 / 3 | grep |
| Status-label maps defined | 13 separate definitions; `in_progress` is labelled both "In Arbeit" and "In Bearbeitung" | grep |
| ASCII-transliterated German ("pruefen", "Stueck", …) | 46 occurrences, 5 of them customer-facing in the portal | grep |
| Largest chunks (min / gzip) | `TimeTrackingPage` 384.8/112.9 kB (recharts), `index` 314.1/102.3 kB, `index.esm` 143.7/58.7 kB, `OrderDetailPage` 86.5/22.3 kB, `useFormValidation` (zod) 72.2/19.8 kB | build output |

---

## A. Status of prior findings (docs/review/2026-04-23/02-frontend-react.md)

| Prior finding | Status now | Evidence |
|---|---|---|
| P0 No ErrorBoundary | **Fixed.** New issues in FE-14 | `App.tsx:70`, `MainLayout.tsx:280` |
| P0 Portal raw `fetch` sends cookies | **Fixed** (`credentials: 'omit'`). A new, worse portal bug is FE-01 | `CustomerPortalPage.tsx:191-198` |
| P0 CSRF: interceptor no-op | **Mitigated.** Auth cookie is `SameSite=Strict`; the interceptor is still a no-op | `api/routers/auth.py:118,266`, `client.ts:61-64` |
| P1 Hard `window.location.href='/login'` loses drafts | **Open** | `client.ts:86-88,129-131` |
| P1 TimeTracking init effect `[]` deps | **Open and worse:** it runs before auth, so the provider never initialises after login (FE-07) | `TimeTrackingContext.tsx:271-298` |
| P1 Two WebSockets per user | **Open.** Also, the TimeTracking socket never receives its channel (FE-08) | `TimeTrackingContext.tsx:338`, `NotificationBell.tsx:152` |
| P1 QrCameraScanner deps disable | **Open** | `QrCameraScanner.tsx:277` |
| P1 TimerWidget effect before useState | **Open** | `TimerWidget.tsx:31-36` |
| P1 ActiveTimerWidget empty deps | **Moot:** the component is orphaned (only re-exported), 454 LOC dead | `components/time-tracking/index.ts:2` |
| P1 5 s polling | **Open.** It also keeps running after logout (FE-19) | `TimeTrackingContext.tsx:242-249` |
| P1 OrderContext Map + LS write | **Open** (not re-profiled) | `OrderContext.tsx:38-39` |
| P1 ScannerContext bench-listener ordering | Not re-verified | n/a |
| P1 Error detection by German substring | **Open** | `TimerWidget.tsx:136,199` |
| P1 `window.prompt` | **Partial:** 3 prompts + 3 confirms remain | `ActiveTimerWidget.tsx:345`, `QuotesPage.tsx:987,1004`, `DashboardPage.tsx:231`, `RepairDetailPage.tsx:706`, `MetalTypeManager.tsx:198` |
| P1 Scan sounds not precached | **Open:** `dist/sw.js` has no `.mp3` entries | `vite.config.ts:29` |
| P1 AuthenticatedImage URL leak | **Improved:** `cancelled` guard plus revoke on cleanup | `AuthenticatedImage.tsx:25-60` |
| P1 OrderList missing statuses | **Moot:** OrderList has 0 importers (dead code) | grep |
| P1 `catch (err: any)` | **Open**, 76 sites; `extractErrorInfo` is still private to ActionHandlers | `ActionHandlers.ts:134` |
| P1 Modals: no dialog role / focus trap / dirty guard | **Partial:** 19 `role="dialog"` now; still no shared `<Modal>`, no focus trap in most, overlay click discards drafts (FE-16) | `OrderFormModal.tsx:328-333` |
| P1 `handleManualKeyDown` dead | **Open** | `QrCameraScanner.tsx:418-425` |
| P2 tsconfig unused/unchecked flags | **Open** | `tsconfig.json:17-18` |
| P2 Context `value` not memoised (Auth, TimeTracking) | **Open** | `AuthContext.tsx:158`, `TimeTrackingContext.tsx:343` |
| P2 `hasRole` toUpperCase normalisation | **Open.** It caused a real bug elsewhere (FE-12) | `AuthContext.tsx:37` |
| P2 recharts eager | **Open:** 385 kB TimeTrackingPage chunk | build |
| P2 useWebSocket eslint-disable | **Open** (and ESLint never runs, FE-15) | `useWebSocket.ts:139` |
| P2 LoginPage no 429 branch | **Open** | `LoginPage.tsx:32-35` |

---

## B. Findings

### FE-01 [CRITICAL] The public customer portal redirects every customer to the staff login
- **Evidence:** `App.tsx:64-81` puts `/portal` *inside* `<AuthProvider><ScannerProvider><TimeTrackingProvider>`. On mount, `AuthContext.tsx:76` calls `GET /users/me` and `TimeTrackingContext.tsx:276-279` calls `/time-tracking/running` and `/activities`. For a visitor with no cookie these return 401. The interceptor then calls `/refresh`, which returns 401 "No token provided" (`api/routers/auth.py:188-193`), and then:
  ```ts
  // client.ts:81-88
  const isRefreshEndpoint = originalRequest.url?.includes('/refresh');
  if (isRefreshEndpoint) {
    localStorage.removeItem('user');
    window.dispatchEvent(new Event('auth:session-expired'));
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
  ```
- **Impact:** a customer opening `/portal` is bounced to the staff login page within about 100 ms. The only customer-facing feature is unreachable. `CustomerPortalPage.test.tsx:47` renders the page without providers, so the test suite cannot catch this. No e2e spec covers `/portal`.
- **Fix:** move `/portal` out of the provider tree (a separate `<Route>` element before the providers, or a `PublicShell`). Make the interceptor never hard-redirect on public paths. Add an e2e test that loads `/portal` with no cookie.
- **Effort:** S. **Confidence:** high (traced through the backend handler; not executed in a browser).

### FE-02 [CRITICAL] Starting a timer by QR scan fails on every device until an activity ID already exists in localStorage, and nothing in the app writes it first
- **Evidence:** the overlay always passes `activityId: null` (`ScanOverlay.tsx:418`). The handler then falls back to localStorage:
  ```ts
  // ActionHandlers.ts:181-187
  const activityId = readActivityId(ctx);   // ctx.activityId ?? localStorage['scanner_last_activity_id']
  if (activityId === null) {
    ctx.hooks.toast('Bitte zuerst eine Aktivitaet auf dem Werkbank-Screen waehlen.', 'warning');
    return;
  ```
  The key is written *only* by `rememberActivityId()` after a **successful** scan start or switch (`ActionHandlers.ts:194,262`). A repo-wide grep finds `scanner_last_activity_id` only in `ActionHandlers.ts` and two tests that pre-seed it (`test/ActionHandlers.test.ts`, `test/Slice11PrimaryScenario.test.tsx`). No "Werkbank-Screen" activity picker exists (`QuickActionModalV2.tsx:4` notes pickers were removed).
- **Impact:** flow (b), the headline bench feature, is a dead end. Every tap on "Timer starten" or "Timer wechseln" gives a warning toast pointing to a screen that does not exist.
- **Fix:** add an activity step to the QuickAction flow (top-5 most-used activities as big buttons; `activitiesApi.getMostUsed` already exists), or pre-select the last-used activity from the server. Remove the localStorage pre-seed from tests so they cover a fresh device.
- **Effort:** S-M. **Confidence:** high.

### FE-03 [HIGH] Scan actions ignore the entity type: repair scans open or book against the *order* with the same numeric ID
- **Evidence:** `entityId()` returns `entity.entity_id` for any type (`ActionHandlers.ts:99-103`). For a repair, the backend emits `take_photo`, `print_label` and (when IN_REPAIR) `start_timer` (`scanner_service.py:1077-1085`). The handlers hard-code orders:
  ```ts
  // ActionHandlers.ts:316-320, 324-329
  ctx.hooks.navigate(`/orders/${id}?action=take-photo`);
  ...
  ctx.hooks.navigate(`/${type === 'order' ? 'orders' : type}/${id}?action=print-label`); // -> "/repair/17" (no such route)
  ```
  `handleStartTimer` posts `order_id: id` (`:189-193`). Time entries have no repair link (`models/time_entry.py:13`).
- **Impact:** "Foto aufnehmen" on repair REP-17 shows order #17, which is someone else's piece and customer data. Once FE-02 is fixed, "Timer starten" on a repair will book labour to an unrelated order (wrong Soll/Ist, wrong invoice). "Etikett drucken" on a repair falls through to the dashboard.
- **Fix:** switch on `entity_type` in every handler; hide `start_timer` for repairs until time entries support `repair_job_id`.
- **Effort:** S. **Confidence:** high.

### FE-04 [HIGH] Half of the backend's quick actions have no frontend handler, and several handlers deep-link to query params or routes that don't exist
- **Evidence:** the backend emits `add_material`, `add_note`, `contact_customer`, `check_stock`, `reorder`, `advance_repair` (primary for repairs), and `repair_diagnosis` (`scanner_service.py:924-958`). `ACTION_HANDLERS` (`ActionHandlers.ts:494-507`) has none of them, so `dispatchAction` throws `Unbekannte Aktion: …` (`:531-534`). QuickActionModalV2 renders every returned action, primary first (`QuickActionModalV2.tsx:256-261`). Existing handlers navigate to `?action=take-photo`, `?action=print-label`, `?action=consume-material`, `?edit=status`, `?edit=location` (`ActionHandlers.ts:273,280,319,328,379`), but **no page reads `action` or `edit`**: `useSearchParams` appears only in `OrdersPage.tsx:29` and `ConsultationWizardPage.tsx:35`. `open_entity` and the status hint map to `/metal-inventory/purchases/:id` and `/materials/:id` (`ActionHandlers.ts:340-341`, `ScanOverlay.tsx:430-431`); neither route exists in `App.tsx`, so both redirect to /dashboard.
- **Impact:** scanning a repair puts a primary button on screen that always errors. About 7 of 12 order actions either error or land on a generic page.
- **Fix:** filter unknown action IDs client-side (or make the backend and frontend share one registry), implement the deep-link params on OrderDetailPage (open the tab or modal), and fix the route map.
- **Effort:** M. **Confidence:** high.

### FE-05 [HIGH] Dashboard work queue drops or downgrades overdue orders and shows "alles erledigt" when loading fails
- **Evidence:** `DashboardPage.tsx:80-190`. The only deadline branches are "today" (`dl === today`) and "within 3 days" (`dl > today`). A **past** deadline falls through: it becomes `low` if `in_progress`/`confirmed`, `medium` if `waiting_for_fitting`, and is **dropped** for `new`, `draft`, `fitting_done`, `ready_for_setting` and `quality_check`. On load failure:
  ```ts
  // DashboardPage.tsx:210-213
  } catch (err) {
    console.error('Fehler beim Laden der Goldschmied-Daten:', err);
  } finally { setIsLoading(false); }
  // -> todoItems.length === 0 -> "Keine offenen Aufgaben — alles erledigt!" (:257)
  ```
- **Impact:** flow (e). The one screen meant to show what is late hides late work. A network or backend failure looks like "nothing to do".
- **Fix:** add an `overdue → urgent` branch, include all non-terminal statuses, and add an error state with retry. Unit-test `buildTodoList` (it is pure).
- **Effort:** S. **Confidence:** high.

### FE-06 [HIGH] Lists, pickers and dashboards silently cap at 100 or 200 rows
- **Evidence:** `ordersApi.getAll` defaults to `limit 100` (`api/orders.ts:20`), and the backend sorts by `created_at desc` (`order_service.py:154`). OrdersPage fetches once, then filters and paginates client-side (`OrdersPage.tsx:76,91-110`). The order form's customer dropdown has `limit: 100 // 100 is ample` (`OrderFormModal.tsx:193`), with customers sorted newest first (`customer_service.py:540`). Dashboard/KPIs/Alerts/Deadlines each use `limit: 100` (`DashboardPage.tsx:204,448,566`; `DeadlinesWidget.tsx:24`; `AlertsWidget.tsx:67`; `DashboardKPIs.tsx:31`). GlobalSearch filters 200 orders client-side (`GlobalSearch.tsx:145`). TimerWidget offers the first 100 orders (`TimerWidget.tsx:174`).
- **Impact:** after roughly 100 orders (a few months for a small workshop), older open orders disappear from the list, search, dashboard and timer picker. A returning customer who is older than the newest 100 **cannot be selected** when creating an order. KPI revenue and "active orders" are computed on a truncated sample.
- **Fix:** server-side filters/search/pagination for the orders list; reuse `CustomerTypeahead` (already built for consultations, `components/consultation/CustomerTypeahead.tsx:40`) in OrderFormModal, QuotesPage (`limit: 500`, `QuotesPage.tsx:848`) and RepairsPage. Add a backend `/dashboard/summary` endpoint.
- **Effort:** M. **Confidence:** high.

### FE-07 [HIGH] TimeTrackingProvider initialises once, before login, and never again
- **Evidence:** providers mount above the routes (`App.tsx:66-69`). The init effect is `[]` (`TimeTrackingContext.tsx:271-298`). On `/login` it runs unauthenticated and fails; after `login()` nothing re-runs it. `logout()` (`AuthContext.tsx:139-142`) doesn't reset `runningEntry`, stop polling, or clear `running_time_entry`, `scanner_last_activity_id` or `user` state held by other providers.
- **Impact:** after a fresh login, a timer already running (started on another device) is not shown until a full reload. The goldsmith may start a second one; the backend refuses and TimerWidget silently "recovers" via substring match (`TimerWidget.tsx:199`). On a shared bench tablet, user B briefly sees user A's timer.
- **Fix:** key the initialisation on `user?.id` (`useEffect(..., [user?.id])`) and reset all per-user state on logout. Better: remount the per-user provider subtree with `key={user?.id}`.
- **Effort:** S. **Confidence:** high.

### FE-08 [HIGH] The live-update wiring is dead: the frontend never subscribes to the channels the backend publishes
- **Evidence:** the only socket is `/ws/notifications/{userId}` (`useWebSocket.ts:52`), which the backend binds to Redis `notifications:{user_id}` (`main.py:331-338`). Timer events go to `time_tracking_updates` (`time_tracking_service.py:724,802,891`) and order events to `order_updates`, which only `/ws/orders` forwards (`main.py:302-311`). The frontend never opens `/ws/orders` (grep). So `handleWsMessage` for `time_tracking_updates` (`TimeTrackingContext.tsx:322-337`) never fires. Dashboard, order list and order detail have no live refresh at all.
- **Impact:** "Meister's laptop reflects the bench iPad within 1 s" (the comment at `TimeTrackingContext.tsx:314-319`) is not true. Cross-device freshness relies on the 5 s poll, which runs only if a timer was running at mount. Two sockets per user (Bell plus TimeTracking) cost connections for nothing.
- **Fix:** one `WebSocketProvider` that opens both endpoints (or a backend fan-out of `time_tracking_updates`/`order_updates` into `notifications:{uid}`), with subscribers by channel. Invalidate query caches on events (see F).
- **Effort:** M. **Confidence:** high.

### FE-09 [HIGH] Offline banner promises sync that doesn't exist
- **Evidence:** `OfflineIndicator.tsx:84`: "Daten werden synchronisiert, sobald die Verbindung wiederhergestellt ist". There is no offline mutation queue, no Workbox BackgroundSync (`vite.config.ts:31-100` has none), and `/api/*` mutations are `NetworkOnly`.
- **Impact:** a goldsmith who stops a timer or saves a note while offline sees a failed request (or an unhandled axios "Network Error" string) and believes it will sync later. The work is lost.
- **Fix:** change the copy to "Offline – Änderungen werden nicht gespeichert". Disable submit buttons while offline. Optionally add a BackgroundSync queue for the 3 bench mutations (timer start/stop, note).
- **Effort:** S (copy) / M (queue). **Confidence:** high.

### FE-10 [HIGH] "Pause" on the timer is cosmetic: the server keeps counting
- **Evidence:**
  ```ts
  // TimerWidget.tsx:90-95
  // Pause/resume is a local UI action only — the backend timer keeps running.
  setIsPaused((prev) => !prev);
  ```
  The stop dialog shows the frozen, paused value as "Zeit:" (`:409-411`). The backend records full wall time.
- **Impact:** the lunch break gets booked to the customer's order. That feeds the labour estimator corpus (V1.3) and invoices. The UI actively tells the user otherwise.
- **Fix:** remove Pause, or implement it as a server interruption (`POST /time-tracking/{id}/interruption` exists, `ActionHandlers.ts:309`).
- **Effort:** S. **Confidence:** high.

### FE-11 [HIGH] Service worker caches authenticated PII and financial API responses with no user scoping, and CacheFirst serves stale activities
- **Evidence:** `vite.config.ts:33-78`. `/api/v1/orders` and `/api/v1/materials` use `NetworkFirst` with `networkTimeoutSeconds: 10` and `statuses: [0, 200]`. `/api/v1/activities` uses **`CacheFirst`** for 1 h. Logout never clears caches (`grep caches.` finds 0 hits in src).
- **Impact:** (1) Orders (customer names, prices, which CLAUDE.md classes as financial) persist in Cache Storage on shared tablets after logout. They are served to *any* next user when the LAN is slow (>10 s) or offline, which bypasses role filtering (a VIEWER can get an ADMIN's pricing). (2) A newly created activity (ActiveTimer/ActivityPicker "Neue Aktivität") doesn't appear for up to an hour because CacheFirst never hits the network.
- **Fix:** drop runtime caching of authenticated APIs, or partition it by user and clear it on logout via `caches.delete`. Switch activities to `StaleWhileRevalidate` or `NetworkFirst`.
- **Effort:** S. **Confidence:** high on the config; medium on real-world frequency.

### FE-12 [MEDIUM] Role enum casing drift breaks an admin feature
- **Evidence:** the backend serialises `role` as lowercase `"admin"|"goldsmith"|"viewer"` (`db/models.py:69-71`, `models/user.py:169`). The frontend types it as `'ADMIN'|'GOLDSMITH'|'VIEWER'|'USER'` (`types.ts:299`; `USER` doesn't exist). `hasRole` papers over this with `toUpperCase()` (`AuthContext.tsx:37`), but `MetalInventoryPage.tsx:42` compares directly: `const isAdmin = user?.role === 'ADMIN';`.
- **Impact:** "Metalltypen verwalten" (`MetalInventoryPage.tsx:258`) is never shown to real admins. More silent bugs of this kind will follow while the type is wrong.
- **Fix:** normalise once in `authApi.getCurrentUser`, or type `UserRole` as lowercase and generate it from OpenAPI (F-2).
- **Effort:** S. **Confidence:** high.

### FE-13 [MEDIUM] Order photos: no upload in the UI; the gallery and customer timeline use unservable URLs
- **Evidence:** `photosApi` has only `getForOrder` (`api/photos.ts:5`), while the backend has `POST /orders/{id}/photos` (`routers/photos.py:55`). `OrderPhotosTab` passes only `file_path`, with `id: Number(...) || Math.random()` (`OrderDetailPage.tsx:523-529`). `PhotoCompare` then renders a raw `<img src={file_path}>` (`PhotoCompare.tsx:73-76`, `:111`), but files are only served via `/photos/{id}/file` (`routers/photos.py:136`; no StaticFiles mount in `main.py`). CustomerDetailPage builds `/orders/${order.id}/photos/${id}/file` (`CustomerDetailPage.tsx:239`), a route that doesn't exist. It also fires one request per order (N+1, `:230-245`).
- **Impact:** flow (a)/(c). Orders can't be documented with photos from the ERP (only repairs and consultations can), and existing order photos and customer-timeline thumbnails render broken. Random keys make the gallery remount on each render.
- **Fix:** add an upload with `capture="environment"` (copy `RepairDetailPage.tsx:453`). Pass `thumbSrc`/`fullSrc = /photos/{id}/thumbnail|file`. Use stable IDs. Return `first_photo_id` with the orders list.
- **Effort:** M. **Confidence:** high for the missing upload and wrong URL; medium for the broken-image rendering (depends on the stored `file_path` format, `photo_service.py:160`).

### FE-14 [MEDIUM] ErrorBoundary: "Neu laden" doesn't reload (a stale chunk after deploy stays broken), and the page boundary resets on every layout re-render
- **Evidence:** both variants call `handleRetry` (reset state only) (`ErrorBoundary.tsx:48-50,76`). With `registerType: 'autoUpdate'` (`vite.config.ts:22`) a deploy replaces hashed chunks. A lazy import of an old hash then throws, and `React.lazy` caches the rejection, so retry re-throws. `componentDidUpdate` clears the error whenever `children` identity changes (`:43-45`). `<Outlet/>` is a new element on every MainLayout render, and MainLayout re-renders on each 5 s poll (`TimeTrackingContext.tsx:246`) because the context value isn't memoised.
- **Fix:** the app variant should do `window.location.reload()`, and chunk-load errors should auto-reload once. Reset the page boundary on `location.key` instead of `children`.
- **Effort:** S. **Confidence:** medium-high.

### FE-15 [MEDIUM] No ESLint at all; the hooks rules are unenforced
- **Evidence:** no ESLint config file and no `eslint`/`eslint-plugin-react-hooks`/`jsx-a11y` in `package.json`. There are 14 `eslint-disable` comments for rules that never run, and 69 `[]`-deps hooks. There is also a rules-of-hooks smell at `TimerWidget.tsx:31-36`.
- **Fix:** add `eslint` + `eslint-plugin-react-hooks` (rules-of-hooks: error, exhaustive-deps: warn) + `jsx-a11y`, baseline the existing violations, and gate CI.
- **Effort:** S. **Confidence:** high.

### FE-16 [MEDIUM] Forms: inconsistent validation, raw axios messages, no unsaved-changes protection
- **Evidence:** zod/`useFormValidation` is used in 6 forms only (Login, Customer, Material, User, Order, OccasionBudget). Repairs, Quotes, Invoices, TimeEntry, Calendar and Metal forms are hand-rolled. Repair modals show `err.message` (for example "Request failed with status code 422", in English) (`RepairsPage.tsx:118-121`, `RepairDetailPage.tsx:184`; 10 sites total). No `beforeunload`/`useBlocker` anywhere. The 860-line OrderFormModal closes on overlay click without a dirty check (`OrderFormModal.tsx:328-333`). A session expiry hard-reloads (`client.ts:129-131`), which discards drafts including the quote signature. Double-submit guards (`submitting`/`actionLoading` + `disabled`) are generally present.
- **Fix:** a shared `getErrorMessage(err)` (promote `extractErrorInfo`, which handles Pydantic 422 arrays); a `<Modal dirty>` primitive; standardise on one form approach (see F-3).
- **Effort:** M. **Confidence:** high.

### FE-17 [MEDIUM] Walk-in repair intake: the customer is entered as a raw numeric ID
- **Evidence:** `RepairsPage.tsx:197-206`, a `<input type="number" name="customer_id" placeholder="Optional">` labelled "Kunden-ID". After create, the modal closes and stays on the list (`:297-300`); it doesn't open the new repair for photos/checklist. CustomerDetailPage has no repairs section (no "repair" in the file).
- **Impact:** see flow (a). About 8 extra taps and a memorised ID per intake. Repairs are easily saved with no customer, so that customer can't be notified or found later.
- **Fix:** `CustomerTypeahead` with inline "Neuer Kunde"; navigate to `/repairs/{id}` after create; list repairs on the customer page.
- **Effort:** S-M. **Confidence:** high.

### FE-18 [MEDIUM] Cross-page hand-offs pass query params nobody reads
- **Evidence:** OrderDetailPage "Angebot erstellen" goes to `/quotes?order_id=…&customer_id=…` (`OrderDetailPage.tsx:155`), but QuotesPage has no `useSearchParams`/`useLocation` (grep). CreateQuoteModal starts empty, with a free-text order number (`QuotesPage.tsx:83-84,159`). This is the same class of bug as FE-04.
- **Fix:** read the params and auto-open the modal pre-filled.
- **Effort:** S. **Confidence:** high.

### FE-19 [MEDIUM] Background polling continues after logout and when idle
- **Evidence:** `stopPolling` is called only from `stopTracking` and unmount (`TimeTrackingContext.tsx:145,296`). TimerWidget stops via `timeTrackingApi.stop` directly (`TimerWidget.tsx:115`), bypassing the context, so the interval keeps polling `/time-tracking/running` every 5 s forever. After logout each poll produces 401 + `/refresh` 401, which is 2 requests / 5 s against a `10/minute` refresh limiter (`auth.py:167`).
- **Fix:** route all stops through the context; stop polling when `runningEntry` is null or the user is null.
- **Effort:** S. **Confidence:** high.

### FE-20 [MEDIUM] Data layer: no cancellation, no dedupe, 54 copies of loading/error boilerplate
- **Evidence:** 0 AbortController uses; 54 hand-rolled loading flags; the admin dashboard fires `GET /orders/?limit=100` four times in parallel (`DashboardPage.tsx:448`, `DashboardKPIs.tsx:31`, `AlertsWidget.tsx:67`, `DeadlinesWidget.tsx:24`). RepairsPage search has a debounce but no stale-response guard (`RepairsPage.tsx:292-295`). TimeTrackingPage re-fetches `/users/me` instead of using AuthContext (`TimeTrackingPage.tsx:45`). CustomerDetailPage downloads 200 invoices and filters client-side (`CustomerDetailPage.tsx:363-367`).
- **Fix:** see F-1 (TanStack Query).
- **Effort:** L (incremental). **Confidence:** high.

### FE-21 [MEDIUM] Customer portal is thin and shows unfinished content
- **Evidence:** placeholder contact `info@goldschmiede.de` / `+49 0 000 000` hard-coded (`CustomerPortalPage.tsx:168-170`). `estimated_completion` is rendered raw (ISO string) (`:150`). German is transliterated in customer copy ("Stueck", "pruefen", "moeglich", "spaeter", `:159,208,221,229`). Brand is a generic "Goldschmiede". Nothing handles the backend's `GET /portal/status/{token}` (`customer_portal.py:418`) and there is no `/portal/:token` route, so an emailed link can't deep-link. No photos, no quote, no cost-change view.
- **Fix:** see flow (d). Config-driven workshop identity (the theme endpoint exists, `hooks/useTheme.ts:91`), `format(date, 'dd.MM.yyyy', {locale: de})`, real umlauts, and a token route.
- **Effort:** S (polish) / M (token route). **Confidence:** high.

### FE-22 [LOW] Dead code and bundle weight
- **Evidence:** `ActiveTimerWidget.tsx` (454 LOC, orphan), `OrderList.tsx` (0 importers), `RegisterPage.tsx` (unrouted), and `ScanAdoptionDashboard` (routed at `/admin/scan-gate` but absent from the nav, `MainLayout.tsx:255-265`). recharts sits in the TimeTrackingPage chunk (385 kB / 113 kB gz) because `TimeReportsSection` is imported eagerly. Public sourcemaps are shipped (`vite.config.ts:141`, `dist/assets/*.map` served under `/assets/`). The precache is 1.59 MB, so a tablet's first load downloads every route.
- **Fix:** delete the orphans; `React.lazy(TimeReportsSection)`; `sourcemap: 'hidden'`; consider excluding admin chunks from the precache.
- **Effort:** S. **Confidence:** high.

### FE-23 [LOW] Accessibility mechanics in code
- **Evidence:** clickable `<div>`s and `<tr>`s with no role, tabIndex or key handler: dashboard work-queue items (`DashboardPage.tsx:275-277`), admin "Neue Aufträge" (`:524`), repairs rows (`RepairsPage.tsx:373`), ActiveTimer (`:268`). Order-detail tabs are plain buttons with no `role="tab"`/`aria-selected` across 13 tabs (`OrderDetailPage.tsx:173-265`). Star-rating buttons are just "★" with no `aria-label` (`TimerWidget.tsx:158-165`). The TimerWidget start "form" isn't a `<form>` (no Enter submit). Hover-only transforms via `onMouseEnter`. `key={index}` in 6 places (`CostChangeForm.tsx:184` on removable rows is the one that matters).
- **Fix:** convert rows to `<Link>`/`<button>`, tabs to a tablist, add aria-labels, and let jsx-a11y (FE-15) enforce this.
- **Effort:** S-M. **Confidence:** high.

### FE-24 [LOW] Derived state in effects and label drift
- **Evidence:** `filteredOrders` is kept in state and synced by an effect (`OrdersPage.tsx:33,68-70`) instead of `useMemo`. There are 13 separate status-label maps, and `in_progress` reads "In Arbeit" (`QuickActionModalV2.tsx:178`) in the scanner but "In Bearbeitung" elsewhere. Dashboard "Zuletzt aktualisiert" shows render time, not fetch time (`DashboardPage.tsx:660-661`). KPI revenue filters on `updated_at` (any edit moves an order into "this month"), while `completed_at` exists in `OrderRead` (`models/order.py:404`) but not in `OrderType`.
- **Fix:** one `labels.ts` for statuses (a pattern already used in `components/consultation/labels.ts`); `useMemo`; use `completed_at`.
- **Effort:** S. **Confidence:** high.

### FE-25 [LOW] `yarn build` broken in this checkout
- **Evidence:** `yarn build` exits 127 (`Command not found: vite`), while `node node_modules/vite/bin/vite.js build` exits 0. The git status shows a modified `frontend/.yarn/install-state.gz`. It is likely a local install-state mismatch; the Containerfile/CI install fresh.
- **Fix:** `yarn install` locally (not done: no installs per brief). Don't commit the modified install-state.
- **Effort:** S. **Confidence:** medium.

---

## C. Page-by-page

| Page | Lines | Purpose / notes | Primary flow taps (from dashboard) |
|---|---|---|---|
| DashboardPage | 685 | Three role views (Goldsmith work queue, Admin KPIs+alerts+deadlines+"new", Viewer stats). FE-05 (overdue dropped, error shows "alles erledigt"), FE-06 (limit 100, 4× duplicate fetch), `window.prompt` for handoff decline (`:231`), `any` handoffs, clickable divs, no auto-refresh. **Unknown role falls back to the Admin view** (`:633,668`). Repairs absent from every widget. | n/a |
| OrdersPage | 413 | List plus create/edit/delete modal. Fetches 100 once, then client-side filter/sort/paginate (FE-06). Derived state in effect. `?status=` deep link works. | New order: Aufträge (1, or 2 via hamburger) → Neuer Auftrag (1) → form (customer dropdown capped at 100) → Save (1) ≈ **3 taps + typing** |
| OrderDetailPage | 559 | 13 tabs (Details, Kosten, Metall, Material, Status, Verlauf, Zeit, Kommentare, Altgold, Fotos, Übergabe, Kundeninfo, Arbeitszettel, Soll-Ist). God page; no photo upload (FE-13); status change has no success feedback and no "inform customer?" prompt (`:84-94`); `[orderId]` effect omits `fetchOrder`; no `?action`/`?edit` handling (FE-04). | Change status: open order (1) → Status tab (1) → status (1) = **3** |
| RepairsPage | 428 | List plus NewRepairModal. Customer by numeric ID (FE-17); `err.message` errors; `<tr onClick>` not keyboard reachable; no stale-response guard. | New repair: Reparaturen (1-2) → Neue Reparatur (1) → form → Save (1) → row (1) |
| RepairDetailPage | 842 | Status-machine buttons, diagnose/complete modals, photos by phase, intake checklist, history. Good linear flow. `window.confirm` cancel (`:706`); no customer update or notification for repairs; no receipt/label. | Diagnose → quoted: Diagnose stellen (1) → fill → Save (1) |
| CustomersPage | 476 | List/search/create. 9 `any`. `key={idx}` on tags. | New customer: Kunden → Neu → form → Save ≈ 3 |
| CustomerDetailPage | 595 | Orders timeline with thumbnails (N+1, wrong URL FE-13), invoices (fetch 200 and filter), edit. **No repairs, no consultations, no quotes** for the customer. | n/a |
| ConsultationsPage | 148 | List of consultations. Clean, has error/empty states. | n/a |
| ConsultationWizardPage | 224 | Step router via `?step=` (good), steps in `components/consultation/*` with tests. Best-structured flow in the app. | New consultation: Beratung → Neu → 7 steps |
| QuotesPage | 1277 | God component (23 useState): list, create modal, detail panel, editable line items, EstimatorPanel, signature approval, PDF. Ignores `?order_id` (FE-18); `window.prompt`/`confirm` (`:987,1004`); customers `limit 500`; quotes can't link to repairs. | Quote from order: order (1) → Angebot erstellen (1) → Neues Angebot (1) → re-select customer + type order no. → Create (1) → add lines → Senden (1) |
| InvoicesPage | 1158 | God component (27 useState): list/filters, create-from-order (orders `limit 500`), mark paid, PDF. | n/a |
| TimeTrackingPage | 408 | Own entries, manual entry modal, summary cards, reports (recharts, eager). Re-fetches `/users/me`. | Manual entry: Zeiterfassung → + → form → Save |
| ScannerPage | 544 | Camera + manual/HID input, server scan log, legacy LS migration. Solid structure; the flow dead-ends at FE-02. | see flow (b) |
| CalendarPage | 527 | Events + deadlines; event modal. No error-empty distinction. | n/a |
| MaterialsPage | 492 | CRUD + image upload. 8 `any`. | n/a |
| MetalInventoryPage | 505 | Purchases, consume, type manager. `isAdmin` casing bug (FE-12). | n/a |
| UsersPage | 262 | Admin CRUD, activate/deactivate. OK. | n/a |
| UserSettingsPage | 51 | Bench-mode toggle only. No password change or profile edit (a UI gap). | n/a |
| AdminSystemPage | 946 | Health/SMTP/theme/admin tools; 21 useState. God component; the `/admin/scan-gate` page isn't linked from it or the nav. | n/a |
| ScanAdoptionDashboard | 327 | Scan-gate metrics; unreachable from the nav. | n/a |
| CustomerPortalPage | 337 | Public lookup (ref + email) → status stepper. Unreachable (FE-01); thin (FE-21). | see flow (d) |
| LoginPage | 95 | zod validated; always redirects to `/dashboard` (ProtectedRoute doesn't pass `from`, `ProtectedRoute.tsx:40`), so deep links and QR-label URLs are lost. No 429 message. | n/a |
| RegisterPage | 142 | Dead (unrouted since fix A3). | n/a |

---

## D. UX-flow traces

### (a) Walk-in customer with a repair → captured with photo and quote
Steps (tablet portrait; sidebar behind a hamburger):
1. ☰ → Kunden (2) → "Neuer Kunde" (1) → CustomerFormModal (name, phone, email; PII) → Speichern (1). Read the `#ID` off the list row (`CustomersPage.tsx:287`).
2. ☰ → Reparaturen (2) → "Neue Reparatur" (1) → description, type, **type the customer ID**, value, date → Speichern (1). The modal closes and you stay on the list.
3. Tap the new row (1) → Fotos tab (1) → phase "Aufnahme" → camera (`capture="environment"`) (1-2) → shutter. Intake checklist (`IntakeChecklist.tsx`) is on the detail page (checkbox taps).
4. "Diagnose stellen" (1) → estimated cost/date → Speichern (1) → status `quoted`.
5. Customer approval: "Angebot bestätigen" is tapped **by staff** (`RepairDetailPage.tsx:95-98`); no signature is captured (unlike QuotesPage).

**Total: about 16-18 taps plus typing and one memorised ID.** Friction: the numeric customer ID (FE-17); no "search or create customer" inline; no navigation to the repair after create; no printed intake receipt or bag label from the repair (a scanner action exists but misroutes, FE-03); the repair "quote" is just `estimated_cost` (the formal Kostenvoranschlag in QuotesPage cannot reference a repair); no customer notification for repairs (Kundeninfo is order-only).
**Missing for the goal:** one intake screen (customer typeahead/new → item → 1-3 photos → estimate → print bag label/receipt with QR) of about 6-8 taps; repair ↔ quote link; repair Kundeninfo.

### (b) Bench: start/stop time on an order via QR
Designed path: ScanFab (1) → camera → scan label → QuickAction "Timer starten" (1) → **toast "Bitte zuerst eine Aktivität auf dem Werkbank-Screen wählen" – dead end** (FE-02).
Working fallback (no QR): TimerWidget FAB (1) → order `<select>` of the newest 100, showing "#id - title (customer)" (2) → activity `<select>` (2) → "Timer starten" (1) = **6 taps**. Selects are poor with dirty gloves; there is no search.
Stop: FAB (1) → Stopp (1) → the dialog pre-fills ratings 3/4 → "Stoppen & Speichern" (1) = **3 taps**. Via QR (once FE-02 is fixed): scan (1) + "Timer stoppen" (1) = 2.
Switch order by scanning another label: atomic `/switch` endpoint is well built (`ActionHandlers.ts:209-264`) but blocked by the same activity gap.
Pitfalls: fake Pause (FE-10); running widget shows only "Auftrag #42" (no title or activity, `TimerWidget.tsx:319-321`); a timer started on the tablet isn't live on the laptop (FE-08); after login a running timer is invisible (FE-07); repair scans book to the wrong order (FE-03); no sound offline (mp3 not precached).
**Missing:** an activity chooser inside the scan result (top-5 big buttons, remember per user server-side), 1-tap stop with ratings optional/deferred, and an ACTIVITY QR sheet for the bench (the `ACTIVITY:` prefix is already routed, `scan-router.ts:28`).

### (c) Order status changes → customer informed
1. Order (1) → Status tab (1) → new status (1). No success toast, no nudge.
2. Separately: Kundeninfo tab (1) → kind (progress / ready_for_pickup / custom) → subject/body → PhotoPicker (select existing order photos; none can be uploaded from the ERP, FE-13) → "Erstellen & senden" (1). This sends email if SMTP is configured (`KundeninfoTab.tsx:172`), otherwise it downloads a PDF to hand over manually and requires "Als zugestellt markieren".
3. Cost change (§649): the Kosten tab's CostChangeSection/Form sends the request; the customer's response is recorded by staff (email_reply/in_person/phone).

**Total: about 6-8 taps plus writing text.** Status change and notification are fully decoupled, so the customer is informed only if the goldsmith remembers. Repairs have no equivalent. `CostAlertBanner` exists for §649, but nothing flags "status changed, customer not yet informed".
**Missing:** after a status change to `waiting_for_fitting`/`completed`, offer "Kunde informieren?" with a template pre-filled per status and the latest photos pre-selected (1 extra tap); the same for repairs (`ready` → pickup notice); a "not yet informed" indicator on the dashboard.

### (d) Customer views feedback/photos/quote and approves
Today: the customer must know the URL `/portal`, type the order/repair number and email, and would see status label, stepper, step name and estimated date (raw ISO). **In practice they are redirected to the staff login (FE-01).** There are no photos, no quote, no cost-change detail, no approval and no messages. The emailed Kundeninfo has no portal link, and the backend's token endpoint `GET /portal/status/{token}` is unused by the frontend. Quote approval happens in-shop on the staff tablet via SignatureCanvas (`QuotesPage.tsx:239-300`); repair approval is a staff button.
Per the confirmed product decision (memory: "no live portal (email/PDF)"), self-service approval is out of scope. But then the portal should at least work and deep-link from the email.
**Missing to reach "clients get better feedback on their jewellery":** a working public route (FE-01), a token link in every Kundeninfo email/PDF (QR on the PDF), shared photos (the ones selected in Kundeninfo), a formatted date, real workshop contact details, and optionally a read-only quote/cost-change view with "call us to approve".

### (e) End of day: what Anne sees about open work and deadlines
If Anne is ADMIN (owner): KPIs (active = only `new` + `in_progress`; revenue from `updated_at`; computed over the newest 100 orders), AlertsWidget (low stock, metal, overdue count), DeadlinesWidget (next 14 days, top 5, **excludes overdue** since `deadlineDate >= now`, `DeadlinesWidget.tsx:35`), "Neue Aufträge" (status `new`, top 5). **She never sees the Goldsmith work queue, repairs, pending handoffs, unsent customer updates, open quotes awaiting reply, or today's booked hours per order.** If Anne is GOLDSMITH: the work queue, with the overdue bug (FE-05).
Taps: 0 (landing page). But answering "what is late and who needs a call?" needs Aufträge → sort by deadline → mentally filter, then Reparaturen → filter, which is about 6+ taps and misses anything beyond 100 rows.
**Missing:** one "Heute / Überfällig / Wartet auf Kunde / Abholbereit" board spanning orders and repairs from a server endpoint, each row linking to its next action (call, send update, start timer), in line with the CLAUDE.md principle "every data display should link to its natural next action".

---

## E. Type drift (scripted field diff: `frontend/src/types.ts` vs Pydantic read schema)

| Frontend type | Backend schema | Drift |
|---|---|---|
| `OrderType` (`types.ts:185`) | `models/order.py:OrderRead` (:361) | Missing `actual_hours`, `completed_at`; `order_type`/`finish_type` typed `string` instead of enum; `punzierung_verified_marks` written by the scanner (`ActionHandlers.ts:415`) but absent from the type |
| `OrderStatus` (`types.ts:168`) | `db/models.py:OrderStatusEnum` (:47) | Values match (lowercase). No drift |
| `UserType.role` / `UserRole` (`types.ts:299`) | `models/user.py:User.role` → `UserRole` `"admin"…` (`db/models.py:69`) | **Casing drift** (FE uppercase, BE lowercase) plus phantom `'USER'`. Real bug FE-12 |
| `Customer` (`types.ts:~65`) | `models/customer.py:CustomerRead` | Fields match; `tags` required in FE vs `Optional[List[str]]` in BE (defaults to `[]`, low risk) |
| `TimeEntry` | `models/time_entry.py:TimeEntryRead` | No field drift. FE assumes naive UTC timestamps and appends `Z` (`TimerWidget.tsx:59-61`); make the serialiser emit TZ |
| `Activity` | `models/activity.py:ActivityRead` | Missing `hourly_rate`, `is_billable` (financial; good that the UI doesn't show it, but types should say it's there) |
| `RepairJob` / `RepairJobStatus` | `models/repair.py:RepairJobRead` | Fields match; status values match |
| `Quote` / `QuoteStatus` (`types.ts:803`) | `models/quote.py:QuoteResponse` | Fields match; statuses match lowercase (the V1.3 DRAFT-casing bug is fixed) |
| `Invoice` (`types.ts:734`) | `models/invoice.py:InvoiceResponse` | Fields match |
| `MaterialType` | `models/material.py:MaterialRead` | FE-only `stock_value` (computed client-side, or it doesn't exist in the response) |
| `OrderPhoto` | `models/order_photo.py:OrderPhotoRead` | Fields match, but no URL field; the FE invents `file_url` (`CustomerDetailPage.tsx:239`) |
| `WebSocketMessage` (`useWebSocket.ts:20`) | `notification_service.py` payload | Untyped `[key]: unknown`; consumers probe `type`/`channel`/`action` ad hoc |

The field-level drift is small, since the team clearly syncs by hand. The risk sits in **enum casing, invented fields, and 126 hand-maintained interfaces in a 1285-line file**. `customer-updates.ts` keeps its own types to dodge a name collision (`api/customer-updates.ts:3-5`).

---

## F. Architecture recommendations (suggested order)

1. **Fix the public/private shell split and per-user lifecycle first (S).** Put `/portal` outside the providers. Key the per-user providers on `user.id`. Clear per-user state, localStorage and SW caches on logout. This covers FE-01, FE-07, FE-11 and FE-19 and unblocks everything else.
2. **Generated API types (S-M).** `openapi-typescript` against FastAPI's `/openapi.json`, in CI with a diff check. Migrate `types.ts` module by module (start with User/Order enums). This removes the FE-12 class of bugs and the 1285-line manual file. `orval` can also generate clients if wanted.
3. **TanStack Query as the data layer (M, incremental).** Replace the 54 loading flags and 130 effects page by page. You get request dedupe (the 4× dashboard fetch), cancellation, retry, `staleTime`, and invalidation on mutation. Wire the single WebSocket provider to `queryClient.invalidateQueries(['orders'])` / `['timer']` (fixes FE-08 properly). Start with Dashboard, Orders and TimeTracking, the highest-traffic screens.
4. **Server-side list and search endpoints (M, with backend).** Paginated/filtered `/orders`, `/repairs`, `/customers/search`, and a `/dashboard/work-queue` spanning orders and repairs. Frontend: one `<EntityTypeahead>` (generalise `CustomerTypeahead`) used in Order, Repair, Quote and Timer pickers (FE-06, FE-17).
5. **Shared UI primitives (M).** `<Modal>` (role, focus trap, Esc, dirty guard, replaces 18 hand-rolled overlays), `<PromptDialog>` (replaces the prompt/confirm calls), `<Tabs>` (ARIA tablist), `<AsyncState>` (loading/error/empty), `labels.ts` for all status maps, and `getErrorMessage()`. The design-system agent owns the look; this is the behaviour layer.
6. **One form approach (M).** Keep zod (already used in 6 forms and in the bundle). Add `react-hook-form` + `@hookform/resolvers/zod` for the big forms (OrderFormModal 860, CustomerFormModal 640, Quote/Invoice editors) for dirty tracking, field arrays (line items; fixes `key={index}`) and fewer re-renders. Small forms can stay on `useFormValidation`.
7. **Split the god pages (M).** QuotesPage (1277), InvoicesPage (1158), AdminSystemPage (946), RepairDetailPage (842). Extract panels and hooks along the existing sub-component seams. Lazy-load tabs in OrderDetailPage.
8. **Lint and test gates (S).** ESLint with hooks + jsx-a11y (FE-15). Unit tests for pure logic (`buildTodoList`, interceptor, AuthContext init). Extend CI e2e from smoke/auth to `goldsmith-workflow` plus a new portal-unauthenticated spec and a fresh-device QR-start spec.
9. **State:** don't migrate to Zustand yet. After TanStack Query takes server state, the remaining contexts (Auth, Scanner, Toast, Theme) are small. Memoise their `value`s.

## G. Things the user might have missed

- **The QR bench flow and the customer portal, the two features most tied to the product goal, are both non-functional in the browser even though all 485 unit tests pass.** In each case the tests set up state the real app never produces: a pre-seeded localStorage activity, and rendering the portal without providers.
- **Repairs are second-class in the frontend:** no time tracking (time entries are order-only), no Kundeninfo, no quote link, no dashboard presence, not on the customer page, and not in global search. For a walk-in-heavy workshop that is likely the majority of jobs.
- **Anne's likely role (ADMIN) sees the office dashboard, not the work queue.** Check which role she uses day to day.
- **Mutations are online-only while the UI claims offline sync.** On a workshop LAN with flaky Wi-Fi this is where bench data gets lost.
- **Shared tablets:** API data (customer names, prices) stays in the service-worker cache and localStorage (`user`, `running_time_entry`) after logout, which conflicts with the CLAUDE.md data-privacy rules for financial data.
- **Deep links are dropped at login** (no `from` state), so a QR label or email link that opens an order URL always lands on the dashboard after sign-in.
- **The ESLint "disable" comments give a false sense of lint coverage.** No linter runs on the frontend.
- **The CI e2e job runs only smoke and auth specs** (`ci.yml:340`); the 27-test goldsmith-workflow suite and the estimator flow are local-only.
- **Hard-coded placeholder contact details** (`info@goldschmiede.de`, `+49 0 000 000`) would ship to real customers.

---

## Verification (2026-09-25)

Verifier: `.orchestrated-fable/ux-erp-audit-2026-09/verify-frontend-domain-design.md` (adversarial; re-ran the build commands and chunk sizes). No finding dropped.

| ID | Title (short) | Claimed | Verdict | Corrected severity | Verifier note |
|---|---|---|---|---|---|
| FE-01 | Public portal redirects to staff login | CRITICAL | CONFIRMED | CRITICAL | `client.ts:81-88` exempts only `/login`; the portal test renders the page bare, so it cannot catch this |
| FE-02 | QR timer activity dead end | CRITICAL | CONFIRMED | CRITICAL | Exactly one production `dispatchAction` call site, always `activityId: null`: unconditional on a fresh device |
| FE-03 | Repair scans hit the order with the same ID | HIGH | CONFIRMED | HIGH | `handleOpenEntity` does switch on type; take-photo and start-timer do not |
| FE-04 | Missing quick-action handlers | HIGH | CONFIRMED | HIGH | 12 handler keys; none of the 7 backend action IDs listed; `dispatchAction` throws |
| FE-05 | Dashboard drops overdue orders | HIGH | CONFIRMED | HIGH | Same bug as DOM-14 |
| FE-06 | Hardcoded 100/200-row caps | HIGH | CONFIRMED | HIGH | |
| FE-07 | TimeTrackingProvider initialises once, before login | HIGH | CONFIRMED | HIGH | `logout()` resets nothing per-user |
| FE-08 | Frontend never subscribes to the backend's live channels | HIGH | CONFIRMED | HIGH | `handleWsMessage` for `time_tracking_updates` is dead code; no `/ws/orders` in the frontend |
| FE-09 | Offline banner promises sync | HIGH | CONFIRMED | HIGH | No BackgroundSync plugin; other `/api/` routes NetworkOnly |
| FE-10 | Fake pause | HIGH | CONFIRMED | HIGH | Comment reproduced verbatim; no API call |
| FE-11 | Service worker caches PII/financial data, not cleared on logout | HIGH | CONFIRMED | HIGH | `grep caches.` outside tests: 0 hits |
| FE-13 | No order-photo upload | MEDIUM | CONFIRMED | **HIGH** | Same defect as DOM-01 (impact H); the #1 precondition for the feedback goal (05 §D) |
| FE-25 | `yarn build` broken in this checkout | LOW | CONFIRMED | LOW | `yarn build` 127; `node node_modules/vite/bin/vite.js build` 0 with matching chunk sizes |

MEDIUM and LOW findings other than FE-13 and FE-25 were outside the verifier's scope.
