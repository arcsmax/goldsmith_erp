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

See H2 + H5 in docs/superpowers/plans/qr-barcode-workflow/V1.1-AMENDMENTS.md.
"""
from __future__ import annotations

from datetime import datetime, timedelta

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
    OrderStatusHistory,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    ValuationCertificate,
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


class TestGdprErasureScrubsH5Fields:
    """H5: end-to-end coverage of the 8 additional PII-leak fields.

    Single API call must scrub every H5 surface that the customer has
    data in — valuation certificate, repair job, order-status-history
    note, etc. Proves Art. 17 compliance at the HTTP boundary, not
    just at the service layer.
    """

    @pytest.mark.asyncio
    async def test_single_erase_scrubs_valuation_repair_and_status_history(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_user,
        admin_auth_headers: dict,
    ):
        pii_name = test_customer.first_name
        pii_surname = test_customer.last_name

        # Order + status history (order-scoped H5 surface)
        order = Order(
            title="Trauring",
            description=f"Ring fuer {pii_name} {pii_surname}",
            customer_id=test_customer.id,
            status=OrderStatusEnum.COMPLETED,
            price=0.0,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        history = OrderStatusHistory(
            order_id=order.id,
            from_status="in_progress",
            to_status="completed",
            changed_by=admin_user.id,
            notes=f"Bei Abholung durch {pii_surname} bemerkt",
        )
        db_session.add(history)

        # Valuation certificate (customer-scoped H5 surface)
        valuation = ValuationCertificate(
            certificate_number="WG-2026-H5-01",
            order_id=order.id,
            customer_id=test_customer.id,
            created_by=admin_user.id,
            item_description=f"Wertgutachten fuer {pii_name} {pii_surname}",
            gemstones_description=None,
            appraised_value=1500.0,
            valuation_date=datetime.utcnow(),
            valid_until=datetime.utcnow() + timedelta(days=730),
            goldsmith_name="Integration Test Goldsmith",
        )
        db_session.add(valuation)

        # Repair job (customer-scoped H5 surface, no order link needed)
        repair = RepairJob(
            repair_number="REP-2026-H5-01",
            bag_number="H5-BAG-01",
            customer_id=test_customer.id,
            received_by=admin_user.id,
            item_description=f"Ring von {pii_name} {pii_surname}",
            item_type=RepairItemType.RING,
            status=RepairJobStatus.RECEIVED,
            diagnosis_notes=f"{pii_surname} wuenscht Politur",
        )
        db_session.add(repair)

        await db_session.commit()
        await db_session.refresh(history)
        await db_session.refresh(valuation)
        await db_session.refresh(repair)

        history_id = history.id
        valuation_id = valuation.id
        repair_id = repair.id

        # Act — single API call
        response = await client.delete(
            f"/api/v1/customers/{test_customer.id}/gdpr-erase",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert "pii_redactions" in body
        counts = body["pii_redactions"]

        # Counts must reflect redactions in every H5 surface we populated
        assert counts["order_status_history.notes"] >= 1
        assert counts["valuation_certificates.item_description"] >= 2
        assert counts["repair_jobs.item_description"] >= 2
        assert counts["repair_jobs.diagnosis_notes"] >= 1

        # DB state — every H5 field must have the PII replaced
        scrubbed_history = (
            await db_session.execute(
                select(OrderStatusHistory).filter(
                    OrderStatusHistory.id == history_id
                )
            )
        ).scalar_one()
        assert pii_surname not in scrubbed_history.notes
        assert "[REDACTED]" in scrubbed_history.notes

        scrubbed_valuation = (
            await db_session.execute(
                select(ValuationCertificate).filter(
                    ValuationCertificate.id == valuation_id
                )
            )
        ).scalar_one()
        assert pii_name not in scrubbed_valuation.item_description
        assert pii_surname not in scrubbed_valuation.item_description
        assert "[REDACTED]" in scrubbed_valuation.item_description

        scrubbed_repair = (
            await db_session.execute(
                select(RepairJob).filter(RepairJob.id == repair_id)
            )
        ).scalar_one()
        assert pii_name not in scrubbed_repair.item_description
        assert pii_surname not in scrubbed_repair.item_description
        assert pii_surname not in scrubbed_repair.diagnosis_notes
        assert "[REDACTED]" in scrubbed_repair.item_description
        assert "[REDACTED]" in scrubbed_repair.diagnosis_notes

        # Audit log records the H5 counts
        audit = (
            await db_session.execute(
                select(CustomerAuditLog).filter(
                    CustomerAuditLog.customer_id == test_customer.id,
                    CustomerAuditLog.action == "gdpr_pii_scrub",
                )
            )
        ).scalar_one()
        assert audit.details["counts"]["repair_jobs.item_description"] >= 2
        assert audit.details["counts"]["valuation_certificates.item_description"] >= 2
