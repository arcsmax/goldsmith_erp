"""
Unit tests for estimate_accuracy_service (V1.3 estimator, Phase 1, Task 4).

Covers:
- record() persists an EstimateAccuracy row with the exact supplied values.
- calibration() computes MAPE correctly on a hand-verified set of rows.
- calibration() computes per-order-type mean signed bias.
- calibration() excludes actual_hours == 0 rows from MAPE (no
  ZeroDivisionError) while still including them in bias.
- calibration() over empty history returns a sane zero/None result, no crash.
- calibration(order_type=...) scopes both MAPE and bias to that type.
- safe_record_on_completion() is a no-op (no row written, no error) when no
  estimate values are supplied — the current, documented state until V1.3
  Task 5 wires real stored-estimate values through.
- safe_record_on_completion() writes a row when full values ARE supplied
  (forward-compatibility check for Task 5's future call site) and never
  raises even if the underlying write fails.
"""

from __future__ import annotations

from unittest import mock

import pytest

import goldsmith_erp.services.estimate_accuracy_service as estimate_accuracy_service
from goldsmith_erp.db.models import EstimateAccuracy, Order, OrderStatusEnum
from goldsmith_erp.services.estimate_accuracy_service import (
    UNKNOWN_ORDER_TYPE,
    CalibrationResult,
    calibration,
    record,
    safe_record_on_completion,
)


def _make_order(customer_id: int, **overrides) -> Order:
    defaults = dict(
        title="Test Order",
        customer_id=customer_id,
        status=OrderStatusEnum.COMPLETED,
        order_type="ring",
    )
    defaults.update(overrides)
    return Order(**defaults)


async def _make_completed_order(db_session, customer_id: int, **overrides) -> Order:
    order = _make_order(customer_id, **overrides)
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


# ---------------------------------------------------------------------------
# record()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRecord:
    async def test_writes_row_with_supplied_values(self, db_session, sample_customer):
        order = await _make_completed_order(db_session, sample_customer.id)

        accuracy = await record(
            db_session,
            order,
            estimated_hours=10.0,
            actual_hours=8.5,
            estimated_total=500.0,
            actual_total=450.0,
            estimator_version="labor_estimator_v1",
        )

        assert accuracy.id is not None
        assert accuracy.order_id == order.id
        assert accuracy.estimated_hours == 10.0
        assert accuracy.actual_hours == 8.5
        assert accuracy.estimated_total == 500.0
        assert accuracy.actual_total == 450.0
        assert accuracy.estimator_version == "labor_estimator_v1"
        assert accuracy.created_at is not None

        # Row is actually durable — reload from a fresh query, not just the
        # in-memory object handed back by record().
        reloaded = await db_session.get(EstimateAccuracy, accuracy.id)
        assert reloaded is not None
        assert reloaded.order_id == order.id
        assert reloaded.actual_hours == 8.5


# ---------------------------------------------------------------------------
# calibration()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCalibration:
    async def test_empty_history_returns_zero_result_without_crash(self, db_session):
        result = await calibration(db_session)

        assert isinstance(result, CalibrationResult)
        assert result.rows_loaded == 0
        assert result.rows_considered_for_mape == 0
        assert result.rows_excluded_zero_actual == 0
        assert result.mape is None
        assert result.bias_by_order_type == {}

    async def test_mape_and_bias_hand_verified(self, db_session, sample_customer):
        """
        Hand-verified numbers:

        ring:  estimated=10, actual=8   -> |8-10|/8   = 0.25   ; signed = +2
        chain: estimated=5,  actual=5   -> |5-5|/5    = 0.0    ; signed =  0
        ring:  estimated=20, actual=25  -> |25-20|/25 = 0.2    ; signed = -5
        chain: estimated=3,  actual=0   -> EXCLUDED from MAPE  ; signed = +3

        MAPE = (0.25 + 0.0 + 0.2) / 3 = 0.15
        bias[ring]  = mean([+2, -5]) = -1.5
        bias[chain] = mean([0, +3])  =  1.5
        """
        order_ring_1 = await _make_completed_order(
            db_session, sample_customer.id, order_type="ring"
        )
        order_chain_1 = await _make_completed_order(
            db_session, sample_customer.id, order_type="chain"
        )
        order_ring_2 = await _make_completed_order(
            db_session, sample_customer.id, order_type="ring"
        )
        order_chain_2 = await _make_completed_order(
            db_session, sample_customer.id, order_type="chain"
        )

        await record(
            db_session,
            order_ring_1,
            estimated_hours=10.0,
            actual_hours=8.0,
            estimated_total=100.0,
            actual_total=80.0,
            estimator_version="v1",
        )
        await record(
            db_session,
            order_chain_1,
            estimated_hours=5.0,
            actual_hours=5.0,
            estimated_total=50.0,
            actual_total=50.0,
            estimator_version="v1",
        )
        await record(
            db_session,
            order_ring_2,
            estimated_hours=20.0,
            actual_hours=25.0,
            estimated_total=200.0,
            actual_total=250.0,
            estimator_version="v1",
        )
        await record(
            db_session,
            order_chain_2,
            estimated_hours=3.0,
            actual_hours=0.0,
            estimated_total=30.0,
            actual_total=0.0,
            estimator_version="v1",
        )

        result = await calibration(db_session)

        assert result.rows_loaded == 4
        assert result.rows_considered_for_mape == 3
        assert result.rows_excluded_zero_actual == 1
        assert result.mape == pytest.approx(0.15)
        assert result.bias_by_order_type == pytest.approx({"ring": -1.5, "chain": 1.5})

    async def test_order_type_filter_scopes_mape_and_bias(
        self, db_session, sample_customer
    ):
        order_ring_1 = await _make_completed_order(
            db_session, sample_customer.id, order_type="ring"
        )
        order_ring_2 = await _make_completed_order(
            db_session, sample_customer.id, order_type="ring"
        )
        order_chain = await _make_completed_order(
            db_session, sample_customer.id, order_type="chain"
        )

        await record(
            db_session,
            order_ring_1,
            estimated_hours=10.0,
            actual_hours=8.0,
            estimated_total=100.0,
            actual_total=80.0,
            estimator_version="v1",
        )
        await record(
            db_session,
            order_ring_2,
            estimated_hours=20.0,
            actual_hours=25.0,
            estimated_total=200.0,
            actual_total=250.0,
            estimator_version="v1",
        )
        await record(
            db_session,
            order_chain,
            estimated_hours=5.0,
            actual_hours=5.0,
            estimated_total=50.0,
            actual_total=50.0,
            estimator_version="v1",
        )

        result = await calibration(db_session, order_type="ring")

        assert result.rows_loaded == 2
        assert result.rows_considered_for_mape == 2
        assert result.mape == pytest.approx((0.25 + 0.2) / 2)
        assert result.bias_by_order_type == pytest.approx({"ring": -1.5})

    async def test_limit_restricts_to_most_recent_rows(
        self, db_session, sample_customer
    ):
        """With limit=1, only the most-recently-created row is considered."""
        order_old = await _make_completed_order(
            db_session, sample_customer.id, order_type="ring"
        )
        order_new = await _make_completed_order(
            db_session, sample_customer.id, order_type="chain"
        )

        await record(
            db_session,
            order_old,
            estimated_hours=10.0,
            actual_hours=8.0,
            estimated_total=100.0,
            actual_total=80.0,
            estimator_version="v1",
        )
        await record(
            db_session,
            order_new,
            estimated_hours=5.0,
            actual_hours=5.0,
            estimated_total=50.0,
            actual_total=50.0,
            estimator_version="v1",
        )

        result = await calibration(db_session, limit=1)

        assert result.rows_loaded == 1
        assert result.bias_by_order_type == pytest.approx({"chain": 0.0})

    async def test_unknown_order_type_bucketed_when_order_type_is_null(
        self, db_session, sample_customer
    ):
        order = await _make_completed_order(
            db_session, sample_customer.id, order_type=None
        )

        await record(
            db_session,
            order,
            estimated_hours=4.0,
            actual_hours=4.0,
            estimated_total=40.0,
            actual_total=40.0,
            estimator_version="v1",
        )

        result = await calibration(db_session)

        assert result.bias_by_order_type == {UNKNOWN_ORDER_TYPE: 0.0}


# ---------------------------------------------------------------------------
# safe_record_on_completion() — defensive completion-hook wrapper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSafeRecordOnCompletion:
    async def test_no_op_when_no_estimate_values_supplied(
        self, db_session, sample_customer
    ):
        """Documented current state: Order has no stored estimate yet (Task
        5's job), so the completion hook calls this with all-None args.
        Completing an order with NO estimate must write NO row and must
        not raise."""
        order = await _make_completed_order(db_session, sample_customer.id)

        await safe_record_on_completion(db_session, order)

        result = await calibration(db_session)
        assert result.rows_loaded == 0

    async def test_writes_row_when_full_values_supplied(
        self, db_session, sample_customer
    ):
        """Forward-compatibility: once Task 5 passes real values, the same
        wrapper must actually persist them."""
        order = await _make_completed_order(db_session, sample_customer.id)

        await safe_record_on_completion(
            db_session,
            order,
            estimated_hours=6.0,
            actual_hours=7.0,
            estimated_total=60.0,
            actual_total=70.0,
            estimator_version="v1",
        )

        result = await calibration(db_session)
        assert result.rows_loaded == 1

    async def test_never_raises_when_record_fails(self, db_session, sample_customer):
        order = await _make_completed_order(db_session, sample_customer.id)

        async def _boom(*args, **kwargs):
            raise RuntimeError("simulated record() failure")

        with mock.patch.object(estimate_accuracy_service, "record", _boom):
            with mock.patch.object(
                estimate_accuracy_service.logger, "error"
            ) as error_spy:
                # Must not raise.
                await safe_record_on_completion(
                    db_session,
                    order,
                    estimated_hours=6.0,
                    actual_hours=7.0,
                    estimated_total=60.0,
                    actual_total=70.0,
                    estimator_version="v1",
                )

        assert error_spy.called
