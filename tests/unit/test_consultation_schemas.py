import pytest
from pydantic import ValidationError

from goldsmith_erp.models.consultation import (
    ConsultationCreate,
    ConsultationConvertRequest,
    NoGoCreate,
)


def test_budget_range_must_be_ordered():
    with pytest.raises(ValidationError):
        ConsultationCreate(customer_id=1, budget_min=500.0, budget_max=100.0)


def test_no_go_value_is_stripped_and_required():
    with pytest.raises(ValidationError):
        NoGoCreate(category="allergy", value="   ")
    ok = NoGoCreate(category="allergy", value="  Nickel ")
    assert ok.value == "Nickel"


def test_convert_target_restricted():
    with pytest.raises(ValidationError):
        ConsultationConvertRequest(target="invoice")
    assert ConsultationConvertRequest(target="order").target == "order"
