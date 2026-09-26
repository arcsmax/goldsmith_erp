"""API schemas for the job spine (ARCH phase 5, ``GET /jobs``)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from goldsmith_erp.db.models import JobKind, JobStatus
from goldsmith_erp.models._common import Money
from goldsmith_erp.models.order import OrderTimelineItem


class JobCustomer(BaseModel):
    """Customer summary on a job row (name only; no contact data)."""

    id: int
    display_name: str


class JobListItem(BaseModel):
    """One order or repair on the job spine (kanban card)."""

    id: int
    kind: JobKind
    number: str = Field(description="AU-YYYY-NNNN (Auftrag) or REP-YYYY-NNNN")
    title: Optional[str] = None
    status: JobStatus = Field(description="Unified lifecycle")
    status_label: str
    kind_status: str = Field(description="Raw order / repair status")
    deadline: Optional[datetime] = None
    on_hold_since: Optional[datetime] = None
    resume_date: Optional[date] = None
    customer_id: Optional[int] = None
    customer: Optional[JobCustomer] = None
    order_id: Optional[int] = None
    repair_id: Optional[int] = None
    # Financial (FINANCIAL_VIEW only): order.price (net) or the repair's
    # actual / estimated cost. Stripped for VIEWER by the router.
    agreed_price: Optional[Money] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobTimelineRead(BaseModel):
    """Merged history of one job (delegates to the per-kind timeline)."""

    job_id: int
    kind: JobKind
    order_id: Optional[int] = None
    repair_id: Optional[int] = None
    items: List[OrderTimelineItem]


def _customer_summary(customer: Any) -> Optional[JobCustomer]:
    if customer is None:
        return None
    parts = [customer.first_name, customer.last_name]
    name = " ".join(p for p in parts if p) or customer.company_name or ""
    return JobCustomer(id=customer.id, display_name=name or f"Kunde #{customer.id}")


def job_list_item(job: Any, status_label: str) -> JobListItem:
    """Build the list item from a Job row with customer/order/repair loaded."""
    order, repair = job.order, job.repair
    price: Any = None
    if order is not None:
        price = order.price
    elif repair is not None:
        price = (
            repair.actual_cost
            if repair.actual_cost is not None
            else repair.estimated_cost
        )
    return JobListItem(
        id=job.id,
        kind=JobKind(job.kind),
        number=job.number,
        title=job.title,
        status=JobStatus(job.status),
        status_label=status_label,
        kind_status=job.kind_status,
        deadline=job.deadline,
        on_hold_since=job.on_hold_since,
        resume_date=job.resume_date,
        customer_id=job.customer_id,
        customer=_customer_summary(job.customer),
        order_id=order.id if order is not None else None,
        repair_id=repair.id if repair is not None else None,
        agreed_price=price,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
