# Research: "Set up your design system in Claude Design"

> Cleaned copy of the research notes taken on 2026-09-24 for the UI/UX playbook (`docs/design/UI-UX-PLAYBOOK.md`). Content and quotations are unchanged except that em dashes inside quotations are rendered as a spaced hyphen, to follow the repository writing rule. Counts about this repository are superseded by the design investigation (40 stylesheets, 1,580 hard-coded hex values in CSS); where an older count appears below it is marked.

- **Primary URL:** https://support.claude.com/en/articles/14604397-set-up-your-design-system-in-claude-design
- **Fetch date:** 2026-09-24
- **Fetch complete:** Yes. Fetched twice: (a) WebFetch (live page, model-rendered, close paraphrase), (b) Exa `web_fetch_exa` (full raw text, but apparently an **older cached revision**: "Updated over 3 weeks ago", says Enterprise is "default off" and has no `/design-sync` or migration section). Where they differ, both are noted. The article is short, about 600 words.
- **Linked page also fetched (1 of max 3):** https://support.claude.com/en/articles/14604416-get-started-with-claude-design (WebFetch summary only, not verbatim).
- **Not fetched:** the Claude Design admin guide (14604406) and the Artifacts admin guide (16994751). Both cover admin/permissions and have no design guidance.

**Main caveat up front:** this is a product-setup help article, not a design-methodology guide. It says **what** a Claude-generated design system contains and **how** to feed and publish one. It gives almost no guidance on token naming, doc structure, accessibility, responsiveness or avoiding "AI-looking" UI. Sections 3, 5 and 6 below are therefore mostly "the article is silent", plus inferences that are marked as such.

---

## 1. What Claude Design is and how a design system is set up

**What it is.**
> "Creating a design system allows Claude Design to produce outputs that fit your specifications. It extracts reusable components, colors, typography, and patterns from the assets you provide - codebases, slide decks, or other design references - and uses them as the foundation for every project created within your account."
> (support.claude.com, 14604397, Exa revision)

Live revision, paraphrased: a design system "captures colors, typography, components, and layout patterns so Claude applies them consistently to new designs and decks."

From the linked "Get started" article (paraphrased): Claude Design is a beta feature for making designs, prototypes and visual work through conversation. It runs in a conversation, in the Artifacts tab, in Claude Code, and standalone at claude.ai/design. Design systems can come "from a GitHub repo, design files, raw uploads, or your local codebase."

**Availability.** Beta on Pro, Max, Team, Enterprise. Live revision: on by default for Pro/Max/Team. Enterprise admins enable it under *Organization settings > Artifacts*. The older revision says "default off for Enterprise plans."

**Audience and cadence.**
> "This guide is for the designer or brand owner who will set up the design system. You only need to do this once; after setup, all team members' projects automatically use it (for Team and Enterprise plans)." (Exa revision)

**Three creation paths (live revision only):**
1. **From chat.** Ask Claude to build a design system from connected apps, uploaded files, Figma files, decks, logos and fonts. "Works best for brand design systems."
2. **From Claude Code.** "If your design system exists as React components, run `/design-sync` in Claude Code. It reads tokens and components directly - best for product design systems in code." **This is the path that fits Goldsmith ERP.**
3. **Migrate from claude.ai/design.** Design tab in sidebar, then "Migrate team design systems", then "Let Claude clean it up" (Claude tidies guides, tokens and components).

**Step-by-step setup at claude.ai/design (both revisions):**
1. Open Claude Design. Click the organization name in the lower-left of the project picker. Select or create an org, then complete the onboarding flow.
2. Upload brand and product assets (during onboarding or later from org settings).
3. Review the generated design system ("UI kit") and validate it with test prompts.
4. Switch on the "Published" toggle.

**Accepted inputs (Step 2):**
> "Codebases: If your design system lives in code (for example, a React component library), you can link or upload the repository. Claude will read the components and styles."
> "Prototypes: Screenshots, web flows, and existing design files."
> "Slide decks or documents: Even a well-designed PowerPoint or PDF that reflects your brand can work. Claude extracts colors, layout patterns, and typographic choices."
> "Individual assets: Logos, color palette files, typography specimens."
> "You only need one source to get started, but providing multiple gives Claude more to work with."
> (Exa revision)

The chat path adds **Figma files, fonts and connected apps**. Formats named explicitly: PowerPoint, PDF, screenshots, React repos. No token file format (JSON, DTCG, CSS variables) is named.

**Prerequisites:**
> "Permissions granted by your organization admin for design system setup."
> "At least one of the following as source material: A codebase with your design system or component library; A slide deck or document that reflects your visual identity; Brand guideline assets (logos, color palettes, typography specs)."

## 2. What a well-formed design system consists of (per the article)

The article describes what Claude **generates**. It does not give a normative spec. Output ("UI kit"):
> "Color palette: Primary, secondary, and accent colors extracted from your assets."
> "Typography: Font families, sizes, and weights."
> "Components: Buttons, cards, navigation elements, and other reusable UI patterns."
> "Layout patterns: Spacing, grid systems, and page structures."
> (Exa revision)

The live revision's migration step also refers to the parts of a design system as **"guides, tokens, and components"**. That is a three-part model: prose usage guides, design tokens, and component definitions.

**Validation by example prompts:**
> "To validate your design system, create a test project and see if the output matches your brand expectations. Try prompts like: 'Create a landing page for [your product].' 'Design a dashboard showing [relevant metrics].' 'Make a presentation about [a topic your team commonly presents on].'"

**Do/don't guidance:** none beyond the tips in section 5. The article does not mention states (hover, focus, disabled), elevation/shadows, radii, motion, iconography, dark mode or content/voice rules.

## 3. Recommended documentation structure an AI coding agent can consume

**The article does not prescribe one.** There is no README template, no tokens-file schema and no naming convention.

What can be inferred:
- The mental model is **guides + tokens + components** (migration wording).
- For code-based systems, Claude "will read the components and styles" and `/design-sync` "reads tokens and components directly". So the **code itself is the source of truth**, and it has to be readable as code: tokens as named variables, components as React components. A separate spec document is not required.
- Inference, not in the article: an agent will extract more reliably if tokens live in one discoverable file and components have clear names and a single place per pattern. Scattered hex literals and duplicate button styles produce a noisier extraction.

## 4. Keeping design system and code in sync, versioning, exporting

- **Sync code to design:** `/design-sync` in Claude Code, which reads tokens and components from the React codebase (live revision). The article does not say whether it is one-way or repeatable, how conflicts work, or whether it writes anything back to code.
- **Updating:**
  > "Brands evolve. When your design system changes, you can update it within Claude Design. From your Claude Design organization settings, click the 'Open' button next to the design system you want to edit. Click the 'Remix' button in the upper right corner to open the chat interface on the left side of the window. From here, you can work with Claude to change your design system."
  > (Exa revision)
- **Management:** *Settings > Design systems*. Enterprise admins can restrict publishing, setting defaults and deletion to specific users.
- **Publishing:** the "Published" toggle makes it the default for new projects created from the Claude Design home screen in that org, "instead of the default."
- **Versioning:** not covered. The "Get started" article (paraphrased) lists "absence of version history in the current beta release" as a known limitation.
- **Export/handoff (from "Get started", paraphrased):** ZIP, PDF, PPTX and standalone HTML, plus integrations (Adobe Experience Manager, Canva, Gamma, Miro, Netlify, Vercel, Wix) and a **Claude Code handoff** for design-to-code.

## 5. Tips on prompting for consistent UI, generic AI look, accessibility, responsiveness

**From the primary article (the only two tips):**
> "Include real examples, not just specs. A finished landing page or marketing site tells Claude more about your brand's feel than a color palette alone."
> "Iterate. If the first extraction doesn't capture your brand well, try uploading additional or different assets."
> (Exa revision)

The first tip is the article's most useful guidance: **finished screens convey "feel" better than token lists.** It is also the closest the article comes to addressing generic-looking output.

**From "Get started" (paraphrased):**
- Good prompts specify **goal, layout, content and audience**.
- Start simple, then add complexity. Ask for **variations** when unsure of direction.
- Refinement modes: **chat** for broad or structural changes ("Make the color scheme darker"), **inline comments** for targeted component-level changes, **direct canvas editing** for quick visual tweaks.

**Accessibility:** not mentioned. **Responsive layouts:** not mentioned beyond "grid systems" and "page structures" as extracted layout patterns. **Generic AI-looking UI:** not addressed by name.

## 6. Applicability to a codebase with CSS token files instead of Tailwind

- The article says Claude "will read the components and styles" of a codebase and extracts from "color palette files". It does **not** restrict this to Tailwind, CSS variables or any particular format. A CSS custom-property token file fits "styles" / "tokens".
- **Local check of the repository:** `frontend/src/styles/brand-tokens.css` (114 lines) is **not plain CSS**. It begins with `@import "tailwindcss";` and declares tokens in a Tailwind v4 `@theme { ... }` block, for example `--color-brand-cta-50..900` (gold/amber CTA), `--color-brand-primary-50..900` (charcoal/slate surfaces) and `--color-brand-cream-*` (ivory backgrounds). The project is a **hybrid**: Tailwind v4 theme tokens exposed as CSS custom properties, plus hand-written per-feature CSS files in `frontend/src/styles/` (about 20 by a first count; the design investigation counts 40 including `styles/components/`) (buttons.css, orders.css, dashboard.css and others). MEMORY also records a "Tailwind-layer gotcha". The playbook describes it that way.
- Since `@theme` tokens compile to ordinary `--color-*` custom properties, `/design-sync` should be able to read them either way. The article does not confirm this.

---

## Direct applicability to Goldsmith ERP

1. **Use the Claude Code path, not the upload path.** The ERP is a product design system that lives in React code. Run `/design-sync` from the repo (live revision: "best for product design systems in code") instead of uploading screenshots or PDFs to claude.ai/design.
2. **Clean up the token source before syncing.** Keep `brand-tokens.css` as the single token file (color, typography, spacing, radius). Remove or map any raw hex values in the feature CSS files to `var(--color-brand-*)`, so the extraction picks up one consistent palette instead of stray values.
3. **Cover all four categories the generator expects.** It extracts color palette, typography (family/size/weight), components and layout (spacing/grid/page structure). Check that brand-tokens.css actually defines the typography and spacing scales, not only the color ramps. Any gap there will be filled with defaults.
4. **Treat semantic roles as primary/secondary/accent.** Claude's output uses "primary, secondary, and accent". Document how CTA gold, charcoal primary and cream map onto those roles. Note that the naming clash is real: in this repo "primary" means charcoal surfaces while the CTA is gold. Without that note an agent may put gold on `primary` buttons.
5. **Consolidate components into one place per pattern.** Claude "will read the components". A single Button, Card, StatusBadge and Table implementation, rather than duplicated class strings, makes extraction and later generation consistent. The global `buttons.css` from the V1.2 fixes is a good anchor.
6. **Give real reference screens, not only tokens.** Following the article's main tip, point the design system (or an agent brief) at 2-3 finished, representative ERP screens, for example the order detail, the quote editor with EstimatorPanel, and the dashboard. These show the workshop "feel" better than the palette does.
7. **Validate with ERP-relevant test prompts.** Adapt the article's validation step: "Design a dashboard showing open orders, overdue deadlines and material stock", "Create an order detail view with status timeline and photos", "Create a quote editor with line items". Compare the results against the live app.
8. **Write guides, tokens and components as three artefacts.** Mirror the article's migration model. Keep tokens in `brand-tokens.css`, components in code, and add one short usage guide (the playbook itself) covering rules the article does not: focus states, WCAG contrast of gold on cream, touch targets for workshop tablets, and density for data tables.
9. **Plan for no version history.** Claude Design has no version history in beta. Keep the repo, meaning the tokens file and the playbook in git, as the versioned source of truth, and treat Claude Design as a derived consumer. Re-run `/design-sync` after token changes.
10. **Keep data privacy in mind with uploads.** If screenshots are ever uploaded to claude.ai/design, use demo data only. Real screens contain customer PII and pricing (CLAUDE.md data-privacy rules). The article gives no guidance on this.

## Locally available related skills

Under `~/.claude/skills` (user): no design-specific skill. The nearest are `gsd-ui-phase` (UI-SPEC design contract), `gsd-ui-review` (6-pillar visual audit) and `gsd-sketch` (throwaway HTML mockups). `humanizer` is for copy only.

Under `~/.claude/plugins/cache`:
- `claude-plugins-official/frontend-design/*/skills/frontend-design`: Anthropic's frontend-design skill, about distinctive, non-templated aesthetic direction.
- `ecc/2.0.0-rc.1/skills/design-system`: generate or audit a design system. Its output is `DESIGN.md` + `design-tokens.json` + `design-preview.html`, and it includes a 10-dimension visual audit.
- `ecc/2.0.0-rc.1/skills/frontend-design-direction`: product-specific design direction for production UI.
- `ecc/2.0.0-rc.1/skills/frontend-a11y`: frontend accessibility.
- `ecc/2.0.0-rc.1/skills/accessibility`: accessibility (general).
- `ecc/2.0.0-rc.1/skills/frontend-patterns`: frontend patterns.
- `ecc/2.0.0-rc.1/skills/liquid-glass-design`, `frontend-slides` - not relevant to the ERP.

Built into the session: `artifact-design`, `dataviz` (charts and dashboard stat tiles, relevant to the ERP dashboard), `ecc:make-interfaces-feel-better`, `ecc:dashboard-builder`.

Repo `.claude/skills`: only `truecourse-analyze`, `truecourse-fix`, `truecourse-hooks`, `truecourse-list`. None are design-related.

Not found locally: no `/design-sync` skill or command file. It is presumably a built-in Claude Code command. That was not verified.

## Open questions / things the article did not answer

- What exactly does `/design-sync` read (CSS custom properties? Tailwind `@theme`? TS theme objects?), is it repeatable, and does it ever write back to the codebase?
- Is there a canonical token file format (DTCG JSON, CSS variables) or a documentation layout that improves extraction?
- How are component states (hover, focus, disabled, error), density variants, dark mode and elevation represented?
- Accessibility: does the generated system enforce contrast or focus styles? This is not mentioned at all.
- Responsive and breakpoint handling: not mentioned.
- Is there any guidance on avoiding generic or templated output, other than "include real examples"?
- Versioning and rollback of design systems ("no version history" in beta), and how multiple design systems per org are chosen.
- Whether a design system created in Claude Design applies to Claude Code sessions, or only to projects created from the Claude Design home screen.
- Data handling for uploaded codebases and screenshots (retention, training), which matters for PII-bearing ERP screens.
