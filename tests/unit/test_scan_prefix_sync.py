"""SC-06: the frontend scan prefix list must equal the backend's.

The client canonicalises scanned payloads with ``KNOWN_SCAN_PREFIXES`` in
``frontend/src/lib/scanPayload.ts``; the server resolves them with
``KNOWN_PREFIXES_V1_1``. A silent drift would misroute or mis-log scans, so
this test reads the TypeScript literal and compares the two sets.
"""

import re
from pathlib import Path

from goldsmith_erp.services.scanner_service import KNOWN_PREFIXES_V1_1

SCAN_PAYLOAD_TS = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "scanPayload.ts"
)


def _frontend_prefixes() -> set[str]:
    source = SCAN_PAYLOAD_TS.read_text(encoding="utf-8")
    block = re.search(r"KNOWN_SCAN_PREFIXES = \[(.*?)\] as const", source, re.S)
    assert block is not None, "KNOWN_SCAN_PREFIXES literal not found"
    return set(re.findall(r"'([A-Z]+)'", block.group(1)))


def test_frontend_and_backend_prefix_sets_are_equal() -> None:
    assert _frontend_prefixes() == set(KNOWN_PREFIXES_V1_1)
