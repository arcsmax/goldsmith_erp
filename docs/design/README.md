# docs/design

Design documentation for the Goldsmith ERP frontend (`frontend/`). Humans and AI coding agents read this
folder before any UI change.

## Contents

| Path | What it is |
|---|---|
| `UI-UX-PLAYBOOK.md` | The main document: design principles, token spec, component primitives, page templates, accessibility checklist, the Claude Code working process, skill vetting, migration plan, definition of done, German glossary. Start here. |
| `research/2026-09-24-claude-design-system-notes.md` | Notes on the Claude Design help article "Set up your design system" (`/design-sync`, guides + tokens + components). |
| `research/2026-09-24-aidesigner-frontend-design-notes.md` | Notes on the aidesigner.ai article about UI design with Claude Code (hard rules, visual references, screenshot loop) and a summary of the local frontend-design skill. |
| `research/2026-09-24-snyk-ui-ux-skills-notes.md` | Notes on Snyk's "Top 8 Claude skills for UI/UX engineers", including the skill supply-chain warnings and the local skill inventory. |
| `design-investigation.md` (to be added) | The 2026-09-24 audit of the current frontend: token inventory, duplicates, contrast measurements, workshop fit, improvement plan I-01 to I-30. The playbook takes all its counts from it. Until it is copied here, the original is in `.orchestrated-fable/ux-erp-audit-2026-09/`. |

## Rules for this folder

- The source of truth for tokens is `frontend/src/styles/brand-tokens.css`. The playbook documents it; a pull
  request that changes one updates the other.
- Research notes are dated snapshots. Do not edit their findings; add a new dated note instead.
- Numbers in the playbook trace either to the design investigation or to the contrast script in its Appendix B.
- Screenshots used in design work contain demo data only and are not committed here.

## Related

- Project rules: `CLAUDE.md` (the playbook section 7a holds the UI rules block to paste there).
- Agent personas: `.claude/agents/design-lead.md` (@jason), `.claude/agents/ux-researcher.md` (@uxresearch).
