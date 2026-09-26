// Quote line items (W4-03): the editable table for DRAFT quotes, the
// read-only table for every other status, and the totals block.
//
// The editable table is one react-hook-form with a field array. Rows are
// keyed by the field-array key (never the index), every row is bound to its
// database line item through `itemId`, and a row is validated with the zod
// row schema before it is saved. Saving happens on blur (text and numbers)
// or on change (the type select), so typing does not call the API on every
// keystroke. The add row is a second small form with the same schema.
// Validation runs synchronously through the zod schema (safeParse), so an
// invalid row is never sent and its errors land in the form state.
import React, { useEffect, useState } from 'react';
import {
  useFieldArray,
  useForm,
  type FieldPath,
  type FieldValues,
  type UseFormReturn,
  type UseFormSetError,
} from 'react-hook-form';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import type { Quote, QuoteLineItem, QuoteLineItemInput } from '../../types';
import { Button, IconButton } from '../../ui';
import { LINE_TYPE_LABELS, LINE_TYPES } from './quoteFormat';
import {
  EMPTY_LINE_ITEM,
  lineItemSchema,
  MAX_DESCRIPTION_LENGTH,
  type LineItemRowValues,
  type LineItemsFormValues,
  type LineItemValues,
} from './quoteSchemas';

const ROW_FIELDS = ['line_type', 'description', 'quantity', 'unit_price'] as const;

function toRow(item: QuoteLineItem): LineItemRowValues {
  return {
    itemId: item.id,
    line_type: item.line_type,
    description: item.description,
    quantity: item.quantity,
    unit_price: item.unit_price,
  };
}

function toInput(values: LineItemValues): QuoteLineItemInput {
  return {
    line_type: values.line_type,
    description: values.description.trim(),
    quantity: values.quantity,
    unit_price: values.unit_price,
  };
}

/** Validate one line item; on failure put each zod issue on its field. */
function parseLineItem<T extends FieldValues>(
  values: unknown,
  setError: UseFormSetError<T>,
  prefix: string,
): LineItemValues | null {
  const parsed = lineItemSchema.safeParse(values);
  if (parsed.success) return parsed.data;
  parsed.error.issues.forEach((issue) => {
    const name = `${prefix}${String(issue.path[0])}` as FieldPath<T>;
    setError(name, { type: 'validate', message: issue.message });
  });
  return null;
}

function isUnchanged(values: LineItemValues, item: QuoteLineItem | undefined): boolean {
  return (
    item !== undefined &&
    values.line_type === item.line_type &&
    values.description.trim() === item.description &&
    values.quantity === item.quantity &&
    values.unit_price === item.unit_price
  );
}

export interface EditableLineItemsProps {
  items: QuoteLineItem[];
  disabled: boolean;
  onAdd: (data: QuoteLineItemInput) => Promise<void>;
  onSave: (itemId: number, data: QuoteLineItemInput) => Promise<void>;
  onRemove: (itemId: number) => Promise<void>;
}

interface LineItemRowProps {
  form: UseFormReturn<LineItemsFormValues>;
  index: number;
  item: QuoteLineItem | undefined;
  disabled: boolean;
  onSave: EditableLineItemsProps['onSave'];
  onRemove: EditableLineItemsProps['onRemove'];
}

function LineItemRow({ form, index, item, disabled, onSave, onRemove }: LineItemRowProps) {
  const [busy, setBusy] = useState(false);
  const { register, getValues, setError, clearErrors, resetField, formState } = form;
  const rowErrors = formState.errors.items?.[index];
  const locked = disabled || busy;

  const commit = async () => {
    if (locked || !item) return;
    const values = getValues(`items.${index}`);
    if (isUnchanged(values, item)) return;
    // Invalid values (empty description, cleared or negative numbers) are
    // never sent; the row keeps the typed value and shows the error.
    clearErrors(`items.${index}`);
    const parsed = parseLineItem(values, setError, `items.${index}.`);
    if (!parsed) return;
    setBusy(true);
    try {
      await onSave(item.id, toInput(parsed));
      ROW_FIELDS.forEach((field) =>
        resetField(`items.${index}.${field}`, { defaultValue: values[field] as never }),
      );
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!item) return;
    setBusy(true);
    try {
      await onRemove(item.id);
    } finally {
      setBusy(false);
    }
  };

  const errorText = rowErrors
    ? ROW_FIELDS.map((field) => rowErrors[field]?.message).filter(Boolean).join(' ')
    : '';
  const errorId = `quote-line-${index}-error`;
  const invalid = (field: (typeof ROW_FIELDS)[number]) => (rowErrors?.[field] ? true : undefined);

  return (
    <tr>
      <td className="ui-num">{index + 1}</td>
      <td>
        <select
          className="ui-field__control"
          aria-label="Art der Position"
          disabled={locked}
          {...register(`items.${index}.line_type`, { onChange: () => void commit() })}
        >
          {LINE_TYPES.map((type) => (
            <option key={type} value={type}>
              {LINE_TYPE_LABELS[type]}
            </option>
          ))}
        </select>
      </td>
      <td>
        <input
          type="text"
          className="ui-field__control"
          aria-label="Beschreibung"
          maxLength={MAX_DESCRIPTION_LENGTH}
          disabled={locked}
          aria-invalid={invalid('description')}
          aria-describedby={errorText ? errorId : undefined}
          {...register(`items.${index}.description`, { onBlur: () => void commit() })}
        />
        {errorText && (
          <p id={errorId} className="ui-field__error quote-lines__error">
            {errorText}
          </p>
        )}
      </td>
      <td className="ui-align-end">
        <input
          type="number"
          className="ui-field__control ui-num"
          inputMode="decimal"
          min={0}
          step="0.01"
          aria-label="Menge"
          disabled={locked}
          aria-invalid={invalid('quantity')}
          {...register(`items.${index}.quantity`, {
            valueAsNumber: true,
            onBlur: () => void commit(),
          })}
        />
      </td>
      <td className="ui-align-end">
        <input
          type="number"
          className="ui-field__control ui-num"
          inputMode="decimal"
          min={0}
          step="0.01"
          aria-label="Einzelpreis"
          disabled={locked}
          aria-invalid={invalid('unit_price')}
          {...register(`items.${index}.unit_price`, {
            valueAsNumber: true,
            onBlur: () => void commit(),
          })}
        />
      </td>
      <td className={`ui-num ui-align-end ${MONEY_CLASS}`}>{formatEur(item?.total)}</td>
      <td className="ui-align-end">
        <IconButton
          icon="trash"
          variant="danger"
          label={`Position ${index + 1} entfernen`}
          disabled={locked}
          onClick={() => void remove()}
        />
      </td>
    </tr>
  );
}

function AddLineItemRow({ disabled, onAdd }: Pick<EditableLineItemsProps, 'disabled' | 'onAdd'>) {
  const form = useForm<LineItemValues>({ defaultValues: EMPTY_LINE_ITEM });
  const { register, getValues, setError, clearErrors, reset, watch, formState } = form;
  const [busy, setBusy] = useState(false);
  const draft = watch();
  const locked = disabled || busy;
  const hasDescription = Boolean(draft.description?.trim());

  const submit = async () => {
    clearErrors();
    const parsed = parseLineItem(getValues(), setError, '');
    if (!parsed) return;
    setBusy(true);
    try {
      await onAdd(toInput(parsed));
      reset(EMPTY_LINE_ITEM);
    } finally {
      setBusy(false);
    }
  };

  const errorText = [
    formState.errors.description?.message,
    formState.errors.quantity?.message,
    formState.errors.unit_price?.message,
  ]
    .filter(Boolean)
    .join(' ');
  const draftTotal =
    Number.isFinite(draft.quantity) && Number.isFinite(draft.unit_price)
      ? draft.quantity * draft.unit_price
      : null;

  return (
    <tr className="quote-lines__add">
      <td aria-hidden="true">+</td>
      <td>
        <select
          className="ui-field__control"
          aria-label="Art der neuen Position"
          disabled={locked}
          {...register('line_type')}
        >
          {LINE_TYPES.map((type) => (
            <option key={type} value={type}>
              {LINE_TYPE_LABELS[type]}
            </option>
          ))}
        </select>
      </td>
      <td>
        <input
          type="text"
          className="ui-field__control"
          placeholder="Neue Position…"
          aria-label="Beschreibung der neuen Position"
          maxLength={MAX_DESCRIPTION_LENGTH}
          disabled={locked}
          {...register('description')}
        />
        {errorText && <p className="ui-field__error quote-lines__error">{errorText}</p>}
      </td>
      <td className="ui-align-end">
        <input
          type="number"
          className="ui-field__control ui-num"
          inputMode="decimal"
          min={0}
          step="0.01"
          aria-label="Menge der neuen Position"
          disabled={locked}
          {...register('quantity', { valueAsNumber: true })}
        />
      </td>
      <td className="ui-align-end">
        <input
          type="number"
          className="ui-field__control ui-num"
          inputMode="decimal"
          min={0}
          step="0.01"
          aria-label="Einzelpreis der neuen Position"
          disabled={locked}
          {...register('unit_price', { valueAsNumber: true })}
        />
      </td>
      <td className={`ui-num ui-align-end ${MONEY_CLASS}`}>{formatEur(draftTotal)}</td>
      <td className="ui-align-end">
        <Button
          variant="primary"
          loading={busy}
          disabled={locked || !hasDescription}
          onClick={() => void submit()}
        >
          Hinzufügen
        </Button>
      </td>
    </tr>
  );
}

const LineItemsHead: React.FC<{ editable: boolean }> = ({ editable }) => (
  <thead>
    <tr>
      <th scope="col">Pos.</th>
      {editable && <th scope="col">Art</th>}
      <th scope="col">Beschreibung</th>
      <th scope="col" className="ui-align-end">
        Menge
      </th>
      <th scope="col" className="ui-align-end">
        Einzelpreis
      </th>
      <th scope="col" className="ui-align-end">
        Gesamt
      </th>
      {editable && (
        <th scope="col">
          <span className="ui-visually-hidden">Aktionen</span>
        </th>
      )}
    </tr>
  </thead>
);

/** Editable line items of a DRAFT quote; every add, edit and removal is saved at once. */
export function EditableLineItems({ items, disabled, onAdd, onSave, onRemove }: EditableLineItemsProps) {
  const form = useForm<LineItemsFormValues>({ defaultValues: { items: items.map(toRow) } });
  const { fields } = useFieldArray({ control: form.control, name: 'items', keyName: 'fieldKey' });
  const { reset } = form;

  // Server-canonical values win after every save, add or removal; a row the
  // user is still typing in (dirty) keeps its typed value.
  useEffect(() => {
    reset({ items: items.map(toRow) }, { keepDirtyValues: true });
  }, [items, reset]);

  const byId = new Map(items.map((item) => [item.id, item]));

  return (
    <div className="ui-table-scroll">
      <table className="ui-table quote-lines">
        <caption className="ui-visually-hidden">Positionen des Kostenvoranschlags</caption>
        <LineItemsHead editable />
        <tbody>
          {fields.map((field, index) => (
            <LineItemRow
              key={field.fieldKey}
              form={form}
              index={index}
              item={byId.get(field.itemId)}
              disabled={disabled}
              onSave={onSave}
              onRemove={onRemove}
            />
          ))}
          <AddLineItemRow disabled={disabled} onAdd={onAdd} />
        </tbody>
      </table>
    </div>
  );
}

export const ReadOnlyLineItems: React.FC<{ items: QuoteLineItem[] }> = ({ items }) => (
  <div className="ui-table-scroll">
    <table className="ui-table quote-lines">
      <caption className="ui-visually-hidden">Positionen des Kostenvoranschlags</caption>
      <LineItemsHead editable={false} />
      <tbody>
        {items.map((item, index) => (
          <tr key={item.id}>
            <td className="ui-num">{index + 1}</td>
            <td>{item.description}</td>
            <td className="ui-num ui-align-end">{item.quantity}</td>
            <td className={`ui-num ui-align-end ${MONEY_CLASS}`}>{formatEur(item.unit_price)}</td>
            <td className={`ui-num ui-align-end ${MONEY_CLASS}`}>{formatEur(item.total)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export const QuoteTotals: React.FC<{ quote: Quote }> = ({ quote }) => (
  <dl className="quote-totals">
    <div className="quote-totals__row">
      <dt>Zwischensumme</dt>
      <dd className={`ui-num ${MONEY_CLASS}`}>{formatEur(quote.subtotal)}</dd>
    </div>
    <div className="quote-totals__row">
      <dt>MwSt {quote.tax_rate} %</dt>
      <dd className={`ui-num ${MONEY_CLASS}`}>{formatEur(quote.tax_amount)}</dd>
    </div>
    <div className="quote-totals__row quote-totals__row--grand">
      <dt>Gesamtbetrag</dt>
      <dd className={`ui-num ${MONEY_CLASS}`}>{formatEur(quote.total)}</dd>
    </div>
  </dl>
);
