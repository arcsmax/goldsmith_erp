"""
Integration tests for GDPR Art. 17 customer erasure — end-to-end through the API.

Companion to `tests/unit/test_gdpr_customer_erasure.py`, which covers the
scrubber in isolation. These tests exercise the full HTTP path:
  DELETE /api/v1/customers/{id}/gdpr-erase

and assert that after a single request:
  - Customer.deletion_scheduled_at is set
  - Customer.is_active is False
  - orders.description / orders.special_instructions are scrubbed
  - order_comments.text is scrubbed
  - customer_audit_logs gains a `gdpr_pii_scrub` row
  - gdpr_requests gains an `erasure` row (H3 progress)
  - The response body reports the redaction counts

See H2 in docs/superpowers/plans/qr-barcode-workflow/V1.1-AMENDMENTS.md.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    CustomerAuditLog,
    GDPRRequest,
    Order,
    OrderComment,
    OrderStatusEnum,
)


def _erase_url(customer_id: int) -> str:
    return f"/api/v1/customers/{customer_id}/gdpr-erase"


class TestGdprErasureScrubsPii:

    @pytest.mark.asyncio
    async def test_erasure_scrubs_order_description_end_to_end(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        """Full happy path: order description scrubbed + response reports counts."""
        # Arrange: test_customer is 'Maria Mustermann' from conftest.
        order = Order(
            title="Trauringe",
            description=(
                f"Trauring fuer {test_customer.first_name} {test_customer.last_name}"
            ),
            special_instructions=(
                f"Anruf unter {test_customer.phone} vor Abholung"
            ),
            customer_id=test_customer.id,
            status=OrderStatusEnum.IN_PROGRESS,
            price=1200.00,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)
        order_id = order.id

        # Act
        response = await client.delete(
            _erase_url(test_customer.id),
            headers=admin_auth_headers,
        )

        # Assert — response shape
        assert response.status_code == 200
        body = response.json()
        assert body["customer_id"] == test_customer.id
        assert "pii_redactions" in body
        assert body["pii_redactions"]["total"] >= 3  # 2 name tokens + 1 phone

        # Assert — DB state: customer is scheduled for deletion
        customer_result = await db_session.execute(
            select(Customer).filter(Customer.id == test_customer.id)
        )
        customer = customer_result.scalar_one()
        assert customer.is_active is False
        assert customer.deletion_scheduled_at is not None

        # Assert — DB state: order description is scrubbed
        order_result = await db_session.execute(
            select(Order).filter(Order.id == order_id)
        )
        scrubbed_order = order_result.scalar_one()
        assert test_customer.first_name not in scrubbed_order.description
        assert test_customer.last_name not in scrubbed_order.description
        assert "[REDACTED]" in scrubbed_order.description

        # Assert — DB state: special_instructions phone scrubbed
        assert test_customer.phone not in scrubbed_order.special_instructions
        assert "[REDACTED]" in scrubbed_order.special_instructions

    @pytest.mark.asyncio
    async def test_erasure_scrubs_order_comments(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_user,
        admin_auth_headers: dict,
    ):
        order = Order(
            title="Repair",
            description="Ring groesser machen",
            customer_id=test_customer.id,
            status=OrderStatusEnum.NEW,
            price=0.0,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        comment = OrderComment(
            order_id=order.id,
            user_id=admin_user.id,
            text=(
                f"{test_customer.first_name} {test_customer.last_name} "
                "hat heute angerufen wegen Anprobe."
            ),
        )
        db_session.add(comment)
        await db_session.commit()
        await db_session.refresh(comment)
        comment_id = comment.id

        response = await client.delete(
            _erase_url(test_customer.id),
            headers=admin_auth_headers,
        )
        assert response.status_code == 200

        scrubbed_result = await db_session.execute(
            select(OrderComment).filter(OrderComment.id == comment_id)
        )
        scrubbed = scrubbed_result.scalar_one()
        assert test_customer.first_name not in scrubbed.text
        assert test_customer.last_name not in scrubbed.text
        assert "[REDACTED]" in scrubbed.text

    @pytest.mark.asyncio
    async def test_erasure_writes_pii_scrub_audit_log(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_user,
        admin_auth_headers: dict,
    ):
        """customer_audit_logs must gain a gdpr_pii_scrub entry."""
        order = Order(
            title="Ring",
            description=f"Ring fuer {test_customer.first_name} {test_customer.last_name}",
            customer_id=test_customer.id,
            status=OrderStatusEnum.NEW,
            price=0.0,
        )
        db_session.add(order)
        await db_session.commit()

        response = await client.delete(
            _erase_url(test_customer.id),
            headers=admin_auth_headers,
        )
        assert response.status_code == 200

        audit_result = await db_session.execute(
            select(CustomerAuditLog).filter(
                CustomerAuditLog.customer_id == test_customer.id,
                CustomerAuditLog.action == "gdpr_pii_scrub",
            )
        )
        audit_rows = audit_result.scalars().all()
        assert len(audit_rows) == 1
        assert audit_rows[0].user_id == admin_user.id
        assert audit_rows[0].details["counts"]["total"] >= 2

    @pytest.mark.asyncio
    async def test_erasure_writes_gdpr_request_row(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        """H3 progress: gdpr_requests table must be written to."""
        response = await client.delete(
            _erase_url(test_customer.id),
            headers=admin_auth_headers,
        )
        assert response.status_code == 200

        request_result = await db_session.execute(
            select(GDPRRequest).filter(GDPRRequest.customer_id == test_customer.id)
        )
        row = request_result.scalar_one()
        assert row.request_type == "erasure"
        assert row.status == "completed"

    @pytest.mark.asyncio
    async def test_erasure_is_idempotent_via_duplicate_request(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        """Second erasure returns 409 — the customer row cannot be double-erased.

        This also pins the invariant that the scrubber does not produce
        a second round of redactions.
        """
        order = Order(
            title="Ring",
            description=(
                f"Ring fuer {test_customer.first_name} {test_customer.last_name}"
            ),
            customer_id=test_customer.id,
            status=OrderStatusEnum.NEW,
            price=0.0,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)
        order_id = order.id

        first = await client.delete(
            _erase_url(test_customer.id), headers=admin_auth_headers,
        )
        assert first.status_code == 200

        first_result = await db_session.execute(
            select(Order).filter(Order.id == order_id)
        )
        description_after_first = first_result.scalar_one().description

        second = await client.delete(
            _erase_url(test_customer.id), headers=admin_auth_headers,
        )
        assert second.status_code == 409

        # Order description must not have been re-scrubbed.
        second_result = await db_session.execute(
            select(Order).filter(Order.id == order_id)
        )
        assert second_result.scalar_one().description == description_after_first
