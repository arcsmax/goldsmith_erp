# src/goldsmith_erp/models/comparison.py
"""
Pydantic schemas for Soll/Ist-Vergleich (quote vs. actual comparison).

Financial data — access restricted to ADMIN and GOLDSMITH roles.
All access must be audit-logged per CLAUDE.md data privacy rules.
"""

from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import List, Optional


SIGNIFICANT_DEVIATION_THRESHOLD = 20.0  # Abweichung > 20% wird als signifikant markiert


class ComparisonMetric(BaseModel):
    """
    A single Soll/Ist metric pair with deviation calculation.

    soll  = Planned / estimated value (Sollwert)
    ist   = Actual recorded value (Istwert)
    deviation_percent  = (ist - soll) / soll * 100  (positive = over-run)
    deviation_abs      = ist - soll  (in the metric's native unit)
    is_significant     = True when |deviation_percent| > 20%
    """

    soll: Optional[float] = Field(None, description="Planned / estimated value (Sollwert)")
    ist: Optional[float] = Field(None, description="Actual recorded value (Istwert)")
    deviation_percent: Optional[float] = Field(
        None,
        description="Relative Abweichung in Prozent — positiv = Mehraufwand, negativ = Einsparung"
    )
    deviation_abs: Optional[float] = Field(
        None,
        description="Absolute Abweichung in der nativen Einheit der Metrik"
    )
    is_significant: bool = Field(
        False,
        description=f"True wenn |Abweichung| > {SIGNIFICANT_DEVIATION_THRESHOLD}%"
    )


class ActivityBreakdown(BaseModel):
    """
    Per-activity time breakdown within an order.

    Compares time entries against the activity's average_duration_minutes
    (the Soll-Wert derived from Activity.average_duration_minutes).
    When no activity average exists the soll fields are None.
    """

    activity_id: int
    activity_name: str
    activity_category: str = Field(description="fabrication, administration, waiting, …")

    # Time in minutes
    actual_minutes: float = Field(description="Summe der duration_minutes aus TimeEntry-Eintraegen")
    estimated_minutes: Optional[float] = Field(
        None,
        description="Sollwert aus Activity.average_duration_minutes (wenn vorhanden)"
    )
    deviation_minutes: Optional[float] = Field(
        None,
        description="actual_minutes - estimated_minutes"
    )
    deviation_percent: Optional[float] = Field(
        None,
        description="Relative Abweichung in Prozent"
    )
    is_significant: bool = False
    entry_count: int = Field(description="Anzahl der TimeEntry-Eintraege fuer diese Aktivitaet")


class OrderComparison(BaseModel):
    """
    Full Soll/Ist-Vergleich for a single order.

    Aggregates all comparison metrics for an order so the goldsmith
    can see at a glance where estimates were accurate and where they drifted.
    """

    order_id: int
    order_title: str
    order_type: Optional[str] = None
    status: str
    completed_at: Optional[datetime] = None

    # Core Soll/Ist metrics
    hours: ComparisonMetric = Field(description="Arbeitszeit: labor_hours (Soll) vs actual_hours (Ist)")
    material_weight: ComparisonMetric = Field(
        description="Materialgewicht in Gramm: estimated_weight_g vs actual_weight_g"
    )
    material_cost: ComparisonMetric = Field(
        description="Materialkosten in EUR: material_cost_calculated vs tatsaechliche Materialnutzung"
    )
    total_price: ComparisonMetric = Field(
        description="Gesamtpreis in EUR: calculated_price (Kalkulation) vs price (Endpreis)"
    )

    # Activity-level time breakdown
    activity_breakdown: List[ActivityBreakdown] = Field(
        default_factory=list,
        description="Zeitaufschluesselung nach Aktivitaetstyp"
    )

    # Summary score
    overall_accuracy_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description=(
            "Genauigkeitsscore 0-100: 100 = perfekte Schaetzung, "
            "niedrigerer Wert = groessere mittlere Abweichung"
        )
    )

    # Flag: at least one metric exceeds the significance threshold
    has_significant_deviation: bool = Field(
        False,
        description=f"True wenn mindestens eine Metrik > {SIGNIFICANT_DEVIATION_THRESHOLD}% Abweichung hat"
    )

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Workshop-wide aggregate statistics
# ---------------------------------------------------------------------------


class OrderTypeDeviation(BaseModel):
    """Summary of estimation accuracy for a specific order type."""

    order_type: str
    order_count: int
    avg_hours_deviation_percent: Optional[float] = None
    avg_material_deviation_percent: Optional[float] = None
    avg_cost_deviation_percent: Optional[float] = None
    direction: str = Field(
        description="'over' = systematisch unterschaetzt, 'under' = ueberschaetzt, 'accurate' = im Rahmen"
    )


class ActivityDeviation(BaseModel):
    """Aggregated deviation for a specific activity type across all orders."""

    activity_name: str
    activity_category: str
    order_count: int
    avg_deviation_percent: Optional[float] = None
    avg_deviation_minutes: Optional[float] = None
    direction: str = Field(
        description="'over' = Mehraufwand, 'under' = Minderbedarf, 'accurate' = im Rahmen"
    )


class TrendPoint(BaseModel):
    """A single data point for a trend line (week or month bucket)."""

    period_label: str = Field(description="z.B. '2026-KW12' oder '2026-03'")
    period_start: datetime
    order_count: int
    avg_hours_deviation_percent: Optional[float] = None
    avg_material_deviation_percent: Optional[float] = None
    avg_cost_deviation_percent: Optional[float] = None


class WorkshopStats(BaseModel):
    """
    Soll/Ist-Statistiken fuer die gesamte Werkstatt in einem Zeitraum.

    Used for the analytics dashboard showing where the workshop consistently
    over- or under-estimates so future Kalkulationen can be adjusted.
    """

    date_from: datetime
    date_to: datetime
    total_completed_orders: int

    # Average deviations (in percent, + = over-run)
    avg_hours_deviation_percent: Optional[float] = Field(
        None, description="Mittlere Arbeitszeitabweichung ueber alle Auftraege"
    )
    avg_material_deviation_percent: Optional[float] = Field(
        None, description="Mittlere Materialgewichtsabweichung ueber alle Auftraege"
    )
    avg_cost_deviation_percent: Optional[float] = Field(
        None, description="Mittlere Materialkostenabweichung ueber alle Auftraege"
    )

    # Orders with significant deviation
    significant_deviation_count: int = Field(
        0, description="Anzahl Auftraege mit mindestens einer signifikanten Abweichung"
    )
    significant_deviation_percent: Optional[float] = Field(
        None, description="Anteil der Auftraege mit signifikanter Abweichung in Prozent"
    )

    # Breakdown by order type (Auftragstyp)
    most_underestimated_order_types: List[OrderTypeDeviation] = Field(
        default_factory=list,
        description="Auftragstypen, bei denen der Aufwand am haeufigsten unterschaetzt wird"
    )
    most_overestimated_order_types: List[OrderTypeDeviation] = Field(
        default_factory=list,
        description="Auftragstypen, bei denen der Aufwand am haeufigsten ueberschaetzt wird"
    )

    # Breakdown by activity type (Aktivitaetstyp)
    most_underestimated_activities: List[ActivityDeviation] = Field(
        default_factory=list,
        description="Aktivitaeten, die systematisch laenger dauern als geschaetzt"
    )
    most_overestimated_activities: List[ActivityDeviation] = Field(
        default_factory=list,
        description="Aktivitaeten, die systematisch kuerzer dauern als geschaetzt"
    )

    # Accuracy trend over the period (improving / worsening)
    trend: List[TrendPoint] = Field(
        default_factory=list,
        description="Zeitlicher Verlauf der Schaetzgenauigkeit"
    )
    trend_direction: Optional[str] = Field(
        None,
        description="'improving', 'worsening', 'stable', oder None wenn zu wenig Daten"
    )

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Per-goldsmith accuracy
# ---------------------------------------------------------------------------


class UserAccuracy(BaseModel):
    """
    Soll/Ist-Genauigkeit fuer einen einzelnen Goldschmied.

    Compares the individual's estimation accuracy to the workshop average
    so coaching conversations can be evidence-based.
    """

    user_id: int
    user_name: str  # Anonymized for display: first_name + last_name initial

    total_orders: int
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None

    # Individual averages
    avg_hours_deviation_percent: Optional[float] = None
    avg_material_deviation_percent: Optional[float] = None

    # Comparison to workshop average (positive = worse than average)
    hours_vs_workshop_avg: Optional[float] = Field(
        None,
        description="Differenz zur Werkstatt-Durchschnittsabweichung in Prozentpunkten"
    )
    material_vs_workshop_avg: Optional[float] = Field(
        None,
        description="Differenz zur Werkstatt-Durchschnittsabweichung in Prozentpunkten"
    )

    # Best and worst order types for this goldsmith
    best_order_types: List[OrderTypeDeviation] = Field(
        default_factory=list,
        description="Auftragstypen mit der genauesten Schaetzung"
    )
    worst_order_types: List[OrderTypeDeviation] = Field(
        default_factory=list,
        description="Auftragstypen mit der ungenauesten Schaetzung"
    )

    # Trend
    improvement_trend: Optional[str] = Field(
        None,
        description="'improving', 'worsening', 'stable', oder None wenn zu wenig Daten"
    )

    model_config = ConfigDict(from_attributes=True)
