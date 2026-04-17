#!/usr/bin/env python3
"""
Generate the 10 synthetic QR-code fixtures used by the V1.1 alloy-
mismatch smoke test (A13.4 / spec §14.a row c).

Run from the repo root:
    poetry run python docs/field-test-kit/V1.1-synthetic-qr-fixtures/generate.py

Outputs PNG + accompanying README rows + a CSV that an automated
dogfood runner can consume. The fixtures are deterministic: re-running
the script produces byte-identical files. Add to version control so the
repo carries its own test inputs.

Each fixture is a *pair* — an ORDER scan then a METAL scan whose
alloys mismatch. The expected UI behaviour is identical for all 10:
AlloyMismatchModal opens on scan of the METAL code while the timer on
the ORDER is active.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import segno  # 1.6+ (Poetry dep; see pyproject.toml)

# Each row: (scenario_id, order_id, order_alloy, metal_id, metal_alloy, description_de)
FIXTURES: list[tuple[str, int, str, int, str, str]] = [
    ("01-750gg-vs-585rg",  701, "750_GG",     1,  "585_RG",  "Auftrag 18k Gelbgold vs. Material 14k Rotgold"),
    ("02-925-vs-750wg",    702, "925_AG",     2,  "750_WG",  "Auftrag Sterlingsilber vs. Material 18k Weissgold"),
    ("03-585rg-vs-750gg",  703, "585_RG",     3,  "750_GG",  "Auftrag 14k Rotgold vs. Material 18k Gelbgold"),
    ("04-pt950-vs-750gg",  704, "950_PT",     4,  "750_GG",  "Auftrag Platin vs. Material 18k Gelbgold"),
    ("05-750wg-vs-585gg",  705, "750_WG",     5,  "585_GG",  "Auftrag 18k Weissgold vs. Material 14k Gelbgold"),
    ("06-585gg-vs-585rg",  706, "585_GG",     6,  "585_RG",  "Auftrag 14k Gelbgold vs. Material 14k Rotgold (Farbdifferenz)"),
    ("07-925-vs-585rg",    707, "925_AG",     7,  "585_RG",  "Auftrag Silber vs. Material Rotgold"),
    ("08-375-vs-585",      708, "375_GG",     8,  "585_GG",  "Auftrag 9k Gelbgold vs. Material 14k Gelbgold (Feingehalt)"),
    ("09-999-vs-925",      709, "999_AG",     9,  "925_AG",  "Auftrag Feinsilber vs. Material Sterlingsilber"),
    ("10-pd-vs-pt",        710, "PD_950",    10,  "950_PT",  "Auftrag Palladium vs. Material Platin"),
]

HERE = Path(__file__).resolve().parent


def make_qr(payload: str, out_path: Path) -> None:
    """Render a QR PNG.

    `scale=8` gives ~250px width which prints nicely at 12mm on matte
    label stock. `border=2` matches the Avery L7160 margin tolerance.
    """
    qr = segno.make(payload, error="M")
    qr.save(str(out_path), scale=8, border=2)


def main() -> int:
    csv_rows = [
        [
            "scenario_id",
            "order_png",
            "order_payload",
            "order_alloy",
            "metal_png",
            "metal_payload",
            "metal_alloy",
            "description_de",
            "expected_behavior",
        ]
    ]
    for scenario_id, order_id, o_alloy, metal_id, m_alloy, desc in FIXTURES:
        order_payload = f"ORDER:{order_id}"
        metal_payload = f"METAL:{metal_id}"
        order_png = HERE / f"{scenario_id}.order.png"
        metal_png = HERE / f"{scenario_id}.metal.png"
        make_qr(order_payload, order_png)
        make_qr(metal_payload, metal_png)
        csv_rows.append(
            [
                scenario_id,
                order_png.name,
                order_payload,
                o_alloy,
                metal_png.name,
                metal_payload,
                m_alloy,
                desc,
                "AlloyMismatchModal erscheint nach METAL-Scan",
            ]
        )

    csv_path = HERE / "expected-behavior.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerows(csv_rows)

    print(f"Wrote {len(FIXTURES) * 2} PNG files + 1 CSV to {HERE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
