// "Preisgestaltung" tab of the order form (W3-06). Financial data: the order
// form is only offered to ADMIN and GOLDSMITH (canCreateOrders/canEditOrders).
import React from 'react';
import { useFormContext } from 'react-hook-form';
import { Field } from '../../../ui';
import type { OrderFormValues } from './orderFormSchema';

type PricingKey = 'labor_hours' | 'hourly_rate' | 'profit_margin_percent' | 'vat_rate';

const PAIRS: readonly (readonly { key: PricingKey; label: string; suffix: string; placeholder: string }[])[] = [
  [
    { key: 'labor_hours', label: 'Arbeitsstunden', suffix: 'h', placeholder: '0,0' },
    { key: 'hourly_rate', label: 'Stundensatz', suffix: '€/h', placeholder: '75,00' },
  ],
  [
    { key: 'profit_margin_percent', label: 'Gewinnmarge', suffix: '%', placeholder: '40' },
    { key: 'vat_rate', label: 'MwSt.', suffix: '%', placeholder: '19' },
  ],
];

export const PricingSection: React.FC = () => {
  const { register, formState } = useFormContext<OrderFormValues>();
  const { errors } = formState;

  return (
    <div className="tab-content-form">
      <Field
        label="Manueller Preis"
        name="price"
        inputMode="decimal"
        suffix="€"
        help="Optional: überschreibt die automatische Preisberechnung. Leer lassen für automatische Berechnung."
        error={errors.price?.message}
      >
        <input id="price" type="text" {...register('price')} />
      </Field>

      {PAIRS.map((pair) => (
        <div className="form-row" key={pair[0].key}>
          {pair.map(({ key, label, suffix, placeholder }) => (
            <Field key={key} label={label} name={key} inputMode="decimal" suffix={suffix} error={errors[key]?.message}>
              <input id={key} type="text" placeholder={placeholder} {...register(key)} />
            </Field>
          ))}
        </div>
      ))}
    </div>
  );
};
