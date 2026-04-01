"""
Categorical encoding utilities for ML feature vectors.

All functions return flat dicts whose keys follow the pattern
<prefix>_<value> so they can be merged directly into a feature dict
and later converted to a pandas DataFrame column per key.

Unknown categories are handled gracefully: every known value gets a 0,
and the unknown indicator column gets a 1.
"""

from __future__ import annotations

# ── Known category vocabularies ───────────────────────────────────────────────

KNOWN_ORDER_TYPES: list[str] = [
    "ring",
    "chain",
    "pendant",
    "earrings",
    "bracelet",
    "brooch",
    "repair",
    "custom",
]

KNOWN_METAL_TYPES: list[str] = [
    "gold_24k",
    "gold_22k",
    "gold_18k",
    "gold_14k",
    "gold_9k",
    "silver_999",
    "silver_925",
    "silver_800",
    "platinum_950",
    "platinum_900",
    "palladium",
    "white_gold_18k",
    "white_gold_14k",
    "rose_gold_18k",
    "rose_gold_14k",
]

KNOWN_ACTIVITY_TYPES: list[str] = [
    "fabrication",
    "setting",
    "polishing",
    "engraving",
    "casting",
    "soldering",
    "filing",
    "administration",
    "waiting",
    "quality_check",
    "repair",
    "consultation",
]

KNOWN_FINISH_TYPES: list[str] = [
    "polished",
    "matte",
    "brushed",
    "hammered",
    "sandblasted",
    "rhodium_plated",
    "oxidized",
    "unknown",
]

KNOWN_SETTING_TYPES: list[str] = [
    "prong",
    "bezel",
    "channel",
    "pave",
    "bar",
    "flush",
    "tension",
    "cluster",
    "invisible",
    "unknown",
]


# ── Internal helper ───────────────────────────────────────────────────────────

def _one_hot(
    value: str | None,
    known_values: list[str],
    prefix: str,
) -> dict[str, int]:
    """
    Produce a one-hot dict for *value* over *known_values*.

    - If value is None or empty, all columns are 0 and
      ``<prefix>_unknown`` is set to 1.
    - If value is not in the vocabulary, all known columns are 0
      and ``<prefix>_unknown`` is set to 1.
    - ``<prefix>_unknown`` is always present in the output so that
      downstream code can rely on a fixed column count.
    """
    result: dict[str, int] = {f"{prefix}_{v}": 0 for v in known_values}
    result[f"{prefix}_unknown"] = 0

    if not value:
        result[f"{prefix}_unknown"] = 1
        return result

    normalised = value.strip().lower()
    if normalised in known_values:
        result[f"{prefix}_{normalised}"] = 1
    else:
        result[f"{prefix}_unknown"] = 1

    return result


# ── Public encoding functions ─────────────────────────────────────────────────

def encode_order_type(order_type: str | None) -> dict[str, int]:
    """
    One-hot encode an order type string.

    Returns a dict with keys ``order_type_ring``, ``order_type_chain``,
    ..., ``order_type_custom``, ``order_type_unknown``.
    """
    return _one_hot(order_type, KNOWN_ORDER_TYPES, "order_type")


def encode_metal_type(metal_type: str | None) -> dict[str, int]:
    """
    One-hot encode a metal type string (matches MetalType enum values).

    Returns a dict with keys ``metal_type_gold_18k``,
    ``metal_type_silver_925``, ..., ``metal_type_unknown``.
    """
    return _one_hot(metal_type, KNOWN_METAL_TYPES, "metal_type")


def encode_activity_type(activity_type: str | None) -> dict[str, int]:
    """
    One-hot encode an Activity.category value.

    Returns a dict with keys ``activity_type_fabrication``,
    ``activity_type_setting``, ..., ``activity_type_unknown``.
    """
    return _one_hot(activity_type, KNOWN_ACTIVITY_TYPES, "activity_type")


def encode_finish_type(finish_type: str | None) -> dict[str, int]:
    """
    One-hot encode a finish type string derived from order description.

    Returns a dict with keys ``finish_type_polished``,
    ``finish_type_matte``, ..., ``finish_type_unknown``.
    """
    return _one_hot(finish_type, KNOWN_FINISH_TYPES, "finish_type")


def encode_setting_type(setting_type: str | None) -> dict[str, int]:
    """
    One-hot encode a Gemstone.setting_type value.

    When an order has multiple gemstones with different settings, the
    dominant setting (most common) should be passed here.

    Returns a dict with keys ``setting_type_prong``,
    ``setting_type_bezel``, ..., ``setting_type_unknown``.
    """
    return _one_hot(setting_type, KNOWN_SETTING_TYPES, "setting_type")
