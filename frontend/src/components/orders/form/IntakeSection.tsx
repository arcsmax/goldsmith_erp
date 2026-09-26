// "Auftrag" tab of the order form (W3-06): the goldsmith intake fields,
// the Pflichtfelder progress, and the stones on a saved order.
import React from 'react';
import { useFormContext, useWatch } from 'react-hook-form';
import { Field, type PageStateValue } from '../../../ui';
import { ALLOY_CHOICES, alloyChoiceKey, findAlloyChoice } from '../orderIntakeOptions';
import { GemstoneFields } from './GemstoneFields';
import { SURFACE_FINISH_OPTIONS } from './orderFormOptions';
import type { OrderFormValues } from './orderFormSchema';

export interface Pflichtfeld {
  key: string;
  label: string;
  filled: boolean;
}

/** Fields needed before the order can be confirmed. DOM-05: by order type. */
export function pflichtfelderOf(values: Pick<OrderFormValues, 'title' | 'metal_type' | 'alloy' | 'deadline' | 'order_type' | 'ring_size_mm'>): Pflichtfeld[] {
  return [
    { key: 'title', label: 'Bezeichnung', filled: values.title.trim() !== '' },
    { key: 'alloy', label: 'Legierung & Farbe', filled: values.metal_type !== '' && values.alloy !== '' },
    { key: 'deadline', label: 'Abgabetermin', filled: values.deadline !== '' },
    ...(values.order_type === 'ring'
      ? [{ key: 'ring_size_mm', label: 'Ringmaß', filled: values.ring_size_mm !== '' }]
      : []),
  ];
}

interface IntakeSectionProps {
  pflichtfelder: readonly Pflichtfeld[];
  /** Saved orders edit their stones here; a new order shows a hint. */
  isEdit: boolean;
  canViewCost: boolean;
  gemstonesState: PageStateValue;
}

export const IntakeSection: React.FC<IntakeSectionProps> = ({ pflichtfelder, isEdit, canViewCost, gemstonesState }) => {
  const { register, setValue, control, formState } = useFormContext<OrderFormValues>();
  const { errors } = formState;
  const [metalType, alloy, orderType, fittingDate] = useWatch({
    control,
    name: ['metal_type', 'alloy', 'order_type', 'fitting_date'],
  });

  // DOM-06: one "Legierung & Farbe" choice sets metal_type AND alloy.
  const alloyChoice = alloyChoiceKey(metalType, alloy);
  const hasLegacyAlloyPair = alloyChoice === '' && (metalType !== '' || alloy !== '');
  const handleAlloyChoice = (key: string) => {
    const choice = findAlloyChoice(key);
    const options = { shouldDirty: true, shouldValidate: formState.isSubmitted };
    setValue('metal_type', (choice?.metal_type ?? '') as OrderFormValues['metal_type'], options);
    setValue('alloy', choice?.alloy ?? '', options);
  };

  const filled = pflichtfelder.filter((f) => f.filled).length;
  const missing = pflichtfelder.filter((f) => !f.filled).map((f) => f.label);
  const isComplete = filled === pflichtfelder.length;

  return (
    <div className="tab-content-form">
      <p className="pflichtfelder-indicator" role="status">
        <span className="pflichtfelder-label">Pflichtfelder:</span>
        <span className={`pflichtfelder-count pflichtfelder-count--${isComplete ? 'ok' : 'warn'}`}>
          {filled}/{pflichtfelder.length} ausgefüllt
        </span>
        {!isComplete && <span className="pflichtfelder-missing"> — Fehlend: {missing.join(', ')}</span>}
      </p>

      <Field
        label="Legierung & Farbe"
        name="alloy_choice"
        required
        error={errors.metal_type?.message ?? errors.alloy?.message}
        help={
          hasLegacyAlloyPair
            ? `Bisher gespeichert: ${metalType || '—'} / ${alloy || '—'}. Bitte Legierung & Farbe neu wählen.`
            : undefined
        }
      >
        <select id="alloy_choice" value={alloyChoice} onChange={(e) => handleAlloyChoice(e.target.value)}>
          <option value="">Legierung & Farbe auswählen</option>
          {ALLOY_CHOICES.map((choice) => (
            <option key={choice.key} value={choice.key}>
              {choice.label}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Oberfläche" name="surface_finish">
        <select id="surface_finish" {...register('surface_finish')}>
          <option value="">Oberfläche auswählen</option>
          {SURFACE_FINISH_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </Field>

      {orderType === 'ring' && (
        <Field
          label="Ringmaß (mm Innenumfang)"
          name="ring_size_mm"
          required
          inputMode="decimal"
          suffix="mm"
          help="EU-Innenumfang in mm (Ringgröße 52 = 52 mm)"
          error={errors.ring_size_mm?.message}
        >
          <input id="ring_size_mm" type="text" placeholder="z. B. 52,5" {...register('ring_size_mm')} />
        </Field>
      )}

      <Field
        label="Anprobe-Datum"
        name="fitting_date"
        help={
          fittingDate
            ? undefined
            : 'Ohne Anprobe-Datum wird der Status nach Bestätigung auf „Wartet auf Anprobe“ gesetzt.'
        }
      >
        <input id="fitting_date" type="date" {...register('fitting_date')} />
      </Field>

      <label className="checkbox-label">
        <input type="checkbox" {...register('has_scrap_gold')} />
        <span>Altgold vorhanden (Altgold-Verrechnung erforderlich)</span>
      </label>

      <Field label="Sonderwünsche" name="special_instructions" error={errors.special_instructions?.message}>
        <textarea
          id="special_instructions"
          rows={4}
          placeholder="Besondere Anforderungen des Kunden (Gravur, Lieferbedingungen, …)"
          {...register('special_instructions')}
        />
      </Field>

      {isEdit ? (
        <GemstoneFields canViewCost={canViewCost} state={gemstonesState} />
      ) : (
        <p className="form-hint">
          Steine lassen sich nach dem Anlegen des Auftrags erfassen (Auftrag bearbeiten → Auftrag).
        </p>
      )}
    </div>
  );
};
