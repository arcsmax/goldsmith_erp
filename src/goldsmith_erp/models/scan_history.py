"""Read schemas for the scan history of a piece (2026-09 audit, SC-02/SC-03).

Every scan of a job bag writes a ``scan_logs`` row (``action_taken``
``scan_only`` / ``unrecognised``), and every action picked afterwards a
second row that points back via ``context.parent_scan_id``. These schemas
project those rows for the "Scan-Verlauf" views.

Projection rules (CLAUDE.md privacy rules):

  * Only who (user name), when, where (bench / location label), what
    (action + result) and how (input source). No financial fields, no
    customer data, no entity payload — the rows only carry ids.
  * ``raw_payload`` / ``resolved_*`` are exposed on the cross-piece search
    (ADMIN/GOLDSMITH) only, where the reader needs to know which piece a
    row is about.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class LastScanRead(BaseModel):
    """Last scan of a piece ("Zuletzt gescannt von … um … in …")."""

    model_config = ConfigDict(extra="forbid")

    scanned_at: datetime
    user_id: int
    user_name: str
    location: Optional[str] = None
    action_taken: Optional[str] = None


class PieceScanRead(BaseModel):
    """One row of the per-piece Scan-Verlauf (VIEWER allowed)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    scanned_at: datetime
    user_id: int
    user_name: str
    location: Optional[str] = None
    action_taken: Optional[str] = None
    action_result: Optional[str] = None
    input_source: Optional[str] = None
    parent_scan_id: Optional[str] = None


class ScanHistoryRow(PieceScanRead):
    """One row of the cross-piece admin search (ADMIN/GOLDSMITH)."""

    raw_payload: str
    resolved_type: Optional[str] = None
    resolved_id: Optional[str] = None
    resolution_path: Optional[str] = None
    device_id: Optional[str] = None


class PieceScanPage(BaseModel):
    """Paged per-piece history, newest first."""

    model_config = ConfigDict(extra="forbid")

    items: List[PieceScanRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    next_offset: Optional[int] = None


class ScanHistoryPage(BaseModel):
    """Paged cross-piece search result, newest first."""

    model_config = ConfigDict(extra="forbid")

    items: List[ScanHistoryRow]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    next_offset: Optional[int] = None
