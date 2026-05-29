# Goldsmith ERP — LikeC4 architecture workspace

This folder holds the version-controlled, text-source **C4 model** for the goldsmith ERP, authored in [LikeC4](https://likec4.dev) and rendered as an interactive web app + Mermaid exports.

```
docs/architecture/likec4/
├── package.json           — likec4 dev dependency, npm scripts
├── src/
│   └── goldsmith-erp.c4   — the model (edit this, hot-reload picks it up)
├── dist/                  — output of `npm run build` (gitignored)
└── exports/               — output of `npm run export:*` (gitignored)
```

## Quick start

```bash
npm install          # installs likec4
npm run dev          # opens http://localhost:5173 with hot-reload
```

Other scripts:

| Script                  | What it does                                      |
| ----------------------- | ------------------------------------------------- |
| `npm run dev`           | Dev server with live preview at `:5173`.          |
| `npm run build`         | Static site → `dist/` (deployable anywhere).      |
| `npm run export:mermaid`| Mermaid `.mmd` per view → `exports/mermaid/`.     |
| `npm run export:png`    | PNG per view → `exports/`. Needs Playwright.      |
| `npm run validate`      | Lint the model. Run before commits.               |

The **full install + usage guide (Mac + Windows)** is in [`docs/technical/architecture/likec4-setup.md`](../../technical/architecture/likec4-setup.md).
