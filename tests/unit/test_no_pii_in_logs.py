"""Application log statements must never interpolate raw PII (GDPR-10).

CLAUDE.md: "NEVER log customer PII in plaintext — use anonymized IDs in log
messages." The request-path/query-string leak (customer search terms,
portal tokens landing in the access log via `str(request.url)`) is SEC-05 /
GDPR-10's original finding and is covered separately by
`test_request_logging_no_query.py`, which fixed `middleware/logging.py` to
log `request.url.path` only.

This test targets the broader GDPR-10 ask: *application* log statements
written throughout services/routers must not pass an e-mail, name, phone
number or address straight to `logger.*` as a regression guard, so a future
change cannot quietly reintroduce a PII leak into the logs without a test
failure. It scans every `logger.<level>(...)` call in the source tree for a
known set of PII-bearing attribute/variable name fragments.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "goldsmith_erp"

_LOGGER_CALL_RE = re.compile(
    r"logger\.(?:debug|info|warning|warn|error|critical|exception)\s*\("
)

# Attribute/local-variable name fragments that indicate raw PII is being
# passed to a logger call. Word-boundary-anchored so e.g. "customer_id" (a
# safe numeric FK, logged everywhere) never matches "customer_email".
_FORBIDDEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\.email\b"),
    re.compile(r"\.phone\b"),
    re.compile(r"\.address\b"),
    re.compile(r"\.first_name\b"),
    re.compile(r"\.last_name\b"),
    re.compile(r"\bcustomer_email\b"),
    re.compile(r"\bcustomer_name\b"),
    re.compile(r"\buser_email\b"),
]


def _find_logger_calls(text: str) -> list[str]:
    """Return the full source text of every balanced `logger.<level>(...)` call.

    Walks forward from each match's opening "(" counting paren depth
    (skipping parens inside string literals) until it returns to zero, so
    a call's own arguments are isolated from unrelated code that follows it
    in the file.
    """
    calls: list[str] = []
    for match in _LOGGER_CALL_RE.finditer(text):
        start = match.end() - 1  # index of the opening "("
        depth = 0
        in_str: str | None = None
        end = None
        i = start
        while i < len(text):
            ch = text[i]
            if in_str:
                if ch == "\\":
                    i += 1  # skip the escaped character too
                elif ch == in_str:
                    in_str = None
            elif ch in ("'", '"'):
                in_str = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
            i += 1
        if end is not None:
            calls.append(text[match.start() : end + 1])
    return calls


def test_no_logger_call_interpolates_raw_pii():
    violations = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for call in _find_logger_calls(text):
            for pattern in _FORBIDDEN_PATTERNS:
                if pattern.search(call):
                    violations.append(f"{path}: {' '.join(call.split())[:160]}")
                    break

    assert not violations, (
        "Found logger calls that appear to interpolate raw PII "
        "(email/name/phone/address) directly instead of an anonymized id "
        "(CLAUDE.md, GDPR-10):\n" + "\n".join(violations)
    )
