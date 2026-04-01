"""
ML constants: feature names, target variable, column groupings, and thresholds.

These names are the authoritative identifiers used across feature_engineering.py,
encoders.py, and any downstream model training code.  Every key emitted by
FeatureEngineer maps to a name defined here.
"""

# ── Target variable ───────────────────────────────────────────────────────────
# Total productive labor hours recorded against the completed order.
TARGET_VARIABLE: str = "actual_hours"

# ── Minimum samples required before training is attempted ────────────────────
MIN_TRAINING_SAMPLES: int = 100

# ── Raw categorical columns (before one-hot expansion) ───────────────────────
CATEGORICAL_FEATURES: list[str] = [
    "order_type",
    "metal_type",
    "finish_type",
    "setting_type",
    "order_created_weekday",
    "order_created_month",
]

# ── Boolean columns ───────────────────────────────────────────────────────────
BOOLEAN_FEATURES: list[str] = [
    "has_engraving",
    "customer_is_repeat",
]

# ── Numeric columns ───────────────────────────────────────────────────────────
NUMERIC_FEATURES: list[str] = [
    "complexity_rating",
    "metal_weight_grams",
    "stone_count",
    "stone_total_carat",
    "deadline_in_days",
    "customer_previous_orders",
    "similar_orders_avg_hours",
    "user_avg_speed_ratio",
    "total_interruption_minutes",
    "seasonal_factor",
]

# ── One-hot expanded prefixes (used by encoders.py) ──────────────────────────
# After expansion the column names follow the pattern  <prefix>_<value>.
ONE_HOT_PREFIXES: dict[str, str] = {
    "order_type":  "order_type",
    "metal_type":  "metal_type",
    "finish_type": "finish_type",
}

# ── Feature importance ordering (from domain knowledge, not fitted model) ────
# Earlier = more predictive according to workshop experience.
DOMAIN_FEATURE_IMPORTANCE: list[str] = [
    "complexity_rating",
    "order_type",
    "stone_count",
    "metal_weight_grams",
    "similar_orders_avg_hours",
    "user_avg_speed_ratio",
    "stone_total_carat",
    "has_engraving",
    "deadline_in_days",
    "customer_previous_orders",
    "seasonal_factor",
    "total_interruption_minutes",
    "customer_is_repeat",
    "metal_type",
    "finish_type",
    "setting_type",
    "order_created_weekday",
    "order_created_month",
]

# ── Seasonal factors by month (1 = normal load, >1 = busier) ─────────────────
# Based on German goldsmith seasonal demand patterns.
SEASONAL_FACTORS: dict[int, float] = {
    1:  0.85,   # January  — quiet after Christmas
    2:  0.90,   # February — Valentine's spike mid-month
    3:  0.95,
    4:  1.00,
    5:  1.05,   # Mother's Day
    6:  1.10,   # Wedding season starts
    7:  1.15,   # Wedding season peak
    8:  1.10,   # Wedding season tail
    9:  1.00,
    10: 1.00,
    11: 1.20,   # Christmas pre-season
    12: 1.35,   # Christmas peak
}

# ── Inferred order types from title/description keywords ─────────────────────
ORDER_TYPE_KEYWORDS: dict[str, list[str]] = {
    "ring":     ["ring", "reif", "solitär", "verlobung", "ehering", "bandring"],
    "chain":    ["kette", "chain", "collier"],
    "pendant":  ["anhänger", "pendant", "medaillon"],
    "earrings": ["ohrring", "ohrstecker", "ohrhänger", "creole"],
    "bracelet": ["armband", "armreif", "bracelet"],
    "brooch":   ["brosche", "brooch", "anstecker"],
    "repair":   ["reparatur", "repair", "umarbeitung", "restauration", "löten"],
    "custom":   ["sonderanfertigung", "entwurf", "custom", "individuell", "neu"],
}
