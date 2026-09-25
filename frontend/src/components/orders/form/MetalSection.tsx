// "Metall" tab of the order form (W3-06): weight, Verschnitt and the costing
// method for the alloy picked on the "Auftrag" tab.
import React from 'react';
import { useFormContext, useWatch } from 'react-hook-form';
import { Field } from '../../../ui';
import { alloyChoiceKey, findAlloyChoice } from '../orderIntakeOptions';
import { COSTING_METHOD_OPTIONS } from './orderFormOptions';
import type { OrderFormValues } from './orderFormSchema';

export const MetalSection: React.FC = () => {
  const { register, control, formState } = useFormContext<OrderFormValues>();
  const { errors } = formState;
  const [metalType, alloy, costingMethod] = useWatch({
    control,
    name: ['metal_type', 'alloy', 'costing_method_used'],
  });
  const choice = findAlloyChoice(alloyChoiceKey(metalType, alloy));

  return (
    <div className="tab-content-form">
      <p className="form-hint">
        {choice
          ? `Legierung & Farbe: ${choice.label}`
          : 'Bitte zuerst im Tab „Auftrag“ Legierung & Farbe wählen.'}
      </p>
      {errors.metal_type?.message && (
        <p className="ui-field__error" role="alert">
          {errors.metal_type.message}
        </p>
      )}

      {metalType && (
        <>
          <div className="form-row">
            <Field
              label="Geschätztes Gewicht"
              name="estimated_weight_g"
              required
              inputMode="decimal"
              suffix="g"
              error={errors.estimated_weight_g?.message}
            >
              <input id="estimated_weight_g" type="text" placeholder="0,00" {...register('estimated_weight_g')} />
            </Field>
            <Field
              label="Verschnitt"
              name="scrap_percentage"
              inputMode="decimal"
              suffix="%"
              error={errors.scrap_percentage?.message}
            >
              <input id="scrap_percentage" type="text" placeholder="5" {...register('scrap_percentage')} />
            </Field>
          </div>

          <Field label="Kalkulationsmethode" name="costing_method_used">
            <select id="costing_method_used" {...register('costing_method_used')}>
              {COSTING_METHOD_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </Field>

          {costingMethod === 'specific' && (
            <Field
              label="Charge-ID"
              name="specific_metal_purchase_id"
              required
              inputMode="numeric"
              error={errors.specific_metal_purchase_id?.message}
            >
              <input
                id="specific_metal_purchase_id"
                type="text"
                placeholder="Charge-ID eingeben"
                {...register('specific_metal_purchase_id')}
              />
            </Field>
          )}
        </>
      )}
    </div>
  );
};
