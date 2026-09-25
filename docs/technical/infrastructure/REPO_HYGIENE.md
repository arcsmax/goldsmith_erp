# Repository hygiene: stale worktrees and branches (OPS-14)

The 2026-09-25 audit branch (`audit/2026-09-fixes`) was built by many parallel
agents, each in its own `git worktree` under `.claude/worktrees/`. Once an
agent's branch merges into the integration branch, its worktree and branch
are leftover state — disk usage and clutter, not a functional risk, but worth
a periodic pass. This document is that pass's procedure, not a one-off fix:
`git worktree remove` and `git branch -d` are **never run automatically** by
any script here, and never by an agent from inside one of the worktrees under
review — deleting a sibling worktree's checkout from another worktree risks
destroying another session's in-flight work.

## Check what is stale

```bash
make worktree-status
# or directly:
bash scripts/list-stale-worktrees.sh
```

This is read-only. For every worktree other than the one you are running it
from, it reports whether the worktree's branch tip is already an ancestor of
`main` and of `audit/2026-09-fixes`, and gives a verdict:

- **MERGED** — the branch's work already landed on `main` or the integration
  branch. Safe to remove *after* an independent clean-status check (below).
- **ACTIVE** — unmerged work. Do not remove without confirming with whoever
  is running that agent/session.
- **branch gone** — the worktree's branch no longer exists (already deleted
  or force-pushed over elsewhere). The worktree itself is orphaned.

## Remove a confirmed-stale worktree

Only after `list-stale-worktrees.sh` says `MERGED` or `branch gone` **and**
you have independently confirmed there is no uncommitted work in it:

```bash
git -C <path> status --short          # must be empty
git -C <path> log --oneline main..HEAD  # must be empty (or already merged)
git worktree remove <path>
git branch -d <branch>                # only after the worktree is gone
```

Never `git worktree remove --force` or `git branch -D` on a worktree/branch
you have not personally verified — that is exactly the kind of "quick fix"
that destroys another session's work. If in doubt, leave it and ask.

## `alembic_backup/`

A single tracked file, `alembic_backup/env.py`, sits at the repo root with no
documented purpose: not referenced by `Makefile`, `alembic.ini`, or any doc
found in the 2026-09-25 audit pass. `scripts/list-stale-worktrees.sh` prints
its last-touched commit as a starting point for review. Because it is a
tracked file (not a build artifact), removing it is a deliberate `git rm`
decision for whoever owns the alembic setup, made after reading its history
(`git log -p -- alembic_backup/`) — not something this pass does
automatically.

## See also

- [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) — production
  deployment, upgrade and rollback (a different kind of "hygiene": running
  containers, not dev worktrees).
