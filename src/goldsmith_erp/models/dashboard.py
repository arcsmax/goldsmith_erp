# src/goldsmith_erp/models/dashboard.py
"""Response schemas for ``GET /dashboard/today`` (the "Heute" view, W2-03).

Findings FE-05, DOM-14, DOM-15, DOM-15b (docs/review/2026-09-25/).

The payload is deliberately small (minimum-data principle): ids, a display
title, the customer's display name, dates and status. No design text
(order description, update bodies) is returned. The only financial field is
``PendingItem.amount``; the router strips it for callers without
``Permission.FINANCIAL_VIEW`` (SEC-01 / GDPR-03).
"""

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

WorkItemKind = Literal["order", "repair"]
PendingKind = Literal[
    "cost_change", "customer_update", "repair_ready", "order_ready", "quote"
]


class WorkItem(BaseModel):
    """An order or repair with a due date (overdue and due-soon lanes)."""

    kind: WorkItemKind
    id: int
    reference: str = Field(description="Auftrag #id or REP number")
    title: str
    status: str
    due_date: date
    days_overdue: int = Field(
        description="Positive: days past due. Zero: due today. Negative: days left."
    )
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    bag_number: Optional[str] = None
    job_id: Optional[int] = Field(
        default=None, description="Job spine id (GET /jobs/{id}); ARCH phase 5"
    )


class PendingItem(BaseModel):
    """Something waiting on the customer, or on a retry towards them."""

    kind: PendingKind
    id: int
    title: str
    reference: str
    since: datetime = Field(description="When the item started waiting (UTC)")
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    order_id: Optional[int] = None
    repair_id: Optional[int] = None
    quote_id: Optional[int] = None
    job_id: Optional[int] = None
    bag_number: Optional[str] = None
    valid_until: Optional[date] = None
    # Financial: cost change new amount / quote total. Stripped for VIEWER.
    amount: Optional[float] = None


class TimerItem(BaseModel):
    """A time entry started today or still running."""

    id: str
    order_id: int
    order_title: Optional[str] = None
    user_id: int
    user_name: Optional[str] = None
    activity_name: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    is_running: bool


class LaneCounts(BaseModel):
    overdue: int
    due_soon: int
    customer_pending: int
    timers: int


class DashboardToday(BaseModel):
    """Everything the start-of-day view needs, in one response."""

    today: date
    generated_at: datetime
    can_view_financials: bool
    truncated: bool = Field(
        description="True when a lane hit the safety cap and is incomplete"
    )
    overdue: List[WorkItem]
    due_soon: List[WorkItem]
    customer_pending: List[PendingItem]
    timers: List[TimerItem]
    counts: LaneCounts
