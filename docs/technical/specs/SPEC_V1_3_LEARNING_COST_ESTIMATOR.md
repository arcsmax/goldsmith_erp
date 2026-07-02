# SPEC V1.3 — Learning Cost Estimator (Lernender Kostenkalkulator)

Status: **Draft — pending review**
Date: 2026-07-02
Depends on: existing CostCalculationService, MetalPriceHistory, TimeEntry,
DurationPredictor (`ml/duration_model.py`), Quote; V1.2's projected-cost
service (shared rollup logic)

## Goal

A quote in minutes, during the consultation, that gets better with every
completed job: live metal prices + labor estimated from the workshop's own
history of similar pieces — transparent enough to show the customer.

Decision (Max, 2026-07-02): **statistical, not ML**. We follow the
analogous → parametric estimating path (research doc §4): start with
"median of similar past jobs," graduate to parametric factors only when data
volume justifies it. No jewelry competitor has this (validated market gap).

## Part A — Live metal prices

- **Primary source: Deutsche Bundesbank** daily gold reference price via free
  SDMX REST API — authoritative, EUR-native, no key, daily granularity
  (sufficient for workshop quoting). **Secondary (optional, keyed):
  MetalpriceAPI** for silver/platinum/palladium and intraday needs; free tier
  100 req/mo covers 1 fetch/day with slack. Config chooses sources; both
  write to the existing `MetalPriceHistory` with their existing
  `MetalPriceSource` enum values (extend enum: BUNDESBANK, METALPRICE_API).
- `MetalPriceSyncService` + scheduled job (APScheduler in-process, container-
  friendly; runs at startup + daily 09:00) — fetch, validate (sanity band vs
  previous price ±20%, else flag & keep manual), store, publish notification
  on failure. Manual entry stays as fallback (fail loudly, degrade gracefully).
- Alloy math: fine-price × Feingehalt (585/750/925…) + configurable
  Verarbeitungszuschlag per alloy — extends existing calculator inputs,
  replaces its "hardcoded/manual price" gap (SPEC_V2 open question #1).

## Part B — Labor estimation from history (the "learning" part)

### Data

Source of truth: completed orders with (a) tracked billable time rolled up
per activity, (b) order features already stored — `order_type`,
`finish_type`, `alloy`, `ring_size_mm`, gemstone count, repair vs custom.
V1.1 consultations add materials/complexity signals over time.

### Method (v1: analogous estimating)

`LaborEstimator.estimate(features) →`

```
{
  hours_p50, hours_p20, hours_p80,     # median + range of similar jobs
  sample_size, similarity_level,        # exact-match tier or relaxed tier
  similar_orders: [ids],                # explainability: "based on these 7 rings"
  suggested_activities: [{activity, median_hours}],  # per-activity breakdown
}
```

Similarity tiers, relaxing until `sample_size >= 5` (else return
`insufficient_data` and fall back to manual — never fake confidence):

1. same order_type + finish_type + stone-setting present/absent
2. same order_type + finish_type
3. same order_type
4. all completed orders (only as visible "workshop average", never auto-filled)

Reuses/extends `DurationPredictor.find_similar_orders` rather than a parallel
implementation. Pure SQL/pandas percentiles — no model training, explainable
by construction ("Median von 7 ähnlichen Aufträgen: 6,5 h [4,0–9,0]").

### Learning loop

- On order completion: snapshot `estimated_hours` (from quote) vs
  `actual_hours` (time rollup) into new table `EstimateAccuracy`
  (order_id, estimated_hours, actual_hours, estimated_total, actual_total,
  estimator_version, created_at). This is the Craftybase-style
  "auto-cost on completion event" (research doc idea #4).
- Calibration view: rolling MAPE + bias (are we systematically under-quoting
  stone setting?) per order_type. Surfaced on a small dashboard card —
  every metric links to the orders behind it.
- The goldsmith's manual adjustment of a suggestion is itself signal: store
  `suggested_hours` vs `quoted_hours` on the quote to measure trust over time.
- Parametric upgrade (V2.x, explicitly out of scope now): fit simple factors
  (e.g. +x h per stone) once `EstimateAccuracy` has ≥100 rows.

## Part C — Quote builder integration

- Quote form gains an "Kalkulation" panel: live metal price (with date + source
  badge), weight input → material line auto-computed; labor line shows the
  estimator suggestion with range + "basierend auf N ähnlichen Aufträgen"
  (tap to see them) + one-tap accept or manual override; stones/findings lines;
  margin + VAT as today.
- Designed to be **customer-presentable** during the V1.1 consultation
  (conversion flow pre-fills features from the consultation).
- Confidence honesty: below 5 similar jobs the panel says so and shows the
  workshop-average as reference only.

## API

- `GET /metal-prices/current?metal=&alloy=` (computed alloy price)
- `POST /metal-prices/sync` (manual trigger, ADMIN)
- `POST /estimates/labor` body = feature set → estimator response
- `GET /estimates/accuracy` (calibration dashboard data, ADMIN/GOLDSMITH)
- All financial → existing financial-data permissions + audit logging.

## Failure modes

- Price API down: use last stored price, badge shows its age; warn when >7 days
  stale. Never block quoting.
- Insufficient history: explicit `insufficient_data`, manual entry, no silent
  workshop-average auto-fill.
- Time-tracking gaps (untracked work would poison the loop): completion
  snapshot flags orders whose tracked hours are implausibly low
  (< P10 of similar) and excludes them from the estimator corpus with a
  visible "excluded, why" list — bad data must not silently teach the system.

## Testing

- Unit: alloy math, similarity-tier relaxation, percentile math with small N,
  sanity-band price validation, corpus exclusion rules.
- Integration: sync job writes MetalPriceHistory + failure notification path;
  completion event writes EstimateAccuracy; estimator endpoint permission
  matrix.
- Golden dataset test: seeded synthetic order history with known percentiles →
  estimator returns expected values (regression guard for the math).

## Open questions

1. Hourly rate(s): move to per-activity rates here? (V1.2 proposed a single
   shop rate; estimator per-activity breakdown makes per-activity rates
   natural — decide with Anne.)
2. Bundesbank covers gold; silver/platinum need MetalpriceAPI (key, free tier)
   — is a free-tier signup acceptable, or manual entry for non-gold?
3. Should the customer-facing quote show the labor *range* or a single number?
   (Proposed: single number on the document, range only in the internal UI.)
