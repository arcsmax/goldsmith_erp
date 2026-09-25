"""BE-15: core/timeutil.py and the Europe/Berlin rendering of documents."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from goldsmith_erp.core.timeutil import (
    DATE_FORMAT,
    ensure_utc,
    format_local,
    local_today,
    to_local,
    utcnow,
)
from goldsmith_erp.models._common import UtcDatetime
from goldsmith_erp.services.pdf_service import _fmt_date, _get_jinja_env


def test_utcnow_is_aware_utc():
    now = utcnow()
    assert now.utcoffset() == timedelta(0)


def test_ensure_utc_reads_naive_as_utc_and_converts_aware():
    assert ensure_utc(datetime(2026, 1, 1, 12, 0)) == datetime(
        2026, 1, 1, 12, 0, tzinfo=timezone.utc
    )
    plus_two = datetime(2026, 6, 1, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    converted = ensure_utc(plus_two)
    assert converted.utcoffset() == timedelta(0)
    assert converted.hour == 10
    assert ensure_utc(None) is None


@pytest.mark.parametrize(
    "utc_value, expected",
    [
        # New Year's Eve 23:30 UTC is already next year in Berlin (CET +1).
        (datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc), "01.01.2027 00:30"),
        # Summer time (CEST +2).
        (datetime(2026, 7, 1, 22, 15, tzinfo=timezone.utc), "02.07.2026 00:15"),
        # Naive input is read as UTC.
        (datetime(2026, 3, 1, 10, 0), "01.03.2026 11:00"),
    ],
)
def test_format_local_renders_europe_berlin(utc_value, expected):
    assert format_local(utc_value) == expected


def test_format_local_keeps_plain_dates_and_none():
    assert format_local(date(2026, 5, 4), DATE_FORMAT) == "04.05.2026"
    assert format_local(None) == "-"
    assert format_local(None, empty="") == ""


def test_to_local_and_local_today():
    assert to_local(datetime(2026, 1, 1, tzinfo=timezone.utc)).utcoffset() == timedelta(
        hours=1
    )
    assert isinstance(local_today(), date)


def test_pdf_dates_are_berlin_days():
    late_evening_utc = datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc)
    assert _fmt_date(late_evening_utc) == "01.01.2027"
    template = _get_jinja_env().from_string("{{ d|local_date }}")
    assert template.render(d=late_evening_utc) == "01.01.2027"


class TestUtcDatetimeSchemaType:
    def test_aware_input_becomes_aware_utc(self):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(UtcDatetime)
        value = adapter.validate_python("2026-09-25T10:00:00+02:00")
        assert value == datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)
        assert value.utcoffset() == timedelta(0)

    def test_z_suffix_and_naive_input(self):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(UtcDatetime)
        assert adapter.validate_python("2026-09-25T08:00:00.000Z") == datetime(
            2026, 9, 25, 8, 0, tzinfo=timezone.utc
        )
        # naive: read as UTC for one release
        assert adapter.validate_python("2026-09-25T08:00:00") == datetime(
            2026, 9, 25, 8, 0, tzinfo=timezone.utc
        )
