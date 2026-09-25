# Frontend API types (generated from OpenAPI)

The backend's Pydantic schemas are the single source of truth for the shapes the frontend reads (FE-12, W3-02).

**Files**
- `frontend/scripts/gen-api-types.mjs` imports `goldsmith_erp.main:app` (no server, DB or Redis), writes `app.openapi()` to `frontend/openapi.json`, then runs `openapi-typescript`.
- `frontend/src/api/generated/schema.d.ts` holds the generated types. Do not edit it.
- `frontend/src/api/generated/enums.json` holds every OpenAPI enum's values, used as the runtime witness in `src/api/generatedTypes.test.ts`.
- `frontend/src/api/generated/index.ts` is hand-written and holds the aliases (`Schemas`, `Schema<'OrderRead'>`, `ApiOrder`, `ApiUserRole`, ...).
- `frontend/src/types.ts` re-exports these under the old names (`OrderType`, `UserRole`, `Customer`, ...), so callers do not change.

**Workflow after changing a backend schema**
1. `make types` (uses `poetry run python`; or `PYTHON=/path/to/venv/python node frontend/scripts/gen-api-types.mjs`).
2. `cd frontend && yarn tsc --noEmit`: every caller the change breaks shows up here. Fix the callers, not the generated file.
3. Commit `frontend/openapi.json` and `frontend/src/api/generated/` together with the backend change.

**CI gate.** `make types-check` (the `lint-frontend` job) regenerates the files and fails if `git diff` over `frontend/openapi.json` and `frontend/src/api/generated/` is non-empty, or if an untracked file appears there.

**Rules for `types.ts`**
- New read types: `export type X = ApiX` or `Schemas['XRead']`. Never hand-write a response shape the backend already declares.
- Narrow a field only where the backend declares `str` but validates a fixed set (`Customer.customer_type`, `Activity.category`, `ScrapGold.status`). Say why in a comment.
- Add fields the schema cannot express only with a comment naming the router that adds them (`Customer.allergies`, which is consent-gated and added by `customers.py _customer_response`).
- Roles are lowercase on the wire (`'admin' | 'goldsmith' | 'viewer'`). `hasRole` and `ProtectedRoute` accept either case (`RoleName`); direct comparisons with `user.role` must use lowercase.

**Open items**
- `OrderType` still overrides `materials`, `hourly_rate`, `scrap_percentage`, `costing_method_used`, `profit_margin_percent` and `vat_rate` with their old non-null types (`OrderLegacyFields`), because `OrderDetailPage.tsx` and `components/orders/CostBreakdownCard`/`MetalInventoryCard` belong to another work item. The wire values are nullable, and `materials` is `MaterialBase[]`.
- Create/update input types and the non-migrated read types (materials, metal inventory, calendar, estimator, time-tracking stats) are still hand-written. Migrate them the same way.
