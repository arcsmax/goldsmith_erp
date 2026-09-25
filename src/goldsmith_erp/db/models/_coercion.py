"""Assignment-time Decimal / aware-UTC coercion, installed after all models load."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import Float, Numeric, event

from goldsmith_erp.core.timeutil import ensure_utc
from goldsmith_erp.db.models.base import Base
from goldsmith_erp.db.types import UtcDateTime

# ── Decimal coercion on assignment (BE-14) ─────────────────────────────────
# Numeric columns load as Decimal, but a service that assigns a float (or an
# int) would leave that float on the instance until the next refresh, and the
# next ``Decimal * float`` raises TypeError. Every assignment to a Numeric
# column is therefore converted here: floats go through ``str`` (so 0.1 stays
# 0.1, not 0.1000000000000000055…), and the value is quantized to the column
# scale with ROUND_HALF_UP, which is what the printed documents show.


def _numeric_setter(scale: int) -> Any:
    quantum = Decimal(1).scaleb(-scale)

    def _coerce(target: Any, value: Any, oldvalue: Any, initiator: Any) -> Any:
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, Decimal):
            dec = value
        elif isinstance(value, (int, float)):
            dec = Decimal(str(value))
        else:
            return value
        if not dec.is_finite():
            raise ValueError(f"Non-finite value for Numeric column: {value!r}")
        return dec.quantize(quantum, rounding=ROUND_HALF_UP)

    return _coerce


def _install_numeric_coercion() -> None:
    for mapper in Base.registry.mappers:
        for prop in mapper.column_attrs:
            column = prop.columns[0]
            col_type = getattr(column, "type", None)
            if not isinstance(col_type, Numeric) or isinstance(col_type, Float):
                continue
            if col_type.scale is None:
                continue
            event.listen(
                getattr(mapper.class_, prop.key),
                "set",
                _numeric_setter(col_type.scale),
                retval=True,
            )


# ── Aware-UTC coercion on assignment (BE-15) ───────────────────────────────
# UtcDateTime already normalises on the way to and from the database, but a
# naive value assigned in Python (legacy callers, tests) would stay naive on
# the instance until the next refresh and then fail to compare with aware
# values. Assignments are therefore normalised to aware UTC right away.


def _utc_setter(target: Any, value: Any, oldvalue: Any, initiator: Any) -> Any:
    if isinstance(value, datetime):
        return ensure_utc(value)
    return value


def _install_utc_coercion() -> None:
    for mapper in Base.registry.mappers:
        for prop in mapper.column_attrs:
            column = prop.columns[0]
            if isinstance(getattr(column, "type", None), UtcDateTime):
                event.listen(
                    getattr(mapper.class_, prop.key), "set", _utc_setter, retval=True
                )
