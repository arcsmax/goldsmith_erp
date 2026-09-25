// CostChangeForm — §649 cost-change request form (V1.2 Task 5).
//
// Client-validates BEFORE calling the API so we never round-trip a
// guaranteed-422: `new_amount` must be > 0, `reason` must be 10–2000 chars
// (mirrors CostChangeCreate's backend constraints exactly — see Backend
// Contract in docs/planning/phase-plans/2026-07-03-v1.2-frontend-plan.md).
// Line items are optional, capped at 30 rows; a row only counts as "filled"
// (and thus validated/submitted) once it has a label or an amount.
import React, { useState } from 'react';
import type {
  CostChangeCreateInput,
  CostChangeLineItem,
  CostChangeLineItemKind,
} from '../../api/customer-updates';
import { MONEY_CLASS } from '../../lib/format';
import { Button, Field, IconButton } from '../../ui';
import './cost-change.css';

export interface CostChangeFormProps {
  onSubmit: (input: CostChangeCreateInput) => Promise<void>;
  disabled?: boolean;
}

const REASON_MIN = 10;
const REASON_MAX = 2000;
const LINE_ITEMS_MAX = 30;

const LINE_ITEM_KIND_LABELS: Record<CostChangeLineItemKind, string> = {
  add: 'Hinzufügen',
  remove: 'Entfernen',
  change: 'Änderung',
};

interface LineItemDraft {
  label: string;
  amount: string;
  kind: CostChangeLineItemKind;
}

interface FormErrors {
  newAmount?: string;
  reason?: string;
  lineItems?: string;
}

function emptyLineItem(): LineItemDraft {
  return { label: '', amount: '', kind: 'add' };
}

function isLineItemFilled(item: LineItemDraft): boolean {
  return item.label.trim().length > 0 || item.amount.trim().length > 0;
}

/** Parse a decimal typed with a comma or a point ("12,50" or "12.50"). */
function parseDecimal(value: string): number {
  const trimmed = value.trim();
  if (!trimmed) return Number.NaN;
  return Number(trimmed.replace(',', '.'));
}

function isLineItemValid(item: LineItemDraft): boolean {
  return (
    item.label.trim().length > 0 &&
    Number.isFinite(parseDecimal(item.amount))
  );
}

function toLineItemPayload(item: LineItemDraft): CostChangeLineItem {
  return {
    label: item.label.trim(),
    amount: parseDecimal(item.amount),
    kind: item.kind,
  };
}

export function CostChangeForm({ onSubmit, disabled = false }: CostChangeFormProps) {
  const [newAmount, setNewAmount] = useState('');
  const [reason, setReason] = useState('');
  const [lineItems, setLineItems] = useState<LineItemDraft[]>([]);
  const [errors, setErrors] = useState<FormErrors>({});
  const [submitting, setSubmitting] = useState(false);

  const isBusy = disabled || submitting;

  const addLineItem = () => {
    if (lineItems.length >= LINE_ITEMS_MAX) return;
    setLineItems((prev) => [...prev, emptyLineItem()]);
  };

  const updateLineItem = (index: number, patch: Partial<LineItemDraft>) => {
    setLineItems((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  };

  const removeLineItem = (index: number) => {
    setLineItems((prev) => prev.filter((_, i) => i !== index));
  };

  const validate = (): { valid: boolean; nextErrors: FormErrors } => {
    const nextErrors: FormErrors = {};

    const amountValue = parseDecimal(newAmount);
    if (!Number.isFinite(amountValue) || amountValue <= 0) {
      nextErrors.newAmount = 'Neuer Betrag muss größer als 0 sein.';
    }

    const trimmedReason = reason.trim();
    if (trimmedReason.length < REASON_MIN || reason.length > REASON_MAX) {
      nextErrors.reason = `Begründung muss zwischen ${REASON_MIN} und ${REASON_MAX} Zeichen lang sein.`;
    }

    const filledItems = lineItems.filter(isLineItemFilled);
    if (filledItems.length > LINE_ITEMS_MAX) {
      nextErrors.lineItems = `Maximal ${LINE_ITEMS_MAX} Positionen erlaubt.`;
    } else if (filledItems.some((item) => !isLineItemValid(item))) {
      nextErrors.lineItems = 'Jede Position benötigt eine Bezeichnung und einen gültigen Betrag.';
    }

    return { valid: Object.keys(nextErrors).length === 0, nextErrors };
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isBusy) return;

    const { valid, nextErrors } = validate();
    setErrors(nextErrors);
    if (!valid) return;

    const input: CostChangeCreateInput = {
      new_amount: parseDecimal(newAmount),
      reason: reason.trim(),
      line_items: lineItems.filter(isLineItemFilled).map(toLineItemPayload),
    };

    setSubmitting(true);
    try {
      await onSubmit(input);
      setNewAmount('');
      setReason('');
      setLineItems([]);
      setErrors({});
    } catch {
      // The parent reports the failure (toast); keep the draft for a retry.
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="cost-change-form" noValidate onSubmit={(e) => void handleSubmit(e)}>
      <Field
        label="Neuer Betrag (netto)"
        name="new_amount"
        inputMode="decimal"
        suffix="€"
        error={errors.newAmount}
      >
        <input
          id="cost-change-new-amount"
          type="text"
          className={MONEY_CLASS}
          value={newAmount}
          onChange={(e) => setNewAmount(e.target.value)}
          disabled={isBusy}
        />
      </Field>

      <Field
        label="Begründung"
        name="reason"
        help={`${reason.length}/${REASON_MAX} Zeichen (mind. ${REASON_MIN})`}
        error={errors.reason}
      >
        <textarea
          id="cost-change-reason"
          rows={4}
          maxLength={REASON_MAX}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          disabled={isBusy}
        />
      </Field>

      <fieldset className="cost-change-line-items">
        <legend className="cost-change-line-items__legend">Positionen (optional)</legend>

        {lineItems.map((item, index) => (
          <div className="cost-change-line-item-row" key={index}>
            <Field label={`Bezeichnung Position ${index + 1}`} name={`line_item_label_${index}`}>
              <input
                type="text"
                maxLength={200}
                value={item.label}
                onChange={(e) => updateLineItem(index, { label: e.target.value })}
                disabled={isBusy}
              />
            </Field>
            <Field
              label={`Betrag Position ${index + 1}`}
              name={`line_item_amount_${index}`}
              inputMode="decimal"
              suffix="€"
            >
              <input
                type="text"
                className={MONEY_CLASS}
                value={item.amount}
                onChange={(e) => updateLineItem(index, { amount: e.target.value })}
                disabled={isBusy}
              />
            </Field>
            <Field label={`Art Position ${index + 1}`} name={`line_item_kind_${index}`}>
              <select
                value={item.kind}
                onChange={(e) =>
                  updateLineItem(index, { kind: e.target.value as CostChangeLineItemKind })
                }
                disabled={isBusy}
              >
                {(Object.keys(LINE_ITEM_KIND_LABELS) as CostChangeLineItemKind[]).map((kind) => (
                  <option key={kind} value={kind}>
                    {LINE_ITEM_KIND_LABELS[kind]}
                  </option>
                ))}
              </select>
            </Field>
            <IconButton
              icon="trash"
              variant="danger"
              label={`Position ${index + 1} entfernen`}
              className="cost-change-line-item-row__remove"
              onClick={() => removeLineItem(index)}
              disabled={isBusy}
            />
          </div>
        ))}
        {errors.lineItems && (
          <p className="cost-change-error" role="alert">
            {errors.lineItems}
          </p>
        )}

        <Button
          variant="secondary"
          icon="plus"
          onClick={addLineItem}
          disabled={isBusy || lineItems.length >= LINE_ITEMS_MAX}
        >
          Position hinzufügen
        </Button>
      </fieldset>

      <div className="cost-change-form-actions">
        <Button type="submit" variant="primary" loading={submitting} disabled={isBusy}>
          Kostenänderung anlegen
        </Button>
      </div>
    </form>
  );
}

export default CostChangeForm;
