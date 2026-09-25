# src/goldsmith_erp/models/_common.py
"""
Shared Pydantic helpers for API input schemas.

Datetime convention (see docs/architecture/ADR-2026-09-25-price-semantics.md):
the DB columns are ``TIMESTAMP WITHOUT TIME ZONE`` holding UTC, and the rest
of the code compares against ``datetime.utcnow()``. The browser sends ISO
strings with a ``Z`` suffix, which Pydantic parses as tz-aware. Every API
datetime input is therefore normalised to naive UTC at the schema boundary:

- aware input  -> converted to UTC, tzinfo dropped
- naive input  -> interpreted as UTC (unchanged)

This is the same rule ``models/repair.py::_strip_tzinfo`` already applies.
"""

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Optional, Union, cast

from pydantic import BeforeValidator, GetJsonSchemaHandler, PlainSerializer, TypeAdapter
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

_DATETIME_ADAPTER: TypeAdapter[datetime] = TypeAdapter(datetime)


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Return ``value`` as naive UTC; ``None`` passes through."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _parse_to_naive_utc(value: object) -> object:
    """BeforeValidator: parse str/datetime input and normalise to naive UTC."""
    if value is None:
        return None
    parsed = _DATETIME_ADAPTER.validate_python(value)
    return to_naive_utc(parsed)


UtcNaiveDatetime = Annotated[datetime, BeforeValidator(_parse_to_naive_utc)]
"""A datetime field that is always naive UTC after validation."""


# ── Exact decimals on the wire contract (BE-14) ────────────────────────────
#
# Money, weights and rates are ``Decimal`` inside the application (the DB
# columns are NUMERIC, see docs/architecture/ADR-2026-09-25-numeric-and-tz.md)
# but the JSON contract with the frontend stays a plain JSON number:
#
# - input accepts numbers and numeric strings, exactly like ``float`` did;
#   a JSON number is converted via its shortest repr, so 0.1 is Decimal("0.1")
# - JSON output is a float (``model_dump(mode="json")`` / FastAPI responses);
#   ``model_dump()`` in Python mode keeps the Decimal
# - the OpenAPI schema is ``{"type": "number"}`` plus the same
#   minimum/maximum keywords a ``float`` field produced, in both validation
#   and serialization mode, so FastAPI does not split models into
#   ``-Input``/``-Output`` variants and the generated TS types do not change.

_JSON_BOUND_KEYWORDS = (
    ("ge", "minimum"),
    ("gt", "exclusiveMinimum"),
    ("le", "maximum"),
    ("lt", "exclusiveMaximum"),
    ("multiple_of", "multipleOf"),
)


def _json_number(value: Any) -> Union[int, float]:
    # Keep the literal the Field() was declared with (0 vs 0.0), exactly as a
    # float field renders it.
    if isinstance(value, (int, float)):
        return value
    return float(value)


def _decimal_core(schema: Any) -> Any:
    """Unwrap field-validator wrappers down to the ``decimal`` core schema."""
    while isinstance(schema, dict) and schema.get("type") != "decimal":
        inner = schema.get("schema")
        if inner is None:
            break
        schema = inner
    return schema


class _DecimalAsJsonNumber:
    """JSON-schema hook: render a (constrained) Decimal like a float field."""

    def __get_pydantic_json_schema__(
        self, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        rendered: dict[str, Any] = {"type": "number"}
        decimal_schema = _decimal_core(schema)
        for constraint, keyword in _JSON_BOUND_KEYWORDS:
            bound = decimal_schema.get(constraint)
            if bound is not None:
                rendered[keyword] = _json_number(bound)
        return rendered


def _decimal_to_json(value: Decimal) -> float:
    return float(value)


Money = Annotated[
    Decimal,
    PlainSerializer(_decimal_to_json, return_type=Any, when_used="json-unless-none"),
    _DecimalAsJsonNumber(),
]
"""EUR amount: Decimal in Python, JSON number on the wire (NUMERIC(12, 2))."""

Weight = Money
"""Grams / quantities: same wire behaviour as Money (NUMERIC(12, 3))."""

Percent = Money
"""Percentages (VAT, margin): same wire behaviour as Money (NUMERIC(5, 2))."""


def number_default(value: float) -> Decimal:
    """Default for a Money/Weight/Percent field that renders as a JSON number.

    A ``Decimal`` default would appear as a string (``"19.0"``) in the
    OpenAPI schema; the float literal keeps it a number. Pair it with
    ``validate_default=True`` on input schemas so the runtime value is a
    Decimal too. The cast only tells mypy what validation produces.
    """
    return cast(Decimal, value)


CENT = Decimal("0.01")

DecimalLike = Union[Decimal, float, int, str]


def to_decimal(value: Any) -> Optional[Decimal]:
    """Convert a number to Decimal without binary-float noise; None passes."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def dec(value: Any, default: DecimalLike = 0) -> Decimal:
    """Like :func:`to_decimal`, but None becomes ``default`` (0)."""
    converted = to_decimal(value)
    if converted is None:
        converted = to_decimal(default)
    assert converted is not None
    return converted


def money(value: Any) -> Decimal:
    """Round to the cent with commercial rounding (ROUND_HALF_UP); None is 0."""
    return dec(value).quantize(CENT, rounding=ROUND_HALF_UP)
