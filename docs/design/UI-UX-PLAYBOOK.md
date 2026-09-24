# Goldsmith ERP: UI/UX Playbook

## 0. About this document
| Field | Value |
|---|---|
| Purpose | The rules every UI change in `frontend/` follows: tokens, components, page templates, accessibility, and the working process with Claude Code. |
| Audience | Humans (Max, contributors, reviewers) and AI coding agents (Claude Code, subagents such as @jason and @uxresearch). Agents treat every "must" and "never" here as a hard rule. |
| Status | Proposed target, pending approval by Max (open decisions in Appendix C). The code does not match it yet; section 9 is the migration path. Once approved, new code follows the playbook wherever code and playbook disagree. |
| Date | 2026-09-25 |
| Baseline | `design-investigation.md` (original in `.orchestrated-fable/ux-erp-audit-2026-09/`; a copy is added under `docs/design/`), a static audit of `main` @73fff19 dated 2026-09-24. All counts in this document come from it unless marked "computed" (see Appendix B). |
| Sources | [Claude Design: set up your design system](https://support.claude.com/en/articles/14604397-set-up-your-design-system-in-claude-design); [aidesigner.ai: How to design beautiful UIs with Claude Code](https://www.aidesigner.ai/blog/claude-code-frontend-design); [Snyk: Top 8 Claude skills for UI/UX engineers](https://snyk.io/articles/top-claude-skills-ui-ux-engineers/); local Anthropic `frontend-design` skill (`~/.claude/plugins/marketplaces/claude-plugins-official/plugins/frontend-design/skills/frontend-design/SKILL.md`). Notes on each are in `docs/design/research/`. |

Language: this document is English. Product words (labels, statuses, buttons) are German and appear in the exact form the UI must show.

## 1. Product context and design principles
Goldsmith ERP runs one goldsmith workshop: the owner Anne, a few staff, bench work with dirty or gloved hands, tablets and phones on the LAN, QR codes on job bags. The goal is simple: make it faster for the goldsmith to know where every piece and every client stands, and give clients clearer feedback on their jewelry. Office tasks (invoices, metal stock) matter, but the bench is the hardest context and sets the floor for everything else.
### P1. Readable from one metre
A goldsmith glances at a tablet propped on the bench while holding a piece. The one fact that matters on a screen (status, deadline, next step) must be readable from about 1 m under bright, directional workshop light. That means body text at 1rem minimum on bench views, a high-contrast palette (text at 7:1 or better where possible, never below 4.5:1), and status shown by icon plus label, never by colour alone.
- Do: show "▲ in 2 Tagen" with an icon and a text label next to the order title, in `--type-md` or larger.
- Don't: show a plain date in 0.85rem grey text and expect the user to work out urgency.
### P2. Big targets, no typing
Hands are dirty, gloved or busy. Every interactive element is at least 44 x 44 px (`--touch-min`); primary bench actions are 56 px (`--touch-comfort`). Prefer taps, chips, steppers, pickers and scans over free text. When typing is unavoidable, set the right `inputmode` so the phone shows the right keyboard.
- Do: offer "Anprobe erledigt" as a single 56 px button on the order card.
- Don't: make the user open a modal, find a status dropdown and confirm.
### P3. Scan first
The QR code on the job bag is the fastest way into any order. The scan action is reachable from every screen with one thumb (the ScanFab, bottom right), and a scan lands on the order with its next action already offered. One scanner entry point, one scanner UI.
- Do: scan, land on the order, see "Zeit starten" and the status change button at the top.
- Don't: keep three competing scanner entry points (header link, FAB, dashboard tile) with two different UIs (design-investigation E, I-24).
### P4. Every display links to its next action
A number, alert or empty list is only useful if it leads somewhere. Every KPI, badge, warning and empty state carries a link or button to the thing you would do next (this is a project rule in `CLAUDE.md`). Destructive actions are never the easiest tap.
- Do: "3 Aufträge überfällig" links to the filtered order list; an empty order list shows "Ersten Auftrag anlegen".
- Don't: show "Keine Aufträge gefunden." with nothing to press, or put 🗑️ next to ✏️ in every table row (design-investigation I-16).
### P5. German, one hand, and sometimes offline
The UI speaks correct German (real umlauts, `…` not `...`, one term per concept, see section 11) in the user's vocabulary. Phone layouts work with one thumb: primary actions sit in the bottom half, navigation is a bottom tab bar. The LAN drops sometimes; the app says so visibly, keeps unsaved input, and never loses a half-filled form to a stray tap on the backdrop.
- Do: "Auftrag speichern" produces the toast "Auftrag gespeichert"; the offline banner sits above the header; a dirty form asks before closing.
- Don't: ship "Loschen", "Bestatigen" or "fuer" (design-investigation D, about 20 occurrences), or close a form modal on backdrop tap.

## 2. Current state (the baseline we migrate away from)
Source: `design-investigation.md` sections B to H. Paths are relative to `frontend/`.

| Area | What exists today | Evidence |
|---|---|---|
| Tokens | `src/styles/brand-tokens.css` (114 lines): Tailwind v4 `@import "tailwindcss"` plus an `@theme` block with cta (amber), primary (slate), cream, accent (rose), secondary (bronze) ramps, and a small semantic `:root` tier. No spacing, type, radius, shadow, z-index or motion scales; only `--touch-min` / `--touch-comfort`. | `brand-tokens.css:1-114`, B.4 |
| Stylesheets | 40 global plain-CSS files (27 in `src/styles/`, 13 in `src/styles/components/`), 14,789 lines, loaded lazily per route and never unloaded, so shared class names change look with navigation history. | A, B.5 |
| Tailwind use | Imported but barely used: 14 usages of `@utility` classes, about 26 class strings. A plan doc says "NO Tailwind". | A, I-25 |
| Hard-coded colour | 1,580 hex values in CSS (223 distinct), 192 in TSX, 222 inline `style={{}}` in 37 files, 9 different golds, 4 variable families for "body text", 41 custom properties referenced but never defined. | B.2, B.3 |
| Duplicates | `.btn-primary` defined 7 times, 56 distinct `.btn-*` names, `.status-badge` 3 conflicting definitions plus 8+ other badge systems, `.modal-overlay` x4, `.modal-header` x5, `.form-group` x5, 17 table classes. | B.5, D |
| Contrast | Primary gold `#d97706` with white text: 3.19:1 (fails AA). Focus ring `#f59e0b` on white: 2.15:1. Active nav 2.86:1. Global error red `#ff4444`: 3.41:1. | F.1 |
| Focus and dialogs | `outline: none` 33 times, 18 `:focus-visible` rules. 7 of 15 modal files lack `role="dialog"`, 2 handle Escape, no focus trap anywhere. | F.2, F.4 |
| Status | `OrderStatus` has 10 values; only `new`, `in_progress`, `completed`, `delivered` have CSS. `draft`, `confirmed`, `waiting_for_fitting`, `fitting_done`, `ready_for_setting`, `quality_check` render unstyled. Labels differ between pages (for example "Endkontrolle" vs "Qualitätsprüfung"). | D, `types.ts:168-178`, `OrderDetailPage.tsx:551-560`, `CustomerDetailPage.tsx:23-35` |
| Dark mode | `index.html` adds `.dark`, but `ThemeProvider` and `ThemeToggle` are never mounted; only three files have dark rules. | F.5 |
| Type and icons | `Inter` declared but never loaded; 50 distinct font sizes; emoji as icons in nav and buttons. | G, B.2 |
| Good parts to keep | 44 px touch tokens, TimerWidget, 56 px ScanFab (`ScanFab.css:26-31`), ConfirmDialog focus and Escape handling (`ConfirmDialog.tsx:54-70`), colour-blind-safe invoice badges (`invoices.css:85-99`), 41 live or alert regions. | D, F.3 |

The rest of this playbook describes the target. Section 9 sequences the move.

## 3. Design tokens: the single source of truth
**Rule: no hex, `rgb()`, `hsl()` or named colour appears outside `frontend/src/styles/brand-tokens.css`.** Pages and components use semantic tokens only (never the raw `--color-brand-*` ramps). The same applies to spacing, type size, radius, shadow, z-index and duration: use the scale token. Media-query breakpoints are the one allowed literal, because CSS custom properties cannot be used inside `@media`.

Tiers:
1. **Primitives** (`@theme static` block): raw ramps. Only `brand-tokens.css` references them.
2. **Semantic** (`:root`): roles such as `--color-text`, `--color-primary`, `--tone-done-fg`. Everything else uses these.
3. **Component** (optional, in the component's own CSS): `--button-height` and similar, defined from semantic tokens.
### 3.1 Colour roles (light theme)
All ratios computed with the WCAG 2.x relative-luminance formula (script in Appendix B). "Surface" is the page background `#faf8f4` (kept from today's `--color-surface-page`); "raised" is card white.

| Token | Value | Use | Contrast (computed) |
|---|---|---|---|
| `--color-surface` | `#faf8f4` | page background | |
| `--color-surface-raised` | `#ffffff` | cards, dialogs, inputs | |
| `--color-surface-sunken` | `#f3efe7` | table headers, wells, tab strip | |
| `--color-text` | `#1e293b` | body and headings | 13.79 on surface, 14.63 on raised, 12.76 on sunken |
| `--color-text-muted` | `#57534e` | secondary text, meta | 7.19 on surface, 7.63 on raised, 6.65 on sunken |
| `--color-border` | `#e3ddd2` | decorative dividers only | 1.35 on raised (not for input edges) |
| `--color-border-strong` | `#8a8175` | input, checkbox and card-edge boundaries that carry meaning | 3.83 on raised, 3.61 on surface (1.4.11 needs 3.0) |
| `--color-primary` | `#b45309` | primary button fill, links, active nav marker | white on it 5.02; as link text 4.73 on surface, 5.02 on raised |
| `--color-primary-hover` | `#92400e` | hover and pressed | white on it 7.09 |
| `--color-primary-contrast` | `#ffffff` | text and icons on primary | 5.02 |
| `--color-primary-subtle` | `#fef3c7` | active nav background, selected row | `#92400e` text on it 6.37 |
| `--color-accent` | `#c5a55a` | metal gold for brand marks, rules, chart series. Decorative only | 2.36 vs white: never text, never the only boundary. `#1e293b` on it 6.20 |
| `--color-accent-strong` | `#7c5e10` | accent-coloured text (portal headings, price highlights) | 6.06 on raised |
| `--color-success` / `-bg` / `-fg` | `#15803d` / `#dcfce7` / `#166534` | success fills, badges | white on `#15803d` 5.02; fg on bg 6.49 |
| `--color-warning` / `-bg` / `-fg` | `#c2410c` / `#ffedd5` / `#9a3412` | warnings, "waiting" | white on `#c2410c` 5.18; fg on bg 6.38. Today's `#e08020` with white text gives 2.89 |
| `--color-danger` / `-bg` / `-fg` | `#b91c1c` / `#fee2e2` / `#991b1b` | errors, destructive buttons | white on `#b91c1c` 6.47; `#b91c1c` text 6.47 on raised, 6.10 on surface; fg on bg 6.80 |
| `--color-info` / `-bg` / `-fg` | `#1d4ed8` / `#dbeafe` / `#1e40af` | info notes, running timer | fg on bg 7.15 |
| `--color-focus` | `#1e293b` | focus ring on light surfaces | 13.79 on surface |
| `--color-focus-on-dark` | `#ffffff` | focus ring on the gold header | 5.02 on `#b45309` |
| `--color-header-bg` | gradient `#b45309` to `#78350f` | app header | white text 5.02 at the light end, 9.07 at the dark end |

**Why `#b45309`:** it is the existing `--color-brand-cta-700`, it keeps the amber identity, and it is the smallest move that passes AA for white text (5.02:1), exactly as design-investigation I-01 recommends. `#d97706` (3.19) and `#f59e0b` (2.15) stay as primitives but must never carry text or be the focus ring. The metal gold `#c5a55a` becomes the brand accent, which gives the app a precious-metal note without a contrast cost, as long as it is decorative.

Focus ring note: `#1e293b` against the `#b45309` button itself is only 2.91:1, so the ring is always drawn with `outline-offset: 2px`, which places it on the surface (13.79:1).
### 3.2 Status colours, icons and labels
One map (`src/design/status.ts`, to be created in phase 2) holds label, tone and icon for every status. `<StatusBadge>` reads only from it. Tones are token triplets `--tone-<name>-fg / -bg / -border`. Icons are Lucide names (MIT, design-investigation I-22). Labels are the canonical German strings; where pages disagree today, this table wins.

Tones (fg on bg, computed): neutral `#374151` on `#f3f4f6` 9.37; info `#1e40af` on `#dbeafe` 7.15; progress `#115e59` on `#ccfbf1` 6.73; waiting `#9a3412` on `#ffedd5` 6.38; check `#5b21b6` on `#ede9fe` 7.57; done `#166534` on `#dcfce7` 6.49; handover `#334155` on `#e2e8f0` 8.40; danger `#991b1b` on `#fee2e2` 6.80. Amber is deliberately **not** a status tone, so "in progress", "warning" and "click me" no longer share one hue (design-investigation G).

**Order statuses** (`OrderStatusEnum`, `src/goldsmith_erp/db/models.py:47-63`; `OrderStatus`, `frontend/src/types.ts:168-178`):

| Value | Label (de) | Tone | Icon | Border | Note |
|---|---|---|---|---|---|
| `draft` | Entwurf | neutral | `pencil` | dashed | not yet confirmed with the customer |
| `new` | Neu | info | `sparkles` | solid | legacy value; display only, never set by new code |
| `confirmed` | Bestätigt | info | `clipboard-check` | solid | |
| `in_progress` | In Bearbeitung | progress | `hammer` | solid | |
| `waiting_for_fitting` | Wartet auf Anprobe | waiting | `hourglass` | solid | blocked on the customer |
| `fitting_done` | Anprobe abgeschlossen | progress | `user-check` | solid | |
| `ready_for_setting` | Bereit zum Fassen | progress | `gem` | solid | today also "Bereit für Steinbesatz"; use "Bereit zum Fassen" |
| `quality_check` | Qualitätskontrolle | check | `scan-search` | solid | today also "Endkontrolle" / "Qualitätsprüfung"; same word as repairs |
| `completed` | Fertiggestellt | done | `circle-check` | solid | |
| `delivered` | Ausgeliefert | handover | `package-check` | double | finished and with the customer |

**Repair statuses** (`RepairJobStatus`, `models.py:1788-1805`; labels today in `RepairsPage.tsx:16-26`):

| Value | Label (de) | Tone | Icon | Border | Note |
|---|---|---|---|---|---|
| `received` | Eingang | info | `inbox` | solid | |
| `diagnosed` | Diagnose | progress | `search` | solid | |
| `quoted` | Angebot offen | waiting | `file-text` | solid | today "Angebot"; "offen" makes the waiting state explicit |
| `approved` | Genehmigt | info | `thumbs-up` | solid | |
| `in_repair` | In Arbeit | progress | `wrench` | solid | |
| `quality_check` | Qualitätskontrolle | check | `scan-search` | solid | |
| `ready` | Abholbereit | done | `circle-check` | solid | today "Fertig"; the model comment says Abholbereit |
| `picked_up` | Abgeholt | handover | `package-check` | double | |
| `cancelled` | Storniert | danger | `circle-x` | solid, label struck through | |

**Other status families** (same map, same component; labels from the model comments):

| Family (enum) | Values and tone |
|---|---|
| Quote (`QuoteStatus`) | Entwurf neutral, Gesendet waiting, Genehmigt done, Abgelehnt danger, Abgelaufen neutral, In Auftrag umgewandelt handover |
| Invoice (`InvoiceStatus`) | Entwurf neutral, Versendet waiting, Bezahlt done, Überfällig danger, Storniert danger (keep the prefix plus border-style pattern from `invoices.css:85-99`) |
| Consultation (`ConsultationStatus`) | Entwurf neutral, Abgeschlossen done, Umgewandelt handover, Archiviert neutral |
| Cost change (`CostChangeStatus`) | Entwurf neutral, Gesendet waiting, Zugestimmt done, Abgelehnt danger, Ersetzt neutral |
| Handoff (`HandoffStatusEnum`) | Offen waiting, Übernommen done, Abgelehnt danger |
| Hallmark (`HallmarkStatus`) | Nicht eingereicht neutral, Eingereicht waiting, Genehmigt info, Abgelehnt danger, Punziert done |
| Scrap gold (`ScrapGoldStatus`) | Erfasst info, Berechnet progress, Unterschrieben done, Verrechnet handover |
| Customer update (`CustomerUpdateStatus`) | Entwurf neutral, Versendet done, Versand fehlgeschlagen danger |

Deadline urgency is not a status but uses the same rule (shape plus text, design-investigation I-04): `<DeadlineChip>` shows ● "in 9 Tagen" (neutral), ▲ "in 2 Tagen" (waiting), ■ "3 Tage überfällig" (danger).
### 3.3 Scales
| Scale | Tokens |
|---|---|
| Spacing (4 px base, 8 pt rhythm) | `--space-1` 4px, `--space-2` 8px, `--space-3` 12px, `--space-4` 16px, `--space-5` 24px, `--space-6` 32px, `--space-7` 48px, `--space-8` 64px |
| Type size (ratio about 1.25) | `--type-sm` 0.875rem (meta, table headers; never on bench views), `--type-base` 1rem, `--type-md` 1.125rem, `--type-lg` 1.375rem, `--type-xl` 1.75rem, `--type-2xl` 2.25rem, `--type-glance` 3rem (bench and wall numbers). Line height 1.5 body, 1.2 headings |
| Fonts | `--font-sans`: "IBM Plex Sans", system-ui, sans-serif. `--font-mono`: "IBM Plex Mono", ui-monospace, monospace (order numbers, hallmark and lot codes only). `--font-serif`: "IBM Plex Serif", Georgia, serif (portal and document headings only). Weights 400, 500, 600. Self-host woff2 files and precache them in the PWA; do not load from a font CDN (offline use, and no third-party requests from customer pages) |
| Numerals | `font-variant-numeric: tabular-nums` on prices, weights (g), fineness, hours and dates |
| Radius | `--radius-sm` 4px (inputs, badges), `--radius-md` 8px (buttons, cards), `--radius-lg` 12px (dialogs, sheets), `--radius-pill` 999px (chips only) |
| Shadow | `--shadow-1` (cards), `--shadow-2` (dropdowns, sticky bars), `--shadow-3` (dialogs). No other shadows |
| Motion | `--duration-fast` 120ms (press, hover), `--duration-base` 200ms (expand, toast in), `--duration-slow` 300ms (sheet, drawer). `--ease-standard` cubic-bezier(0.2, 0, 0, 1) |
| Reduced motion | One global rule: under `prefers-reduced-motion: reduce`, all transitions and animations drop to 0.01ms and no transform-based entrance runs. Hover lifts only inside `@media (hover: hover)` |
| Breakpoints | phone below 600px, tablet 600px to 1023px, desktop 1024px and up. Bottom tab bar below 1024px. The two widths 600px and 1024px are the only allowed media-query values (today there are about 20) |
| Z-index | `--z-header` 100, `--z-banner` 110 (offline banner above header), `--z-drawer` 200, `--z-timer` 300, `--z-fab` 310, `--z-modal` 400, `--z-scan` 500, `--z-toast` 600 |
| Touch | `--touch-min` 44px (every target), `--touch-comfort` 56px (bench primary actions, Werkbank-Modus default). Absolute floor per WCAG 2.5.8 is 24 x 24 px with spacing, used only for dense desktop tables |

### 3.4 Target `brand-tokens.css`
```css
@import "tailwindcss";

/* Tier 1: primitives. `static` emits every variable even when no Tailwind utility
   uses it, because plain CSS files reference them via var(). Existing cta, primary,
   cream, accent and secondary ramps stay unchanged; two ramps are added. */
@theme static {
  --color-brand-cta-100: #fef3c7; --color-brand-cta-700: #b45309;
  --color-brand-cta-800: #92400e; --color-brand-cta-900: #78350f;   /* (excerpt) */
  --color-brand-metal-400: #c5a55a; --color-brand-metal-700: #7c5e10; /* new: metal gold */
  --color-brand-stone-50: #faf8f4;  --color-brand-stone-100: #f3efe7;  /* new: warm neutrals */
  --color-brand-stone-200: #e3ddd2; --color-brand-stone-500: #8a8175;
  --color-brand-stone-600: #57534e;
  --font-sans: "IBM Plex Sans", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, monospace;
  --font-serif: "IBM Plex Serif", Georgia, serif;
}

/* Tier 2: semantic roles. The only tokens pages and components may use. */
:root {
  --color-surface: var(--color-brand-stone-50);   --color-surface-raised: #ffffff;
  --color-surface-sunken: var(--color-brand-stone-100);
  --color-text: var(--color-brand-primary-800);   --color-text-muted: var(--color-brand-stone-600);
  --color-border: var(--color-brand-stone-200);   --color-border-strong: var(--color-brand-stone-500);
  --color-primary: var(--color-brand-cta-700);    --color-primary-hover: var(--color-brand-cta-800);
  --color-primary-contrast: #ffffff;              --color-primary-subtle: var(--color-brand-cta-100);
  --color-accent: var(--color-brand-metal-400);   --color-accent-strong: var(--color-brand-metal-700);
  --color-success: #15803d; --color-success-bg: #dcfce7; --color-success-fg: #166534;
  --color-warning: #c2410c; --color-warning-bg: #ffedd5; --color-warning-fg: #9a3412;
  --color-danger: #b91c1c;  --color-danger-bg: #fee2e2;  --color-danger-fg: #991b1b;
  --color-info: #1d4ed8;    --color-info-bg: #dbeafe;    --color-info-fg: #1e40af;
  --color-focus: var(--color-brand-primary-800);  --color-focus-on-dark: #ffffff;
  --color-header-bg: linear-gradient(135deg, var(--color-brand-cta-700), var(--color-brand-cta-900));

  --tone-neutral-fg: #374151;  --tone-neutral-bg: #f3f4f6;  --tone-neutral-border: #9ca3af;
  --tone-info-fg: #1e40af;     --tone-info-bg: #dbeafe;     --tone-info-border: #3b82f6;
  --tone-progress-fg: #115e59; --tone-progress-bg: #ccfbf1; --tone-progress-border: #14b8a6;
  --tone-waiting-fg: #9a3412;  --tone-waiting-bg: #ffedd5;  --tone-waiting-border: #f97316;
  --tone-check-fg: #5b21b6;    --tone-check-bg: #ede9fe;    --tone-check-border: #8b5cf6;
  --tone-done-fg: #166534;     --tone-done-bg: #dcfce7;     --tone-done-border: #22c55e;
  --tone-handover-fg: #334155; --tone-handover-bg: #e2e8f0; --tone-handover-border: #64748b;
  --tone-danger-fg: #991b1b;   --tone-danger-bg: #fee2e2;   --tone-danger-border: #ef4444;

  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
  --space-5: 24px; --space-6: 32px; --space-7: 48px; --space-8: 64px;
  --type-sm: 0.875rem; --type-base: 1rem; --type-md: 1.125rem; --type-lg: 1.375rem;
  --type-xl: 1.75rem; --type-2xl: 2.25rem; --type-glance: 3rem;
  --radius-sm: 4px; --radius-md: 8px; --radius-lg: 12px; --radius-pill: 999px;
  --shadow-1: 0 1px 2px rgb(30 41 59 / 0.08); --shadow-2: 0 4px 12px rgb(30 41 59 / 0.12);
  --shadow-3: 0 12px 32px rgb(30 41 59 / 0.18);
  --duration-fast: 120ms; --duration-base: 200ms; --duration-slow: 300ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
  --z-header: 100; --z-banner: 110; --z-drawer: 200; --z-timer: 300;
  --z-fab: 310; --z-modal: 400; --z-scan: 500; --z-toast: 600;
  --touch-min: 44px; --touch-comfort: 56px;

  /* Legacy aliases (kept until phase 4, then deleted), including undefined names in use. */
  --color-interactive-primary: var(--color-primary);
  --color-interactive-primary-hover: var(--color-primary-hover);
  --color-border-focus: var(--color-focus); --ring-color-focus: var(--color-focus);
  --text-color-link: var(--color-primary);
  --text-primary: var(--color-text); --text-secondary: var(--color-text-muted);
}

/* Werkbank-Modus: bigger type and targets (design-investigation I-28). */
:root.bench { --type-base: 1.125rem; --type-md: 1.375rem; --touch-min: 56px; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; }
}
```
Verify after any token change: `yarn build`, then grep the built CSS in `frontend/dist/assets/` for a primitive you added to confirm Tailwind emitted it.

## 4. Component primitives
All primitives live in `frontend/src/ui/`, one folder each (`Button/Button.tsx`, `Button/Button.css`, `Button/Button.test.tsx`). Co-located CSS uses semantic tokens only, and its class names are prefixed `ui-` so they cannot collide with page CSS. Pages must not define `.btn*`, `.modal*`, `.status-badge*`, `.form-group` or `.empty-state` (design-investigation, README guidance). Each primitive ships a Vitest test for its accessibility contract.
### 4.1 Button and IconButton
Purpose: every clickable action. Replaces `.btn-primary` x7 (`buttons.css:59`, `materials.css:185`, `customers.css:333`, `auth.css:78`, `repairs.css:469`, `calendar.css:368`, `utilities.css:4`) and the 56 `.btn-*` names.
```ts
type ButtonProps = {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'md' | 'lg';            // md = 44px, lg = 56px (bench); no size below 44px
  loading?: boolean;             // keeps width, shows spinner, sets aria-busy, blocks clicks
  icon?: IconName;               // leading icon, decorative (aria-hidden)
  type?: 'button' | 'submit';    // default 'button'
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'type'>;

type IconButtonProps = {
  icon: IconName;
  label: string;                 // required; becomes aria-label and the tooltip
  variant?: 'ghost' | 'secondary' | 'danger';
  size?: 'md' | 'lg';
};
```
States: default, hover (`@media (hover: hover)` only), pressed, focus-visible, disabled, loading. Rules: one `primary` per view region; `danger` never sits directly next to the frequent action; labels are verb plus noun ("Auftrag speichern"); no emoji and no trailing `→`; icon-only buttons are only for universally known actions (close, more, edit) and always have `label`. Links that navigate are `<a>`/`<Link>` styled as a button, not buttons.
### 4.2 StatusBadge and DeadlineChip
Purpose: show any status. Replaces `status-badge` in `orders.css:133-160`, `dashboard.css:717-744`, `repairs.css:234`, and `invoice-`, `quote-`, `kundeninfo-`, `cost-change-`, `handoff-`, `scrap-gold-`, `portal-status-badge`.
```ts
type StatusKind = 'order' | 'repair' | 'quote' | 'invoice' | 'consultation'
  | 'costChange' | 'handoff' | 'hallmark' | 'scrapGold' | 'customerUpdate';
type StatusBadgeProps = { kind: StatusKind; status: string; size?: 'md' | 'lg' };
type DeadlineChipProps = { deadline: string | null; now?: Date };
```
Always icon plus label, sentence case (no `text-transform: uppercase`), tone from section 3.2. Unknown values render the raw value in neutral and log a warning, so a new backend status is noticed. The badge is text, not a button; if it opens a status change, wrap it in a Button.
### 4.3 Modal, Dialog and Sheet
Purpose: every overlay. Replaces 17 `modal-overlay` usages with 4 CSS definitions (`pages.css:3-15` and others), `confirm-dialog-overlay`, `cost-change-modal-overlay`, `timer-stop-dialog-overlay`, `punz-overlay`, `photo-lightbox-overlay`, `modal-backdrop`, `modal-box`.
```ts
type ModalProps = {
  open: boolean;
  onClose: () => void;
  title: string;                   // rendered as h2, wired to aria-labelledby
  description?: string;            // aria-describedby
  size?: 'sm' | 'md' | 'lg';
  initialFocusRef?: React.RefObject<HTMLElement>;
  dismissOnBackdrop?: boolean;     // default false; true only for read-only content
  isDirty?: boolean;               // asks "Änderungen verwerfen?" before closing
  footer?: React.ReactNode;        // primary action right on desktop, full-width bottom on phone
  children: React.ReactNode;
};
```
Build on native `<dialog>` with `showModal()` (gives focus containment and `inert` background), or a tested focus trap. Escape closes (subject to `isDirty`). Focus returns to the trigger on close. Close button is an IconButton of 44 px (today about 32 px, `pages.css:44-51`). Below 600px the modal becomes a full-screen sheet with the footer pinned to the bottom. ConfirmDialog becomes `<Modal size="sm">` and keeps its good parts (`ConfirmDialog.tsx:54-70`), with correct labels "Löschen" and "Bestätigen" (today "Loschen", "Bestatigen", `ConfirmDialog.tsx:83`).
### 4.4 Field (form fields)
Purpose: label, input, help and error as one unit. Replaces `.form-group` x5, `.error-message` x5, `error-text`, and the per-form `.required` styles (`orders.css:47-70`).
```ts
type FieldProps = {
  label: string;                   // always visible; placeholder is never the label
  name: string;
  required?: boolean;              // shows "Pflichtfeld" marker text, sets aria-required
  help?: string;                   // aria-describedby
  error?: string;                  // aria-invalid + aria-describedby, text starts with what is wrong
  inputMode?: 'text' | 'decimal' | 'numeric' | 'tel' | 'email' | 'search';
  children: React.ReactElement;    // the input, select or textarea; Field wires id/htmlFor
};
```
Input rules: height at least 44px, 1rem text (prevents iOS zoom), border `--color-border-strong`, focus uses the global ring. Weights and prices: `inputMode="decimal"`, accept both comma and point, show the unit ("g", "€") as a suffix. Phone: `type="tel"`. Order number or QR fallback: `inputMode="numeric"` with a scan button beside it. Errors in German say what is wrong and how to fix it ("Gewicht fehlt. Bitte in Gramm eingeben."), never just "Ungültig". On submit with errors, focus moves to the first invalid field and an error summary is announced.
### 4.5 DataTable and ListCard
Purpose: every list. Replaces 17 table classes (`orders-table`, `order-table`, `data-table`, `repairs-table`, `quotes-table`, `invoices-table`, `materials-table`, `metal-inventory-table`, `line-items-table`, ...).
```ts
type Column<T> = { key: string; header: string; render: (row: T) => React.ReactNode;
  align?: 'start' | 'end'; hideBelow?: 'tablet' | 'desktop'; numeric?: boolean };
type DataTableProps<T> = { rows: T[]; columns: Column<T>[]; rowHref: (row: T) => string;
  caption: string; state: PageStateValue; empty: EmptyStateProps };
```
Desktop (1024px and up): semantic `<table>` with `<caption>` (visually hidden allowed), sticky sunken header in sentence case, numeric columns right-aligned with tabular numerals. Tablet and phone: each row becomes a ListCard (thumbnail, title, customer, DeadlineChip, StatusBadge) with the whole card as one link. Rows are links (`<a>`), never `<tr onClick>` (today `OrdersPage.tsx:320-323`, `RepairsPage.tsx:373`). One row action at most; delete lives on the detail page or behind a "Mehr" menu. Truncate with CSS `line-clamp`, not `substring(0, 50) + "..."` (`OrdersPage.tsx:326`).
### 4.6 Card
Purpose: group related content on detail pages and dashboards. Replaces `stat-card`, `kpi-card`, `summary-card` and the unused glass `@utility card` (`utilities.css:83-90`). Props: `title?`, `action?` (a link or Button in the card header), `tone?` (for alert cards), `children`. Rules: raised surface, `--radius-md`, `--shadow-1` or a border, never both plus a gradient. Do not chop every page into identical cards (the "SaaS-card kit" tell from the frontend-design skill); use cards where content really is a separate group, and plain sections elsewhere.
### 4.7 EmptyState
Purpose: tell the user what to do when there is nothing to show. Replaces `empty-state` x10 plus 14 variants (`repairs-empty`, `cdetail-empty`, `handoff-empty`, ...). Props: `icon`, `title`, `body?`, `action` (required for lists the user can fill; optional only for truly read-only views). Example: title "Noch keine Aufträge", action "Ersten Auftrag anlegen", secondary "QR-Code scannen".
### 4.8 LoadingState and PageState
Purpose: loading, error and empty for a whole page or region. Replaces `page-loading` x13 plus 12 variants and `page-error` x14. `type PageStateValue = { status: 'loading' | 'error' | 'empty' | 'ready'; error?: string; retry?: () => void }`. Skeleton rules: skeletons mirror the real layout (rows for lists, blocks for detail), appear only after 300ms to avoid flicker, and are `aria-hidden` with a visually hidden "Wird geladen…" in a polite live region. Errors show what failed and a "Erneut versuchen" button. One loading string: "Wird geladen…" with a real ellipsis.
### 4.9 Toast
Purpose: short confirmation of an action the user just took. Keep `Toast.tsx` and `ToastContext`; fix two things. (1) Only `error` toasts use `role="alert"`; success, info and warning use `role="status"` (today every toast is `role="alert"`, `Toast.tsx:75`). (2) Dismiss label "Benachrichtigung schließen" (today "schliessen", `Toast.tsx:91`). Rules: the toast repeats the button's verb in past tense ("Auftrag gespeichert"); errors that need a decision go in the page or a dialog, not a toast; destructive success toasts offer "Rückgängig" where the backend allows it; toasts sit above the tab bar and the FAB (`--z-toast`) and never cover the primary button.
### 4.10 PageHeader
Purpose: page title, context and the one primary action. Replaces `.page-header` in `pages.css` and `invoices.css` and the per-page title blocks. Props: `title`, `subtitle?`, `back?: { href: string; label: string }`, `primaryAction?: ButtonProps & { label: string }`, `secondaryActions?`. Rules: the page title is the only `h1` (the header logo stops being an `h1`, `MainLayout.tsx:78`); the primary action sits top-right on desktop and becomes a sticky bottom bar or the FAB position on phones.
### 4.11 Tab bar and navigation
Purpose: move between sections. Two parts. (1) **App tab bar** below 1024px: five slots "Heute", "Aufträge", "Scan" (centre, 56px), "Zeit", "Mehr"; icon plus label, `aria-current="page"` on the active item, respects the safe-area inset, and the TimerWidget sits above it. Desktop keeps the sidebar, grouped as Werkstatt (Aufträge, Reparaturen, Zeiterfassung, Scanner), Kunden (Kunden, Beratung, Kostenvoranschläge), Büro (Rechnungen, Material, Metallinventar, Kalender), Verwaltung (Benutzer, System, Einstellungen) per design-investigation I-11. The drawer, where still used, closes on Escape and returns focus. (2) **In-page tabs** (order detail, order form, replaces `.form-tabs` in `orders.css:11-41`): WAI-ARIA tabs pattern (`role="tablist"`, arrow-key navigation, `aria-selected`), 44px tall, horizontally scrollable on phones, no tab hidden behind "more" if it holds required fields.

## 5. Page templates
Each page uses exactly one template. Primary action placement is fixed per template so users build muscle memory.
### 5.1 List page (Aufträge, Reparaturen, Kunden, Rechnungen)
```
Desktop (>=1024)                                   Phone (<600)
+------------------------------------------------+ +----------------------+
| Aufträge                       [+ Neuer Auftrag]| | Aufträge         [⋮] |
| [Suche.........] [Status v] [Frist v]  12 von 40| | [Suche.............] |
+------------------------------------------------+ | (Alle)(Offen)(Heute) |
| Foto | Titel        | Kunde   | Frist   | Status| +----------------------+
| [img]| Trauringe    | Meier   | ▲ 2 Tg. | ⚒ In..| | [img] Trauringe      |
| [img]| Kette kürzen | Schulz  | ● 9 Tg. | ✓ Bes.| |  Meier  ▲ in 2 Tagen |
+------------------------------------------------+ |  ⚒ In Bearbeitung    |
                                                   +----------------------+
                                                   |         ...          |
                                                   |          [+] (FAB)   |
                                                   |Heute Auftr ◉ Zeit Mehr|
                                                   +----------------------+
```
Rules: primary action in PageHeader (desktop) or as a bottom-right FAB above the tab bar (phone; the scan FAB moves to the tab bar centre). Filters as chips on phone, selects on desktop; the current filter is in the URL. Every row shows photo, title, customer, DeadlineChip and StatusBadge (design-investigation I-15). Empty state with action. Default sort: deadline ascending.
### 5.2 Detail page (Auftrag, Kunde, Reparatur)
```
+----------------------------------------------------------+
| ‹ Aufträge                                               |
| Trauringe Meier   ⚒ In Bearbeitung   ▲ in 2 Tagen         |
| [Nächster Schritt: Anprobe erledigt]  [Zeit starten] [⋮] |
+-------------------------------+--------------------------+
| Tabs: Übersicht | Fotos | Material | Zeit | Kunde        |
| (tab content)                 | Side panel (desktop):    |
|                               | Kunde, Frist, Preis*,    |
|                               | letzte Aktivität         |
+-------------------------------+--------------------------+
 * price only for ADMIN / GOLDSMITH (CLAUDE.md financial-data rule)
```
Rules: the header shows identity (photo, title), status, deadline and the **next action** as the primary button, derived from the status (for example `waiting_for_fitting` offers "Anprobe erledigt"). Destructive actions live in the "⋮" menu with a ConfirmDialog. On phone the side panel moves under the header as a collapsible summary, and the primary action is a sticky bottom bar. Customer detail follows the same frame with "Neuer Auftrag für diese Kundin" as the primary action. Design IP and pricing blocks render only for permitted roles; never hide them with CSS alone.
### 5.3 Wizard (Beratung, consultation)
```
+--------------------------------------------------+
| Beratung: Frau Meier               Entwurf ✎     |
| (1) Anlass ─ (2) Wunsch ─ (3) Maße ─ (4) Abschluss|
+--------------------------------------------------+
| Step content, one topic per step, chips first    |
|                                                  |
+--------------------------------------------------+
| [Zurück]                  Gespeichert  [Weiter]  |
+--------------------------------------------------+
```
Rules: numbered steps are allowed here because the content is a real sequence. Auto-save every step (the model's `draft` status is the auto-save target) and show "Gespeichert" / "Wird gespeichert…" in a polite live region. "Weiter" is the primary action, bottom-right, sticky on phone; "Zurück" never discards input. Validation per step, on "Weiter", with focus moved to the first error. Leaving mid-wizard keeps the draft; the list shows it with the Entwurf badge.
### 5.4 Dashboard ("Heute")
```
+-----------------------------------------------------------+
| Heute, Donnerstag 25.09.                   [QR scannen]   |
+-------------------+-------------------+-------------------+
| ■ 3 überfällig  › | ▲ 5 diese Woche › | ⏱ Timer läuft   › |
+-------------------+-------------------+-------------------+
| Mein Arbeitsvorrat (sorted by deadline)                   |
|  [img] Trauringe Meier   ▲ in 2 Tagen  [Anprobe erledigt] |
|  [img] Kette Schulz      ● in 9 Tagen  [Zeit starten]     |
+-----------------------------------------------------------+
| Anproben heute (2) ›          | Abholbereit (4) ›         |
+-----------------------------------------------------------+
```
Rules: the default home for everyone who makes things, including Anne as ADMIN (today ADMIN lands on KPIs, design-investigation I-14); KPIs move to a secondary "Kennzahlen" tab. Every tile is a link to the filtered list (P4). Numbers use `--type-glance` and tabular numerals. "Zuletzt aktualisiert" shows data time, not render time. No charts on the bench view.
### 5.5 Scanner and bench mode (Werkbank-Modus)
```
+--------------------------------------+
|  [ camera viewfinder, 70% height ]   |
|  "QR-Code auf der Auftragstüte"      |
+--------------------------------------+
| Zuletzt: #1042 Trauringe Meier    ›  |
| [Nummer eintippen]                   |
+--------------------------------------+
After a scan: order card sheet with StatusBadge, DeadlineChip,
[Zeit starten] [Status ändern] [Auftrag öffnen], all 56px.
```
Rules: one scanner, the ScanFab plus ScanOverlay (design-investigation I-24); `/scanner` becomes history and manual entry. Bench mode (`:root.bench`) raises type and targets (section 3.4), hides the footer and secondary navigation, and is switchable from the user menu and "Einstellungen" (today unreachable from nav, design-investigation C). Success feedback is visual and optionally audible, never colour-only. The camera view never auto-opens without a user tap.
### 5.6 Customer-facing page (portal, email, PDF)
```
+--------------------------------------+
| [Workshop logo]  Goldschmiede <Name> |
+--------------------------------------+
| Ihr Auftrag: Trauringe               |
| [latest approved progress photo]     |
| ● Angenommen ● In Arbeit ○ Abholbereit|
| Voraussichtlich fertig: 10.10.2026   |
| [Kostenänderung ansehen und zustimmen]|
+--------------------------------------+
| Fragen? Tel. ... · E-Mail ...        |
+--------------------------------------+
```
Rules: formal "Sie" throughout (as the portal uses today). Workshop name and logo come from theme settings, never a hardcoded "Goldschmiede" (`CustomerPortalPage.tsx:250`). Same tokens as the app (serif headings from `--font-serif`, accent gold for brand marks), no separate dark visual language (`portal.css:11`). Show only customer-safe data: status, customer-facing step names, approved photos, dates, and amounts the customer has been sent. Never internal notes, design files, material costs or other customers' data. One primary action at a time (approve, call). Email and PDF use the same content order and labels. This is the one surface where the frontend-design skill's brand guidance applies fully (section 7b).

## 6. Accessibility checklist (WCAG 2.2 AA)
- [ ] **Contrast:** text at least 4.5:1 (3:1 only at 24px regular or 18.66px bold and up); UI boundaries, icons that carry meaning, and focus rings at least 3:1. Use the ratios in section 3.1; compute any new pair with Appendix B.
- [ ] **Focus ring:** one global rule, `:focus-visible { outline: 3px solid var(--color-focus); outline-offset: 2px; }`, and `var(--color-focus-on-dark)` inside the header. Never `outline: none` without a visible replacement (today 33 occurrences). No ring on mouse click (use `:focus-visible`, not `:focus`).
- [ ] **Keyboard:** everything reachable and operable by keyboard in visual order; no positive `tabindex`; clickable rows are links; menus and tabs follow WAI-ARIA patterns; dialogs trap focus, close on Escape and return focus to the trigger.
- [ ] **Landmarks and headings:** one `h1` per page (the page title), `header`, `nav` with `aria-label`, `main`; headings in order.
- [ ] **Status and live regions:** status never by colour alone (icon plus text, WCAG 1.4.1); save state, loading and scan results announced in `role="status"` regions; only errors use `role="alert"`.
- [ ] **Forms:** every control has a visible `<label>` bound by `htmlFor`/`id`; required fields marked in text and `aria-required`; errors identified in text, linked by `aria-describedby`, `aria-invalid` set (3.3.1, 3.3.3); `autocomplete` on name, email, phone, address.
- [ ] **Target size:** 24 x 24 px absolute minimum (2.5.8), 44 x 44 px default, 56 px on bench views; at least 8px between adjacent targets; destructive target not adjacent to a frequent one.
- [ ] **Reduced motion:** global reduced-motion rule present; no parallax, no auto-playing motion; hover effects only under `(hover: hover)`.
- [ ] **Language:** `<html lang="de">` (already set in `index.html`); any English fragment in content gets `lang="en"`; `hyphens: auto` on narrow columns for long compounds such as "Kostenänderungsanfrage".
- [ ] **Icons and images:** decorative icons `aria-hidden="true"`; icon-only buttons have a German `aria-label` (and no mismatch with `title`, compare `ThemeToggle.tsx:11-12`); jewelry photos have alt text naming the piece ("Trauring Gelbgold, Seitenansicht").
- [ ] **Zoom and reflow:** usable at 200% zoom and at 320px width without horizontal scrolling (except data tables in their own scroll container).
- [ ] **Focus not obscured (2.4.11):** sticky header, tab bar, TimerWidget and toasts never cover the focused element; use `scroll-padding` equal to their heights.
- [ ] **Automated check:** `@axe-core/playwright` smoke test passes with zero serious or critical violations on the changed pages (to be added in phase 1).

## 7. Working with Claude Code on UI
### 7a. Rules block for `CLAUDE.md`
Paste this block into the project `CLAUDE.md` under "Working Style". It is short on purpose: hard, checkable rules work; soft adjectives do not (aidesigner research, section 2.1).
```markdown
## UI rules (full playbook: docs/design/UI-UX-PLAYBOOK.md)
- NEVER write a hex, rgb(), hsl() or named colour outside frontend/src/styles/brand-tokens.css.
- NEVER use raw --color-brand-* ramps in pages or components; use semantic tokens (--color-text, --color-primary, --tone-*).
- NEVER use raw px/rem for spacing, font-size, radius, shadow, z-index or duration; use the --space-*, --type-*, --radius-*, --shadow-*, --z-*, --duration-* scales.
- NEVER use media-query widths other than 600px and 1024px.
- NEVER define .btn*, .modal*, .status-badge*, .form-group, .empty-state or table classes in page CSS; use src/ui primitives.
- NEVER add inline style={{}} except for runtime values (progress width, image aspect).
- NEVER show status by colour alone; ALWAYS use <StatusBadge kind status> (icon + German label).
- NEVER add a status label outside src/design/status.ts.
- NEVER use outline: none without a visible :focus-visible replacement.
- NEVER make an interactive element smaller than 44x44px (56px on bench views).
- NEVER put a destructive action next to the frequent action; destructive actions need ConfirmDialog.
- NEVER close a form modal on backdrop click; dirty forms ask before closing.
- NEVER use emoji as icons; use the shared icon set with aria-hidden, and aria-label on icon-only buttons.
- NEVER make a <tr>, <div> or <span> clickable; use <a>/<Link> or <button>.
- NEVER write German UI text without real umlauts and ß; use … not ...; no ALL CAPS labels.
- ALWAYS take UI strings from the glossary (playbook section 11); one term per concept.
- ALWAYS write button labels as verb + noun ("Auftrag speichern"); the success toast repeats it ("Auftrag gespeichert").
- ALWAYS give every list an EmptyState with an action and every KPI or alert a link to its next action.
- ALWAYS use Field for form inputs (visible label, error text, correct inputMode).
- ALWAYS use Modal for overlays (focus trap, Escape, focus return, full-screen below 600px).
- ALWAYS use tabular-nums for prices, weights, hours and dates.
- ALWAYS gate pricing, material cost and design IP by role in code, not by hiding with CSS.
- ALWAYS run the screenshot loop at 1280 and 390 (playbook 7d) before calling UI work done.
- ALWAYS use demo data in screenshots; never real customer data.
```
### 7b. When to use the frontend-design skill
The installed Anthropic skill (`frontend-design:frontend-design`) pushes toward a distinctive aesthetic. The Snyk article itself says internal tools that need consistency should pair it with a structured design system. So:
- **Use it** for: the client portal, customer emails and PDFs (quote, cost change, pickup notice), the login screen, and the one-time brand pass (phase 5 of section 9). Invoke it explicitly: "Use the frontend-design skill. Brief: customer portal for a one-owner goldsmith workshop; audience: private customers on phones; job: show the status and latest photo of their piece and get approval for cost changes. Constraints: tokens and fonts from docs/design/UI-UX-PLAYBOOK.md section 3 are fixed."
- **Do not use it** for internal ERP screens. There, this playbook is the design system; the skill's "take aesthetic risk" instruction conflicts with consistency.
- Keep its quality floor and writing rules everywhere: responsive to mobile, visible focus, reduced motion, sentence case, active verbs, errors that say how to fix, empty states that invite action.
### 7c. Give a reference, not adjectives
Words like "modern", "clean" or "beautiful" produce generic output (aidesigner research, section 2.3). Instead give:
1. A reference screen: a screenshot of an existing page that already follows this playbook, the ASCII template from section 5, or a sketch photo.
2. The template name ("List page template, section 5.1") and the primitives to use.
3. Real content: German labels from section 11 and realistic demo data (a ring, 5,2 g Gelbgold 750, Frist in 2 Tagen).
4. Named constraints: "bench view, 56px targets, no charts".
### 7d. Screenshot, compare, fix (Playwright MCP)
Run this loop for every UI change, at most two fix passes; after that, hand remaining differences to a human (aidesigner research: the first pass closes most of the gap).

1. Start the stack with demo data (`make start`, or `podman-compose up -d db redis` plus `yarn dev` in `frontend/`). Log in as a demo user. Never point the loop at a database with real customers.
2. Resize: `browser_resize` to width 1280, height 800.
3. Navigate: `browser_navigate` to the changed route.
4. Capture: `browser_take_screenshot` (full page) and `browser_snapshot` (accessibility tree). Save screenshots to the session scratchpad or `.playwright-mcp/`; do not commit them.
5. Resize to width 390, height 844 and repeat steps 3 and 4. For bench views, also capture with the `bench` class on `<html>`.
6. Compare against the reference and list the differences by dimension, as a list, not a verdict: type hierarchy, colour tokens, spacing rhythm, alignment, target sizes, focus visibility (press Tab with `browser_press_key` and capture), status icons and labels, overflow at 390.
7. Check computed facts with `browser_evaluate`: horizontal overflow (`document.documentElement.scrollWidth > innerWidth`), any interactive element under 44px, any element whose computed colour is not from tokens (spot check).
8. Fix the listed differences, then repeat steps 2 to 7 once.
9. Report: the routes checked, both widths, the difference list, what was fixed, and what is left for a human.
### 7e. Reviewer checklist for a UI pull request
- [ ] Hex ratchet did not go up: `grep -rEo '#[0-9a-fA-F]{3,8}\b' frontend/src --include=*.css --include=*.tsx | grep -v brand-tokens.css | wc -l` is less than or equal to the count on `main`.
- [ ] No new `.btn*`, `.modal*`, `.status-badge*`, `.form-group` definitions in page CSS; no new inline styles.
- [ ] New or changed statuses go through `status.ts` and `<StatusBadge>`.
- [ ] Screenshots at 1280 and 390 attached (demo data), plus a focus screenshot.
- [ ] Section 6 checklist items touched by the change are satisfied; axe smoke test green.
- [ ] German copy checked against section 11; umlauts correct; verbs consistent through the flow.
- [ ] Every new list, KPI or alert has a next action; every destructive action has a ConfirmDialog.
- [ ] Role gating for financial data and design IP is in code and covered by a test.
- [ ] `yarn build`, `yarn test` and `tsc` pass.
### 7f. Keeping tokens and code in sync
- `brand-tokens.css` is the source of truth. This playbook documents it; if they disagree, fix the playbook in the same pull request that changes the tokens.
- A token change updates, in the same pull request: section 3 tables, the contrast script output (Appendix B), and any affected screenshot references.
- Add a CI step that fails when the hex ratchet count rises (section 7e command), and later a stylelint `color-no-hex` rule for files other than `brand-tokens.css` (design-investigation I-08).
- Optional: run `/design-sync` in Claude Code to load the tokens and React components into Claude Design (Claude Design help article). Its exact behaviour with Tailwind `@theme` is not documented, so treat Claude Design as a consumer of the repo, never the source, and re-run it after token changes. Upload only demo-data screenshots.
### 7g. Prompt templates
Copy, fill the `<...>` parts, and paste. Each template names the section it relies on so the agent reads it.
```text
NEW PAGE: Build <route> (<German title>) with the <List|Detail|Wizard|Dashboard|Scanner|Customer-facing> template,
playbook 5.<n>. Only src/ui primitives and semantic tokens. Data: <hook/API>. Primary action: "<Verb Nomen>".
Next action per status: <mapping>. Roles: <who sees what; pricing only ADMIN/GOLDSMITH>. Empty state: "<title>"
with action "<label>". Labels from section 11. Finish with the 7d loop at 1280 and 390 and report the diff list.

NEW COMPONENT: Create src/ui/<Name>/ (tsx, css, test) per playbook section 4. Purpose: <one sentence>. Props:
<TypeScript sketch>. States: default, hover, focus-visible, disabled, loading, error. Test the a11y contract:
<keyboard, aria, focus return>. Tokens only, ui- class prefix. List the classes/files it replaces; delete nothing yet.

FIX A11Y: Audit <files or route> against playbook section 6 (WCAG 2.2 AA). Report file:line, criterion, severity.
Fix critical and serious findings with minimal diffs using src/ui primitives. Re-run axe and the 7d loop with a
keyboard-focus pass; report before and after.

MIGRATE STYLESHEET: Migrate frontend/src/styles/<file>.css to tokens per playbook section 3. Replace every hex,
px spacing, font-size, radius, shadow and z-index with the nearest semantic token; list values with no close
token instead of inventing one. Delete rules duplicated by src/ui, switch the TSX to primitives, scope page
selectors under the page root class. Report the hex count before and after, then run the 7d loop.
```

## 8. Skills and tooling
### 8.1 Adoption order
Based on the Snyk research, adapted to what is already installed:

1. **Accessibility gate (now).** Use the installed ecc `accessibility` and `frontend-a11y` skills and the `ecc:a11y-architect` agent for `file:line` audits. Add deterministic tooling that skills cannot replace: `@axe-core/playwright` in the existing Playwright suite and `eslint-plugin-jsx-a11y` (both are new dev dependencies; `package.json` changes are serialized work).
2. **Performance pass.** ecc `react-performance` (described as adapted from Vercel's React best practices). Order: request waterfalls, then bundle size, then re-renders. Do not also install the Vercel copy.
3. **Component API.** ecc `react-patterns` for composition while building `src/ui` (explicit variants instead of boolean props, for example `ConfirmDialog` danger variant). Skip React 19-only rules; the project is on React 18.3.
4. **Design audit.** ecc `design-system` (audit mode, 10 dimensions) or `gsd-ui-review` after each migration phase, measured against this playbook.
5. **Optional, after vetting:** vendor Vercel `web-design-guidelines` and `composition-patterns` (MIT) into `.claude/skills/`, with the rules file copied locally instead of fetched at runtime.
6. **Not adopted:** UI/UX Pro Max (runs a third-party Python script; landing-page oriented), Bencium (no licence; cite its principles instead: feedback within 100ms, forgiveness, progressive disclosure), AccessLint MCP (low adoption; axe covers it), Vercel React Native skills (not applicable).

The Anthropic `frontend-design` skill is already installed; use it only as described in 7b.
### 8.2 Mandatory vetting before installing any third-party skill
Snyk reports prompt injection in 36% of skills tested, 1,467 malicious payloads across the ecosystem, and critical security flaws in 13% of skills tested, some of which tried to exfiltrate credentials. This repository holds customer PII, pricing and design IP, so every skill is reviewed like code:

1. Read `SKILL.md` and every bundled file completely, including references and scripts.
2. Check `allowed-tools` in the frontmatter. A skill that needs `Bash`, `Write` or network tools gets extra scrutiny; prefer skills limited to `Read`, `Grep`, `Glob`.
3. Read every script. Look for network calls (`curl`, `fetch`, `requests`, `WebFetch`), writes outside the project, reading of `~/.ssh`, `.env`, tokens or shell history, obfuscated or encoded strings, and instructions that tell the agent to ignore prior rules.
4. Check source and licence: Anthropic and Vercel are lower risk; unknown maintainers need a full read. No licence means do not install.
5. Remove runtime remote fetches: vendor any remote rules file and pin it.
6. Install at project level (`.claude/skills/`) through a pull request so the team reviews it. Check for name collisions: a user-level skill with the same name silently overrides the project copy.
7. Automated scanners help but do not replace reading; Snyk warns they give a false sense of safety.
8. Record the vetted version (commit hash) in the pull request description.
### 8.3 Stand-ins already installed
- Guideline audit: ecc `accessibility`, ecc `frontend-a11y`, `ecc:a11y-architect` agent, `gsd-ui-review`.
- React rules: ecc `react-performance` (performance), ecc `react-patterns` (composition).
- Design system: ecc `design-system` (generate and audit), `gsd-ui-phase` (UI-SPEC), `gsd-sketch` (mockups), ecc `frontend-design-direction`, Anthropic `frontend-design`.
- Charts and KPI tiles: `dataviz`. Browser checks: Playwright MCP, Claude in Chrome, `@playwright/test` ^1.58.2 (`frontend/package.json`).

## 9. Migration plan
Efforts are rough estimates for one developer with agent help. Each phase ends with the section 7d loop and the section 7e checklist.

| Phase | Scope | Acceptance criteria | Effort |
|---|---|---|---|
| **1. Tokens only** | Change token values, no refactor: primary to `#b45309`, focus ring to `#1e293b` with the global `:focus-visible` rule, danger to `#b91c1c`, the offline banner above the header (`--z-banner`), add semantic tokens and scales (section 3.4), aliases for the 41 undefined properties, and `--tone-*` rules for all 10 order statuses in the existing `.status-badge` CSS as a stopgap. Fix the about 20 umlaut strings. Add the axe smoke test (login, dashboard, orders, order detail) and the hex ratchet in CI. | No AA text contrast failure from section 2 remains on those four pages; every order status renders styled; axe shows zero serious or critical issues; ratchet recorded. | 2 to 3 days |
| **2. Primitives** | Build `src/ui`: Button, IconButton, StatusBadge with `status.ts`, DeadlineChip, Modal (and ConfirmDialog on it), Field, DataTable/ListCard, Card, EmptyState, PageState, PageHeader, TabBar, Tabs. Adopt an SVG icon set. Load IBM Plex locally. | Each primitive has tests for its a11y contract; a demo route (dev only) shows all states at 1280 and 390; no page changed yet. | 1.5 to 2 weeks |
| **3. Pages, highest traffic first** | Migrate one page per pull request in this order: Dashboard ("Heute"), Orders list, Order detail, Scanner and Time tracking, Customers (list and detail). Then Repairs, Quotes, Invoices, Consultations, Materials, Metal inventory, Scrap gold, Calendar, Users, Admin, Portal. Each pull request replaces duplicates and inline styles on that page and switches to the template. Add the app tab bar and grouped navigation with the Dashboard pull request. | Page uses only primitives and semantic tokens; its stylesheet has zero hex values; hex ratchet drops; screenshots attached; no functional regression in Vitest or Playwright. | 1 to 3 days per page |
| **4. Delete duplicates** | Remove the duplicate `.btn*`, `.modal*`, `.status-badge*`, `.form-group`, table and empty-state rules from all page CSS; delete `utilities.css` `@utility` set, `OrderList.tsx`, legacy aliases and the Vite leftovers in `index.css`. Enable stylelint `color-no-hex` outside `brand-tokens.css`. Decide the Tailwind question (Appendix C). | `grep` finds no definition of those classes outside `src/ui`; stylelint passes; hex count outside `brand-tokens.css` is zero or listed as justified exceptions. | 2 to 4 days |
| **5. Dark mode and brand pass** | Add dark values for every semantic token under `:root.dark` (sketch in Appendix B: text `#f5f5f4` on `#1c1917` 16.03, primary `#f59e0b` with dark text 8.14), mount ThemeProvider and a toggle in the user menu, compute dark tone pairs, and optionally a "Werkstatt hoher Kontrast" mode. Run the frontend-design skill for portal, emails and PDFs. | Every page passes the section 6 contrast checks in both themes; screenshots in light and dark at both widths; no hard-coded colour left to break dark mode. | 1 to 1.5 weeks |

## 10. Definition of done for any UI change
- [ ] Matching page template (section 5); only `src/ui` primitives for buttons, badges, dialogs, fields, lists, cards, empty and loading states; `<StatusBadge>` for every status, `<DeadlineChip>` for every deadline.
- [ ] No new hex, raw spacing, font-size, radius, shadow or z-index values; hex ratchet not higher than `main`.
- [ ] Every list has an EmptyState with an action; every KPI and alert links to its next action; no destructive action beside the frequent one.
- [ ] Targets at least 44px (56px on bench views); visible focus everywhere; keyboard path works; dialogs trap and return focus; reduced motion respected.
- [ ] Fields labelled, errors in text, correct `inputMode`; dirty forms do not close on backdrop.
- [ ] German copy correct (umlauts, `…`, glossary terms, verb carried through to the toast).
- [ ] Role gating for pricing, material cost and design IP enforced in code and tested.
- [ ] Screenshot loop run at 1280 and 390 (section 7d), difference list resolved or handed off; axe, `yarn test`, `tsc`, `yarn build` green.
- [ ] If tokens changed: section 3 and Appendix B updated in the same pull request.

## 11. Glossary of German UI terms
Use exactly these words in the UI. Code names follow the existing models; do not rename code to match.

| German UI term | English | Code name |
|---|---|---|
| Auftrag / Aufträge | order(s) | `Order`, `OrderStatusEnum` |
| Kunde / Kundin / Kunden | customer(s) | `Customer` |
| Reparatur / Reparaturen | repair job(s) | `RepairJob`, `RepairJobStatus` |
| Kostenvoranschlag (KV) | quote, estimate | `Quote`, `QuoteStatus` (nav label today "Angebote"; see Appendix C) |
| Rechnung / Rechnungen | invoice(s) | `Invoice`, `InvoiceStatus` |
| Altgold | scrap gold (financial data) | `ScrapGold`, `ScrapGoldStatus` |
| Werkstatt | workshop | (context, navigation group) |
| Werkbank-Modus | bench mode | `ScannerContext` setting, `:root.bench` |
| Übergabe | handoff between goldsmiths | `OrderHandoff`, `HandoffStatusEnum` |
| Abholung / abholbereit | pickup / ready for pickup | `ready`, `PICKUP_READY` |
| Ausgeliefert | delivered to customer | `delivered` |
| Anprobe | fitting | `waiting_for_fitting`, `fitting_done` |
| Fassen / Fassung | stone setting / setting | `ready_for_setting` |
| Qualitätskontrolle | quality check | `quality_check` |
| Entwurf | draft | `draft` |
| Beratung | consultation | `Consultation`, `ConsultationStatus` |
| Maße / Ringgröße | measurements / ring size | `MeasurementType` (Maßbibliothek) |
| Legierung | alloy | alloy fields, `AlloyMismatchModal` |
| Feingehalt / Feingold | fineness / fine gold content | metal fields |
| Punzierung / Punze | hallmarking / hallmark stamp | `OrderHallmark`, `HallmarkStatus` |
| Oberfläche | surface finish | (activity, order field) |
| Material / Metallinventar | materials / metal inventory | `Material`, metal inventory models |
| Zeiterfassung | time tracking | `TimeEntry` |
| Tätigkeit | activity (for time entries) | `Activity` |
| Unterbrechung | interruption | `Interruption` |
| Kostenänderung | cost change request (§649 BGB notice) | `CostChangeRequest`, `CostChangeStatus` |
| Kundeninfo / Kunden-Update | customer update (email or PDF) | `CustomerUpdate`, `CustomerUpdateStatus` |
| Frist / Liefertermin | deadline / delivery date | `deadline` |
| Abbrechen / Löschen / Bestätigen | cancel / delete / confirm | ConfirmDialog labels |
| Storniert | cancelled | `cancelled` |

Tone: internal UI uses short neutral labels (infinitive or noun: "Auftrag speichern", "Neue Reparatur"). Customer-facing text uses "Sie".

## Appendix A. Source notes summary
**Claude Design help article** (support.claude.com 14604397; notes: `research/2026-09-24-claude-design-system-notes.md`)
- A setup article, not a methodology guide; says what a generated design system contains, not how to structure one.
- Model: guides + tokens + components. Output covers colour palette, typography, components, layout patterns.
- For code-based systems, `/design-sync` in Claude Code "reads tokens and components directly".
- Main tip: real finished screens convey feel better than a palette.
- Silent on accessibility, responsiveness, states, dark mode, versioning.
- No version history in beta, so the repo stays the versioned source of truth.
- Implication here: one token file and one component per pattern make extraction reliable.
- Clarify primary/accent naming: in this repo "primary" ramp is slate, the CTA is gold.
- Upload only demo-data screenshots (PII rules).
- Validate with ERP test prompts (dashboard, order detail, quote editor).

**aidesigner.ai article** (Tyler Yin, 2026-05-02; notes: `research/2026-09-24-aidesigner-frontend-design-notes.md`)
- Thesis: generic output is a context problem; set up rules and references before prompting.
- Hard rules beat soft suggestions ("Never use Inter" vs "use beautiful typography").
- Keep the CLAUDE.md design block short; move detail into skills or docs.
- Name specific styles, never "modern/clean".
- Visual reference beats text description.
- Screenshot, compare, list deltas by dimension, fix; two passes.
- Lock the result into a tokens file named as source of truth.
- Vendor bias (promotes its paid MCP); stack assumptions (Next.js, shadcn) do not apply.
- Its marketing-page rules (3x size jumps, atmospheric heroes) conflict with a dense tool.
- Silent on accessibility and data-dense UI.

**Snyk article** (Stephen Thoemmes, 2026-03-02; notes: `research/2026-09-24-snyk-ui-ux-skills-notes.md`)
- Eight skills: Anthropic frontend-design, three Vercel skills plus React Native, UI/UX Pro Max, Bencium, AccessLint.
- frontend-design suits marketing pages; pair with a structured system for internal tools.
- web-design-guidelines is a quality gate: 100+ rules, `file:line` output, fetches rules at runtime.
- Combine layers: direction, design intelligence, compliance gate, engineering patterns.
- Security: prompt injection in 36% of skills tested, 1,467 malicious payloads, 13% with critical flaws.
- Five-step pre-install checklist: read everything, check source, check `allowed-tools`, scan scripts, be careful with Python.
- User-level skills override project skills of the same name.
- Evaluation signals: licence, recency, focused scope, precise trigger description.
- Most recommendations have installed ecc stand-ins here.
- Silent on visual regression and screenshot loops.

**Local frontend-design skill**
- Persona: design lead who gives each client a distinct identity; ground choices in the subject's world.
- Plan tokens first (4 to 6 hex colours, type roles, ASCII layout), review for genericness, then build.
- Lists current AI-default looks to avoid, including the SaaS-card kit and ALL-CAPS eyebrow labels.
- Numbered markers only for real sequences; motion only in response to user action or one orchestrated moment.
- Quality floor: responsive, visible focus, reduced motion, accessible colour.
- Writing: user vocabulary, active verbs, the same verb through a flow, errors that say how to fix, empty states that invite action.

## Appendix B. Contrast computation
All "computed" ratios in this document come from this script (WCAG 2.x relative luminance). Run it with `python3` after any colour change and paste the output into the pull request.
```python
def lum(h):
    h = h.lstrip('#')
    r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

def ratio(fg, bg):
    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)

pairs = [  # expected output in comments
    ("text/surface", "#1e293b", "#faf8f4"), ("text/raised", "#1e293b", "#ffffff"),        # 13.79, 14.63
    ("text/sunken", "#1e293b", "#f3efe7"), ("muted/surface", "#57534e", "#faf8f4"),       # 12.76, 7.19
    ("muted/raised", "#57534e", "#ffffff"), ("muted/sunken", "#57534e", "#f3efe7"),       # 7.63, 6.65
    ("border/raised", "#e3ddd2", "#ffffff"), ("border-strong/raised", "#8a8175", "#ffffff"),  # 1.35, 3.83
    ("border-strong/surface", "#8a8175", "#faf8f4"), ("white/primary", "#ffffff", "#b45309"), # 3.61, 5.02
    ("white/primary-hover", "#ffffff", "#92400e"), ("primary/surface", "#b45309", "#faf8f4"), # 7.09, 4.73
    ("hover/primary-subtle", "#92400e", "#fef3c7"), ("focus/surface", "#1e293b", "#faf8f4"),  # 6.37, 13.79
    ("focus/primary", "#1e293b", "#b45309"), ("accent/raised", "#c5a55a", "#ffffff"),     # 2.91, 2.36
    ("text/accent", "#1e293b", "#c5a55a"), ("accent-strong/raised", "#7c5e10", "#ffffff"),  # 6.20, 6.06
    ("white/success", "#ffffff", "#15803d"), ("white/warning", "#ffffff", "#c2410c"),     # 5.02, 5.18
    ("white/danger", "#ffffff", "#b91c1c"), ("danger/surface", "#b91c1c", "#faf8f4"),     # 6.47, 6.10
    ("white/header-end", "#ffffff", "#78350f"),                                          # 9.07
    ("tone neutral", "#374151", "#f3f4f6"), ("tone info", "#1e40af", "#dbeafe"),          # 9.37, 7.15
    ("tone progress", "#115e59", "#ccfbf1"), ("tone waiting", "#9a3412", "#ffedd5"),      # 6.73, 6.38
    ("tone check", "#5b21b6", "#ede9fe"), ("tone done", "#166534", "#dcfce7"),            # 7.57, 6.49
    ("tone handover", "#334155", "#e2e8f0"), ("tone danger", "#991b1b", "#fee2e2"),       # 8.40, 6.80
    ("dark text/surface", "#f5f5f4", "#1c1917"), ("dark text/raised", "#f5f5f4", "#292524"),  # 16.03, 13.90
    ("dark muted/surface", "#a8a29e", "#1c1917"), ("dark muted/raised", "#a8a29e", "#292524"),  # 6.93, 6.01
    ("dark text/primary", "#1c1917", "#f59e0b"), ("dark link/surface", "#fbbf24", "#1c1917"),  # 8.14, 10.48
    ("dark focus/surface", "#fde68a", "#1c1917"), ("dark border/raised", "#78716c", "#292524"),  # 14.04, 3.16
    ("baseline white/#d97706", "#ffffff", "#d97706"), ("baseline #f59e0b/white", "#f59e0b", "#ffffff"),  # 3.19, 2.15
]
for name, fg, bg in pairs:
    print(f"{ratio(fg, bg):5.2f}  {name}")
```
The script reproduces the design-investigation baseline values (3.19 for white on `#d97706`, 2.15 for `#f59e0b` on white), which cross-checks the formula.

## Appendix C. Open questions
1. **Tailwind or plain CSS.** The design-investigation (I-25) recommends removing the Tailwind import because the team writes plain CSS and the layer conflict caused invisible buttons (`buttons.css:4-23`). This playbook keeps the `@theme static` block because it is what exists; if Tailwind is removed, the primitives move to `:root` unchanged and nothing else in the playbook changes. Owner: Max.
2. **Typeface.** IBM Plex (OFL, tabular figures, good German glyphs) is proposed as a "technical workshop ledger" direction. Confirm with Anne, or keep system fonts for legibility.
3. **"Angebote" or "Kostenvoranschläge".** The nav says Angebote while the code and domain say Kostenvoranschlag. Pick one label for the UI.
4. **"Ausgeliefert" vs "Übergeben"** for `delivered`: goldsmiths may say "abgeholt" or "übergeben". Check with Anne.
5. **Sie or du internally.** Customer-facing is "Sie"; internal UI currently avoids direct address. Keep it that way unless Anne prefers "du".
6. **Dark mode vs high-contrast mode.** Is the workshop problem darkness or glare? That decides whether phase 5 builds dark mode, a high-contrast light mode, or both.
7. **Wall display.** Lena's brief mentions a wall-mounted status view readable from 2 m; not in scope of any template yet.
8. **Icon set.** Lucide is suggested (MIT). Custom icons for Legierung, Fassung, Oberfläche and Altgold need a designer.
9. **Runtime theme colours.** Admins can set theme colours without contrast checks (`useTheme.ts:52-61`). Restrict to token presets or validate at 4.5:1.
10. **`/design-sync` behaviour** with Tailwind `@theme` tokens is undocumented; test once before relying on it.
