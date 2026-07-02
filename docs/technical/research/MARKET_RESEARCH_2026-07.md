# Market Research: Jewelry Workshop Software (July 2026)

Research basis for the V1.1–V1.3 roadmap. Compiled 2026-07-02 from a structured
web-research pass (competitor scan, repair-tracking practice, approval-flow prior
art, cost-estimation approaches, consultation/intake patterns).

## 1. Competitor / Prior-Art Scan

| Product | Segment | Pricing | Covers | Worth stealing | Gap vs our vision |
|---|---|---|---|---|---|
| **PIRO Fusion/Retail** (gopiro.com) | US retail/manufacturer chains | not public | customer mgmt, memo/consignment inventory | memo/consignment model → maps to Altgold consignment | heavyweight, US-centric, no portal/QR/estimator |
| **Valigara** (valigara.com) | multichannel sellers | tiered, unpublished | spot-price-linked inventory valuation | real-time metal-price-linked pricing | catalog only — no workshop floor |
| **The Edge** (theedgeforjewelers.com) | US independent retailers | not public | CRM, repair tracking | KPI benchmarking sister product (2,000+ retailers) | on-prem, US-only, no photos/QR/portal |
| **Gem Logic** (gem-logic.com) | small–mid retail, 200+ shops | $299–$699+/mo | repair jobs, before/after photos, kanban, auto SMS/email status | photo repair tickets + automated status messages — closest to our update vision | no per-piece QR, no scrap inventory, no learning estimator |
| **Craftybase** (craftybase.com) | small-batch makers | $49–$349/mo | BOM material draw-down, true COGS | auto-costing on "manufacture" event — feeds a learning estimator | no customer-facing layer at all |
| **WinJewel** (winjewel.com) | small–mid retail, legacy | not public | customers, inventory, repairs | — | dated architecture |
| **JewelMate JM20** (logicmate.com) | mid–large wholesale | not public | barcode/RFID raw-metal tracking by purity | RFID/barcode variance reporting for stock counts | no small-workshop focus |
| **PrismaNote** (prismanote.de) — DACH | retail jeweler/goldsmith | €89–€199/mo + TSE | customers, repairs, photos, **Altgold module**, partial portal | Altgold as first-class module (validates our build) | no per-piece QR, no consultation capture, no estimator |
| **Joinpoints** (app.joinpoints.io) — DACH | small workshop/atelier | €24.99/user/mo + €250 setup | kanban jobs, before/after photos, **sketch attachment**, SMS/email pickup notices | sketch/markup attached inside the job pipeline — best intake overlap found | no material inventory, no portal, no estimator |
| **crystalworks.enterprise** (crystalworks.de) — DACH | retail, 420+ customers | not public | occasion-based CRM (birthdays, weddings) | occasion-triggered workflows | retail/POS-first, no workshop tracking |

Not verified as real/relevant products: CASH.Jewels, DiamantSoft, GemLogis
(diamond-testing hardware, not software), Combit (generic reporting component).

**Key takeaway:** no competitor unifies QR-per-piece + photo progress + customer
approval + learning estimator + Altgold + consultation capture. Joinpoints
(intake/photos), PrismaNote (Altgold/portal), and Craftybase (BOM costing) each
cover fragments. A self-improving estimator appears absent from the entire market.

## 2. Repair-Tracking Practice

- Job envelopes: digital "job envelopes" (Jewel360), barcode-printed physical
  repair envelopes (Jewelry Shopkeeper). Workbench (useworkbench.ca) captures
  notes/photos/signed terms at intake (200k+ images across 50k+ jobs) but tracks
  digitally only — no tag on the piece.
- QR/barcode is consistently applied to the *ticket/envelope/label*, not the
  piece. "Rat-tail" barcode label stock for rings exists
  (weprintbarcodes.com/jewelry-barcode-labels.html). **QR directly on the piece
  is an unclaimed differentiation angle** — we already do this on main.
- Photo intake as dispute mitigation is established practice: StoneBridge
  Jewelry's public checklist (prongs, pavé, engraving, hallmark, existing wear),
  Jewelers Mutual requires dated photos for claims, German Goldschmiede sources
  confirm before-photos "to protect both parties." (One blog citing dispute
  percentages had no citation trail — treat those numbers as marketing.)

## 3. Customer Approval Patterns

- Auto-repair SaaS (Tekmetric, Shopmonkey, AutoLeap, Mitchell1): digital
  inspection → **itemized line-by-line approve/decline** → delivered as SMS/email
  link, *no portal login* → e-signature with verbal/phone/paper fallback →
  instant shop notification. Declined items stay on the customer profile for
  later follow-up.
- No tool confirmed to have an explicit "revised estimate re-approval" screen;
  mid-job changes are added as new line items. **Construction change orders are
  the better model** for cost overruns: description / justification / cost impact,
  sequential e-signature, version-controlled audit trail with the prior state
  visible.

### German legal framework (verified at gesetze-im-internet.de)

- The rule lives at **§649 BGB "Kostenanschlag"** (renumbered in the 2018
  Bauvertragsrecht reform — many sources still cite the old §650).
- A Kostenvoranschlag is **non-binding by default**; binding requires an explicit
  Festpreis commitment. Presumed free of charge (§632 Abs. 3 BGB).
- If a *substantial* overrun becomes foreseeable, the contractor has an
  **Anzeigepflicht** — notify the customer *unverzüglich*. Failing to notify
  gives the customer leverage to refuse the excess (doctrinal mechanism varies
  by source — moderate confidence).
- No statutory percentage for "wesentlich"; Verbraucherzentrale/IHK/HWK guidance
  commonly cites **~15–20%**, courts also weigh the absolute Euro amount.
- Sources: gesetze-im-internet.de/bgb/__649.html; verbraucherzentrale.de
  (Handwerker-Auftrag guidance); hwk-rhein-main.de Kostenvoranschlag PDF.

**Product implication:** the overrun-notification workflow is a *compliance
feature* ("this tool keeps you legally safe"), not just UX.

## 4. Cost Estimation

- Established PM vocabulary: **analogous estimating** (similar-past-job sizing)
  → **parametric estimating** (statistical, once data accumulates). A "learning"
  estimator that matures along this path is rigorous and explainable — no ML
  black box needed.
- Job-shop ERPs (Craftybase, Katana, JobBOSS², Fulcrum, KipwareQTE) do
  time+material rollup and estimate-vs-actual *reporting*, but no automatic
  feedback loop into future estimates.
- ML estimators exist outside jewelry (Machine Research — trains on a shop's own
  actuals; DigiFabster; Xometry). A 2024 ScienceDirect paper covers ML costing
  for engineered-to-order products with **sparse data** — the small-workshop case.
- **No jewelry-specific learning estimator found. Genuine market gap.**
- Metal price APIs (EUR): **MetalpriceAPI** (100 req/mo free → $5+/mo),
  Metals-API.com, GoldAPI.io (limits unverified — check before integrating).
  **Deutsche Bundesbank** publishes a free authoritative daily gold reference
  price via SDMX REST API — daily-lagged, which is fine for workshop quoting.

## 5. Consultation / Intake

- **No purpose-built jewelry consultation-intake product exists.** Closest:
  CounterSketch (Gemvision/Stuller) — collaborative CAD sales tool, not
  structured intake.
- Best transferable patterns from adjacent industries: tattoo consultation apps
  (InkHunter AR preview; Tattoo Studio Pro structured consent/intake tied to
  client profiles) and Morpholio Trace (sketch-over-photo annotation with Apple
  Pencil).
- Ring sizing: **ISO 8653:2016** — size = inner circumference in mm (size 50 =
  50 mm). German practice matches ISO. US size ≈ (circumference_mm − 36.5) / 2.55.
- "Style profile / no-gos": **no established standard anywhere** — adjacent apps
  capture metal preference, allergy flags (nickel), stone type, budget tier.
  Greenfield: safe to design from scratch.

## Top 12 ideas worth adopting

1. Photo-based job tickets + automated email status updates (Gem Logic).
2. Altgold as a first-class module (PrismaNote — validates what we built).
3. Sketch/markup attached inside the job record, not a separate file (Joinpoints).
4. BOM-driven auto-costing on completion events feeds the estimator (Craftybase).
5. Itemized per-line approve/decline; declined items retained for follow-up
   (Shopmonkey/Tekmetric).
6. Construction-style change-order presentation for cost overruns (what changed,
   why, prior state visible, timestamped decision).
7. Analogous → parametric estimating framework for the "learning" estimator.
8. QR on the physical piece, not just the ticket (no competitor confirmed doing it).
9. Mandatory photo-intake checklist (prongs, pavé, engraving, hallmark, wear).
10. §649 BGB overrun workflow as a marketed compliance feature (~15–20% alert).
11. Occasion-based CRM triggers (birthdays, wedding dates) — cheap retention.
12. Sketch-over-photo annotation UX from Morpholio Trace (future drawing canvas).

## Confidence flags

Weakest evidence: (a) explicit "re-approval on cost change" screens in
auto-repair SaaS (inferred), (b) exact §649 BGB remedy for failure to notify
(moderate), (c) free-tier limits of GoldAPI.io/Metals-API (unverified).
"Style profile/no-gos" and "jewelry sketch consultation" returned thin results
industry-wide — validated white space, not a research gap.
