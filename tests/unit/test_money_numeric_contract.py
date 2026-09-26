"""BE-14: money is NUMERIC in the DB, Decimal in Python, a JSON number on the wire.

Covers the three layers the refactor touches:

* ORM: Numeric columns load as ``Decimal`` and assignments are coerced to a
  cent-exact ``Decimal`` (ROUND_HALF_UP) by the setter listener in
  ``db/models.py``.
* Schemas: ``models._common.Money`` accepts numbers, keeps Decimal in Python
  mode, serialises to a JSON number and renders exactly like a ``float``
  field in the OpenAPI schema (both modes, so FastAPI doesn't split models).
* Services: the explicit psychological price rule replaces float
  ``round()`` (``_round_price(244.50)`` used to give 243.99).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import pytest
from pydantic import BaseModel, Field
from sqlalchemy import select

from goldsmith_erp.db.models import MetalPurchase, MetalType, Order
from goldsmith_erp.models._common import Money, dec, money
from goldsmith_erp.models.invoice import InvoiceResponse
from goldsmith_erp.services.cost_calculation_service import CostCalculationService


class _MoneyModel(BaseModel):
    amount: Money = Field(ge=0, description="x")
    optional: Optional[Money] = Field(None, ge=0, le=100)
    rate: Money = Field(19.0, ge=0, le=100, validate_default=True)


class _FloatModel(BaseModel):
    amount: float = Field(ge=0, description="x")
    optional: Optional[float] = Field(None, ge=0, le=100)
    rate: float = Field(19.0, ge=0, le=100)


class TestMoneySchemaType:
    def test_input_number_becomes_exact_decimal(self):
        model = _MoneyModel(amount=0.1)
        assert model.amount == Decimal("0.1")
        assert isinstance(model.amount, Decimal)
        assert model.rate == Decimal("19.0")

    def test_numeric_string_is_accepted_like_float_did(self):
        assert _MoneyModel(amount="1.005").amount == Decimal("1.005")

    def test_constraints_still_enforced(self):
        with pytest.raises(ValueError):
            _MoneyModel(amount=-1)
        with pytest.raises(ValueError):
            _MoneyModel(amount=1, optional=101)

    def test_json_output_is_a_number_python_output_is_decimal(self):
        model = _MoneyModel(amount=Decimal("12.30"), optional=None)
        assert json.loads(model.model_dump_json()) == {
            "amount": 12.3,
            "optional": None,
            "rate": 19.0,
        }
        assert model.model_dump()["amount"] == Decimal("12.30")

    @pytest.mark.parametrize("mode", ["validation", "serialization"])
    def test_json_schema_is_identical_to_a_float_field(self, mode):
        money_schema = _MoneyModel.model_json_schema(mode=mode)
        float_schema = _FloatModel.model_json_schema(mode=mode)
        money_schema["title"] = float_schema["title"]
        assert money_schema == float_schema

    def test_invoice_response_openapi_stays_number(self):
        props = InvoiceResponse.model_json_schema(mode="serialization")["properties"]
        assert props["total"]["type"] == "number"
        assert props["amount_due"]["anyOf"][0] == {"type": "number"}


class TestMoneyHelpers:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            (0.145, "0.15"),
            (2.675, "2.68"),
            ("1.005", "1.01"),
            (Decimal("-1.005"), "-1.01"),
            (None, "0.00"),
        ],
    )
    def test_money_rounds_half_up_from_the_decimal_text(self, raw, expected):
        assert money(raw) == Decimal(expected)

    def test_dec_default(self):
        assert dec(None, default=19) == Decimal("19")
        assert dec(0.1) == Decimal("0.1")


class TestPsychologicalPriceRule:
    @pytest.mark.parametrize(
        "price, expected",
        [
            ("243.45", "243.00"),
            ("243.49", "243.00"),
            ("244.50", "244.99"),  # float round() gave 243.99 (BE-14)
            ("245.67", "245.99"),
            ("248.12", "248.00"),
            ("0.49", "0.00"),
        ],
    )
    def test_round_price(self, price, expected):
        result = CostCalculationService._round_price(Decimal(price))
        assert result == Decimal(expected)
        assert isinstance(result, Decimal)


@pytest.mark.asyncio
class TestOrmDecimal:
    async def test_numeric_columns_load_as_decimal(self, db_session):
        purchase = MetalPurchase(
            date_purchased=datetime.utcnow() - timedelta(days=1),
            metal_type=MetalType.GOLD_18K,
            weight_g=12.3456,
            remaining_weight_g=12.3456,
            price_total=1234.5,
            price_per_gram=99.99995,
        )
        db_session.add(purchase)
        await db_session.commit()
        purchase_id = purchase.id
        db_session.expunge_all()

        loaded = (
            await db_session.execute(
                select(MetalPurchase).where(MetalPurchase.id == purchase_id)
            )
        ).scalar_one()
        assert isinstance(loaded.price_total, Decimal)
        assert loaded.price_total == Decimal("1234.50")
        # weights are milligram-exact, per-gram prices 4 dp, half up
        assert loaded.weight_g == Decimal("12.346")
        assert loaded.price_per_gram == Decimal("100.0000")

    async def test_float_assignment_is_coerced_to_cent_exact_decimal(self):
        order = Order(title="x", price=1.005)
        assert order.price == Decimal("1.01")
        order.price = 0.1 + 0.2
        assert order.price == Decimal("0.30")
        order.price = None
        assert order.price is None

    async def test_non_finite_assignment_fails_loudly(self):
        with pytest.raises(ValueError, match="Non-finite"):
            Order(title="x", price=float("nan"))

    async def test_float_columns_are_left_alone(self):
        order = Order(title="x", labor_hours=1.25)
        assert order.labor_hours == 1.25
        assert isinstance(order.labor_hours, float)
