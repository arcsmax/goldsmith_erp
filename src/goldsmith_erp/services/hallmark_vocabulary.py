"""Hallmark (Punzierungs-Check) mark vocabulary derived from the order's
alloy (W2-09; findings DOM-22, DOM-23, DOM-44; decision D-10).

Before this module, ``models.order._validate_punzierung_marks`` allowed
exactly four Feingehalt codes (585/750/925/950pt), so an order in any other
common alloy (333, 375, 900, 999, Ag800, ...) could never record a true
Feingehalt mark — DOM-22 called this out as "forces false records". This
module is the single source of the allowed vocabulary, built from
:class:`goldsmith_erp.db.models.AlloyType` (the same enum the Altgold /
scrap-gold valuation uses, see ``models/scrap_gold.py``), so a new alloy
only needs to be added once.

D-10 also softens the completion gate: an order may advance to COMPLETED
either with a verified Feingehalt mark, or with a documented
``"nicht punziert: <Grund>"`` entry (the piece was deliberately not
hallmarked — legal in Germany, but the reason must be on record). Both
paths are represented as strings in the same ``punzierung_verified_marks``
list so no schema change is needed.

Two Feingehalt spellings are accepted for the same alloy:

* the legacy wire code the PunzierungsCheckModal and Slice 5 tests already
  use (``"feingehalt_585"``, ...), kept for backward compatibility;
* the plain mark as it would actually be read off the piece (``"585"``,
  ``"Au585"``, ``"Ag925"``, ``"Pt950"``, ...), for any future caller (a
  hallmark-reading scanner, an import) that has no reason to know the
  legacy code.

Deliberately imported from ``models/order.py`` (a models module depending
on a services module, the reverse of the usual layering) because the
Pydantic vocabulary check and the alloy-derived mark table must never
drift apart — see the field_validator's docstring.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Optional

from goldsmith_erp.db.models import AlloyType

# --------------------------------------------------------------------------- #
# Feingehalt marks per alloy
# --------------------------------------------------------------------------- #

#: Legacy wire code per alloy (unchanged for the four alloys the modal
#: already supported; new codes follow the same "feingehalt_<fineness>"
#: shape, with "_ag" / "_pt" suffixes only where a bare fineness number is
#: ambiguous between gold and another metal).
LEGACY_FEINGEHALT_CODE: Dict[AlloyType, str] = {
    AlloyType.GOLD_999: "feingehalt_999",
    AlloyType.GOLD_900: "feingehalt_900",
    AlloyType.GOLD_750: "feingehalt_750",
    AlloyType.GOLD_585: "feingehalt_585",
    AlloyType.GOLD_375: "feingehalt_375",
    AlloyType.GOLD_333: "feingehalt_333",
    AlloyType.SILVER_999: "feingehalt_999_ag",
    AlloyType.SILVER_925: "feingehalt_925",
    AlloyType.SILVER_800: "feingehalt_800",
    AlloyType.PLATINUM_950: "feingehalt_950_pt",
}

#: One-letter metal prefix used by the plain mark spelling below (matches
#: the German hallmark convention: Au = Gold, Ag = Silber, Pt = Platin).
_METAL_PREFIX: Dict[AlloyType, str] = {
    AlloyType.GOLD_999: "Au",
    AlloyType.GOLD_900: "Au",
    AlloyType.GOLD_750: "Au",
    AlloyType.GOLD_585: "Au",
    AlloyType.GOLD_375: "Au",
    AlloyType.GOLD_333: "Au",
    AlloyType.SILVER_999: "Ag",
    AlloyType.SILVER_925: "Ag",
    AlloyType.SILVER_800: "Ag",
    AlloyType.PLATINUM_950: "Pt",
}

#: The bare fineness digits for each alloy (e.g. "585", "925", "950"). Both
#: ``AlloyType`` string values already are this for gold; silver/platinum
#: values carry the metal prefix, so they are derived here instead of read
#: off ``.value``.
_FINENESS_DIGITS: Dict[AlloyType, str] = {
    AlloyType.GOLD_999: "999",
    AlloyType.GOLD_900: "900",
    AlloyType.GOLD_750: "750",
    AlloyType.GOLD_585: "585",
    AlloyType.GOLD_375: "375",
    AlloyType.GOLD_333: "333",
    AlloyType.SILVER_999: "999",
    AlloyType.SILVER_925: "925",
    AlloyType.SILVER_800: "800",
    AlloyType.PLATINUM_950: "950",
}


def _raw_marks_for(member: AlloyType) -> FrozenSet[str]:
    """Plain marks a goldsmith could plausibly read off the piece."""
    digits = _FINENESS_DIGITS[member]
    prefix = _METAL_PREFIX[member]
    return frozenset({digits, f"{prefix}{digits}"})


#: Every plain (non-legacy-coded) Feingehalt mark accepted for each alloy.
RAW_FEINGEHALT_MARKS: Dict[AlloyType, FrozenSet[str]] = {
    member: _raw_marks_for(member) for member in AlloyType
}

#: Every accepted Feingehalt mark string, legacy code or plain, across all
#: alloys — the Pydantic validator's allow-list. Case-insensitive lookup is
#: applied by :func:`is_feingehalt_mark`; this set holds the canonical case.
ALL_FEINGEHALT_MARKS: FrozenSet[str] = frozenset(
    LEGACY_FEINGEHALT_CODE.values()
) | frozenset().union(*RAW_FEINGEHALT_MARKS.values())

_ALL_FEINGEHALT_MARKS_CASEFOLD: FrozenSet[str] = frozenset(
    m.casefold() for m in ALL_FEINGEHALT_MARKS
)

# --------------------------------------------------------------------------- #
# Marks unrelated to the Feingehalt (unchanged from the original vocabulary)
# --------------------------------------------------------------------------- #

ADDITIONAL_MARKS: FrozenSet[str] = frozenset(
    {"meisterzeichen", "herstellerzeichen", "laenderzeichen"}
)

# --------------------------------------------------------------------------- #
# D-10 soft-gate reason path
# --------------------------------------------------------------------------- #

#: A ``punzierung_verified_marks`` entry starting with this prefix records
#: that the piece was deliberately left unhallmarked, with the reason as
#: free text (hallmarking is voluntary under German law, but the decision
#: not to must be on record — DOM-22/23).
NICHT_PUNZIERT_PREFIX = "nicht punziert: "


def is_hallmark_reason_mark(mark: str) -> bool:
    """True for a well-formed ``"nicht punziert: <Grund>"`` entry."""
    if not mark.casefold().startswith(NICHT_PUNZIERT_PREFIX.casefold()):
        return False
    return len(mark[len(NICHT_PUNZIERT_PREFIX) :].strip()) > 0


def build_hallmark_reason_mark(reason: str) -> str:
    """The canonical ``punzierung_verified_marks`` entry for ``reason``."""
    return f"{NICHT_PUNZIERT_PREFIX}{reason.strip()}"


# --------------------------------------------------------------------------- #
# Lookup helpers
# --------------------------------------------------------------------------- #


def normalize_alloy(alloy: Optional[str]) -> Optional[AlloyType]:
    """Map a free-form ``Order.alloy`` string (e.g. "585", "Ag925", "Pt950",
    as offered by ``OrderFormModal.ALLOY_OPTIONS``) to its ``AlloyType``.

    Case-insensitive: the order form sends "Ag925"/"Pt950" (capitalised),
    while ``AlloyType``'s own values are lowercase ("ag925", "pt950").
    Returns ``None`` for an alloy the enum does not know (e.g. a bare 935 or
    an unset value) — callers must not treat that as a hard failure, only
    as "cannot narrow the vocabulary further".
    """
    if not alloy:
        return None
    stripped = alloy.strip().casefold()
    for member in AlloyType:
        if member.value.casefold() == stripped:
            return member
    return None


def feingehalt_mark_for_alloy(alloy: Optional[str]) -> Optional[str]:
    """The canonical (legacy-coded) Feingehalt mark for ``alloy``, if known."""
    member = normalize_alloy(alloy)
    if member is None:
        return None
    return LEGACY_FEINGEHALT_CODE[member]


def allowed_marks_for_alloy(alloy: Optional[str]) -> list[str]:
    """Every mark the PunzierungsCheckModal may offer for ``alloy``.

    Includes the matching Feingehalt mark first (when the alloy is known),
    then every other Feingehalt mark (a garbled ``Order.alloy`` must not
    lock the goldsmith out of every hallmark option), then the always-on
    additional marks. Does not include the ``nicht punziert`` reason path —
    that is a separate UI affordance, not a selectable mark.
    """
    matching = feingehalt_mark_for_alloy(alloy)
    ordered_feingehalt = (
        [matching, *(m for m in LEGACY_FEINGEHALT_CODE.values() if m != matching)]
        if matching
        else list(LEGACY_FEINGEHALT_CODE.values())
    )
    return [*ordered_feingehalt, *sorted(ADDITIONAL_MARKS)]


def is_feingehalt_mark(mark: str) -> bool:
    """True when ``mark`` is any recognised Feingehalt mark, for any alloy."""
    return mark.casefold() in _ALL_FEINGEHALT_MARKS_CASEFOLD


def is_valid_mark(mark: str) -> bool:
    """True when ``mark`` is acceptable in ``punzierung_verified_marks``:
    a Feingehalt mark (any alloy), an additional mark, or a ``nicht
    punziert: <Grund>`` entry."""
    if mark in ADDITIONAL_MARKS:
        return True
    if is_feingehalt_mark(mark):
        return True
    return is_hallmark_reason_mark(mark)


def satisfies_hallmark_requirement(marks: list[str]) -> bool:
    """True when ``marks`` documents the D-10 soft gate for COMPLETED:
    at least one real Feingehalt mark, or a documented ``nicht punziert``
    reason. A bare additional mark (Meisterzeichen etc.) alone is *not*
    enough — "Meisterzeichen allein ist kein Reinheits-Audit" (Thomas §3),
    the same principle the modal already enforces client-side.
    """
    return any(is_feingehalt_mark(m) or is_hallmark_reason_mark(m) for m in marks)
