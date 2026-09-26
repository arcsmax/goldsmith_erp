# Research: "How to Design Beautiful UIs With Claude Code (2026)"

> Cleaned copy of the research notes taken on 2026-09-24 for the UI/UX playbook (`docs/design/UI-UX-PLAYBOOK.md`). Content and quotations are unchanged except that em dashes inside quotations are rendered as a spaced hyphen, to follow the repository writing rule. Counts about this repository are superseded by the design investigation (40 stylesheets, 1,580 hard-coded hex values in CSS); where an older count appears below it is marked.

- **URL:** https://www.aidesigner.ai/blog/claude-code-frontend-design
- **Author / date:** Tyler Yin, published 2026-05-02 (per fetched page)
- **Fetch date:** 2026-09-24
- **Fetch completeness:** Complete as far as can be told. The page was fetched 3 times with WebFetch (one summary pass, two "quote verbatim" passes). The fetch tool reported no truncation. WebFetch runs the page through a summarizing model, so short quotes are close to verbatim but may not be character-exact. The code blocks (CLAUDE.md block, install commands, compare prompt) came back verbatim.
- **Followed links (1 of max 3):** Anthropic "Prompting for frontend aesthetics" cookbook, https://platform.claude.com/cookbook/coding-prompting-for-frontend-aesthetics (a primary source the article quotes).
- **Bias note:** The article is published by AIDesigner and promotes the AIDesigner MCP (paid) as the "highest quality" visual-reference option. Treat the tool ranking as vendor marketing. Its stack assumptions are Next.js + Tailwind + shadcn/ui, and **Goldsmith ERP uses none of them**.

---

## 1. Recommended workflow (steps and order)

The article's thesis: generic UI output is "a tooling problem, not a model limitation". Its fix is a layered setup that is done **before** prompting, followed by an iteration loop:

1. **Install the Anthropic Frontend Design skill/plugin** (published 2025-11-12). Its job is to push Claude toward deliberate aesthetic directions (brutalist, maximalist, editorial, ...) and away from defaults.
2. **Add a short "Frontend aesthetics" block to CLAUDE.md**: narrow, enforceable rules for typography, color, backgrounds, motion and components (full text in section 2).
3. **Connect the component registry via MCP** (shadcn MCP plus the shadcn skill), so Claude uses existing primitives instead of inventing new ones.
4. **Provide a visual reference** before generation, not just text. The article ranks the options (see section 3).
5. **Generate, then run the screenshot-compare-refine loop.** Take a screenshot, diff it against the reference, fix the differences. Two passes.
6. **Lock the result into a tokens file** (`app/design-tokens.ts`), point config at it, and make CLAUDE.md name it as the source of truth, so later sessions don't drift.

> "Two passes of this loop is the sweet spot. The first pass closes 70% of the gap. The second pass closes another 25%. Past that you're chasing pixel-level details that need a human eye anyway." (Tyler Yin, aidesigner.ai)

Why context beats prompts (the root cause):

> "Claude Code generates generic UIs because of distributional convergence. Anthropic's official Frontend Aesthetics cookbook...names this directly: 'You tend to converge toward generic, on distribution outputs.'" (Tyler Yin, quoting the Anthropic cookbook)

## 2. Prompting techniques

### 2.1 Hard rules, not soft suggestions

> "'Never use Inter' is enforceable. 'Use beautiful typography' is not. Claude follows hard rules cleanly and ignores soft suggestions almost entirely." (Tyler Yin)

### 2.2 Keep the design block short

> "Twenty lines is plenty." / "Bloated CLAUDE.md files cause Claude to ignore your actual instructions!" (Tyler Yin)

Move the rest into skills instead of CLAUDE.md.

### 2.3 Name specific styles, never "modern/clean"

> "Every site is 'modern and clean.' Ask for 'editorial layout with serif display typography and asymmetric grid' - Claude has actual training data to anchor on." (Tyler Yin)

### 2.4 The recommended CLAUDE.md block (verbatim)

```
# Frontend aesthetics

Avoid generic AI aesthetics. Make creative, distinctive choices.

## Typography
- Never use Inter, Roboto, Open Sans, Lato, Arial, or system fonts.
- Body: Bricolage Grotesque. Display: Fraunces. Mono: JetBrains Mono.
- Use weight extremes: 200 vs 800, not 400 vs 600.
- Size jumps of 3x+, not 1.5x.

## Color & theme
- Commit to a single dominant color with one sharp accent.
- All colors live in CSS variables in `app/globals.css`.
- Forbidden: purple-to-blue gradients on white backgrounds.

## Backgrounds
- Layered CSS gradients or geometric patterns over solid colors.
- Hero sections must have atmospheric depth.

## Motion
- CSS-only for non-React. Motion (formerly Framer Motion) for React.
- One well-orchestrated page-load reveal beats scattered micro-interactions.

## Components
- Always use shadcn/ui primitives where they exist (Button, Card, Dialog, Form).
- Never hand-roll a component that exists in the shadcn registry.
- Tailwind classes only. No inline styles. No CSS modules.
```

Caveat for ERP use: the "3x size jumps", "atmospheric depth" and "hero sections" rules are written for marketing and landing pages. They conflict with a dense, task-focused workshop tool. Take the **shape** of the block (short, prohibitive, concrete), not its values.

### 2.5 Anthropic cookbook techniques (primary source)

The cookbook's full `<frontend_aesthetics>` system prompt covers typography, color and theme, motion and backgrounds, and has an "avoid" list. Key lines:

> "Dominant colors with sharp accents outperform timid, evenly-distributed palettes. Draw from IDE themes and cultural aesthetics for inspiration." (Anthropic cookbook)

> "Avoid generic AI-generated aesthetics: Overused font families (Inter, Roboto, Arial, system fonts); Clichéd color schemes (particularly purple gradients on white backgrounds); Predictable layouts and component patterns; Cookie-cutter design that lacks context-specific character" (Anthropic cookbook)

> "You still tend to converge on common choices (Space Grotesk, for example) across generations." (Anthropic cookbook)

Typography pairing: "High contrast = interesting. Display + monospace, serif + geometric sans, variable font across weights." Font families grouped by aesthetic: Code (JetBrains Mono, Fira Code, Space Grotesk), Editorial (Playfair Display, Crimson Pro, Fraunces), Startup (Clash Display, Satoshi, Cabinet Grotesk), **Technical (IBM Plex family, Source Sans 3)**, Distinctive (Bricolage Grotesque, Obviously, Newsreader).

> "Pick one distinctive font, use it decisively. Load from Google Fonts. State your choice before coding." (Anthropic cookbook, `<use_interesting_fonts>` prompt)

**Isolated / locked prompts.** Instead of the full aesthetics prompt, target a single dimension (e.g. a typography-only `<use_interesting_fonts>` block), or lock a theme with a named block (the cookbook's example is `<always_use_solarpunk_theme>` with 5 bullet traits).

> "You can isolate specific dimensions (typography, color, motion) or lock in a particular theme. This gives you faster generation times and more predictable outputs." (Anthropic cookbook)

### 2.6 Good vs bad prompts (from the article)

| Bad | Good |
|---|---|
| "Is this good?" | "Compare `screenshots/result.png` to the reference. List exactly what differs in: typography size hierarchy, color palette, spacing rhythm, hero section structure. Fix the deltas." |
| "modern", "clean" | "editorial layout with serif display typography and asymmetric grid" |
| "Use beautiful typography" | "Never use Inter" (enforceable) |
| Text-only description | Pasted reference image or Figma frame ("text prompts produce text-shaped output; visual prompts produce visual output") |

## 3. Recommended skills, plugins, MCP servers, tooling

| Tool | What for | Install / URL (as given) |
|---|---|---|
| Anthropic Frontend Design skill/plugin | Deliberate aesthetic direction, bans defaults | https://claude.com/plugins/frontend-design ; manual: `mkdir -p .claude/skills/frontend-design && curl -o .claude/skills/frontend-design/SKILL.md https://raw.githubusercontent.com/anthropics/claude-code/main/plugins/frontend-design/skills/frontend-design/SKILL.md` |
| shadcn/ui MCP + skill | Live component registry, stops duplicate components | `claude mcp add shadcn -- npx shadcn@latest mcp` and `npx skills add shadcn/ui`; docs https://ui.shadcn.com/docs/skills |
| AIDesigner MCP (vendor's own) | Reference visuals: `generate_website_design_image`, `generate_design` (editable HTML), `generate_branding_kit_variations` (9 directions) and `create_brand_kit_from_variation`; modes "clone" / "enhance" / "inspire"; asset extraction | https://www.aidesigner.ai (Pro at $25/month, about 100 credits, about 50 designs) |
| Figma MCP (official) | Structured design frames; alternatively paste screenshots | named, no URL given |
| Claude in Chrome extension | Screenshots, "lowest-friction option if you live in Chrome" | first-party |
| Playwright MCP | Headless screenshots, "more flexible than Chrome and works in headless contexts" | named |
| `scripts/screenshot.sh` | "The lowest-tech approach" | custom, in repo |
| Anthropic Frontend Aesthetics cookbook | Source system prompts | https://platform.claude.com/cookbook/coding-prompting-for-frontend-aesthetics |
| Anthropic Claude Code best practices | General | https://code.claude.com/docs/en/best-practices |

How the article ranks visual references: AIDesigner MCP (new projects, no friction, "highest") > Figma frames (existing designs, high friction, "highest when structured") > screenshots (cloning, medium friction, limited to existing designs) > text description ("AI slop").

## 4. Design systems, tokens, consistency

- Keep all colors in CSS variables in a single file ("All colors live in CSS variables in `app/globals.css`"). The cookbook also says "Use CSS variables for consistency."
- **Component reuse is a hard rule:** "Never hand-roll a component that exists in the ... registry." The MCP connection exists so Claude can *see* what already exists.
- **Lock-in step (verbatim prompt):**
  ```
  Read app/page.tsx and app/globals.css. Extract the design system into
  app/design-tokens.ts with named exports for:
  - colors (background, foreground, primary, accent, muted, border)
  - typography (fontFamily.body, fontFamily.display, fontFamily.mono,
    scale, weights)
  ```
  The same step also covers spacing, radii and motion. Afterwards: "Update CLAUDE.md to reference design-tokens.ts as the source of truth for any new UI work in this project."
- Brand-kit consistency across sessions: the article recommends saving a brand kit (AIDesigner) and reusing it.
- Anti-drift: "Refining the same chat for hours" is listed as a mistake because context degrades. Start fresh sessions and rely on the tokens file plus CLAUDE.md for continuity.

## 5. Iteration and visual feedback

- Loop: **screenshot, compare against reference, list deltas by dimension, fix**. The dimensions named are typography size hierarchy, color palette, spacing rhythm and section structure.
- Ask for a structured delta list, never a verdict ("Is this good?" is the bad example).
- Two passes (about 70% then about 25% of the gap). Leave the rest to a human reviewer.
- > "First passes are drafts. Always run the screenshot-and-compare loop at least once before you call it done." (Tyler Yin)
- Tooling: Claude in Chrome, Playwright MCP (headless), or a repo screenshot script.

## 6. Accessibility, responsive, dark mode, performance, data-dense UI

**The article does not address these.** It is about marketing and landing-page aesthetics. It only links to a separate "dashboard UI design guide" (`/blog/how-to-design-a-dashboard-ui`, not fetched: out of scope, and vendor content). The only indirect point is that a tokens file makes theming (e.g. dark mode) possible. The cookbook's "Vary between light and dark themes" is about variety between generations, not a11y.

For ERP-relevant a11y and responsive guidance, the local frontend-design skill (next section) is the better source: "responsive down to mobile, visible keyboard focus, reduced motion respected, visually accessible".

---

## Local frontend-design skill summary

Path: `/Users/maxbook/.claude/plugins/cache/claude-plugins-official/frontend-design/6bfd4e0c6d3d/skills/frontend-design/SKILL.md`. Four cached versions are identical in size (9390 B). This is newer than, and different from, the version the article describes.

1. Persona: design lead at a studio that gives every client a distinct identity. Make opinionated, brief-specific choices.
2. Ground the design in the subject's industry, materials and vernacular. Confirm subject, audience and primary job first. Use real content.
3. Typography carries personality: one or two families, a deliberate type scale (Elements of Typographic Style), line length under 80 characters.
4. Banned tells: accenting a single word in a headline, ALL-CAPS labels, unnecessary eyebrow labels, and numbered markers (01/02/03) unless the content really is a sequence.
5. Lists 5 current "AI default" looks to avoid when the brief is free: cream + serif + terracotta (#D97757); near-black + acid accent; broadsheet hairlines; the **SaaS-card kit** (identical rounded cards, one radius everywhere, rgba(0,0,0,.1) shadow, gradient washes); template chrome (middle-dot meta strings, "WORD, spaced em dash, fragment", `→` on buttons, monospace for small data labels).
6. Two-pass process: first draft a compact token plan (4-6 named hex colors, type roles, layout with ASCII wireframes, principles), review it against the brief for genericness, and only then code.
7. Watch CSS selector specificity (classes cancelling each other's padding and margin).
8. Restraint: be bold in one place. Quality floor: responsive to mobile, visible keyboard focus, reduced motion respected, accessible color. Self-critique with screenshots. "Remove one accessory."
9. Motion: at most one orchestrated moment. Motion that responds to user actions (open, expand, confirm) is welcome. Per-card hover effects and fade-up on every section read as AI-generated.
10. UX writing: user vocabulary, not system vocabulary. Active-voice CTAs ("Save changes", not "Submit"). The same verb carries through a flow ("Publish" leads to a "Published" toast). Errors say what happened and how to fix it, without apologizing. Empty states invite an action. Sentence case.

Note: the article's CLAUDE.md block (weight extremes, atmospheric heroes, gradient backgrounds) matches the *cookbook*. The *current skill* is more restrained: it treats gradient washes and reflexive decoration as tells.

---

## Direct applicability to Goldsmith ERP

Context checked locally: `frontend/src/styles/` has about 27 plain CSS files at the top level (40 including `styles/components/`) and `brand-tokens.css` (114 lines of `--color-brand-{cta,primary,cream,accent,secondary}-{50..900}` scales). Styles use `font-family: inherit` plus scattered `'Courier New'`/`'Monaco'` monospace stacks. There are **about 1120 hard-coded 6-digit hex literals** across top-level `styles/*.css` (the design investigation counts 1,580 hex values of any length across all stylesheets), and only 13 `prefers-color-scheme`/`prefers-reduced-motion` media queries. `@playwright/test` ^1.58.2 is already installed.

1. **Add a short (≤20-line) "Frontend UI rules" block to CLAUDE.md**, adapted to plain CSS with no Tailwind or shadcn. Examples: "Colors only via `var(--…)` from `styles/brand-tokens.css`; never a new hex literal", "Reuse `styles/buttons.css` classes; never define a new button style in a page CSS", "German UI copy, sentence case, active verbs (`Auftrag speichern`, not `Absenden`)". Keep every rule prohibitive and checkable. Drop the article's Tailwind/shadcn/hero rules.
2. **Make `brand-tokens.css` the named source of truth** (the article's lock-in step, adapted). Add semantic tokens (`--color-surface`, `--color-text`, `--color-border`, `--color-danger`, `--space-*`, `--radius-*`, `--font-*`) on top of the raw 50-900 scales, then burn down the hex literals file by file. Optionally mirror them in a `tokens.ts` for recharts, which needs JS color values, not CSS vars.
3. **Hex-literal lint gate.** Hard rules only work when they can be enforced. A stylelint `color-no-hex` rule (or a grep check in CI) outside `brand-tokens.css` turns rule 1 into a guarantee instead of a hope.
4. **Screenshot-compare loop with the existing Playwright.** Add a `scripts/screenshot` (or Playwright spec) that captures the key pages (Dashboard, Auftragsliste, Auftragsdetail, Kostenvoranschlag, Zeiterfassung) at desktop and mobile widths. Review deltas by dimension (type hierarchy, color, spacing rhythm, structure), 2 passes maximum per change. Ask for delta lists, not "looks good?".
5. **Choose a named direction grounded in the domain, not "modern/clean".** Workshop plus precious metals suggests something like "technical workshop ledger: IBM Plex Sans / Source Sans 3 body, tabular numerals for weights (g), prices and hours, one warm metal accent". The cookbook's "Technical" family list fits a data-dense tool better than its editorial or startup picks. Replace the ad-hoc `'Courier New'` stacks with one mono token, and use it only where monospace carries meaning (order numbers, lot or hallmark codes), per the skill's warning about decorative mono labels.
6. **Avoid the SaaS-card-kit tell on data-heavy pages.** Dashboards and lists should use hierarchy (tables, grouped sections, differentiated radius and elevation), not uniform rounded cards with identical shadows. "Visual structure is information." Numbered markers only for real sequences (e.g. the consultation wizard steps).
7. **Motion budget.** Allow only action-feedback motion (drawer open, status change confirmed, toast). No section fade-ups. Wrap everything in `prefers-reduced-motion`. Only 13 such queries exist today, so audit coverage.
8. **Codify the UX-writing rules for German copy.** Keep the same verb through a flow ("Freigeben" leads to "Freigegeben"). Errors say what failed and how to fix it (important for zod validation messages). Empty states offer the next action, which matches CLAUDE.md's "every data display should link to its natural next action".
9. **Quality floor as a checklist item in reviews:** mobile or tablet width (workshop tablets), visible `:focus-visible` rings, reduced motion, contrast of the amber `--color-brand-cta-*` on white (amber 400-500 on white likely fails WCAG AA for text, so verify).
10. **Session hygiene.** Don't iterate on UI for hours in one chat. Put decisions into tokens and CLAUDE.md, then start fresh (the article's "mistakes" list).

## Open questions

- Is a single distinctive typeface acceptable to the owner (Anne), or is the current system/inherit font a deliberate choice for legibility on workshop devices?
- Should dark mode be supported at all (bright workshop lighting vs. back-office use)? That decides whether semantic tokens need light and dark variants now.
- Is adding stylelint (a new dev dependency, `package.json` is a serialized file) acceptable, or should the hex gate be a grep script?
- Does a reference/target look exist (brand guide, mockups, a Figma file) to compare screenshots against? The article's loop assumes a reference. Without one, the compare step degrades to self-critique.
- The article's linked "dashboard UI design guide" (aidesigner.ai/blog/how-to-design-a-dashboard-ui) was not fetched. It may hold the data-dense guidance this article lacks, but it is vendor content.
- The cached versions of the frontend-design skill: confirm which version the plugin actually loads (the cached `unknown/` version is 8260 B and differs).
