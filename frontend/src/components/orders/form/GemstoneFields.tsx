// "Steine" in the order form (W2-06 DOM-04; W3-06 field array). One fieldset
// per stone on a react-hook-form useFieldArray; the rows are saved with the
// order ("Auftrag speichern") through gemstoneSync. The purchase price is only
// rendered for roles that may see costs, and never for a Kundenstein.
import React from 'react';
import { useFieldArray, useFormContext, useWatch } from 'react-hook-form';
import { Button, EmptyState, Field, PageState, type PageStateValue } from '../../../ui';
import { SETTING_TYPE_OPTIONS } from '../orderIntakeOptions';
import { GEMSTONES_EMPTY_TITLE } from '../GemstoneList';
import { EMPTY_GEMSTONE, type GemstoneRow, type OrderFormValues } from './orderFormSchema';

type TextKey = Exclude<keyof GemstoneRow, 'gemstoneId' | 'is_customer_stone' | 'setting_type'>;

interface GemstoneFieldsProps {
  canViewCost: boolean;
  /** Loading or error state of the saved stones (edit mode). */
  state: PageStateValue;
}

interface RowProps {
  index: number;
  canViewCost: boolean;
  onRemove: () => void;
}

const TEXT_FIELDS: readonly { key: TextKey; label: string; placeholder?: string; inputMode?: 'numeric' | 'decimal'; unit?: string }[] = [
  { key: 'type', label: 'Steinart', placeholder: 'z. B. Diamant' },
  { key: 'quantity', label: 'Anzahl', inputMode: 'numeric' },
  { key: 'carat', label: 'Karat je Stein', inputMode: 'decimal', unit: 'ct' },
  { key: 'color', label: 'Farbe' },
  { key: 'quality', label: 'Reinheit' },
  { key: 'shape', label: 'Form', placeholder: 'z. B. rund' },
];

const GemstoneRowFields: React.FC<RowProps> = ({ index, canViewCost, onRemove }) => {
  const { register, formState, control, setValue } = useFormContext<OrderFormValues>();
  const rowErrors = formState.errors.gemstones?.[index];
  const isCustomerStone = useWatch({ control, name: `gemstones.${index}.is_customer_stone` });
  const position = index + 1;
  const suffix = ` (Stein ${position})`;
  const idOf = (key: string) => `gemstone-${index}-${key}`;

  const textField = ({ key, label, placeholder, inputMode, unit }: (typeof TEXT_FIELDS)[number]) => (
    <Field
      key={key}
      label={label}
      name={`gemstones.${index}.${key}`}
      inputMode={inputMode}
      suffix={unit}
      error={rowErrors?.[key]?.message}
    >
      <input
        id={idOf(key)}
        aria-label={`${label}${suffix}`}
        type="text"
        placeholder={placeholder}
        {...register(`gemstones.${index}.${key}`)}
      />
    </Field>
  );

  const customerStone = register(`gemstones.${index}.is_customer_stone`);

  return (
    <fieldset className="gemstone-row">
      <legend>Stein {position}</legend>
      <div className="form-row">{TEXT_FIELDS.slice(0, 3).map(textField)}</div>
      <div className="form-row">{TEXT_FIELDS.slice(3).map(textField)}</div>
      <div className="form-row">
        <Field label="Fassungsart" name={`gemstones.${index}.setting_type`}>
          <select id={idOf('setting')} aria-label={`Fassungsart${suffix}`} {...register(`gemstones.${index}.setting_type`)}>
            <option value="">Keine Angabe</option>
            {SETTING_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>
        <label className="checkbox-label">
          <input
            type="checkbox"
            aria-label={`Kundenstein${suffix}`}
            {...customerStone}
            onChange={(event) => {
              void customerStone.onChange(event);
              if (event.target.checked) setValue(`gemstones.${index}.cost`, '', { shouldDirty: true });
            }}
          />
          <span>Kundenstein</span>
        </label>
        {canViewCost &&
          !isCustomerStone &&
          textField({ key: 'cost', label: 'Einkaufspreis je Stein', inputMode: 'decimal', unit: '€' })}
      </div>
      <div className="gemstone-row-actions">
        <Button variant="ghost" icon="trash" onClick={onRemove}>
          Stein entfernen
        </Button>
      </div>
    </fieldset>
  );
};

export const GemstoneFields: React.FC<GemstoneFieldsProps> = ({ canViewCost, state }) => {
  const { control } = useFormContext<OrderFormValues>();
  const { fields, append, remove } = useFieldArray({ control, name: 'gemstones', keyName: 'fieldKey' });

  const addButton = (
    <Button variant="secondary" icon="plus" onClick={() => append({ ...EMPTY_GEMSTONE })}>
      Stein hinzufügen
    </Button>
  );

  return (
    <section className="gemstone-repeater" aria-labelledby="order-form-gemstones">
      <h3 id="order-form-gemstones">Steine</h3>
      <PageState state={state} skeleton="list" skeletonCount={2}>
        {fields.length === 0 ? (
          <EmptyState icon="gem" title={GEMSTONES_EMPTY_TITLE} headingLevel={3} action={addButton} />
        ) : (
          <>
            {fields.map((field, index) => (
              <GemstoneRowFields
                key={field.fieldKey}
                index={index}
                canViewCost={canViewCost}
                onRemove={() => remove(index)}
              />
            ))}
            <p className="form-hint">Steine werden mit dem Auftrag gespeichert.</p>
            <div className="gemstone-row-actions">{addButton}</div>
          </>
        )}
      </PageState>
    </section>
  );
};
