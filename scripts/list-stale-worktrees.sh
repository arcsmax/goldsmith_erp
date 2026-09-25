#!/usr/bin/env bash
# scripts/list-stale-worktrees.sh
#
# Read-only report of `git worktree list` cross-referenced against `main` and
# `audit/2026-09-fixes`, to make OPS-14 ("7 stale worktrees under
# .claude/worktrees/, one stray alembic_backup/ directory") an ongoing,
# repeatable check instead of a one-off manual pass.
#
# This script NEVER deletes, removes or modifies anything — it only reports.
# Removal is always a human decision, made from this repo's own worktree,
# never by an agent operating inside one of the worktrees under review (a
# worktree cannot safely judge whether siblings are still in use).
#
# Usage:
#   bash scripts/list-stale-worktrees.sh
#
# For each worktree (other than the current one), prints:
#   - path, branch, HEAD commit
#   - whether the branch tip is already merged into main
#   - whether it is already merged into audit/2026-09-fixes (if that ref exists)
#   - a verdict: MERGED (safe to remove after a diff check) or ACTIVE (unmerged
#     work — do not remove without confirming with whoever owns it)
#
# To actually remove a MERGED worktree, after independently confirming there
# is no uncommitted work in it:
#   git -C <path> status --short          # confirm clean
#   git worktree remove <path>
#   git branch -d <branch>                # only after the worktree is gone
#
# Exit codes: 0 always (this is a report, not a gate).

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

INTEGRATION_REF="audit/2026-09-fixes"
HAS_INTEGRATION_REF=0
if git rev-parse --verify --quiet "${INTEGRATION_REF}" >/dev/null; then
  HAS_INTEGRATION_REF=1
fi

CURRENT_WORKTREE="$(git rev-parse --show-toplevel)"

printf '%-70s %-45s %-8s %-8s %s\n' "PATH" "BRANCH" "IN-MAIN" "IN-${INTEGRATION_REF}" "VERDICT"

git worktree list --porcelain | awk '
  /^worktree / { path=$2 }
  /^branch /   { branch=$2; print path"\t"branch }
  /^detached/  { print path"\t(detached)" }
' | while IFS=$'\t' read -r wt_path wt_branch; do
  [ "${wt_path}" = "${CURRENT_WORKTREE}" ] && continue

  branch_name="${wt_branch#refs/heads/}"

  in_main="?"
  in_integration="-"
  verdict="REVIEW"

  if [ "${wt_branch}" = "(detached)" ]; then
    in_main="n/a"
    verdict="DETACHED — check manually"
  elif git rev-parse --verify --quiet "${wt_branch}" >/dev/null; then
    if git merge-base --is-ancestor "${wt_branch}" main 2>/dev/null; then
      in_main="yes"
    else
      in_main="no"
    fi
    if [ "${HAS_INTEGRATION_REF}" = "1" ]; then
      if git merge-base --is-ancestor "${wt_branch}" "${INTEGRATION_REF}" 2>/dev/null; then
        in_integration="yes"
      else
        in_integration="no"
      fi
    fi

    if [ "${in_main}" = "yes" ] || [ "${in_integration}" = "yes" ]; then
      verdict="MERGED — safe to remove after a clean-status check"
    else
      verdict="ACTIVE — unmerged, confirm with owner before removing"
    fi
  else
    verdict="branch gone — worktree is orphaned, safe to remove"
  fi

  printf '%-70s %-45s %-8s %-8s %s\n' "${wt_path}" "${branch_name}" "${in_main}" "${in_integration}" "${verdict}"
done

echo
echo "alembic_backup/ (tracked, single stray env.py, purpose undocumented):"
if [ -d alembic_backup ]; then
  git log -1 --format='  last touched %ad by %an: %s' -- alembic_backup/ 2>/dev/null || true
  echo "  Not referenced by any Makefile target, alembic.ini, or doc found in the"
  echo "  2026-09-25 audit. Review before removing (git log -p -- alembic_backup/)"
  echo "  — this script does not remove it."
else
  echo "  Not present (already cleaned up)."
fi
