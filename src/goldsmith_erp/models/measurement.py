"""
Pydantic schemas for the customer Massbibliothek (measurement library).

Body measurements are PII — treat them like any other customer personal data:
encrypted at rest (via EncryptedString where applicable), never logged in
plaintext, exportable on GDPR Art. 15 request, erasable on Art. 17 request.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from goldsmith_erp.db.models import FingerPosition, HandSide, MeasurementType


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

# Anthropometric bounds — chosen to span child to bariatric extremes so the
# goldsmith is never locked out of recording a legitimate measurement just
# because it sits outside the population average. Numbers below are
# deliberately wide; the on-screen warning ranges in the UI can be tighter.

# German EU ring size: inner circumference in mm.
# Smallest pinky in a small hand starts around 38 mm; the largest thumb on
# a very large hand can reach the high 80s. Allow 30–90 mm.
_RING_SIZE_MIN = 30.0
_RING_SIZE_MAX = 90.0

# Finger circumference (raw tape measurement) — same range as EU ring size.
_FINGER_CIRC_MIN = 30.0
_FINGER_CIRC_MAX = 90.0

# Chain / necklace length in cm. Collar 25 cm through Opera/Rope 150 cm.
_CHAIN_LENGTH_MIN = 25.0
_CHAIN_LENGTH_MAX = 150.0

# Wrist circumference in cm. Small child wrist 8 cm, very large 35 cm.
_WRIST_MIN = 8.0
_WRIST_MAX = 35.0

# Neck circumference in cm. Small child 20 cm, very large 70 cm.
_NECK_MIN = 20.0
_NECK_MAX = 70.0

# Ankle circumference in cm. Small child 14 cm, very large 50 cm.
_ANKLE_MIN = 14.0
_ANKLE_MAX = 50.0


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MeasurementBase(BaseModel):
    """Fields common to create and update operations."""

    measurement_type: MeasurementType = Field(
        ...,
        description=(
            "What was measured: ring_size, chain_length, wrist_circumference, "
            "finger_circumference, neck_circumference, or ankle_circumference"
        ),
    )
    value: float = Field(
        ...,
        gt=0,
        description=(
            "Numeric measurement value. "
            "Ring sizes: EU inner circumference in mm (e.g. 54.0). "
            "Lengths (chain, wrist, neck, ankle): centimetres."
        ),
    )
    unit: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description='Unit of measure: "mm", "cm", "EU", "US"',
    )
    hand: Optional[HandSide] = Field(
        None,
        description="LEFT or RIGHT — required for ring and bracelet measurements",
    )
    finger: Optional[FingerPosition] = Field(
        None,
        description="Finger position — required for ring_size and finger_circumference",
    )
    notes: Optional[str] = Field(
        None,
        max_length=1000,
        description=(
            'Free-text goldsmith annotation, e.g. '
            '"Knöchel etwas breiter, Weitungsring empfohlen"'
        ),
    )
    measured_at: Optional[datetime] = Field(
        None,
        description="When the measurement was physically taken (defaults to now)",
    )

    @model_validator(mode="after")
    def validate_measurement_constraints(self) -> "MeasurementBase":
        """
        Enforce goldsmith-domain business rules:

        1. Ring measurements need hand + finger.
        2. Value ranges are clamped per measurement type.
        3. Unit must be consistent with type.
        """
        t = self.measurement_type
        v = self.value

        # --- ring_size: EU inner circumference in mm ---
        if t == MeasurementType.RING_SIZE:
            if self.hand is None:
                raise ValueError(
                    "ring_size measurement requires 'hand' (LEFT or RIGHT)"
                )
            if self.finger is None:
                raise ValueError(
                    "ring_size measurement requires 'finger' (thumb, index, …)"
                )
            if not (_RING_SIZE_MIN <= v <= _RING_SIZE_MAX):
                raise ValueError(
                    f"ring_size value must be between {_RING_SIZE_MIN} and "
                    f"{_RING_SIZE_MAX} mm (EU inner circumference). Got {v}."
                )

        # --- finger_circumference: raw tape in mm, basis for EU size ---
        elif t == MeasurementType.FINGER_CIRCUMFERENCE:
            if self.hand is None:
                raise ValueError(
                    "finger_circumference measurement requires 'hand' (LEFT or RIGHT)"
                )
            if self.finger is None:
                raise ValueError(
                    "finger_circumference measurement requires 'finger'"
                )
            if not (_FINGER_CIRC_MIN <= v <= _FINGER_CIRC_MAX):
                raise ValueError(
                    f"finger_circumference must be {_FINGER_CIRC_MIN}–{_FINGER_CIRC_MAX} mm. "
                    f"Got {v}."
                )

        # --- chain_length: cm ---
        elif t == MeasurementType.CHAIN_LENGTH:
            if not (_CHAIN_LENGTH_MIN <= v <= _CHAIN_LENGTH_MAX):
                raise ValueError(
                    f"chain_length must be {_CHAIN_LENGTH_MIN}–{_CHAIN_LENGTH_MAX} cm. "
                    f"Got {v}."
                )

        # --- wrist_circumference: cm ---
        elif t == MeasurementType.WRIST_CIRCUMFERENCE:
            if not (_WRIST_MIN <= v <= _WRIST_MAX):
                raise ValueError(
                    f"wrist_circumference must be {_WRIST_MIN}–{_WRIST_MAX} cm. "
                    f"Got {v}."
                )

        # --- neck_circumference: cm ---
        elif t == MeasurementType.NECK_CIRCUMFERENCE:
            if not (_NECK_MIN <= v <= _NECK_MAX):
                raise ValueError(
                    f"neck_circumference must be {_NECK_MIN}–{_NECK_MAX} cm. "
                    f"Got {v}."
                )

        # --- ankle_circumference: cm ---
        elif t == MeasurementType.ANKLE_CIRCUMFERENCE:
            if not (_ANKLE_MIN <= v <= _ANKLE_MAX):
                raise ValueError(
                    f"ankle_circumference must be {_ANKLE_MIN}–{_ANKLE_MAX} cm. "
                    f"Got {v}."
                )

        return self


class MeasurementCreate(MeasurementBase):
    """Schema for adding a new measurement to a customer's Massbibliothek."""

    # measured_at defaults to server time when not provided
    measured_at: Optional[datetime] = Field(
        None,
        description="Measurement date (defaults to now if omitted)",
    )


class MeasurementUpdate(BaseModel):
    """
    Schema for updating an existing measurement.

    All fields are optional — only provided fields are updated.
    """

    value: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = Field(None, min_length=1, max_length=20)
    hand: Optional[HandSide] = None
    finger: Optional[FingerPosition] = None
    notes: Optional[str] = Field(None, max_length=1000)
    measured_at: Optional[datetime] = None


class MeasurementResponse(BaseModel):
    """Full measurement record returned from the API."""

    id: int
    customer_id: int
    measured_by: Optional[int] = None
    measurement_type: MeasurementType
    value: float
    unit: str
    hand: Optional[HandSide] = None
    finger: Optional[FingerPosition] = None
    notes: Optional[str] = None
    measured_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RingSizeLookupResponse(BaseModel):
    """
    Quick ring-size lookup result for a specific hand/finger combination.

    Used by the convenience endpoint GET /customers/{id}/ring-size.
    """

    customer_id: int
    hand: HandSide
    finger: FingerPosition
    # None means no measurement on record — goldsmith must re-measure
    ring_size_eu: Optional[float] = Field(
        None,
        description="EU ring size (inner circumference in mm). None = not on record.",
    )
    unit: Optional[str] = None
    notes: Optional[str] = None
    measured_at: Optional[datetime] = None
    measured_by: Optional[int] = None
