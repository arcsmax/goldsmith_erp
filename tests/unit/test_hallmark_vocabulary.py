"""Hallmark vocabulary derived from the order's alloy (W2-09; DOM-22, DOM-23,
DOM-44; decision D-10).

Covers:
  * services/hallmark_vocabulary.py — alloy -> allowed Feingehalt marks,
    the "nicht punziert: <Grund>" reason path, and the soft-gate predicate.
  * models/order.OrderUpdate._validate_punzierung_marks — the Pydantic
    field_validator built on top of that vocabulary.
"""

import pytest
from pydantic import ValidationError

from goldsmith_erp.db.models import AlloyType
from goldsmith_erp.models.order import OrderUpdate
from goldsmith_erp.services.hallmark_vocabulary import (
    ADDITIONAL_MARKS,
    NICHT_PUNZIERT_PREFIX,
    allowed_marks_for_alloy,
    build_hallmark_reason_mark,
    feingehalt_mark_for_alloy,
    is_feingehalt_mark,
    is_hallmark_reason_mark,
    is_valid_mark,
    normalize_alloy,
    satisfies_hallmark_requirement,
)


class TestNormalizeAlloy:
    @pytest.mark.parametrize(
        ("alloy", "expected"),
        [
            ("585", AlloyType.GOLD_585),
            ("750", AlloyType.GOLD_750),
            ("333", AlloyType.GOLD_333),
            ("375", AlloyType.GOLD_375),
            ("900", AlloyType.GOLD_900),
            ("999", AlloyType.GOLD_999),
            # OrderFormModal.ALLOY_OPTIONS sends these capitalised.
            ("Ag925", AlloyType.SILVER_925),
            ("Ag800", AlloyType.SILVER_800),
            ("Pt950", AlloyType.PLATINUM_950),
            # Case-insensitive either way.
            ("ag925", AlloyType.SILVER_925),
            ("PT950", AlloyType.PLATINUM_950),
        ],
    )
    def test_normalizes_known_alloys(self, alloy, expected):
        assert normalize_alloy(alloy) is expected

    @pytest.mark.parametrize("alloy", [None, "", "935", "unobtanium"])
    def test_unknown_or_missing_alloy_returns_none(self, alloy):
        assert normalize_alloy(alloy) is None


class TestFeingehaltMarkForAlloy:
    @pytest.mark.parametrize(
        ("alloy", "expected_code"),
        [
            ("585", "feingehalt_585"),
            ("750", "feingehalt_750"),
            ("333", "feingehalt_333"),
            ("375", "feingehalt_375"),
            ("900", "feingehalt_900"),
            ("999", "feingehalt_999"),
            ("Ag925", "feingehalt_925"),
            ("Ag800", "feingehalt_800"),
            ("Pt950", "feingehalt_950_pt"),
        ],
    )
    def test_derives_the_canonical_mark(self, alloy, expected_code):
        # DOM-22: every alloy the order form actually offers must have a
        # real Feingehalt mark, not just the original four (585/750/925/
        # 950pt).
        assert feingehalt_mark_for_alloy(alloy) == expected_code

    def test_unknown_alloy_yields_no_mark(self):
        assert feingehalt_mark_for_alloy("935") is None
        assert feingehalt_mark_for_alloy(None) is None


class TestAllowedMarksForAlloy:
    def test_matching_mark_is_listed_first(self):
        marks = allowed_marks_for_alloy("333")
        assert marks[0] == "feingehalt_333"
        # Every other Feingehalt mark is still offered (garbled Order.alloy
        # must not lock the goldsmith out of every option).
        assert "feingehalt_585" in marks
        assert "feingehalt_950_pt" in marks

    def test_unknown_alloy_still_offers_every_feingehalt_mark(self):
        marks = allowed_marks_for_alloy(None)
        assert "feingehalt_333" in marks
        assert "feingehalt_925" in marks

    def test_additional_marks_are_always_offered(self):
        marks = allowed_marks_for_alloy("585")
        for mark in ADDITIONAL_MARKS:
            assert mark in marks


class TestRawMarkForms:
    """The task's own example: 585 -> "585"/"Au585"; 925 for silver; 950 for
    platinum — plain marks a scanner or a manual entry might use instead of
    the legacy "feingehalt_*" wire code."""

    @pytest.mark.parametrize(
        "mark",
        ["585", "Au585", "750", "Au750", "333", "Au333"],
    )
    def test_gold_raw_marks_are_valid(self, mark):
        assert is_feingehalt_mark(mark)

    @pytest.mark.parametrize("mark", ["925", "Ag925"])
    def test_silver_raw_marks_are_valid(self, mark):
        assert is_feingehalt_mark(mark)

    @pytest.mark.parametrize("mark", ["950", "Pt950"])
    def test_platinum_raw_marks_are_valid(self, mark):
        assert is_feingehalt_mark(mark)

    def test_legacy_codes_remain_valid(self):
        for code in (
            "feingehalt_585",
            "feingehalt_750",
            "feingehalt_925",
            "feingehalt_950_pt",
            "feingehalt_333",
            "feingehalt_375",
            "feingehalt_900",
            "feingehalt_999",
            "feingehalt_800",
        ):
            assert is_feingehalt_mark(code)

    def test_unrelated_string_is_not_a_feingehalt_mark(self):
        assert not is_feingehalt_mark("feingehalt_666")
        assert not is_feingehalt_mark("meisterzeichen")


class TestExtraFeingehaltMarks:
    """Silver 935 and Palladium 950/500 (fix-w2-09-hallmark.md open item #1;
    fix-w2-06-14-16-11.md open item #3): no backing ``AlloyType`` member
    (would need a Postgres enum migration, out of scope), but the mark
    itself must still validate since ``Order.alloy`` is a free string."""

    @pytest.mark.parametrize("mark", ["935", "Ag935", "500", "Pd500", "Pd950"])
    def test_extra_marks_are_valid_feingehalt_marks(self, mark):
        assert is_feingehalt_mark(mark)
        assert is_valid_mark(mark)

    def test_normalize_alloy_still_does_not_know_these(self):
        # No AlloyType member backs them — normalize_alloy stays None,
        # exactly like before this fix (see TestNormalizeAlloy above).
        assert normalize_alloy("935") is None
        assert normalize_alloy("Pd500") is None

    def test_satisfies_hallmark_requirement(self):
        assert satisfies_hallmark_requirement(["935"])
        assert satisfies_hallmark_requirement(["Pd950"])


class TestNichtPunziertReasonPath:
    def test_build_reason_mark_uses_the_exact_prefix(self):
        mark = build_hallmark_reason_mark("Stein zu klein fuer Punze")
        assert mark == f"{NICHT_PUNZIERT_PREFIX}Stein zu klein fuer Punze"
        assert mark == "nicht punziert: Stein zu klein fuer Punze"

    def test_is_hallmark_reason_mark_requires_nonempty_reason(self):
        assert is_hallmark_reason_mark("nicht punziert: Stein zu klein")
        assert not is_hallmark_reason_mark("nicht punziert: ")
        assert not is_hallmark_reason_mark("nicht punziert:")
        assert not is_hallmark_reason_mark("feingehalt_585")

    def test_reason_mark_is_a_valid_mark(self):
        assert is_valid_mark("nicht punziert: Stein zu klein")

    def test_reason_alone_satisfies_the_soft_gate(self):
        assert satisfies_hallmark_requirement(["nicht punziert: Stein zu klein"])


class TestIsValidMark:
    @pytest.mark.parametrize(
        "mark",
        [
            "feingehalt_585",
            "585",
            "Au585",
            "Ag925",
            "Pt950",
            "meisterzeichen",
            "herstellerzeichen",
            "laenderzeichen",
            "nicht punziert: Kunde wollte keine Punze",
        ],
    )
    def test_accepts_every_vocabulary_entry(self, mark):
        assert is_valid_mark(mark)

    @pytest.mark.parametrize(
        "mark", ["feingehalt_666", "", "nicht punziert:", "quatsch"]
    )
    def test_rejects_unknown_marks(self, mark):
        assert not is_valid_mark(mark)


class TestSatisfiesHallmarkRequirement:
    def test_empty_list_does_not_satisfy(self):
        assert not satisfies_hallmark_requirement([])

    def test_additional_mark_alone_does_not_satisfy(self):
        # "Meisterzeichen allein ist kein Reinheits-Audit" (Thomas §3) — the
        # backend guard must enforce the same rule the modal already does.
        assert not satisfies_hallmark_requirement(["meisterzeichen"])
        assert not satisfies_hallmark_requirement(
            ["meisterzeichen", "herstellerzeichen", "laenderzeichen"]
        )

    def test_feingehalt_mark_satisfies(self):
        assert satisfies_hallmark_requirement(["feingehalt_333"])
        assert satisfies_hallmark_requirement(["meisterzeichen", "feingehalt_925"])

    def test_raw_feingehalt_mark_satisfies(self):
        assert satisfies_hallmark_requirement(["585"])
        assert satisfies_hallmark_requirement(["Pt950"])


class TestOrderUpdateValidator:
    """models.order.OrderUpdate._validate_punzierung_marks — the Pydantic
    layer built on top of the vocabulary above."""

    @pytest.mark.parametrize(
        "marks",
        [
            ["feingehalt_333"],
            ["feingehalt_375"],
            ["feingehalt_900"],
            ["feingehalt_999"],
            ["feingehalt_800"],
            ["585", "Au585"],
            ["Ag925"],
            ["Pt950"],
            ["meisterzeichen", "herstellerzeichen", "laenderzeichen"],
            ["nicht punziert: Stein zu klein fuer Punze"],
        ],
    )
    def test_accepts_the_widened_vocabulary(self, marks):
        update = OrderUpdate(punzierung_verified_marks=marks)
        assert update.punzierung_verified_marks == marks

    def test_rejects_unknown_marks(self):
        with pytest.raises(ValidationError):
            OrderUpdate(punzierung_verified_marks=["feingehalt_666"])

    def test_rejects_empty_reason(self):
        with pytest.raises(ValidationError):
            OrderUpdate(punzierung_verified_marks=["nicht punziert:"])

    def test_dedupes_while_preserving_order(self):
        update = OrderUpdate(
            punzierung_verified_marks=[
                "feingehalt_585",
                "meisterzeichen",
                "feingehalt_585",
            ]
        )
        assert update.punzierung_verified_marks == ["feingehalt_585", "meisterzeichen"]

    def test_none_is_left_untouched(self):
        update = OrderUpdate(punzierung_verified_marks=None)
        assert update.punzierung_verified_marks is None
