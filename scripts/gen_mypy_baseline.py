#!/usr/bin/env python3
"""Regenerate the per-module mypy baseline from the current mypy output.

The CI ``lint`` job runs mypy in ``--strict`` mode over ``goldsmith_erp/`` and
has ~1.5k pre-existing errors. Rather than blanket-suppress with
``ignore_errors``, we record, *per module*, the exact set of error codes that
module currently emits as ``[[tool.mypy.overrides]]`` blocks with
``disable_error_code``. Effect:

  * Modules that currently pass stay fully strict.
  * A baselined module is only excused for the specific codes it already
    trips; a *new* code (e.g. someone introduces a ``[return-value]`` bug in a
    module that was only baselined for ``[assignment]``) still fails CI.
  * New modules get full strict checking by default.

This is a debt ledger, not a waiver. When you touch a baselined module, try to
clear its errors and delete its block (see docs/technical/MYPY_BURNDOWN.md).

Usage (from repo root, deps installed via ``poetry install``)::

    poetry run python scripts/gen_mypy_baseline.py            # rewrite pyproject + table
    poetry run python scripts/gen_mypy_baseline.py --check    # fail if pyproject is stale

It rewrites the region between the BEGIN/END markers in the root
``[tool.mypy]`` section of ``pyproject.toml`` and refreshes the debt table in
``docs/technical/MYPY_BURNDOWN.md`` (between its own markers).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
PYPROJECT = REPO_ROOT / "pyproject.toml"
BURNDOWN_DOC = REPO_ROOT / "docs" / "technical" / "MYPY_BURNDOWN.md"

# Must match the mypy invocation in .github/workflows/ci.yml (`lint` job).
MYPY_CMD = ["mypy", "goldsmith_erp/", "--ignore-missing-imports"]

PYPROJECT_BEGIN = (
    "# --- BEGIN generated mypy baseline (scripts/gen_mypy_baseline.py) ---"
)
PYPROJECT_END = "# --- END generated mypy baseline ---"
DOC_BEGIN = "<!-- BEGIN generated mypy baseline table -->"
DOC_END = "<!-- END generated mypy baseline table -->"

ERROR_RE = re.compile(r"^(goldsmith_erp/[^:]+\.py):\d+: error: .*?\[([a-z-]+)\]\s*$")


def run_mypy() -> str:
    """Run mypy exactly as CI does and return combined stdout+stderr."""
    proc = subprocess.run(
        ["poetry", "run", *MYPY_CMD],
        cwd=SRC_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout + proc.stderr


def parse(output: str) -> dict[str, Counter[str]]:
    """Map dotted module -> Counter(error_code -> count)."""
    per_module: dict[str, Counter[str]] = defaultdict(Counter)
    for line in output.splitlines():
        m = ERROR_RE.match(line)
        if not m:
            continue
        rel_path, code = m.group(1), m.group(2)
        module = rel_path[: -len(".py")].replace("/", ".")
        per_module[module][code] += 1
    return per_module


def render_pyproject_blocks(per_module: dict[str, Counter[str]]) -> str:
    lines = [PYPROJECT_BEGIN]
    lines.append("# Generated debt ledger — do not hand-edit. Regenerate with:")
    lines.append("#   poetry run python scripts/gen_mypy_baseline.py")
    total_errors = sum(sum(c.values()) for c in per_module.values())
    lines.append(
        f"# {len(per_module)} modules, {total_errors} suppressed errors as of last run."
    )
    for module in sorted(per_module):
        codes = sorted(per_module[module])
        count = sum(per_module[module].values())
        code_list = ", ".join(f'"{c}"' for c in codes)
        lines.append("[[tool.mypy.overrides]]")
        lines.append(f'module = "{module}"')
        lines.append(f"disable_error_code = [{code_list}]  # {count} error(s)")
    lines.append(PYPROJECT_END)
    return "\n".join(lines)


def render_doc_table(per_module: dict[str, Counter[str]]) -> str:
    rows = []
    for module in sorted(per_module, key=lambda m: (-sum(per_module[m].values()), m)):
        counter = per_module[module]
        count = sum(counter.values())
        codes = ", ".join(f"`{c}`×{n}" for c, n in counter.most_common())
        rows.append(f"| `{module}` | {count} | {codes} |")
    total_errors = sum(sum(c.values()) for c in per_module.values())
    header = [
        DOC_BEGIN,
        f"_Auto-generated: {len(per_module)} modules, {total_errors} suppressed "
        "errors. Regenerate with `poetry run python scripts/gen_mypy_baseline.py`._",
        "",
        "| Module | Errors | Codes suppressed |",
        "| --- | ---: | --- |",
    ]
    return "\n".join(header + rows + [DOC_END])


def replace_region(text: str, begin: str, end: str, payload: str) -> str:
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(text):
        raise SystemExit(f"Markers not found: {begin!r} .. {end!r}. Add them first.")
    return pattern.sub(lambda _: payload, text)


def write_pyproject(per_module: dict[str, Counter[str]]) -> None:
    blocks = render_pyproject_blocks(per_module)
    text = PYPROJECT.read_text()
    PYPROJECT.write_text(replace_region(text, PYPROJECT_BEGIN, PYPROJECT_END, blocks))


def merge(acc: dict[str, Counter[str]], new: dict[str, Counter[str]]) -> None:
    for module, counter in new.items():
        acc[module].update(counter)


def compute_baseline(max_passes: int = 6) -> dict[str, Counter[str]]:
    """Iterate to a fixpoint.

    Disabling an error code wholesale for a module can turn a previously-used
    inline ``# type: ignore[code]`` in that module into an ``unused-ignore``
    error that wasn't in the first pass. We start from an empty baseline, then
    re-run mypy with the accumulated baseline applied and fold in any residual
    codes until mypy is clean (usually 2 passes).
    """
    acc: dict[str, Counter[str]] = defaultdict(Counter)
    # Start from a clean slate so pass 1 sees the true, unsuppressed error set.
    write_pyproject(acc)
    for _ in range(max_passes):
        new = parse(run_mypy())
        if not new:
            return acc
        merge(acc, new)
        write_pyproject(acc)
    raise SystemExit(
        "mypy baseline did not converge; inspect residual errors manually."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if pyproject.toml would change (CI drift guard).",
    )
    args = ap.parse_args()

    if args.check:
        # Non-destructive: current pyproject must already make mypy clean.
        residual = parse(run_mypy())
        if residual:
            print(
                "mypy baseline is STALE — these modules/codes are not "
                "covered:\n  "
                + "\n  ".join(f"{m}: {sorted(c)}" for m, c in sorted(residual.items()))
                + "\nRegenerate with:\n"
                "  poetry run python scripts/gen_mypy_baseline.py",
                file=sys.stderr,
            )
            return 1
        print("mypy baseline is up to date (mypy is clean).")
        return 0

    per_module = compute_baseline()

    if BURNDOWN_DOC.exists():
        doc = BURNDOWN_DOC.read_text()
        doc = replace_region(doc, DOC_BEGIN, DOC_END, render_doc_table(per_module))
        BURNDOWN_DOC.write_text(doc)

    total_errors = sum(sum(c.values()) for c in per_module.values())
    print(
        f"Wrote baseline: {len(per_module)} modules, "
        f"{total_errors} suppressed errors."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
