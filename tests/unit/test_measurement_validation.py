"""
Tests for `MeasurementCreate` value-range validators.

Real-world wrist/neck/ankle measurements span a wider anthropometric
range than the original conservative bounds: a child's wrist can be
8 cm; a bariatric customer's can be over 30 cm. Goldsmiths legitimately
encounter the full spectrum and must not be locked out of recording an
otherwise valid measurement just because it sits outside the average.

These tests pin the new — wider — bounds. They were added as a TDD
red-then-green cycle: the wrist `10.0 cm` user-reported case below
fails against the original `12.0–28.0` bound and is the immediate
trigger for this widening.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from goldsmith_erp.db.models import FingerPosition, HandSide, MeasurementType
from goldsmith_erp.models.measurement import MeasurementCreate


# ---------------------------------------------------------------------------
# Wrist (the immediate user complaint — was 12.0–28.0)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value_cm", [8.0, 10.0, 12.0, 18.0, 28.0, 32.0, 35.0])
def test_wrist_circumference_accepts_wide_range(value_cm: float) -> None:
    """Wrist 8 cm (small child) through 35 cm (very large) all valid."""
    m = MeasurementCreate(
        measurement_type=MeasurementType.WRIST_CIRCUMFERENCE,
        value=value_cm,
        unit="cm",
    )
    assert m.value == value_cm


@pytest.mark.parametrize("value_cm", [0.0, 5.0, 7.9, 35.1, 40.0])
def test_wrist_circumference_rejects_implausible(value_cm: float) -> None:
    """Below 8 or above 35 cm is anatomically implausible — keep guard."""
    with pytest.raises(ValidationError):
        MeasurementCreate(
            measurement_type=MeasurementType.WRIST_CIRCUMFERENCE,
            value=value_cm,
            unit="cm",
        )


# ---------------------------------------------------------------------------
# Neck (was 25.0–60.0)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value_cm", [20.0, 25.0, 40.0, 60.0, 70.0])
def test_neck_circumference_accepts_wide_range(value_cm: float) -> None:
    m = MeasurementCreate(
        measurement_type=MeasurementType.NECK_CIRCUMFERENCE,
        value=value_cm,
        unit="cm",
    )
    assert m.value == value_cm


@pytest.mark.parametrize("value_cm", [10.0, 19.9, 70.1, 100.0])
def test_neck_circumference_rejects_implausible(value_cm: float) -> None:
    with pytest.raises(ValidationError):
        MeasurementCreate(
            measurement_type=MeasurementType.NECK_CIRCUMFERENCE,
            value=value_cm,
            unit="cm",
        )


# ---------------------------------------------------------------------------
# Ankle (was 18.0–40.0)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value_cm", [14.0, 18.0, 25.0, 40.0, 50.0])
def test_ankle_circumference_accepts_wide_range(value_cm: float) -> None:
    m = MeasurementCreate(
        measurement_type=MeasurementType.ANKLE_CIRCUMFERENCE,
        value=value_cm,
        unit="cm",
    )
    assert m.value == value_cm


@pytest.mark.parametrize("value_cm", [5.0, 13.9, 50.1, 100.0])
def test_ankle_circumference_rejects_implausible(value_cm: float) -> None:
    with pytest.raises(ValidationError):
        MeasurementCreate(
            measurement_type=MeasurementType.ANKLE_CIRCUMFERENCE,
            value=value_cm,
            unit="cm",
        )


# ---------------------------------------------------------------------------
# Chain length (was 30.0–120.0)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value_cm", [25.0, 30.0, 60.0, 120.0, 150.0])
def test_chain_length_accepts_wide_range(value_cm: float) -> None:
    m = MeasurementCreate(
        measurement_type=MeasurementType.CHAIN_LENGTH,
        value=value_cm,
        unit="cm",
    )
    assert m.value == value_cm


@pytest.mark.parametrize("value_cm", [5.0, 24.9, 150.1, 300.0])
def test_chain_length_rejects_implausible(value_cm: float) -> None:
    with pytest.raises(ValidationError):
        MeasurementCreate(
            measurement_type=MeasurementType.CHAIN_LENGTH,
            value=value_cm,
            unit="cm",
        )


# ---------------------------------------------------------------------------
# Ring size (EU inner circumference in mm; was 38.0–80.0)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value_mm", [30.0, 38.0, 54.0, 80.0, 90.0])
def test_ring_size_accepts_wide_range(value_mm: float) -> None:
    m = MeasurementCreate(
        measurement_type=MeasurementType.RING_SIZE,
        value=value_mm,
        unit="mm",
        hand=HandSide.LEFT,
        finger=FingerPosition.RING,
    )
    assert m.value == value_mm


@pytest.mark.parametrize("value_mm", [10.0, 29.9, 90.1, 200.0])
def test_ring_size_rejects_implausible(value_mm: float) -> None:
    with pytest.raises(ValidationError):
        MeasurementCreate(
            measurement_type=MeasurementType.RING_SIZE,
            value=value_mm,
            unit="mm",
            hand=HandSide.LEFT,
            finger=FingerPosition.RING,
        )


# ---------------------------------------------------------------------------
# Finger circumference (was 38.0–80.0; same bounds as ring_size)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value_mm", [30.0, 38.0, 65.0, 90.0])
def test_finger_circumference_accepts_wide_range(value_mm: float) -> None:
    m = MeasurementCreate(
        measurement_type=MeasurementType.FINGER_CIRCUMFERENCE,
        value=value_mm,
        unit="mm",
        hand=HandSide.LEFT,
        finger=FingerPosition.INDEX,
    )
    assert m.value == value_mm


@pytest.mark.parametrize("value_mm", [10.0, 29.9, 90.1])
def test_finger_circumference_rejects_implausible(value_mm: float) -> None:
    with pytest.raises(ValidationError):
        MeasurementCreate(
            measurement_type=MeasurementType.FINGER_CIRCUMFERENCE,
            value=value_mm,
            unit="mm",
            hand=HandSide.LEFT,
            finger=FingerPosition.INDEX,
        )


# ---------------------------------------------------------------------------
# Regression of the user-reported case
# ---------------------------------------------------------------------------

def test_user_reported_wrist_10cm_now_accepted() -> None:
    """Direct repro of the bug-report payload."""
    m = MeasurementCreate(
        measurement_type=MeasurementType.WRIST_CIRCUMFERENCE,
        value=10.0,
        unit="cm",
    )
    assert m.value == 10.0
    assert m.measurement_type == MeasurementType.WRIST_CIRCUMFERENCE
