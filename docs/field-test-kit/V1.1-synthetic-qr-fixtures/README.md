# Synthetic QR Fixtures (Slice 13 / A13.4)

Ten curated alloy-mismatch scenarios used by the V1.1 alloy-mismatch
smoke test (spec §14.a row c). Each scenario is a **pair** of QR codes
— one ORDER, one METAL — whose alloys do not agree. The expected UI
behaviour for every pair is identical: scanning the METAL code while a
timer is running on the ORDER must open `AlloyMismatchModal`.

## Contents

- `generate.py` — deterministic regenerator (segno). Run with
  `poetry run python docs/field-test-kit/V1.1-synthetic-qr-fixtures/generate.py`
  from the repo root. Re-running is a no-op unless the script changes.
- `NN-<scenario>.order.png` — QR encoding `ORDER:<id>`.
- `NN-<scenario>.metal.png` — QR encoding `METAL:<id>`.
- `expected-behavior.csv` — machine-readable manifest an automated
  dogfood runner can iterate over.

## How to use

### Manual (workshop)

1. Print the 20 PNGs on **matte** label stock (Avery L7160 or equiv.).
   Glossy/foil labels break QR decoding under LED workshop lighting
   (A8.4 / Thomas §2 step 1).
2. For each scenario `NN`:
   1. Seed the test database so `ORDER:<id>` exists with
      `alloy=<order_alloy>` and `METAL:<id>` points at a purchase with
      `alloy=<metal_alloy>`. Seed values live in the CSV.
   2. Open the app as a GOLDSMITH; scan the ORDER label (timer starts).
   3. Scan the METAL label. `AlloyMismatchModal` must appear.
   4. Record pass/fail in `dogfood-log.csv`.

**Stop-ship trigger (spec §14.a row c):** any single scenario that does
NOT fire the modal is a hard ship blocker.

### Automated

The CSV has columns:

| Column              | Meaning                                              |
|---------------------|------------------------------------------------------|
| scenario_id         | `NN-shortdesc`, also the PNG basename stem           |
| order_png           | file name of the ORDER QR image                      |
| order_payload       | literal QR payload string (e.g. `ORDER:701`)         |
| order_alloy         | expected `orders.alloy` for the seed                 |
| metal_png           | file name of the METAL QR image                      |
| metal_payload       | literal QR payload string (e.g. `METAL:1`)           |
| metal_alloy         | expected `metal_purchases.alloy` for the seed        |
| description_de      | workshop-facing scenario description (German)       |
| expected_behavior   | pass condition string                                |

A Playwright / integration smoke-harness can read `order_payload` +
`metal_payload` directly (skipping image decoding) to stress the
`AlloyMismatchModal` logic without hardware.

## Seeding

Fixtures assume `orders.alloy` and `metal_purchases.alloy` columns are
populated by the test seed. Seed SQL for these rows is NOT shipped here
because the seed pipeline varies by environment (integration fixtures
vs. shell-db paste). Copy the CSV into a spreadsheet and generate the
required `INSERT` statements against the current `orders` /
`metal_purchases` schemas.

## Labels for the workshop

Bring the printed sheet to Meister Thomas's workshop. One sheet (20
labels) suffices for the week-1 field-test session. Store with the rest
of the V1.1 field-test kit (cable, backup scanner, matte stock extras).
