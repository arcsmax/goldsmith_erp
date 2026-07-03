# Editable Quotes + Better Consultation→Quote Conversion — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. No DB migration needed (quote_line_items table already complete).

**Problem (diagnosed live):** Converting a consultation to a quote produces a frozen €0 shell: the quote gets no order_id and no line items, and quotes have NO edit path after creation (no line-item CRUD, no total recompute anywhere in backend or UI). The consultation's budget/piece_type/materials are dropped. Conversion is irreversible. The €0-and-unfixable problem affects *all* quotes, not just consultation-converted ones.

**Goal:** Make quotes editable (line items add/edit/remove with automatic total recompute, gated to DRAFT), seed the consultation→quote conversion with a budget-based starting estimate, and make an accidental conversion reversible.

## Global Constraints (binding — same as all prior plans)
- Backend: classic Column style, `transactional(db)` not nestable, typed exceptions raised OUTSIDE transactional when messages carry user text (IDs-only in logs), `@require_permission` + `current_user` kwarg, financial mutations audit-logged (quotes are financial → follow `_log_quote_access` precedent in quote_service.py), black/isort, new files mypy-clean via casts. Tests `poetry run pytest <path> -v` from repo root.
- Editing is allowed ONLY while quote status is DRAFT (a SENT/APPROVED/CONVERTED Kostenvoranschlag is legally-relevant and must stay immutable — reuse the existing status-gate pattern from `update_quote`/`delete_quote`). Recompute totals via the existing `QuoteService.calculate_totals` — never hand-roll the arithmetic.
- Frontend: German UI, no new deps, string-union types, `logError` for all error logging, `useToast`/`useConfirm`, 44px+ targets, `npx tsc --noEmit` clean before commit. Tests: `vi.mock` before import.
- Conventional commits, no attribution footer.

---

### Task 1 (backend): Quote line-item CRUD + total recompute

**Files:** `services/quote_service.py`, `api/routers/quotes.py`, `models/quote.py` (reuse existing `QuoteLineItemCreate`/`Read`), `tests/unit/test_quote_line_items.py`, extend `tests/integration/test_quotes*.py`.

- `QuoteService.add_line_item(db, quote_id, item: QuoteLineItemCreate, user) -> Quote`, `update_line_item(db, quote_id, item_id, item, user) -> Quote`, `delete_line_item(db, quote_id, item_id, user) -> Quote`. Each: load quote (typed `QuoteNotFoundError`→404 if missing), reject if status != DRAFT (typed `QuoteNotEditableError`→409 generic German 'Nur Entwürfe können bearbeitet werden'), mutate line items in one `transactional(db)`, then **recompute** `subtotal/tax_amount/total` from ALL current line items via `calculate_totals(items, quote.tax_rate)` and persist. Audit-log via the existing quote financial-access logger. Return the reloaded quote with line_items.
- Endpoints (append to quotes.py, `@require_permission(Permission.QUOTE_EDIT)`, `current_user`): `POST /quotes/{quote_id}/line-items` (201, body QuoteLineItemCreate), `PATCH /quotes/{quote_id}/line-items/{item_id}`, `DELETE /quotes/{quote_id}/line-items/{item_id}` → 204. Typed→HTTP mapping (404/409, generic details).
- **Also fix the latent tax_rate bug:** `update_quote` sets tax_rate without recomputing totals — make `update_quote` recompute totals when tax_rate changes (only if DRAFT), via calculate_totals over existing items. Add a test.
- Route-shadowing: `/line-items` sub-paths vs `/{quote_id}/pdf` etc. — verify no collision (deliberate, add a test hitting both).
- Tests: add line item → totals recompute (subtotal=Σ qty×price, tax=subtotal×rate, total); update/delete recompute; non-DRAFT quote → 409 on all three; unknown quote/item → 404; VIEWER 403; tax_rate change on DRAFT recomputes; the route-order test.

### Task 2 (backend): Seed consultation→quote conversion

**Files:** `services/consultation_service.py` (convert_consultation quote branch ~:266-275), `tests/unit/test_consultation_convert.py` (extend).

- In the `target == "quote"` branch, build `additional_line_items` from the consultation instead of leaving it empty:
  - One estimate line: `QuoteLineItemCreate(line_type=QuoteLineType.OTHER, description=f"{piece_label} – Schätzung laut Beratung (Budget {fmt(budget_min)}–{fmt(budget_max)})"[:500], quantity=1.0, unit_price=(budget_min or budget_max or 0.0))`. `piece_label` = the piece_type label already computed in the order branch (reuse/lift it). Use budget_min as the conservative anchor; if both None, unit_price 0.0 (falls back to today's behavior but still one labeled line the goldsmith edits).
  - Keep passing `notes=description[:2000]` as today.
  - Pass these via `QuoteCreate(customer_id=..., notes=..., additional_line_items=[...])` (create_quote already supports additional_line_items).
- The resulting quote is DRAFT with a real starting total (e.g. 1500 €) — fully editable via Task 1. Document in the docstring that this is a budget-based ESTIMATE to be reviewed, not a computed cost.
- Tests: convert a consultation with budget_min=1500/max=2500 → quote total == 1500 (net) with one line item whose description references the budget and piece type; convert with no budget → one line item, unit_price 0 (total 0) but line present; convert-to-order branch unchanged (regression).

### Task 3 (backend): Reversible conversion (unconvert) + close status gap

**Files:** `services/consultation_service.py`, `api/routers/consultations.py`, `tests/unit/test_consultation_convert.py`, integration.

- `ConsultationService.unconvert_consultation(db, consultation_id, user) -> Consultation`: only when status is CONVERTED AND the linked quote (converted_quote_id) is still DRAFT (typed `CannotUnconvertError`→409 'Nur Entwürfe können zurückgesetzt werden' if the quote was already sent/approved/converted, or if an order was created — converted_order_id set → 409, orders are not auto-deleted). In one `transactional(db)`: delete the linked DRAFT quote (its line items cascade or delete explicitly), set consultation.status=COMPLETED, clear converted_quote_id. Audit/log IDs only.
- Endpoint `POST /consultations/{id}/unconvert` (`@require_permission(Permission.CONSULTATION_EDIT)`), typed→HTTP mapping.
- **Close the latent double-convert gap** the review found: in `update_consultation`, reject a `PATCH` that tries to move status OUT of CONVERTED (only the explicit unconvert path may do that) — since converted_quote_id/order_id aren't clearable via PATCH, allowing a bare status flip would orphan the quote and permit a silent second conversion. Add a guard + test.
- Tests: unconvert a fresh conversion (DRAFT quote) → consultation COMPLETED, converted_quote_id NULL, quote gone; unconvert when quote already SENT → 409; unconvert when converted to an order → 409; PATCH status away from CONVERTED → rejected.

### Task 4 (frontend): Quote line-item editor + delete action

**Files:** `frontend/src/pages/QuotesPage.tsx` (QuoteDetailPanel), `frontend/src/api/quotes.ts`, `frontend/src/types.ts`, tests colocated.

- `quotesApi`: add `addLineItem(quoteId, item)`, `updateLineItem(quoteId, itemId, item)`, `deleteLineItem(quoteId, itemId)` (the delete/update quote methods already exist). Types: `QuoteLineItemInput` (line_type union, description, quantity, unit_price).
- `QuoteDetailPanel`: when `quote.status === 'draft'`, render an **editable** line-items table — each row editable (description text, quantity number, unit_price number, line_type select with German labels Material/Arbeit/Edelstein/Sonstiges), a remove (🗑) per row, and an "+ Position hinzufügen" row. On each add/edit/remove → call the API → replace local quote from the response (server-recomputed totals) → totals update live. Non-draft quotes stay read-only as today. All mutations await-then-update, toast + logError on failure, 44px targets, German.
- Wire the existing-but-dead `quotesApi.deleteQuote` as a detail-panel action gated to DRAFT/REJECTED (confirm dialog 'Angebot wirklich löschen?') → on success refresh list + close panel.
- Tests: draft quote renders editable rows + add form; adding a line item calls addLineItem and shows the returned total; non-draft renders read-only (no inputs); delete-quote action calls deleteQuote for a draft.

### Task 5 (frontend): Honest conversion dialog + navigate-to-quote + unconvert button

**Files:** `frontend/src/components/consultation/SummaryStep.tsx`, `frontend/src/api/consultations.ts`, tests.

- Conversion confirm dialog (quote target): message → 'Aus der Beratung wird ein Kostenvoranschlag als Entwurf erstellt — mit einer Budget-Schätzung, die Sie anschließend anpassen. Fortfahren?' (honest about the estimate + editability).
- After successful quote conversion, navigate to the new quote so the goldsmith lands on it ready to edit. If a `/quotes/:id` detail route doesn't exist, add a minimal one (or pass the new quote id via navigate state / query param that QuotesPage opens the detail panel for) — pick the smallest change; document. Success toast stays.
- `consultationsApi.unconvert(id)` → `POST /consultations/{id}/unconvert`. In the converted-state banner (SummaryStep), add a "Überführung rückgängig machen" secondary button (only shown when a quote link exists and — best-effort — is still a draft; the backend enforces the real rule with a 409 → toast 'Nur Entwürfe können zurückgesetzt werden'). On success → toast + navigate back into the wizard/summary as a non-converted consultation (refetch).
- Tests: dialog wording; convert → navigate to the quote (mock useNavigate); unconvert button calls the API and 409 shows the German toast.

### Task 6: Verification + ECC review + PR

- `poetry run pytest -q | tail -3` (zero fail vs baseline ~1524), frontend `yarn test --run | tail -4`, `npx tsc --noEmit`, `yarn build`, black/isort, mypy-new-clean.
- ECC review wave (fastapi-reviewer + react-reviewer + security-reviewer over the diff — editing quotes is financial/audit-relevant; verify DRAFT-gating can't be bypassed and no user text leaks in logs). Fix findings.
- PR to main; note the manual CreateQuoteModal line-item entry (closing the €0 gap for hand-created quotes too) as an optional follow-up if not included.

## Out of scope (note in PR)
- Line-item entry inside CreateQuoteModal (manual quotes can still start €0 then be edited via the new editor — acceptable; follow-up issue).
- V1.3 learning estimator auto-filling the seed line (this plan just gives it a home).
