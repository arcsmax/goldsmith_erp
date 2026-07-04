"""
Pydantic schemas for the V1.3 statistical labor estimator (Phase 1, Task 5).

``LaborEstimateRequest`` mirrors ``ml.labor_estimator.EstimateFeatures``'s
fields (order_type, finish_type, has_stone_setting, alloy,
complexity_rating) — the two are intentionally NOT the same class:
``EstimateFeatures`` is an internal frozen dataclass consumed by the pure-
Python ``LaborEstimator``, while this is the public HTTP request contract
validated by Pydantic (``api/routers/estimator.py`` converts one into the
other).

Financial-exposure rules (CLAUDE.md, this plan's Global Constraints):
* ``LaborEstimateResponse`` never fabricates a number — every
  ``hours_*``/``labor_cost_*`` field is ``None`` together whenever
  ``insufficient_data`` is ``True`` (see
  ``services/estimator_service.py::estimate_labor``).
* Raw per-activity ``hourly_rate`` values are NEVER included here — only
  aggregate computed costs. The per-activity rate table stays internal
  (CostCalculationService only).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from goldsmith_erp.ml.labor_estimator import SimilarityLevel


class LaborEstimateRequest(BaseModel):
    """Job features to request a labor-hours + labor-cost estimate for."""

    order_type: str = Field(
        ...,
        min_length=1,
        description="Type of jewelry piece (ring, chain, pendant, ...)",
        examples=["ring"],
    )
    finish_type: Optional[str] = Field(
        None,
        description="Surface finish, e.g. high_polish, matte, brushed",
    )
    has_stone_setting: bool = Field(
        False, description="Whether the job includes stone setting"
    )
    alloy: Optional[str] = Field(
        None, description="Metal alloy identifier, e.g. gold_585, gold_750"
    )
    complexity_rating: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Complexity from 1 (simple) to 5 (highly complex)",
    )


class LaborEstimateResponse(BaseModel):
    """
    Statistical labor-hours + labor-cost estimate.

    ADMIN/GOLDSMITH only (financial/pricing data). When
    ``insufficient_data`` is ``True``, every ``hours_*``/``labor_cost_*``
    field is ``None`` — never a fabricated number from too few comparable
    orders (see the Phase 1 plan's "never fake confidence" global
    constraint).

    ``labor_cost_p50`` is the single customer-facing number (product
    decision Q3, 2026-07-04); ``labor_cost_p20``/``labor_cost_p80`` are the
    internal-only cost range — Phase 3 (frontend "Kalkulation" panel)
    decides what a customer actually sees.
    """

    model_config = ConfigDict(from_attributes=True)

    hours_p50: Optional[float]
    hours_p20: Optional[float]
    hours_p80: Optional[float]
    labor_cost_p50: Optional[float] = Field(
        None,
        description="Single customer-facing labor cost estimate (product decision Q3)",
    )
    labor_cost_p20: Optional[float] = Field(
        None, description="Internal-only labor cost range floor"
    )
    labor_cost_p80: Optional[float] = Field(
        None, description="Internal-only labor cost range ceiling"
    )
    sample_size: int
    similarity_level: SimilarityLevel
    similar_orders: list[int]
    insufficient_data: bool


class CalibrationResponse(BaseModel):
    """
    Wraps ``estimate_accuracy_service.CalibrationResult`` for the API.

    Field names/shape match ``CalibrationResult`` exactly (built via
    ``model_validate`` against that frozen dataclass) — see that module's
    docstring for the MAPE / bias formulas and the zero-actual exclusion
    rule.
    """

    model_config = ConfigDict(from_attributes=True)

    rows_loaded: int
    rows_considered_for_mape: int
    rows_excluded_zero_actual: int
    mape: Optional[float]
    bias_by_order_type: dict[str, float]
