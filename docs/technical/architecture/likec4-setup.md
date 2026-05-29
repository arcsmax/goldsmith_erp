# LikeC4 — install & use the architecture model

This guide installs [LikeC4](https://likec4.dev) — the architecture-as-code tool we use to render the C4 model of the goldsmith ERP — on **macOS** and **Windows** from scratch, and walks through the day-to-day workflow.

The model itself lives at [`docs/architecture/likec4/src/goldsmith-erp.c4`](../../architecture/likec4/src/goldsmith-erp.c4). Edit it → run `npm run dev` → the browser refreshes immediately.

> **TL;DR for an experienced dev:** clone the repo, `cd docs/architecture/likec4`, `npm install`, `npm run dev`, open `http://localhost:5173`.

---

## 1. Why LikeC4 (and what we considered)

The goldsmith ERP is a containerised FastAPI + React + Postgres + Redis stack with several bounded contexts (orders, materials, time-tracking, scrap-gold, GDPR audit, scanner+ML). We want diagrams that are:

- **Text-source, in git** — diff-friendly, review-able, CI-renderable.
- **Single source → many views** — context, container, component, deployment, dynamic — all derived from one model file.
- **Interactive in the browser** — pan/zoom, click-through navigation, hot-reload while editing.
- **Open-source + 100 % local** — no SaaS lock-in (CLAUDE.md's data-privacy rules apply).

LikeC4 is the only tool that delivers all four at once. Two parallel research passes against the OSS landscape (see [§ Alternatives](#7-alternatives-we-evaluated)) both reached the same verdict for this stack: **LikeC4 stays.** Structurizr `local` is the closest credible alternative; pyreverse + eralchemy2 are useful *complements* (not replacements) and can be wired into CI later.

---

## 2. Prerequisites

| Tool         | Minimum                                  | Why                                          |
| ------------ | ---------------------------------------- | -------------------------------------------- |
| **Node.js**  | **≥ 22.17** for LikeC4 1.38 *(this project's pinned version)* | LikeC4 CLI is a Node app. Newer LikeC4 (≥ 1.57) requires Node ≥ 22.22.3 — see § 6. |
| **npm**      | ≥ 10 (ships with Node 22)                | Installs the dev dep.                        |
| **Git**      | any modern                               | To clone the repo.                           |
| **VSCode** *(recommended)* | latest                       | Excellent LikeC4 extension (`likec4.likec4-vscode`) — syntax, preview, hover. |
| **A modern browser**   | Chrome / Edge / Firefox / Safari  | The dev server renders client-side. |

You **do not** need Python, Postgres, Redis, Podman, Java, or anything from the wider goldsmith-erp toolchain to work on the architecture model — it is fully isolated under `docs/architecture/likec4/`.

---

## 3. Install — macOS

```bash
# 1. Node 22.x (skip if you already have it)
#    Recommended: use Homebrew or nvm.
brew install node@22                     # or: nvm install 22 && nvm use 22
node --version                           # → v22.17.x or higher

# 2. Clone the repo (skip if you already have it)
git clone https://github.com/arcsmax/goldsmith_erp.git
cd goldsmith_erp

# 3. Enter the LikeC4 workspace and install
cd docs/architecture/likec4
npm install                              # ~30s on a fresh machine

# 4. Run the dev server
npm run dev
# → opens http://localhost:5173 with the goldsmith ERP architecture
```

**Optional:** install the VSCode extension for live preview + syntax highlight:

```bash
code --install-extension likec4.likec4-vscode
```

---

## 4. Install — Windows

The exact same commands work in **PowerShell** or **Windows Terminal**. WSL2 is not required, but works fine if you prefer Linux ergonomics.

### Step-by-step (PowerShell)

```powershell
# 1. Node.js 22.x
#    Easiest path: download the LTS installer from https://nodejs.org/en/download
#    or use winget:
winget install OpenJS.NodeJS.LTS

# Verify (open a *new* shell after install so PATH refreshes)
node --version                          # → v22.17.x or higher
npm --version                           # → 10.x or higher

# 2. Git (skip if installed)
winget install Git.Git

# 3. Clone the repo
git clone https://github.com/arcsmax/goldsmith_erp.git
cd goldsmith_erp

# 4. Enter the LikeC4 workspace and install
cd docs\architecture\likec4
npm install                             # may take ~30-60s on first run

# 5. Run the dev server
npm run dev
# → opens http://localhost:5173 in your default browser
```

If the browser does not open automatically, open `http://localhost:5173` manually. Hot-reload works the same as on macOS — save `goldsmith-erp.c4`, the browser refreshes.

### Windows-specific notes

- **Path separator** — the npm scripts use forward slashes; PowerShell handles those fine. If you invoke `likec4` directly with a path argument, both `likec4 build src` and `likec4 build .\src` work.
- **PowerShell execution policy** — the npm scripts run via `npm-cli.js`, which is unaffected. No policy change needed.
- **Antivirus / Defender** — first `npm install` writes thousands of small files in `node_modules\`. Add an exclusion for the repo root if installs feel slow.
- **WSL2** — if you already work in WSL, treat it as Linux: same commands as the macOS section. Cross-mount filesystems (`/mnt/c/...`) are notoriously slow for `npm install`; clone inside the WSL filesystem (`~/code/...`) for sane performance.
- **Browser not opening** — `npm run dev` falls back to printing the URL; click it from the terminal or open manually.

### VSCode extension on Windows

```powershell
code --install-extension likec4.likec4-vscode
```

Or via VSCode UI: **Extensions** → search for `LikeC4` → **Install**.

---

## 5. Daily workflow

### 5.1 Edit the model

Open `docs/architecture/likec4/src/goldsmith-erp.c4` in VSCode. The DSL is roughly four blocks:

```c4
specification { … }   // declare element kinds, tag names, relationship styles
model         { … }   // the actual actors, systems, containers, edges
views         { … }   // which views to render (context, container, dynamic, …)
```

While you edit, leave `npm run dev` running in a terminal — the browser at `:5173` re-renders within ~1 second of saving.

### 5.2 Minimal new view

```c4
view my-new-view {
  title 'A view of what I care about'
  include erp.backend, erp.postgres
  autoLayout LeftRight
}
```

Save → it appears in the dev-server sidebar.

### 5.3 Validate before committing

```bash
npm run validate
```

…or rely on the dev-server console which surfaces warnings as you type. CI may add `likec4 validate` later — keep the model parse-clean.

### 5.4 Build the static site

```bash
npm run build
# → dist/ contains a standalone, interactive site (~5 MB minus fonts)
```

Host `dist/` anywhere — GitHub Pages, S3, the docs CI artefact bucket, nginx in the existing Podman pod. The site is fully client-side, no backend required.

### 5.5 Export Mermaid (for README embeds / PRs)

```bash
npm run export:mermaid
# → exports/mermaid/<view>.mmd per view
```

GitHub, GitLab, and most markdown renderers render Mermaid natively. Paste into a `.md` file:

````markdown
```mermaid
graph LR
  Goldsmith[fa:fa-user Goldsmith]
  …
```
````

### 5.6 Export PNG (for slides, printed docs)

PNG export needs **Playwright** (LikeC4 spins up a headless browser to screenshot the rendered SVG):

```bash
# First time only:
npx playwright install chromium

# Then:
npm run export:png
# → exports/<view>.png per view
```

---

## 6. Version notes & known v1.38 quirks

LikeC4 ships frequent releases. We are intentionally pinned to **the highest version that runs on Node 22.17.x**, which is **1.38.1**. The latest (**1.57.0**, May 2026) requires **Node ≥ 22.22.3** — bump Node first, then `npm install likec4@latest`, and many of the quirks below should disappear.

Quirks observed on 1.38.1, all documented inline in `goldsmith-erp.c4`:

- **Multi-line `'''…'''` descriptions on child elements inside `system { … }`** silently abort parsing of the next sibling. Workaround: keep nested-element descriptions single-line. Top-level actors are unaffected.
- **Inline `#tag` lines inside child element bodies** trigger the same parse abort. Workaround: declare tags but style by element kind in views.
- **Edge tag syntax** — v1.38 expects `#tag` *inside* the `{ … }` property block, not after it.
- **`deployment { … }` blocks** — `instanceOf <fqn>` references trip `FqnRef is empty` warnings; the deployment view is deferred until ≥ 1.57. Local Podman reality is documented in `docs/technical/infrastructure/PODMAN_MIGRATION.md` separately.
- **Nested elements inside non-system kinds** (e.g. components inside a service) — the LikeC4 DSL for the C4 component level needs a different declaration than we tried; pinning that down is the next iteration.
- **`npm install` security audit** — current dep tree has 2 high-severity advisories in transitive deps (typical Node ecosystem noise). Re-evaluate when upgrading to 1.57.

After bumping Node + LikeC4, re-run `npm run dev` and remove these workarounds in `goldsmith-erp.c4`.

---

## 7. Alternatives we evaluated

Two parallel research passes (one focused on DSL/text-based tools, the other on code-first/visual tools) examined every credible OSS-and-local option. Verdict for this stack: **LikeC4 stays.** Below is the short list — full reports captured during the evaluation.

| Tool | License | Verdict for goldsmith_erp |
| ---- | ------- | ------------------------- |
| **Structurizr `local`** (was *Structurizr Lite*; archived 2026-02, replaced by `structurizr/structurizr`) | Apache-2.0 | The only **strictly comparable** alternative. Reference C4 lineage, broadest export menu (incl. native SVG), manual-layout persistence. Loses on slick web UX and embedding flexibility. Use it as a **complement** if SVG exports for printed docs become a must. |
| **C4-PlantUML** | MIT | Renders anywhere PlantUML does (GitLab, Confluence). No model unification, no drill-through, static images only. Not a serious modelling tool for a multi-tier ERP. |
| **Mermaid C4 / architecture-beta** | MIT | Explicitly experimental + unstable syntax; layout collapses past ~6 elements; mermaid-cli still can't render `architecture-beta`. Fine for tiny embedded diagrams, not as authoritative architecture documentation. |
| **D2** (Terrastruct) | MPL-2.0 | Best-looking output, multi-engine layouts, hot-reload, interactive SVG. **Not** C4-native; you lose the level hierarchy + view derivation. Cadence slowed in 2025 (no tagged release since v0.7.1 Aug 2023). |
| **Archi** (ArchiMate) | MIT-style | Wins for enterprise-architecture-grade modelling (capabilities, motivations, GDPR layers). Loses on diagrams-as-code: Archi files are XML blobs, diff-hostile. |
| **draw.io / diagrams.net Desktop** | Apache-2.0 | Excellent visual editor with a C4 shape library. Pure WYSIWYG, no code source. **Diff hostility kills it** for our git-as-source-of-truth approach. |
| **mingrammer/diagrams** (Python) | MIT | Python DSL with polished AWS-style icons. **No C4 levels.** Use it if you ever document cloud infrastructure separately. |
| **pyreverse** (pylint) | GPL-2.0 | **Genuine complement.** Generates UML class/package diagrams from the live Python AST. Run in CI, embed the SVG into the LikeC4-built site for an always-current service-layer view. |
| **eralchemy2** (SQLAlchemy → ER) | Apache-2.0 | **Genuine complement.** Reflects `Base.metadata` (or a live DB) into ER diagrams. Pair with pyreverse: LikeC4 holds the human architecture, these two hold the auto-generated truth. |
| **Ilograph / Gleek** | Proprietary | Disqualified — not OSS / local. |

**Bottom line:** LikeC4 owns the high-level architecture model. **Structurizr local** is a credible secondary for SVG-heavy export workflows. **pyreverse + eralchemy2** are the auto-generated complements that close the "is the diagram up-to-date?" gap.

---

## 8. Troubleshooting

| Symptom | Fix |
| ------- | --- |
| `npm install` fails with `engine` / `node` complaint | Your Node is older than 22.17. Upgrade Node, delete `node_modules/` + `package-lock.json`, re-install. |
| `npm install` hangs on Windows | Defender / antivirus scanning. Add a folder exclusion for `goldsmith_erp\docs\architecture\likec4\node_modules`. |
| Dev server says "address in use" | Port 5173 is taken (often by Vite from the main frontend). `npx likec4 start src --port 5174`. |
| Diagrams render empty in the browser | Validate first: `npm run validate`. Most likely one of the v1.38 quirks above (multi-line description / inline tag) is silently dropping siblings. |
| `npm run export:png` fails with a Playwright stack trace | First-time PNG export needs the headless browser: `npx playwright install chromium`. |
| VSCode extension shows no preview | Reload window (`Ctrl/Cmd+Shift+P` → "Reload Window"). Confirm the workspace folder contains the `.c4` files. |
| Output still has FqnRef warnings I don't understand | The model file documents which v1.38 quirks we hit and how we worked around them. Upgrading to ≥ 1.57 (with Node ≥ 22.22.3) should remove most. |

---

## 9. Reference

- LikeC4 site — https://likec4.dev
- LikeC4 GitHub — https://github.com/likec4/likec4
- LikeC4 VSCode extension — `likec4.likec4-vscode` on the marketplace
- C4 model — https://c4model.com (Simon Brown's reference)
- Structurizr (complement candidate) — https://docs.structurizr.com/local
- The local model in this repo — [`docs/architecture/likec4/src/goldsmith-erp.c4`](../../architecture/likec4/src/goldsmith-erp.c4)
