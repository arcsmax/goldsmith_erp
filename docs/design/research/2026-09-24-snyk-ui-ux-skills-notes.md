# Research: Snyk "Top 8 Claude Skills for UI/UX Engineers"

> Cleaned copy of the research notes taken on 2026-09-24 for the UI/UX playbook (`docs/design/UI-UX-PLAYBOOK.md`). Content and quotations are unchanged except that em dashes inside quotations are rendered as a spaced hyphen, to follow the repository writing rule. Counts about this repository are superseded by the design investigation (40 stylesheets, 1,580 hard-coded hex values in CSS); where an older count appears below it is marked.

- **URL:** https://snyk.io/articles/top-claude-skills-ui-ux-engineers/
- **Author / published:** Stephen Thoemmes, Snyk, 2026-03-02
- **Fetch date:** 2026-09-24
- **Fetch completeness:** Complete. Full article text came from `mcp__plugin_ecc_exa__web_fetch_exa` (about 25k chars, runs through the "Wrapping up" section) and was cross-checked against a WebFetch summary. No linked repos were fetched. Star counts, rule counts and "Last Updated" dates are the article's figures as of March 2026 and may be out of date.
- **Not fetched:** the individual skill repos, the ToxicSkills study, and the "SKILL.md to Shell Access" research. The article only cites them.

---

## 1. Recommended skills

The article's own summary table:

| # | Skill | Stars | Focus | Source |
|---|---|---|---|---|
| 1 | Anthropic Frontend Design | 65,847 | Distinctive, production-grade UI with bold aesthetics | anthropics/skills |
| 2 | Vercel Web Design Guidelines | 19,487 | Web interface audit (100+ rules, accessibility, UX) | vercel-labs/agent-skills |
| 3 | Vercel React Best Practices | 19,487 | React/Next.js performance (57 rules, 8 categories) | vercel-labs/agent-skills |
| 4 | Vercel Composition Patterns | 19,487 | React component architecture and design patterns | vercel-labs/agent-skills |
| 5 | UI/UX Pro Max | 29,636 | Design intelligence: 50 styles, 97 palettes, 9 stacks | nextlevelbuilder/ui-ux-pro-max-skill |
| 6 | Bencium UX Designer | 72 | UX with accessibility, responsive design, motion specs | bencium/bencium-claude-code-design-skill |
| 7 | AccessLint | 8 | WCAG 2.1 auditing, contrast checking, refactoring | accesslint/claude-marketplace |
| 8 | Vercel React Native Skills | 19,487 | Mobile UI performance, animations, navigation | vercel-labs/agent-skills |

### 1.1 Anthropic frontend-design
- **Source:** https://github.com/anthropics/skills (`skills/frontend-design/`). Also in https://github.com/anthropics/claude-code (`plugins/frontend-design/`). License: custom (LICENSE.txt).
- **What it does:** Tackles "AI slop" (the article's phrase). Before writing code, Claude thinks through purpose, tone, constraints and differentiation. It then applies rules in five areas:
  - **Typography:** bans Inter, Roboto, Arial, system fonts and Space Grotesk.
  - **Color:** a cohesive palette defined as CSS variables, with a dominant color plus sharp accents and no purple-on-white.
  - **Motion:** one orchestrated page load rather than many small micro-interactions.
  - **Spatial composition:** asymmetry and grid-breaking layouts.
  - **Backgrounds and visual details:** textures and similar treatments.
- **When to use:** landing pages, marketing sites, portfolios.
- **Install:** `git clone https://github.com/anthropics/skills.git && cp -r skills/skills/frontend-design ~/.claude/skills/`, or `/plugin marketplace add anthropics/claude-code` and then `/plugin menu`.
- **Caveat that matters for an ERP:**
> "If you are building internal tools where consistency matters more than creativity, you may want to pair this with a more structured design system skill (see #5 or #6 below)." (Snyk article, section 1)

### 1.2 Vercel web-design-guidelines
- **Source:** https://github.com/vercel-labs/agent-skills (`skills/web-design-guidelines/`). MIT. Its rules live in the vercel-labs/web-interface-guidelines repo.
- **What it does:**
  1. Fetches the latest guidelines at runtime.
  2. Reads the files you specify.
  3. Checks every file against 100+ rules.
  4. Reports issues in terse `file:line` format.
- **Coverage:** ARIA, visible focus states, labeled inputs, touch target sizes, reduced-motion support, semantic HTML, keyboard navigation and heading hierarchy.
- **When to use:** as a quality gate before accessibility audits or when enforcing UX standards. Runs as a slash command, e.g. `/web-design-guidelines src/components/**/*.tsx`.
- **Install:** `git clone https://github.com/vercel-labs/agent-skills.git && cp -r agent-skills/skills/web-design-guidelines ~/.claude/skills/`, or `/plugin marketplace add vercel-labs/agent-skills`.
> "This is not a creative skill. It is a quality gate. Think of it as a linter for UI/UX best practices..." (Snyk article, section 2)
- **Security note (mine, not the article's):** because the skill fetches its rules from a remote URL at runtime, remote content enters the agent's context. Pin a version or vendor the rules file locally.

### 1.3 Vercel react-best-practices
- **Source:** vercel-labs/agent-skills (`skills/react-best-practices/`). MIT.
- **What it does:** 57 rules in 8 categories, ordered by impact:
  1. Eliminating Waterfalls (CRITICAL)
  2. Bundle Size (CRITICAL)
  3. Server-Side (HIGH)
  4. Client-Side Data Fetching (MEDIUM-HIGH)
  5. Re-render (MEDIUM)
  6. Rendering (MEDIUM)
  7. JS Performance (LOW-MEDIUM)
  8. Advanced (LOW)
- **Rules the article highlights:** `async-suspense-boundaries`, `bundle-barrel-imports`, `bundle-dynamic-imports`, `rerender-derived-state`, `rendering-content-visibility`, `rendering-activity`. Each rule file shows incorrect and correct code.
- **Install:** `cp -r agent-skills/skills/react-best-practices ~/.claude/skills/`.
- **Reason for recommending it:**
> "Performance is a UX concern. A beautifully designed interface that takes 4 seconds to become interactive is a bad user experience..." and "Too many developers (and AI assistants) jump straight to `useMemo` and `React.memo` when the real bottleneck is a waterfall of sequential API calls or a barrel file importing the entire icon library." (Snyk article, section 3)

### 1.4 Vercel composition-patterns
- **Source:** vercel-labs/agent-skills (`skills/composition-patterns/`). MIT.
- **What it does:** Replaces piles of boolean props with composition. Rules:
  - `architecture-avoid-boolean-props`
  - `architecture-compound-components` (Radix-style `Select.Trigger` / `Select.Content`)
  - `state-decouple-implementation`
  - `state-context-interface` (state / actions / meta)
  - `patterns-explicit-variants` (e.g. `<Alert.Destructive>`)
  - `patterns-children-over-render-props`
  - `react19-no-forwardref` (React 19 only)
- **When to use:** designing component APIs or design-system libraries.
- **Install:** `cp -r agent-skills/skills/composition-patterns ~/.claude/skills/`.

### 1.5 UI/UX Pro Max
- **Source:** https://github.com/nextlevelbuilder/ui-ux-pro-max-skill. MIT.
- **What it does:** A Python CLI (`scripts/search.py`) queries a local CSV design database: 50+ styles, 97 palettes, 57 font pairings, 99 UX guidelines, 25 chart types, 9 stacks. The workflow has four steps:
  1. Analyze requirements.
  2. Run `--design-system` (required), which searches 5 domains and returns pattern, style, colors, typography, effects and anti-patterns.
  3. Run domain searches for more detail.
  4. Pull stack guidelines (react, shadcn, html-tailwind, and others).
- **Persistence:** `--design-system --persist` writes `design-system/MASTER.md` plus per-page overrides in `design-system/pages/`. The article points out this lets a dashboard use different density rules from a marketing page while keeping the same palette.
- **Rule priorities:**
  1. Accessibility (CRITICAL)
  2. Touch & Interaction (CRITICAL)
  3. Performance (HIGH)
  4. Layout/Responsive (HIGH)
  5. Typography/Color (MEDIUM)
  6. Animation (MEDIUM)
  7. Style (MEDIUM)
  8. Charts/Data (LOW)
- **Named checks:** contrast ≥ 4.5:1, visible focus rings, alt text, ARIA labels, keyboard navigation, form labels, and a pre-delivery checklist that includes light/dark contrast.
- **"Common Rules for Professional UI":**
  - no emoji icons (use SVGs)
  - `cursor-pointer` on every clickable element
  - transitions of 150-300ms
  - light-mode glass cards at `bg-white/80` or more opaque (not `bg-white/10`)
  - border visibility checked in both themes
- **Install:** `cp -r ui-ux-pro-max-skill/.claude/skills/ui-ux-pro-max ~/.claude/skills/`, or `/plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill`.
- **Example CLI call:** `python3 skills/ui-ux-pro-max/scripts/search.py "elegant luxury" --domain typography`

### 1.6 Bencium UX Designer
- **Source:** https://github.com/bencium/bencium-claude-code-design-skill. License not specified. 72 stars. Last updated Nov 2025.
- **Variants:** `bencium-innovative-ux-designer` and `bencium-controlled-ux-designer` ("for projects where consistency and control matter more than creativity"). Both ship `ACCESSIBILITY.md` (WCAG 2.1/2.2), `RESPONSIVE-DESIGN.md`, `MOTION-SPEC.md` (easing curves, duration tables) and `DESIGN-SYSTEM-TEMPLATE.md`.
- **Principles:**
  - simplicity through reduction
  - material honesty
  - functional layering
  - obsessive detail
  - coherent design language
  - invisibility of technology
- **Interaction guidance:**
  - direct manipulation (inline editing instead of separate forms, drag-and-drop instead of up/down buttons)
  - feedback within 100ms for every interaction
  - forgiveness (prevent errors and let users recover)
  - progressive disclosure (summary → details → advanced)
- **Install:** `cp -r bencium-claude-code-design-skill/bencium-controlled-ux-designer ~/.claude/skills/` (or the innovative variant).

### 1.7 AccessLint plugin
- **Source:** https://github.com/accesslint/claude-marketplace. MIT. 8 stars.
- **Skills:**
  - `contrast-checker`: WCAG ratios, AA/AAA, accessible alternatives that keep the design intent.
  - `refactor`: multi-file fixes for alt text, ARIA and semantic HTML.
  - `use-of-color`: WCAG 1.4.1; finds status, errors or links shown by color alone.
  - `link-purpose`: checks link text.
- **Agent:** `accesslint:reviewer` (WCAG 2.1 A/AA audit with severity levels and WCAG references).
- **MCP server:** `@accesslint/mcp` with tools `calculate_contrast_ratio`, `analyze_color_pair`, `suggest_accessible_color`. Other skills and agents can call these tools too.
- **Install:** `/plugin marketplace add accesslint/claude-marketplace` then `/plugin install accesslint@accesslint`, or manually `cp -r claude-marketplace/plugins/accesslint/skills/* ~/.claude/skills/`.
> "The star count is low (8 stars), but the skill quality is high and the scope is focused." (Snyk article, section 7)

### 1.8 Vercel react-native-skills
- **Source:** vercel-labs/agent-skills (`skills/react-native-skills/`). MIT.
- **What it does:** FlashList, memoized list items, `expo-image`, `Pressable`, animating only transform/opacity.
- **Relevance here:** none. Goldsmith ERP is a web PWA, not React Native. Skip it.

## 2. Security and supply-chain cautions (captured carefully)

> "Snyk's ToxicSkills research found prompt injection in 36% of skills tested and 1,467 malicious payloads across the ecosystem. Always review a skill's `SKILL.md` and any bundled scripts before installing. Treat skills the way you would treat any third-party code you run in your environment." (Snyk article, "Installing a Claude Skill")

> "Snyk's ToxicSkills study found that 13% of skills tested contained critical security flaws, and some actively attempted to exfiltrate credentials. The SKILL.md to Shell Access research demonstrated how three lines of markdown in a skill file can grant an attacker shell access to your machine." (Snyk article, "Security when installing skills")

> "...a malicious one can hide a reverse shell in those instructions and trigger it as soon as the skill loads. Research into poisoned skill marketplaces has also found that automated skill scanners give a false sense of safety, since harmless-looking instructions can chain into shell access. Review any skill from an unofficial source before installing, and limit what it can reach." (Snyk article, "Where to find and install Claude skills")

The article's pre-install checklist:
1. Read `SKILL.md` and every bundled script. They are plain text, not binaries.
2. Check the source. Anthropic, Vercel and well-known maintainers are lower risk; community skills need more scrutiny.
3. Review the `allowed-tools` frontmatter. A skill that needs `Bash` "warrants more scrutiny than one that only uses `Read` and `Grep`."
4. Scan the scripts with Snyk Code or the Snyk MCP.
5. Be especially careful with Python scripts. For example, read `scripts/search.py` in UI/UX Pro Max. The article says that one only queries local CSVs.

Closing principle:
> "The skills on this list are from reputable sources with clear licensing. But the general principle applies: trust, then verify." (Snyk article)

Also noted in the article:
- **Name precedence:** enterprise > personal (user) > project skills. A user-level skill with the same name silently overrides a project skill.
- **Scope:** project-level skills (`.claude/skills/`) are shared with the team through git. User-level skills (`~/.claude/skills/`) are private.
- **Discovery sources:** Claude.ai Customize → Skills; github.com/anthropics/skills; community lists travisvn/awesome-claude-skills and VoltAgent/awesome-agent-skills. The article says unofficial directories should get extra scrutiny.
- **Maintainer offer:** Snyk Secure Developer Program, free scanning for open-source skill and MCP maintainers.

## 3. General UI/UX engineering workflow advice

- **Division of labor:** AI does the repetitive work and humans keep the judgment calls.
> "It handles the repetitive work (generating responsive variants, checking contrast ratios, scaffolding component boilerplate, auditing against checklists) so the human can spend more time on the decisions that actually matter." (Snyk article, intro)
- **Healthy skepticism:** 91% of UX researchers worry about accuracy. AI is good at first drafts and scaffolding but "trip[s] over bespoke tweaks, nuanced interaction patterns" and design judgment.
- **Combine layers:** creative direction + design intelligence + quality/compliance gate + engineering patterns.
> "The most effective approach is to combine skills from multiple categories... They do not conflict. They complement each other, each adding a different layer of quality to Claude's output." (Snyk article, "Wrapping up")
- **Design review as a lint pass:** audit specific file globs and report `file:line` findings (web-design-guidelines, AccessLint reviewer).
- **Accessibility checks:** contrast ≥ 4.5:1, focus visibility, keyboard navigation, labels, no color-only status (WCAG 1.4.1), link purpose, reduced motion, touch target size, heading hierarchy.
- **Component generation:** compound components and explicit variants instead of boolean props; children instead of render props; a provider that owns the state implementation.
- **Performance ordering:** fix waterfalls and bundle size first, re-renders last. Avoid barrel imports. Use Suspense boundaries and `content-visibility` for long lists.
- **Design systems:** a master file plus per-page overrides (Pro Max `MASTER.md`). Pick a "controlled" rather than "innovative" design posture for consistency-first products.
- **Community workflows mentioned in passing:** automatic dark-mode conversion, accessible component variants, WCAG page audits, and Figma/Bolt design-to-code (video).
- **Not covered:** visual regression testing and screenshot loops. The article does not address them.

## 4. Evaluation criteria the article uses

Implicit in the per-skill metadata and commentary:
- GitHub stars (popularity). The article explicitly says a low count, as with AccessLint, does not mean low quality.
- License clarity (MIT preferred; "Not specified" is flagged).
- "Last Updated" recency.
- "Verified SKILL.md: Yes", meaning the skill really exists in skill format.
- Source reputation (Anthropic, Vercel, known maintainers).
- Focused scope and concrete rules with incorrect/correct examples.
- Priority ordering of rules by impact.
- A precise `description` with trigger phrases:
> "vague descriptions activate unreliably, while precise descriptions with explicit trigger phrases ... activate consistently." (Snyk article, "What are Claude Skills")
- Uses progressive disclosure, so it stays cheap on context.
- Minimal `allowed-tools` and no network or shell access it does not need.

---

## Local skill inventory

Checked `~/.claude/skills`, `~/.claude/plugins` (marketplaces and cache, `installed_plugins.json`) and `goldsmith_erp/.claude/skills`. The repo only has `truecourse-*`. Identity was confirmed from SKILL.md frontmatter only.

| Skill from article | Installed locally | Local path if found |
|---|---|---|
| Anthropic frontend-design | **yes** (plugin `frontend-design@claude-plugins-official`, invoked as `frontend-design:frontend-design`) | `~/.claude/plugins/marketplaces/claude-plugins-official/plugins/frontend-design/skills/frontend-design/SKILL.md` |
| Vercel web-design-guidelines | no. **Similar:** ecc `accessibility` (WCAG 2.2 AA), ecc `frontend-a11y`, ecc `make-interfaces-feel-better`, GSD `gsd-ui-review` (6-pillar audit) | `~/.claude/plugins/marketplaces/ecc/skills/accessibility/`, `.../ecc/skills/frontend-a11y/`, `~/.claude/skills/gsd-ui-review/` |
| Vercel react-best-practices | **similar (derived):** ecc `react-performance` says it is "adapted from Vercel Engineering's React Best Practices", 70+ rules, 8 categories | `~/.claude/plugins/marketplaces/ecc/skills/react-performance/SKILL.md` |
| Vercel composition-patterns | no. **Similar:** ecc `react-patterns` ("accessibility-first composition"), mattpocock `codebase-design` | `~/.claude/plugins/marketplaces/ecc/skills/react-patterns/` |
| UI/UX Pro Max | no. **Similar:** ecc `design-system` (generate/audit design systems), GSD `gsd-ui-phase` (UI-SPEC contract) | `~/.claude/plugins/marketplaces/ecc/skills/design-system/`, `~/.claude/skills/gsd-ui-phase/` |
| Bencium UX Designer (controlled/innovative) | no. **Similar:** ecc `frontend-design-direction`, ecc `motion-*` skills | `~/.claude/plugins/marketplaces/ecc/skills/frontend-design-direction/` |
| AccessLint (4 skills + reviewer + MCP) | no. **Similar:** ecc `accessibility`, `frontend-a11y`, agent `ecc:a11y-architect` (WCAG 2.2) | as above |
| Vercel react-native-skills | no (not applicable) | n/a |

## Direct applicability to Goldsmith ERP

Stack context: React 18.3, TypeScript, Vite, Tailwind 4, Vitest, Playwright. No axe-core, jest-axe or eslint-plugin-jsx-a11y found in `frontend/package.json`. Users are workshop staff on shared devices, possibly with gloves or dirty hands.

1. **Do not use frontend-design as the main driver for ERP screens.** It is installed, but the article itself says to pair it with a structured design-system skill for internal tools. Only use it for customer-facing artifacts such as quote/PDF layouts or the email templates in the V1.2 approval flow, and override its ban on system fonts wherever that hurts data density.
2. **First quality gate: web-design-guidelines-style audit.** The Vercel skill is not installed. Run an equivalent `file:line` audit now by invoking ecc `accessibility` + `frontend-a11y` (or the `ecc:a11y-architect` agent) over `frontend/src/components/**/*.tsx` and `frontend/src/pages/**`. The Vercel skill is from a reputable source and MIT, so it is a reasonable option if Max approves. Vendor the rules file instead of letting the skill fetch it at runtime.
3. **Add deterministic a11y tooling, because skills are not a CI gate.** Suggest `@axe-core/playwright` in the existing Playwright e2e suite and `eslint-plugin-jsx-a11y`. This covers AccessLint's `use-of-color` and contrast checks where no plugin is installed. Order status chips (DRAFT/in progress/done) are an obvious WCAG 1.4.1 risk if they are distinguished by color only.
4. **Performance: use the installed ecc `react-performance`, which is already derived from Vercel's rules.** Follow the article's order: waterfalls first (order detail loading its sub-resources in sequence), then bundle size (barrel imports in the icon and component folders), and only then memoization. Do not install the Vercel copy on top of it.
5. **Component APIs: apply composition-pattern rules by hand, using ecc `react-patterns`.** Targets are components that tend to collect boolean props (`ConfirmDialog`, `Toast`, `CustomerFormModal`, `ToggleSetting`). Prefer explicit variants such as `ConfirmDialog.Destructive`. Skip `react19-no-forwardref`, since the project is on React 18.3.
6. **Design system: adopt the Pro Max master + page-override idea without the tool.** Write a `design-system/MASTER.md`-style contract (tokens, density, status colors) with a stricter density override for the dashboard and list pages. Author it with ecc `design-system` or `gsd-ui-phase` (UI-SPEC.md). Installing Pro Max would mean running a third-party Python script and gives an ERP little value (the dataset is landing-page oriented), so treat it as optional reading.
7. **Bencium "controlled" variant is the best philosophical fit but has no license.** Its interaction rules (inline editing over separate forms, feedback within 100ms, forgiveness/undo, progressive disclosure) suit order and material CRUD in a workshop. Because the license is missing and the star count is low, cite the principles in the playbook instead of installing the skill.
8. **Pro Max "Common Rules" worth copying into the playbook straight away:** no emoji icons (SVG only), `cursor-pointer` on every clickable element, 150-300ms transitions, border and contrast checks in both light and dark (`ThemeToggle` exists), contrast ≥ 4.5:1, visible focus rings. Add touch target size from the Vercel guidelines, which matters for gloved workshop use.
9. **Skip react-native-skills entirely.**
10. **Suggested adoption order:**
    1. a11y audit with installed ecc skills + axe in Playwright
    2. react-performance pass
    3. composition refactor of the dialog/toast family
    4. MASTER design contract
    5. optionally, after review, vendor Vercel `web-design-guidelines` and `composition-patterns` into project `.claude/skills/`

## Security notes on adopting skills

- Apply the article's 5-step checklist (section 2) to every new skill. Vercel and Anthropic skills are lowest risk. Bencium (no license, 72 stars) and AccessLint (8 stars, bundles an MCP server `@accesslint/mcp` pulled from npm) need a full read of every file.
- Project-level skills in `goldsmith_erp/.claude/skills/` are committed and shared, so review them like code in a PR. The same applies to anything that touches customer PII, design IP or pricing data under the project's data-privacy rules. A skill that reads the codebase can see encrypted-field logic and pricing code.
- Prefer skills whose `allowed-tools` exclude `Bash`. Pro Max needs `python3` execution. web-design-guidelines fetches a remote rules URL at runtime, which is a prompt-injection surface; pin or vendor it.
- Watch for name collisions. User-level skills override project skills with the same name, so a later personal install could silently shadow a vetted project copy.
- The article warns that automated scanners give "a false sense of safety", so manual review is still required even after a Snyk scan.
- Nothing was installed during this research.

## Open questions

1. Does Max want third-party skills vendored into the repo, which puts them under team review, or kept at user level?
2. Should the Vercel web-design-guidelines rules be vendored and pinned (a static copy) rather than fetched live, to remove the runtime remote-content risk?
3. Is AccessLint's MCP server acceptable, given it is a low-star npm dependency running locally? Or is axe-core in Playwright enough?
4. Bencium has no license. Is citing its principles in an internal playbook acceptable, or should only MIT-licensed sources be used?
5. Target WCAG level: the article's tools cover 2.1 AA, while ecc `accessibility` targets 2.2 AA. Which one is the playbook standard?
6. The article does not cover visual regression or screenshot loops. Those need a separate source, e.g. Playwright `toHaveScreenshot` in the existing e2e suite.
