# mypy Strict-Mode Burndown

The CI `lint` job runs `mypy goldsmith_erp/ --ignore-missing-imports` in
**strict mode** (`[tool.mypy] strict = true` in the root `pyproject.toml`). The
codebase carries a large volume of pre-existing type debt (~1.5k errors across
~100 modules). Fixing it in one heroic pass is impractical and risky; the
[2026-07-26 production-readiness audit](../review/2026-07-26/production-readiness.md)
(Tier 3) prescribes **a per-module baseline / gate-on-diff strategy** instead.

This document describes that baseline and how to burn it down.

## How the gate works

Rather than a blanket `ignore_errors = true` (which would blind us to *all*
type errors in a module forever), the baseline records — **per module** — only
the specific error **codes** that module currently emits, as
`[[tool.mypy.overrides]]` blocks in `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = "goldsmith_erp.api.routers.repairs"
disable_error_code = ["arg-type", "assignment", "attr-defined", "misc", "no-untyped-def"]
```

Consequences:

- **Currently-passing modules stay fully strict.** They have no override block.
- **New modules are strict by default.** Anything not listed is fully checked.
- **A baselined module is only excused for the codes it already trips.** If you
  introduce a *new* class of error — say a `[return-value]` bug in a module that
  was only baselined for `[assignment]` — mypy still fails CI. The gate protects
  new code without forcing a full-repo fix first.

This is strictly stronger than `ignore_errors` and requires no change to the CI
workflow or the mypy invocation — it is pure `pyproject.toml` configuration that
mypy (run from `./src`; it walks up to the root `pyproject.toml`) already honors.

### No module is fully waived

No module uses `ignore_errors = true`. Even `db/models.py` (the largest debt,
~160 errors) is baselined by explicit code list, so a brand-new *kind* of type
error there is still caught. If a module ever becomes genuinely hopeless it
should be discussed and documented here before switching to `ignore_errors`.

## The rule: touch a module, try to shrink the baseline

> **When you modify a module that has an override block, attempt to remove it
> from the baseline** (or at least drop some of its `disable_error_code`
> entries). Add real type annotations, then delete the codes you fixed. If the
> block's list becomes empty, delete the whole block. Never *add* a code to an
> existing block to make new code pass — fix the new code instead.

Because a baselined module still fails on *new* error codes, the gate naturally
pressures debt downward over time as modules get touched.

## Per-module debt table

The table below is generated. Regenerate it (and the `pyproject.toml` blocks)
after any change that affects the error set:

```bash
poetry install                                   # once, in a fresh checkout
poetry run python scripts/gen_mypy_baseline.py   # rewrites pyproject.toml + this table
```

The generator runs mypy exactly as CI does, starts from an empty baseline (so it
sees the true error set), and iterates to a fixpoint (disabling a code can turn
a previously-used inline `# type: ignore` into an `unused-ignore`, which the
next pass folds in). A read-only drift check for CI:

```bash
poetry run python scripts/gen_mypy_baseline.py --check   # non-zero if stale
```

<!-- BEGIN generated mypy baseline table -->
_Auto-generated: 94 modules, 1524 suppressed errors. Regenerate with `poetry run python scripts/gen_mypy_baseline.py`._

| Module | Errors | Codes suppressed |
| --- | ---: | --- |
| `goldsmith_erp.db.models` | 159 | `valid-type`×44, `misc`×44, `no-untyped-call`×38, `no-untyped-def`×13, `assignment`×9, `arg-type`×7, `return-value`×4 |
| `goldsmith_erp.api.routers.metal_inventory` | 78 | `arg-type`×70, `no-untyped-def`×8 |
| `goldsmith_erp.services.comparison_service` | 67 | `arg-type`×40, `call-arg`×15, `assignment`×5, `index`×5, `operator`×2 |
| `goldsmith_erp.api.routers.repairs` | 64 | `arg-type`×19, `misc`×18, `no-untyped-def`×17, `assignment`×9, `attr-defined`×1 |
| `goldsmith_erp.services.customer_service` | 64 | `assignment`×29, `attr-defined`×18, `arg-type`×11, `no-untyped-call`×2, `no-untyped-def`×1, `type-arg`×1, `call-overload`×1, `var-annotated`×1 |
| `goldsmith_erp.services.pdf_service` | 50 | `arg-type`×49, `no-any-return`×1 |
| `goldsmith_erp.api.routers.ml` | 45 | `arg-type`×18, `misc`×9, `unused-ignore`×7, `type-arg`×4, `index`×4, `no-any-return`×1, `no-untyped-def`×1, `assignment`×1 |
| `goldsmith_erp.services.consultation_service` | 44 | `call-arg`×22, `assignment`×12, `comparison-overlap`×4, `arg-type`×4, `no-untyped-def`×2 |
| `goldsmith_erp.api.routers.time_tracking` | 34 | `misc`×15, `no-untyped-def`×14, `arg-type`×3, `assignment`×2 |
| `goldsmith_erp.api.routers.materials` | 33 | `misc`×11, `no-untyped-def`×10, `call-arg`×8, `attr-defined`×3, `return-value`×1 |
| `goldsmith_erp.services.metal_inventory_service` | 33 | `arg-type`×23, `assignment`×8, `operator`×2 |
| `goldsmith_erp.services.handoff_service` | 32 | `union-attr`×18, `assignment`×7, `arg-type`×5, `return-value`×2 |
| `goldsmith_erp.api.routers.quotes` | 31 | `misc`×13, `no-untyped-def`×13, `arg-type`×3, `assignment`×2 |
| `goldsmith_erp.api.routers.customer_updates` | 29 | `misc`×10, `no-untyped-def`×10, `arg-type`×9 |
| `goldsmith_erp.api.routers.comments` | 28 | `arg-type`×20, `misc`×4, `no-untyped-def`×4 |
| `goldsmith_erp.services.quote_service` | 27 | `arg-type`×15, `assignment`×9, `type-arg`×2, `return-value`×1 |
| `goldsmith_erp.api.routers.scrap_gold` | 26 | `misc`×10, `no-untyped-def`×10, `arg-type`×5, `assignment`×1 |
| `goldsmith_erp.services.time_tracking_service` | 26 | `arg-type`×14, `union-attr`×4, `return-value`×3, `assignment`×2, `truthy-function`×2, `operator`×1 |
| `goldsmith_erp.api.routers.consultations` | 25 | `misc`×11, `no-untyped-def`×11, `arg-type`×2, `attr-defined`×1 |
| `goldsmith_erp.api.routers.orders` | 25 | `no-untyped-def`×11, `misc`×11, `arg-type`×3 |
| `goldsmith_erp.api.routers.customers` | 24 | `no-untyped-def`×16, `assignment`×4, `attr-defined`×1, `type-arg`×1, `return-value`×1, `arg-type`×1 |
| `goldsmith_erp.api.routers.invoices` | 23 | `misc`×9, `no-untyped-def`×9, `arg-type`×3, `assignment`×2 |
| `goldsmith_erp.db.repositories.customer` | 23 | `arg-type`×13, `assignment`×6, `no-untyped-def`×3, `override`×1 |
| `goldsmith_erp.services.label_service` | 23 | `attr-defined`×15, `unused-ignore`×8 |
| `goldsmith_erp.services.notification_service` | 21 | `arg-type`×17, `assignment`×4 |
| `goldsmith_erp.api.routers.users` | 20 | `no-untyped-def`×10, `misc`×8, `arg-type`×2 |
| `goldsmith_erp.services.scanner_service` | 18 | `arg-type`×13, `call-overload`×4, `union-attr`×1 |
| `goldsmith_erp.services.invoice_service` | 17 | `arg-type`×9, `assignment`×5, `type-arg`×2, `return-value`×1 |
| `goldsmith_erp.api.routers.handoffs` | 15 | `misc`×5, `no-untyped-def`×5, `arg-type`×4, `call-arg`×1 |
| `goldsmith_erp.api.routers.notifications` | 15 | `misc`×6, `arg-type`×4, `type-arg`×3, `return-value`×1, `unused-ignore`×1 |
| `goldsmith_erp.core.permissions` | 14 | `no-untyped-def`×8, `type-arg`×5, `call-overload`×1 |
| `goldsmith_erp.services.order_service` | 14 | `arg-type`×5, `return-value`×3, `type-arg`×1, `var-annotated`×1, `operator`×1, `assignment`×1, `no-untyped-def`×1, `unused-ignore`×1 |
| `goldsmith_erp.api.routers.activities` | 13 | `misc`×6, `no-untyped-def`×6, `assignment`×1 |
| `goldsmith_erp.api.routers.measurements` | 13 | `no-untyped-def`×6, `arg-type`×6, `attr-defined`×1 |
| `goldsmith_erp.api.routers.photos` | 13 | `misc`×5, `no-untyped-def`×5, `arg-type`×2, `attr-defined`×1 |
| `goldsmith_erp.db.repositories.order` | 13 | `assignment`×6, `arg-type`×3, `no-untyped-def`×2, `union-attr`×2 |
| `goldsmith_erp.services.file_erasure_service` | 13 | `attr-defined`×5, `arg-type`×4, `type-arg`×2, `return-value`×1, `var-annotated`×1 |
| `goldsmith_erp.middleware.rate_limiting` | 12 | `union-attr`×5, `type-arg`×2, `no-untyped-call`×2, `no-any-return`×2, `no-untyped-def`×1 |
| `goldsmith_erp.ml.anomaly_detection` | 12 | `type-arg`×3, `assignment`×3, `arg-type`×3, `attr-defined`×2, `index`×1 |
| `goldsmith_erp.ml.feature_engineering` | 12 | `arg-type`×8, `assignment`×2, `no-any-return`×1, `misc`×1 |
| `goldsmith_erp.services.cost_calculation_service` | 12 | `assignment`×5, `arg-type`×4, `return-value`×2, `no-any-return`×1 |
| `goldsmith_erp.services.repair_service` | 12 | `assignment`×8, `arg-type`×2, `type-arg`×1, `call-overload`×1 |
| `goldsmith_erp.services.user_service` | 11 | `arg-type`×8, `attr-defined`×2, `return-value`×1 |
| `goldsmith_erp.api.routers.calendar` | 10 | `misc`×6, `unused-ignore`×3, `arg-type`×1 |
| `goldsmith_erp.middleware.audit_logging` | 10 | `no-any-return`×5, `type-arg`×3, `unused-ignore`×1, `no-untyped-def`×1 |
| `goldsmith_erp.services.hallmark_service` | 10 | `assignment`×9, `call-overload`×1 |
| `goldsmith_erp.api.routers.customer_portal` | 9 | `call-overload`×4, `type-arg`×2, `arg-type`×2, `no-any-return`×1 |
| `goldsmith_erp.api.routers.hallmarks` | 9 | `misc`×6, `no-untyped-def`×2, `arg-type`×1 |
| `goldsmith_erp.api.routers.metal_types` | 9 | `arg-type`×6, `type-arg`×2, `assignment`×1 |
| `goldsmith_erp.api.routers.valuations` | 9 | `misc`×5, `no-untyped-def`×2, `arg-type`×2 |
| `goldsmith_erp.db.repositories.base` | 9 | `attr-defined`×6, `no-untyped-def`×2, `no-any-return`×1 |
| `goldsmith_erp.api.routers.scanner` | 8 | `misc`×5, `arg-type`×3 |
| `goldsmith_erp.db.seed_data` | 8 | `type-arg`×6, `no-untyped-def`×1, `no-untyped-call`×1 |
| `goldsmith_erp.jobs.gdpr_cleanup` | 8 | `attr-defined`×8 |
| `goldsmith_erp.db.migration_helpers` | 7 | `no-untyped-call`×5, `no-untyped-def`×1, `type-arg`×1 |
| `goldsmith_erp.services.calendar_service` | 7 | `arg-type`×4, `assignment`×2, `unused-ignore`×1 |
| `goldsmith_erp.services.ml_data_service` | 7 | `union-attr`×4, `assignment`×1, `type-arg`×1, `list-item`×1 |
| `goldsmith_erp.services.scrap_gold_service` | 7 | `assignment`×5, `no-untyped-def`×1, `arg-type`×1 |
| `goldsmith_erp.core.security` | 6 | `no-any-return`×4, `type-arg`×2 |
| `goldsmith_erp.db.types` | 6 | `no-untyped-call`×2, `no-any-return`×2, `type-arg`×1, `no-untyped-def`×1 |
| `goldsmith_erp.services.no_go_service` | 6 | `arg-type`×5, `assignment`×1 |
| `goldsmith_erp.api.routers.estimator` | 5 | `misc`×2, `no-untyped-def`×2, `arg-type`×1 |
| `goldsmith_erp.core.encryption` | 5 | `type-arg`×2, `no-untyped-def`×1, `assignment`×1, `no-untyped-call`×1 |
| `goldsmith_erp.main` | 5 | `no-untyped-def`×4, `arg-type`×1 |
| `goldsmith_erp.services.valuation_service` | 5 | `arg-type`×4, `assignment`×1 |
| `goldsmith_erp.api.routers.analytics` | 4 | `misc`×3, `type-arg`×1 |
| `goldsmith_erp.api.routers.auth` | 4 | `no-untyped-def`×3, `arg-type`×1 |
| `goldsmith_erp.middleware.auth_required` | 4 | `no-any-return`×3, `no-untyped-def`×1 |
| `goldsmith_erp.ml.model_registry` | 4 | `unused-ignore`×2, `no-any-return`×2 |
| `goldsmith_erp.models.time_entry` | 4 | `no-untyped-def`×4 |
| `goldsmith_erp.services.accounting_export_service` | 4 | `arg-type`×3, `no-untyped-def`×1 |
| `goldsmith_erp.services.activity_service` | 4 | `operator`×2, `unused-ignore`×1, `return-value`×1 |
| `goldsmith_erp.api.routers.metal_prices` | 3 | `arg-type`×3 |
| `goldsmith_erp.core.config` | 3 | `return-value`×1, `no-untyped-def`×1, `arg-type`×1 |
| `goldsmith_erp.db.repositories.material` | 3 | `assignment`×2, `return-value`×1 |
| `goldsmith_erp.db.session` | 3 | `type-arg`×1, `call-overload`×1, `misc`×1 |
| `goldsmith_erp.services.comment_service` | 3 | `return-value`×1, `arg-type`×1, `assignment`×1 |
| `goldsmith_erp.services.email_service` | 3 | `type-arg`×3 |
| `goldsmith_erp.services.material_service` | 3 | `return-value`×2, `unused-ignore`×1 |
| `goldsmith_erp.services.system_health_service` | 3 | `no-untyped-call`×1, `no-untyped-def`×1, `arg-type`×1 |
| `goldsmith_erp.api.routers.health` | 2 | `arg-type`×2 |
| `goldsmith_erp.api.routers.imports` | 2 | `attr-defined`×1, `arg-type`×1 |
| `goldsmith_erp.core.logging` | 2 | `no-untyped-def`×1, `no-untyped-call`×1 |
| `goldsmith_erp.core.pubsub` | 2 | `no-untyped-def`×1, `type-arg`×1 |
| `goldsmith_erp.middleware.logging` | 2 | `type-arg`×1, `no-any-return`×1 |
| `goldsmith_erp.middleware.security_headers` | 2 | `no-untyped-def`×1, `no-any-return`×1 |
| `goldsmith_erp.models.order` | 2 | `no-untyped-def`×1, `no-untyped-call`×1 |
| `goldsmith_erp.models.quote` | 2 | `type-arg`×2 |
| `goldsmith_erp.models.user` | 2 | `type-arg`×2 |
| `goldsmith_erp.services.metal_price_service` | 2 | `assignment`×1, `type-arg`×1 |
| `goldsmith_erp.api.routers.theme` | 1 | `misc`×1 |
| `goldsmith_erp.services.image_validation` | 1 | `attr-defined`×1 |
| `goldsmith_erp.services.measurement_service` | 1 | `assignment`×1 |
| `goldsmith_erp.services.system_monitor` | 1 | `no-untyped-def`×1 |
<!-- END generated mypy baseline table -->

## Quick wins already taken

The initial baseline commit also fixed the long tail of trivial single-error
modules (annotation-only, no behavior change) so they never entered the
baseline: `middleware/request_metrics.py`, `models/validators.py`,
`models/time_entry_metadata.py`, `models/material.py`, `models/metal_inventory.py`,
`models/customer.py`, `models/consultation.py`, `core/idempotency.py`,
`api/routers/admin_scan_metrics.py`, `services/consultation_photo_service.py`,
and `services/repair_photo_service.py` (its single `arg-type`).

## Known latent issues surfaced (not fixed here — annotation-only scope)

- `services/image_validation.py` uses `Image.LANCZOS`, removed in Pillow 10+.
  On the pinned Pillow 12 this is a real `AttributeError` waiting in the
  thumbnail path — mypy flags it as `[attr-defined]`. It is left in the baseline
  and should be fixed separately as `Image.Resampling.LANCZOS`.
- `services/system_monitor.py` returns SQLAlchemy `Column[int]` values where
  `int` is expected (masked today by an untyped return). Symptomatic of the
  repo-wide ORM typing gap (`Mapped[...]` not yet adopted in `db/models.py`).
