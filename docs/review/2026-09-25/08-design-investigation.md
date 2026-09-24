# Design Investigation — Goldsmith ERP Frontend (2026-09-24)

Scope: `frontend/` on `main` (@73fff19). Static analysis of CSS/TSX, plus a limited live pass (login and portal only, see J).
Paths are relative to `frontend/` unless they start with `docs/` or `.claude/`.

---

## A. Executive summary

- **How it was designed:** a small gold/charcoal/cream token file (`src/styles/brand-tokens.css`) went in first. After that, each feature added its own global plain-CSS stylesheet (27 page files plus 13 component files, 14,789 lines), usually copying the look of the previous page instead of reusing shared primitives. Tailwind v4 is installed and imported (`brand-tokens.css:1`), but it is barely used: 14 usages of its `@utility` classes and about 26 Tailwind class strings. The plan docs even say "NO Tailwind" (`docs/planning/phase-plans/2026-07-02-v1.1-consultation-frontend-plan.md:9`).
- **Verdict:** the intent is good and matches the workshop: 44px touch tokens, a Werkbank-Modus, a scan FAB, an offline banner, German copy, a colorblind-safe invoice badge. The execution is a patchwork admin template. There are 1,580 hardcoded hex values (223 distinct), 9 different golds, 3 to 6 competing definitions of `.btn-primary`, `.status-badge` and `.modal-*`, and they collide at runtime because every stylesheet is global. The core gold CTA fails WCAG AA text contrast (3.19:1). Dark mode is announced but not implemented. Order status (10 states) is styled for only 4 of them.
- **Top 5 improvements:**
  1. Fix the gold contrast. Make `--color-interactive-primary` cta-700 `#b45309` (5.02:1). Make the focus ring a dark color at 3:1 or better.
  2. One status system. Build a single `<StatusBadge kind status>` from one token map covering all 10 order statuses plus repair, quote and invoice statuses, each with an icon and a text label, not color alone.
  3. Shared primitives replace the global duplicates: `Button`, `IconButton`, `Modal` (focus trap, Escape, no backdrop-dismiss on forms), `DataTable` or `ListCard`, `EmptyState`, `PageHeader`. Delete the duplicate class definitions from the page CSS.
  4. Consolidate tokens: spacing, type, radius, shadow and z-index scales, plus semantic status colors. Remove the legacy `--primary-color` and `--text-primary` families and the 41 undefined custom properties.
  5. Workshop-first shell: a bottom tab bar on phones and tablets, grouped navigation, a fixed header overflow at 390px, the offline banner actually visible, and a bench worklist with the deadline Ampel for Anne (ADMIN).

---

## B. Token and style architecture inventory

### B.1 Files
| Layer | File | Notes |
|---|---|---|
| Tokens | `src/styles/brand-tokens.css` (114 l.) | Tailwind `@theme` palette (cta, primary, cream, accent, secondary; `:4-57`) + semantic `:root` tokens (`:60-114`) |
| Global base | `src/index.css` (136 l.) | Vite-template leftovers: `color:#213547` (`:12`), `h1{font-size:3.2em}` (`:49-52`), `.error-message #ff4444` (`:75-81`), forced light input/table colors (`:100-108`), button reset (`:111-135`) |
| Utilities | `src/styles/utilities.css` (147 l.) | Tailwind `@utility` btn/card/typography/input. Only 14 usages repo-wide, effectively dead |
| Global buttons | `src/styles/buttons.css` (90 l.) | Added to fix invisible buttons caused by a cascade-layer conflict (`:1-23`) |
| Feature CSS | 25 page stylesheets + 13 in `styles/components/` | Largest: `order-detail.css` 1637, `repairs.css` 1442, `metal-inventory.css` 1175, `scrap-gold.css` 1039 |
| Runtime theme | `src/hooks/useTheme.ts:29-61` | Admin-configurable colors pushed via `setProperty` (primary, header gradient, accent, page bg). No contrast validation found (medium confidence) |
| Dark mode | `src/contexts/ThemeContext.tsx`, `src/components/ThemeToggle.tsx`, `index.html:4-11` | Provider and toggle are never mounted (see F.5) |

### B.2 Counts (commands per the brief)
| Metric | Value |
|---|---|
| Hex color occurrences in CSS | **1,580** (223 distinct) |
| Hex colors in TSX | 192 |
| Lines containing `px` in `styles/*.css` | **1,200** |
| Inline `style={{` in TSX | **222** in 37 files (top: `InvoicesPage.tsx` 32, `AdminSystemPage.tsx` 32, `MetalTypeManager.tsx` 30, `ScanAdoptionDashboard.tsx` 19, `QuotesPage.tsx` 19) |
| Distinct `font-size` values | **50** (e.g. 0.7, 0.72, 0.75, 0.78, 0.8, 0.82, 0.85, 0.875, 0.9, 0.95rem, plus 13px, 14px, 15px, 20px) |
| Distinct `border-radius` values | 15+ (8px ×135, 12px ×65, 6px ×51, 10px ×40, 4px, 999px, 9999px, 0.5rem, 20px, 16px, 14px, 2px…) |
| Distinct `box-shadow` declarations | 98 |
| `transition` declarations | 174; `prefers-reduced-motion` blocks: 6 |
| Distinct media-query breakpoints | about 20 (768 ×22, 480 ×13, 1024 ×6, 640 ×5, 600 ×4, 1200, 900, 767, 639, 520, 479, 1199, 1100…) |
| Custom properties referenced but never defined | **41** (e.g. `--text-primary`, `--text-secondary`, `--text-tertiary`, `--color-border`, `--color-gold*`, `--color-error*`, `--color-success*`, `--primary-dark`, `--bg-secondary`). 12 are used without a fallback: `--text-primary` ×9 (e.g. `styles/components/CommentsTab.css:20`, `TimeTrackingTab.css:22`), `--text-tertiary` ×2, `--primary-dark` ×3. `--chart-*`/`--preview-*` may be set at runtime (low confidence) |

### B.3 Color drift
- **Gold, 9 distinct values:** `#d97706` ×45, `#f59e0b` ×43, `#c5a55a` ×14, `#b45309` ×11, `#c9a227` ×5 (`components/metal/PriceChart.tsx:118`), `#b8860b` ×5, `#d4a843` ×3 (PWA `theme-color`, `index.html:20`), `#ffd700`, `#daa520`. The token file defines only the Tailwind amber ramp. The warmer "metal" golds (`#c5a55a`, `#c9a227`) have no token.
- **Blue legacy:** `#3b82f6` ×48, `#3498db` ×15 and `#2c3e50` ×21 (Flat-UI palette, a template leftover), plus `--color-chart-primary` "Legacy blue" (`brand-tokens.css:92-93`). `CommentsTab.css:79,247,317` uses a blue primary (`--primary-dark, #2563eb`) inside a gold app.
- **Grays:** `#e5e7eb` ×122, `#333` ×58, `#666` ×54, `#f8f9fa` ×39 and `#e9ecef` ×21 (Bootstrap grays) mix with Tailwind grays. Only `--color-border-default` and `--color-text-*` exist as tokens.
- **Parallel variable families:** `--primary-color`/`--primary-hover`/`--text-dark` (`index.css:21-26`), `--text-color-primary` (`brand-tokens.css:62`), `--color-text-body` (`:80`), and the undefined `--text-primary`. Four names for "body text".
- **Semantic tokens that are themselves hardcoded:** `--color-surface-page:#faf8f4` (`:71`) duplicates `--color-brand-cream-*`, and `--color-text-heading:#1a1a2e` (`:79`) is off-palette.

### B.4 Missing scales
There are no spacing, type, radius, shadow, z-index or motion tokens. The only size tokens are `--touch-min: 44px` and `--touch-comfort: 56px` (`brand-tokens.css:112-113`), used about 5 times. z-index values are ad hoc: header 200 (`layout.css:18`), overlay 149/150, modal 1000 (`pages.css:13`), timer 1050, FAB 1060, scan overlay 1500, offline banner Tailwind `z-50`.

### B.5 Cascade architecture problem
All stylesheets are global and load lazily with their route. Once visited, a page's CSS stays loaded, so the look of shared class names depends on navigation history:
- `.btn-primary` is defined in 7 places: `buttons.css:59` (flat), `materials.css:185` (gradient plus lift), `customers.css:333` (gradient, 0.95rem), `auth.css:78` (gradient), `repairs.css:469`, `calendar.css:368`, and the `@utility` in `utilities.css:4`.
- `.status-badge` is defined 3 times with different radius, case and colors: `orders.css:133-160` (UPPERCASE, r12, delivered = gray), `dashboard.css:717-744` (Capitalize, r20, delivered = indigo `#e0e7ff`), `repairs.css:234` (pill, 0.75rem, different modifier scheme `status-badge received` without the `status-` prefix).
- `.modal-overlay` ×4, `.modal-header` ×5, `.form-group` ×5, `.btn-secondary` ×5, `.error-message` ×5, `.btn-icon` ×2, `.search-box` ×2.
- `buttons.css:4-23` documents one real incident of this ("buttons rendered … invisible / white-on-white"), caused by Tailwind's layered `@utility` losing to the unlayered reset in `index.css:111`.

---

## C. Layout and navigation

- **Shell** (`src/layouts/MainLayout.tsx`): a sticky gradient header (64px, `layout.css:12-29`) with hamburger (mobile), `h1` "Goldsmith ERP" (`MainLayout.tsx:78`), GlobalSearch, "📷 Scanner" link, NotificationBell, user name and "Abmelden". Below it a 250px white sidebar (`layout.css:120-131`) and the content area, then a footer "© … Alle Rechte vorbehalten" (`MainLayout.tsx:287-289`). The footer uses vertical space on a bench tablet for no benefit. Floating extras: TimerWidget, ScanFab, ScanOverlay, HidBurstNudge (`:292-312`).
- **Navigation:** 12 flat, ungrouped links with emoji icons (`MainLayout.tsx:122-266`): 📊📇📋🔧💍💎🥇⏱️📅🧾📝👥⚙️. There are no sections such as "Werkstatt / Kunden / Büro / Admin". Frequent bench actions (Aufträge, Zeiterfassung, Scanner) sit among office functions (Rechnungen, Angebote, Metallinventar). **`/settings` (Werkbank-Modus) has no nav entry.** It is reachable only from the HID nudge toast (`components/HidBurstNudge.tsx:64`, route `App.tsx:199`).
- **Responsive:** one real layout breakpoint. At 768px or less the sidebar becomes an off-canvas drawer (`layout.css:231-258`). There is no tablet-specific layout: a 10" tablet in portrait (768 to 800px) gets either the full 250px sidebar or the drawer. There is no bottom tab bar on phones. The drawer has no Escape handler and no focus trap (`MainLayout.tsx:98-120`).
- **Header overflow at 390px (medium confidence, not verified live):** hamburger 44 + logo (1.2rem, about 130px) + search 44 + Scanner (about 90px) + bell 44 + Abmelden (about 95px) + 4×16px gaps + 40px padding comes to about 550px, which exceeds 390px. Only `.user-name` is hidden (`layout.css:237-239`). `.btn-scanner`/`.btn-logout` shrink only their padding (`:304-312`).
- **Offline banner hidden behind header:** `OfflineIndicator.tsx:55-65` is `fixed top-0 z-50` (Tailwind z-index 50). The header is `position: sticky; top: 0; z-index: 200` (`layout.css:16-18`), so the banner renders underneath the header (high confidence from the CSS; not seen live).
- **Page shells are inconsistent:** `page-container` (Customers, TimeTracking, Consultations), `repairs-page`, `calendar-page`, `dashboard-container`, `scanner-container`, `user-settings-container`, and `.page-header` defined in both `pages.css` and `invoices.css`. The global `h1 { font-size: 3.2em }` (`index.css:49-52`) is a Vite default that each page has to override.
- **Density:** desktop tables use `padding: 1rem` cells with uppercase 0.9rem headers (`orders.css:166-182`). That suits office work. On the bench, list rows would be better as cards with larger type.

---

## D. Component pattern catalogue and inconsistencies

| Pattern | Variants found | Evidence | Problem |
|---|---|---|---|
| Primary button | 7 definitions: flat gold, gradient, gradient plus lift, `@utility` | `buttons.css:59`, `materials.css:185-193`, `customers.css:333-341`, `auth.css:78-86`, `repairs.css:469`, `calendar.css:368`, `utilities.css:4-18` | Look changes with navigation order. Gradient buttons (login screenshot) vs flat elsewhere |
| Base `.btn` | no `min-height` | `buttons.css:25-36`, `.btn-sm` `:54-57` (about 30px tall) | Breaks the 44px rule the tokens promise |
| Button variants | **56** distinct `.btn-*` class names | `grep ^\.btn-` in styles | No variant API; e.g. `btn-create-quote` (`OrderDetailPage.tsx:154`), `btn-quick-action`, `btn-scanner` |
| Icon buttons | Emoji ✏️ 🗑️ with `title` only, no `aria-label` | `OrdersPage.tsx:346-362`; `.btn-icon` `orders.css:205-213` (about 40px) | Edit and delete sit side by side in every row; no accessible name; emoji rendering varies by OS |
| Modal close | `padding:.25rem; font-size:1.5rem` (about 32px) | `pages.css:44-51`, `customers.css:221-225`, `repairs.css:371-375`, `materials.css:68-73` (2rem) | Below 44px, four implementations |
| Modals | 17 `modal-overlay` usages; 4 CSS definitions; plus `confirm-dialog-overlay`, `cost-change-modal-overlay`, `timer-stop-dialog-overlay`, `punz-overlay`, `photo-lightbox-overlay`, `modal-backdrop`, `modal-box` | `pages.css:3-15`; see F.4 | No shared Modal component; semantics vary |
| Tables | 17 different table classes: `orders-table`, `order-table`, `data-table`, `repairs-table`, `quotes-table`, `invoices-table`, `materials-table`, `metal-inventory-table`, `line-items-table`, … | className grep | Only Invoices, Quotes and Users provide `data-label` for the mobile card layout (`pages.css:300-318`); Orders and Repairs just clip in `.table-container{overflow:hidden}` (`pages.css:133-137`), fixed ad hoc in `invoices.css:16-28` |
| Status badges | `status-badge` (3 defs), `invoice-status-badge`, `quote-status-badge`, `kundeninfo-status-badge`, `cost-change-status-badge`, `handoff-status-badge`, `scrap-gold-status-badge`, `portal-status-badge` | `orders.css:133`, `dashboard.css:717`, `repairs.css:234`, `invoices.css:98`, `QuotesPage.tsx:39`, `KundeninfoTab.tsx:69`, `HandoffTab.tsx:135` | 8+ badge systems. OrderStatus has 10 values (`types.ts:168-178`) but only `new/in_progress/completed/delivered` are styled; `confirmed`, `waiting_for_fitting`, `fitting_done`, `ready_for_setting`, `quality_check` = 0 CSS rules. `draft` exists only for invoices/quotes |
| Badge semantic misuse | handoff shown as "new" (blue), fitting as "in_progress" | `DashboardPage.tsx:322` | Color meaning is overloaded |
| Dead or duplicate list | `OrderList.tsx` renders `status-badge` without a modifier and is not imported anywhere | `components/OrderList.tsx:36` | Dead template component |
| Loading states | `page-loading` ×13 plus 12 feature-specific variants, only one skeleton set, text varies ("Lade Aufträge...", "Wird geladen…", "Laden...") | className grep | No shared Spinner/Skeleton; mixed `...` vs `…` |
| Empty states | `empty-state` ×10 plus 14 variants (`repairs-empty`, `cdetail-empty`, `handoff-empty`…) | className grep | Mostly text only, no call to action (e.g. `OrdersPage.tsx:296-300`), which goes against the CLAUDE.md rule "every data display should link to its next action" |
| Error display | `error-message` ×32 (global red `#ff4444`, 3.41:1), `page-error` ×14, `error-text` ×11, `repairs-error`, `admin-error-banner`… | `index.css:75-81` | 5 CSS definitions; contrast fail |
| Forms | `.form-group` ×5 definitions; labels 226, `htmlFor` 165, inputs/selects/textareas 247 | `auth.css:60-71` | About 80 inputs may be unlabeled or wrapped (medium confidence). Focus = border color only (`outline:none` ×33 in CSS) |
| Cards | `@utility card` "glass morphism" (`utilities.css:83-90`) barely used; each page defines `stat-card`, `kpi-card`, `summary-card`… | | The intended glass language isn't applied |
| Headings | `.logo` is an `h1` in the header (`MainLayout.tsx:78`), and pages add their own `h1` (`DashboardPage.tsx:651`, `ScannerPage.tsx:378`) | | Two `h1`s per page |
| Text quality | ASCII or dropped umlauts in UI copy: "Loschen"/"Bestatigen" (`ConfirmDialog.tsx:83`, `OrdersPage.tsx:164,175`, `MaterialsPage.tsx:233`), "moglicherweise noch in Auftragen" (`MaterialsPage.tsx:246`; "Auftragen" means "applying"), "fuer" (`OrderDetailPage.tsx:156`, `QuotesPage.tsx:164`), "Gueltig" (`QuotesPage.tsx:175`), "uebernehmen" (`AlloyMismatchModal.tsx:387,392`), "Bestaetigen" (`PunzierungsCheckModal.tsx:296`). About 20 occurrences | | Reads as unfinished to a German craftsperson |
| Truncation | `substring(0,50)` plus a literal "..." always appended | `OrdersPage.tsx:326` | Short descriptions still show "…"; use CSS `line-clamp` |

**Positive exemplars to standardize on:**
- `invoices.css:85-99`: status conveyed by label prefix plus border style (dashed, solid, dotted, strikethrough), color secondary. This is the colorblind-safe pattern the design lead asked for.
- `ConfirmDialog.tsx:54-70`: focuses the Cancel button, closes on Escape, uses `role=dialog`/`aria-modal`/labelledby/describedby.
- `ScanFab.css:26-31`: 56px FAB using `--touch-comfort`.

---

## E. Workshop-fit assessment

| Criterion | Status | Evidence |
|---|---|---|
| Large tap targets | Partial | 69 uses of `min-height:44px`/touch tokens; hamburger, nav and scanner are 44px (`layout.css:45-56,173,86`). But `.btn` (`buttons.css:25`), `.btn-sm`, modal close (about 32px, `pages.css:44-51`) and `.btn-icon` (about 40px) fall short, and destructive and edit icon buttons sit next to each other (`OrdersPage.tsx:346-362`) |
| Glanceable from 1 to 2 m | Weak | Body 0.85 to 0.95rem dominates (218 declarations). Deadlines in Orders are plain dates with no urgency cue (`OrdersPage.tsx:340-343`). The only Ampel is on the dashboard, with color and a left border (`dashboard.css:501-525`), and there is no wall or kiosk view |
| Colorblind-safe Ampel | Partial | The dashboard urgent/soon/ok levels differ only by red/amber/green hue (`dashboard.css:502-525`); the deadline badge has no icon or shape. Invoice badges are the right model (`invoices.css:85-99`) |
| QR-first | Good but fragmented | Three entry points with two UIs: header link to the `/scanner` page (`MainLayout.tsx:83-85`), the global ScanFab plus overlay (`:301-306`), and the dashboard quick action to `/scanner`. The page and overlay duplicate behavior |
| Minimal typing | Partial | Quick-allergy chips and one-tap patterns exist in the V1.1 plan. Orders creation is a large tabbed modal (`OrderFormModal.tsx:334`, `modal-large`) |
| Dirty-hand mis-taps | Risk | Form modals close on backdrop tap and lose input: `MetalPurchaseFormModal.tsx:257`, `UserFormModal.tsx:98`, `TimeEntryFormModal.tsx:234`, `MaterialsPage.tsx:44`, `QuotesPage.tsx:123,255`, `MetalTypeManager.tsx:220`, `TimeTrackingTab.tsx:296` |
| Offline indicator | Present but likely invisible | `OfflineIndicator.tsx:55-65` z-50 under header z-200 (`layout.css:18`) |
| Glare and lighting / dark mode | Missing | ThemeToggle not mounted; see F.5. Cream page `#faf8f4` with white cards is low-differentiation under halogen light |
| Timer always visible | Good | TimerWidget fixed bottom-right (`TimerWidget.css:3-6,62-70`), stacks with FAB via `--fab-bottom` |
| Bench worklist for the owner | Gap | Anne (owner) is presumably ADMIN, and ADMIN gets the KPI `AdminDashboard` (`DashboardPage.tsx:666-670`). The bench-oriented "Mein Arbeitsvorrat" is GOLDSMITH-only (`:246-249`). Also, "Zuletzt aktualisiert" shows render time, not data time (`:661`, low-medium confidence) |
| Photos as primary identifiers | Weak | Order list has no thumbnail and no customer name column (`OrdersPage.tsx:307-316`), so goldsmiths must remember `#ID`/title. The jewelry itself is the natural identifier |
| Client feedback surface | Thin | The portal (`CustomerPortalPage.tsx`) shows reference, status, a step progress bar and an estimated date. It shows no photos, quote or approval (the V1.2 approval flows are email/PDF per roadmap). The portal name is a hardcoded generic "Goldschmiede" (`:250`), there is an inline `#4ade80` (`:158`), and a separate dark visual language and font stack (`portal.css:11,16`) |

---

## F. Accessibility assessment

### F.1 Contrast (WCAG 2.1 relative luminance, computed)
| Pair | Ratio | AA text (4.5) / non-text (3.0) |
|---|---|---|
| White on `#d97706` — **primary button, header gradient start** (`buttons.css:59-63`, `brand-tokens.css:68,75`) | **3.19** | **FAIL** (buttons are 0.875 to 1rem, weight 500 to 600, not "large") |
| White on `#b45309` (hover, cta-700) | 5.02 | pass |
| White on `#92400e` (header gradient end) | 7.09 | pass |
| White on `#f59e0b` (cta-500 fills) | 2.15 | FAIL |
| White on `#e08020` — `btn-warning` (`utilities.css:57`) | **2.89** | FAIL |
| White on `#16a34a` (success-500 fill) | 3.30 | FAIL for text |
| White on `#dc2626` (danger) | 4.83 | pass |
| `#d97706` link/nav text on white or cream (`--text-color-link`, 49 uses of `color: var(--color-interactive-primary)`) | **3.13 to 3.19** | FAIL |
| `#d97706` on `#fef3c7` — **active nav item** (`layout.css:181-185`) | **2.86** | FAIL |
| `#f59e0b` focus ring on white (`--ring-color-focus`, `brand-tokens.css:65`) | **2.15** | FAIL non-text 3:1 (1.4.11) |
| `#9ca3af` text on white (36 `color:` uses) | 2.54 | FAIL |
| `#ff4444` global `.error-message` (`index.css:76`) | 3.41 | FAIL |
| `#e08020` on `#fff4e6` (warning text) | 2.66 | FAIL (use warning-600: 3.93, still below 4.5) |
| `#334155` portal footer on `#1a1a2e` (`portal.css:449`) | 1.65 | FAIL |
| `#374151` body on page `#faf8f4` | 9.72 | pass |
| `#6b7280` muted on page / card | 4.56 / 4.83 | pass (barely) |
| Order badges new / in_progress / completed | 7.15 / 6.37 / 6.78 | pass |

The brand gold is used at its lightest AA-failing step. The whole CTA and link system needs to move one step darker (cta-700 `#b45309`), or use dark text on gold (`#1e293b` on `#f59e0b` gives about 7.6:1).

### F.2 Focus
- `outline: none` appears 33 times in CSS (e.g. `auth.css:69`, `orders.css:127`, `customers.css:78,94,275`, `order-detail.css:292,1214,1489`), replaced by a border-color change to `#f59e0b` (2.15:1). Only 18 `:focus-visible` rules exist.
- The global `button:focus { outline: 4px auto -webkit-focus-ring-color }` (`index.css:127-130`) shows a ring on mouse click as well.

### F.3 ARIA and semantics
- `aria-*` appears in 61 of 104 non-test TSX files (106 `aria-label`, 51 `aria-hidden`, 25 `aria-modal`, 41 live/alert/status regions). That is solid coverage for a codebase this age.
- Clickable `<tr>` rows without keyboard access: `OrdersPage.tsx:320-323`, `RepairsPage.tsx:373`. 21 `onClick` handlers sit on div/tr/span/li.
- Emoji icon-only buttons rely on `title` (`OrdersPage.tsx:349-362`). `ThemeToggle` has an English `aria-label` while its `title` is German (`ThemeToggle.tsx:11-12`).
- Two `h1`s per page (logo plus page title).

### F.4 Keyboard and modals
- Of 15 files rendering `modal-overlay`, 7 lack `role="dialog"` (TimeTrackingTab, MetalTypeManager, TimeEntryFormModal, MetalPurchaseFormModal, UserFormModal, RepairDetailPage, MaterialsPage). Only 2 handle Escape (`RepairsPage.tsx`, `CostChangeSection.tsx`). No focus trap or `inert` is used anywhere (grep for `focus-trap|inert` returns nothing).
- The mobile nav drawer has no Escape key handling and no focus management (`MainLayout.tsx:98-120`).

### F.5 Dark mode
- `index.html:4-11` adds `.dark` to `<html>` when the OS is dark. `ThemeProvider` (`ThemeContext.tsx:12-36`) and `ThemeToggle` are never rendered: the only `useTheme` in `App.tsx:61` is the admin color hook.
- No main surface has `.dark` rules. Only `toast.css:95,121-134`, `scrap-gold.css:811` and `styles/components/CommentsTab.css:367` react, via `prefers-color-scheme: dark`. On a dark-mode tablet, those three render as dark islands on a light page. Meanwhile `index.css:100-108` forces light inputs and tables.
- The V1.1 plan claims "Both light and dark themes must look intentional (… test visually via ThemeToggle)" (`docs/planning/phase-plans/2026-07-02-v1.1-consultation-frontend-plan.md:14`). That is not achievable in the current code.

### F.6 Motion
174 transitions and 6 reduced-motion blocks. Hover lifts (`translateY(-2px)`, `materials.css:191`, `utilities.css:101`) are pointless on touch devices.

---

## G. Brand and aesthetic assessment

- **First impression (login screenshot):** a full-bleed orange gradient, a white card and a gradient button. It is warm, but it reads as "Tailwind amber template" rather than precious metal. The brand gold `#d97706` is closer to pumpkin than to 750 gold. The more metal-like golds (`#c5a55a`, `#c9a227`, `#d4a843`) appear ad hoc (PWA theme color, charts) but are not tokens.
- **Typography:** `Inter, system-ui…` (`index.css:7`) is declared, but no font file or webfont is loaded (no `@font-face`, no Google Fonts; `public/` has only icons and sounds). It renders Inter only where it is installed locally. There is no display face for the brand, no tabular numerals for prices and weights (grams, Feingold), and 50 ad hoc sizes. The portal uses its own `-apple-system` stack (`portal.css:16`).
- **Iconography:** emoji throughout the nav, buttons and widgets (`MainLayout.tsx:129-262`, `DashboardPage.tsx:248,415,486,508,593`) with inconsistent rendering. The design-lead brief asks for custom icons for Legierung, Fassung, Oberfläche and Altgold; none exist. Inline SVG appears only in ConfirmDialog and the portal mark.
- **Imagery:** photos (the product's most emotional asset) don't appear in lists, dashboards or the client portal. There is photo compare/lightbox inside order detail (`PhotoCompare.tsx`).
- **Two visual languages:** the internal app is light cream and white cards with a gold header. The client portal is a dark navy-to-brown glass look (`portal.css:11`, screenshot). The portal actually looks more "luxury craft" than the app.
- **Status color semantics:** blue = new, amber = in progress, green = completed, gray or indigo = delivered depending on the loaded stylesheet (`orders.css:152-160` vs `dashboard.css:741-744`). Amber also means "warning" (`--color-warning-*`) and "brand/primary", so "in progress", "warning" and "click me" share one hue.
- **Verdict:** generic admin template with gold paint. The bones (warm palette, touch tokens, a thoughtful scan/timer layer) could carry a considered tool. What's missing is a real metal-gold token, a type system, custom icons and photography-first lists.

---

## H. Adherence to intended principles

Sources: `.claude/agents/design-lead.md` (Jason) and `.claude/agents/ux-researcher.md` (Lena).

| Principle | Followed? | Evidence |
|---|---|---|
| Gold/amber palette with WCAG AA contrast | **No** | Palette exists (`brand-tokens.css:6-15`), but the primary CTA is 3.19:1, links 3.13:1, active nav 2.86:1, focus ring 2.15:1 (F.1) |
| All components in Tailwind v4 | **No (contradicted)** | Tailwind imported (`brand-tokens.css:1`) but the plan mandates plain CSS (`v1.1-consultation-frontend-plan.md:9`); `@utility` classes used 14 times. The two docs disagree, so pick one |
| Glass-morphism aesthetic | Barely | `@utility card` blur (`utilities.css:83-90`) mostly unused; only the portal and offline banner use it |
| 44×44 touch targets everywhere | Partial | Tokens exist (`:112-113`) and are applied to the shell, but `.btn`, `.btn-sm`, modal close and icon buttons fall short (D) |
| Responsive 10" tablet to 24" desktop | Partial | Single 768px drawer breakpoint, no tablet-specific layout, header likely overflows at 390px (C) |
| Dark mode for variable lighting | **No** | Provider and toggle unmounted; 3 files with partial dark rules (F.5) |
| Colorblind-safe status Ampel (shape or icon, not only color) | Partial | Invoices yes (`invoices.css:85-99`); dashboard deadlines and order badges are color only (`dashboard.css:502-525`, `orders.css:133-160`) |
| Custom goldsmith iconography | **No** | Emoji only (G) |
| Atomic design / component hierarchy | **No** | No atoms (Button, Badge, Modal); 56 `.btn-*` names; 17 table classes |
| 8pt grid | **No** | Spacing values like 0.35, 0.55, 0.6, 0.9rem, 5px, 14px, 3px (`buttons.css:29,55`, `admin-theme.css:45-58`); no spacing tokens |
| Storybook documentation | No | No Storybook in `package.json` |
| German long-word handling | Partial | German copy throughout, but ASCII umlauts (D). No `hyphens:auto` rule was seen; not grepped exhaustively (low confidence) |
| Lena: visibility of system status | Partial | TimerWidget, NotificationBell, HealthDot and offline banner exist; the banner is likely hidden (C) |
| Lena: one-hand QR/time flow | Largely yes | ScanFab 56px bottom-right plus overlay, TimerWidget; three competing scanner entry points (E) |
| Lena: draft preserved when interrupted | **No** | Backdrop-tap closes form modals and discards input (E) |
| Lena: Ampel readable from 2 m (wall display) | **No** | No kiosk or wall view; 0.85 to 0.95rem type |
| Lena: onboarding self-explanatory | Unknown | Not assessable statically |

---

## I. Improvement plan

| ID | Area | Problem | Evidence | Proposed change | Effort | Impact |
|---|---|---|---|---|---|---|
| I-01 | Contrast | Primary CTA, links, active nav fail AA | F.1; `brand-tokens.css:63,75` | Set `--color-interactive-primary: cta-700 #b45309`, hover cta-800; links cta-700; active nav text cta-800 on cta-50. Or dark text on gold | S | H |
| I-02 | Focus | Focus ring 2.15:1; 33 `outline:none` | `brand-tokens.css:64-65`, F.2 | Global `:focus-visible { outline: 3px solid var(--color-focus) }` with `--color-focus: #92400e` or `#1e293b`; delete per-file `outline:none` | S | H |
| I-03 | Status | 6 of 10 order statuses unstyled; 3 conflicting badge defs; 8+ badge systems | `types.ts:168-178`, `orders.css:133`, `dashboard.css:717`, `repairs.css:234` | `src/design/status.ts` map (status → label, icon, tone) plus one `<StatusBadge>`; tones as tokens `--status-{info,progress,waiting,done,archived,danger}-{fg,bg,border}`; icon plus label always | M | H |
| I-04 | Ampel | Deadline urgency is color only; absent in Orders list | `dashboard.css:502-525`, `OrdersPage.tsx:340-343` | `<DeadlineChip days>` with shape and icon (● ok / ▲ soon / ■ overdue, text "in 2 Tagen"), reused in Orders, Dashboard, Calendar and Order detail | S | H |
| I-05 | Architecture | Global class collisions (`.btn-primary` ×7, `.modal-*` ×4-5, `.form-group` ×5) | B.5 | Move shared primitives to `styles/components/` or `src/ui/`; namespace page CSS (`.orders-page .x`) or migrate to CSS Modules; delete duplicates | L | H |
| I-06 | Primitives | No Button or IconButton API; `.btn` lacks 44px | `buttons.css:25-57` | `<Button variant size>` (min 44px, `lg` = 56px for bench); `<IconButton label>` requiring `aria-label`; one CSS source | M | H |
| I-07 | Modals | 7 modals without `role=dialog`; 13 without Escape; no focus trap; backdrop-tap loses data | F.4, E | `<Modal>` with native `<dialog>` or a focus trap, Escape, `initialFocus`, `dismissOnBackdrop=false` for forms, confirm-on-dirty close | M | H |
| I-08 | Tokens | 1,580 hex (223 distinct), 9 golds, 4 text-var families, 41 undefined vars | B.2, B.3 | Single token file: primitives → semantic → component tiers; add metal-gold `--color-gold-{300..700}` from `#c5a55a`; alias and then delete `--primary-color`, `--text-primary` etc.; stylelint `color-no-hex` outside tokens | M | H |
| I-09 | Scales | 50 font sizes, 15+ radii, 98 shadows, ad hoc z-index | B.2, B.4 | Add `--space-1..10` (8pt), `--text-xs..3xl` (6 to 7 steps, bench min 1rem), `--radius-{sm,md,lg,pill}`, `--shadow-{1,2,3}`, `--z-{header,drawer,modal,toast,fab,overlay}` | M | M |
| I-10 | Offline | Offline banner under the sticky header | `OfflineIndicator.tsx:57`, `layout.css:18` | Use `--z-banner` above the header, or render inside the header flow and push content down | S | H |
| I-11 | Nav | 12 flat links, no grouping, settings unreachable | `MainLayout.tsx:122-266`, `App.tsx:199` | Group into Werkstatt (Aufträge, Reparaturen, Zeiterfassung, Scanner) / Kunden (Kunden, Beratung, Angebote) / Büro (Rechnungen, Material, Metall, Kalender) / Admin; add "Einstellungen" | S | M |
| I-12 | Mobile shell | No bottom nav; header crowding at 390px | `layout.css:231-312` | On ≤1024px: bottom tab bar (Heute, Aufträge, Scan [center FAB], Zeit, Mehr); move Abmelden into user menu; hide footer | M | H |
| I-13 | Dark mode | Promised, unmounted; partial islands | F.5 | Decide: either implement `.dark` semantic token overrides plus mount ThemeProvider/Toggle in user menu, or remove `index.html:4-11` and the 3 partial blocks. Add a "Werkstatt hoher Kontrast" mode instead if glare, not darkness, is the real problem | M | M |
| I-14 | Owner home | Anne (ADMIN) lands on KPI dashboard, not bench worklist | `DashboardPage.tsx:246,666-670` | "Heute" view for all makers: my orders by deadline chip, fittings today, running timer, scan button. KPIs become a secondary tab | M | H |
| I-15 | Lists | Orders table lacks customer and photo; rows not keyboard-accessible; "..." always | `OrdersPage.tsx:307-326` | `<ListCard>` or `<DataTable>` with thumbnail, customer, title, deadline chip, status; row as `<a>`/button; CSS line-clamp; `data-label` mobile cards everywhere | M | H |
| I-16 | Destructive actions | Edit and delete emoji buttons adjacent in every row | `OrdersPage.tsx:346-362` | Move delete into detail page or a kebab menu; keep one primary row action | S | M |
| I-17 | Copy | ASCII or dropped umlauts, "Auftragen" meaning change | D (≈20 sites) | Fix strings; centralize labels (`labels.ts`) and add a lint for `ae|oe|ue` in JSX text | S | M |
| I-18 | Empty states | Text only, no next action | `OrdersPage.tsx:296-300`, 24 variants | `<EmptyState icon title action>` with a primary CTA ("Ersten Auftrag anlegen", "QR scannen") | S | M |
| I-19 | Loading/error | 13+ loading and 5+ error patterns; `#ff4444` fails contrast | D, `index.css:75-81` | `<PageState loading/error/empty>` with skeleton rows; danger token `#b91c1c` on `#fef2f2` | S | M |
| I-20 | Base CSS | Vite template leftovers | `index.css:6-27,49-52,100-135` | Rewrite base: body from tokens, sane `h1-h3` scale, no forced input colors, drop duplicate `prefers-color-scheme: light` blocks | S | M |
| I-21 | Typography | Inter not loaded; no numerals policy | `index.css:7`, `public/` | Self-host Inter variable (woff2, precached by PWA); `font-variant-numeric: tabular-nums` for money, weights and times; optional serif display face for brand and portal headings | S | M |
| I-22 | Iconography | Emoji icons; no domain icons | `MainLayout.tsx:129-262` | Adopt one SVG set (e.g. Lucide, MIT) and draw 4 custom icons (Legierung, Fassung, Oberfläche, Altgold) in the same stroke style | M | M |
| I-23 | Inline styles | 222 `style={{}}` in 37 files | B.2 | Replace with classes or tokens during page migrations (Invoices, AdminSystem, MetalTypeManager first) | M | L |
| I-24 | Scanner | Three entry points and two scanner UIs | `MainLayout.tsx:83-85,301-306`, Dashboard quick action | Keep ScanFab plus overlay as the only scanner; `/scanner` page becomes history and manual entry; remove header link on mobile | S | M |
| I-25 | Tailwind decision | Installed and imported but banned by plan; mixed usage (OfflineIndicator) | `brand-tokens.css:1`, `utilities.css`, plan `:9` | Pick one. Recommendation: keep plain CSS plus tokens (the team's actual practice), remove the Tailwind import and `@utility` file, and port OfflineIndicator. That also removes the cascade-layer bug class | S | M |
| I-26 | Client portal | No photos, quote or approval; generic name; separate visual language; 1.65:1 footer | `CustomerPortalPage.tsx:158,250`, `portal.css:11,449` | Show latest approved progress photo and estimated date prominently; workshop name and logo from theme settings; align portal tokens with the app; fix contrast | M | H |
| I-27 | Runtime theme | Admin can set any colors without contrast checks | `useTheme.ts:52-61` | Validate contrast in the AdminSystem theme form (white-on-primary ≥ 4.5) and show a warning or auto-derive text color | S | M |
| I-28 | Bench mode | Type and targets too small at the bench | E | A "Werkbank-Modus" density class on `<html>` scaling `--text-*` +2 steps and `--touch` to 56px, tied to the existing Werkbank toggle (`ScannerContext.tsx:58`) | M | H |
| I-29 | Motion | Hover lifts on touch; few reduced-motion guards | `materials.css:191`, `utilities.css:101` | `@media (hover:hover)` guard for lifts; global reduced-motion reset | S | L |
| I-30 | Dead code | `OrderList.tsx`, unused `@utility` set, `ThemeToggle` | D, F.5 | Delete after I-05 and I-13 decisions | S | L |

### How to do it (sequencing)

1. **Week 0, quick wins (no refactor):** I-01, I-02, I-10, I-17, I-20, I-16. These are small diffs with high accessibility and trust impact. Add a Playwright a11y smoke test (axe) on login, dashboard, orders and order detail to lock them in.
2. **Consolidate tokens (I-08, I-09, I-25):** one `tokens.css` with three tiers. (a) Primitives: gold, charcoal, cream, rose, bronze and status ramps. (b) Semantic: `--color-bg-*`, `--color-fg-*`, `--color-border-*`, `--color-action-*`, `--status-*`, `--space-*`, `--text-*`, `--radius-*`, `--shadow-*`, `--z-*`, `--touch-*`. (c) Component: `--button-*`, `--badge-*`. Map legacy names to semantic aliases first, then codemod them away. Add stylelint (`color-no-hex`, `declaration-property-value-disallowed-list` for raw px in spacing) scoped to non-token files.
3. **Shared primitives (I-03, I-04, I-06, I-07, I-18, I-19):** `src/ui/` with `Button`, `IconButton`, `StatusBadge`, `DeadlineChip`, `Modal`, `EmptyState`, `PageState`, `PageHeader`, `ListCard`/`DataTable`, `Field` (label, hint, error). Each gets co-located CSS using only semantic tokens, plus a Vitest test for a11y contracts (aria-label required, Escape closes, focus returns).
4. **Shell (I-11, I-12, I-14, I-24, I-28):** grouped sidebar, bottom tab bar ≤1024px, "Heute" home, Werkbank density mode.
5. **Page migrations, highest traffic first:** Orders → Order detail → Dashboard/Heute → Time tracking → Customers → Repairs → Quotes/Invoices → the rest. Each migration deletes that page's duplicate primitives and inline styles (I-05, I-23). Track with a counter such as `grep -c '#[0-9a-f]\{6\}'` per file in CI.
6. **Brand pass (I-21, I-22, I-26, I-13):** font, icons, metal gold, portal alignment, then the dark or high-contrast decision.

### What a design-system README for AI agents should contain (`frontend/src/ui/README.md`)
- **Decision block (top):** "Plain CSS plus tokens, no Tailwind, no component library." Name the token file and the tier rules (pages may use only semantic tokens; never raw hex or px spacing).
- **Token table:** name, value, meaning and allowed usage for color (with contrast ratios pre-computed), space, type, radius, shadow, z-index, touch. Include the "never use cta-500/600 for text or white-on" rule.
- **Primitive catalogue:** import path, props, do/don't, and a minimal JSX example for each `src/ui` component. Include the status map (`status.ts`) as the single place to add a new status.
- **Workshop rules:** touch ≥44px (bench 56px); no destructive action adjacent to a frequent one; form modals never close on backdrop; every list shows deadline chip, status, customer and thumbnail; every empty state has a CTA; text ≥1rem on bench views.
- **A11y checklist:** `:focus-visible` from the global rule only; icon buttons need `label`; dialogs via `<Modal>`; rows are links; status never by color alone.
- **Copy rules:** German with real umlauts, `…` not `...`, labels from `labels.ts`, Sie vs du decision.
- **CSS scoping rule:** page CSS must be namespaced under the page root class or use CSS Modules; it must not define `.btn*`, `.modal*`, `.status-badge*`, `.form-group`.
- **Verification commands:** stylelint, the axe Playwright smoke test, screenshot widths (390 / 768 / 1280), and the hex-count ratchet.

---

## J. Screenshots taken

The full stack (backend, DB) was not available: `docker info` and `podman info` both failed, and port 8000 was serving an unrelated Django app. I ran only the Vite dev server (port 3917, stopped afterwards) and captured the two unauthenticated screens:

- `/Users/maxbook/Documents/Github/Anne/goldsmith_erp/.orchestrated-fable/ux-erp-audit-2026-09/screenshots/login-1280.png`
- `/Users/maxbook/Documents/Github/Anne/goldsmith_erp/.orchestrated-fable/ux-erp-audit-2026-09/screenshots/login-390.png`
- `/Users/maxbook/Documents/Github/Anne/goldsmith_erp/.orchestrated-fable/ux-erp-audit-2026-09/screenshots/portal-1280.png`
- `/Users/maxbook/Documents/Github/Anne/goldsmith_erp/.orchestrated-fable/ux-erp-audit-2026-09/screenshots/portal-390.png`

Dashboard, orders, order detail, customers and time tracking were **not** captured, because they need an authenticated backend. The findings for those screens are static only; for the header overflow (C) and the hidden offline banner (C/E), confidence is marked accordingly.

---

## Verification (2026-09-25)

Verifier: `.orchestrated-fable/ux-erp-audit-2026-09/verify-frontend-domain-design.md` (sections A, F and the top of I; contrast recomputed in Python). In the register, rows I-01 to I-30 are tracked as DES-01 to DES-30.

| Claim | Register ID | Verdict | Corrected impact | Verifier note |
|---|---|---|---|---|
| Primary gold CTA fails AA text contrast at 3.19:1 | DES-01 | CONFIRMED, exact | H | Every ratio in F.1 reproduced to 2 decimals |
| Dark mode announced but not implemented | DES-13 | CONFIRMED | M | Provider and toggle never rendered; exactly 3 files react to dark; also confirmed the English/German aria-label mismatch |
| 6 of 10 order statuses have no CSS style | DES-03 | CONFIRMED, exact | H | Only new, in_progress, completed, delivered styled; `delivered` gray vs indigo depending on the stylesheet |
| 1,580 hardcoded hex colours (223 distinct) | DES-08 | PARTIAL | n/a | Recount: 1,563 occurrences / 219 distinct in `frontend/src/styles`. A methodology footnote; the finding stands |

The remaining improvement-plan rows were outside the verifier's scope.
