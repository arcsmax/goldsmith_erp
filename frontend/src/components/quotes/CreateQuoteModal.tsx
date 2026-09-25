// "Neues Angebot erstellen" (W4-03): react-hook-form + zod on the Modal
// primitive. Escape and the close button ask "Änderungen verwerfen?" once
// the form is dirty (Modal isDirty → useDirtyGuard); the backdrop never
// closes it.
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { CustomerTypeahead } from '../consultation/CustomerTypeahead';
import { useToast } from '../../contexts';
import type { QuoteCreateInput } from '../../types';
import { Button, Field, Modal } from '../../ui';
import {
  createQuoteSchema,
  DEFAULT_TAX_RATE,
  DEFAULT_VALID_DAYS,
  MAX_NOTES_LENGTH,
  type CreateQuoteValues,
} from './quoteSchemas';

const FORM_ID = 'create-quote-form';
const CUSTOMER_INPUT_ID = 'quote-customer';

export interface CreateQuotePrefill {
  customerId?: string;
  orderId?: string;
}

interface CreateQuoteModalProps {
  open: boolean;
  onClose: () => void;
  /** Resolves when the quote was created; rejects to keep the dialog open. */
  onSubmit: (data: QuoteCreateInput) => Promise<void>;
  /** FE-18: prefill from `/quotes?order_id=…&customer_id=…`. */
  prefill?: CreateQuotePrefill;
}

function defaultsFor(prefill?: CreateQuotePrefill): CreateQuoteValues {
  return {
    customer_id: prefill?.customerId ?? '',
    customer_label: prefill?.customerId ? `Kunde #${prefill.customerId}` : '',
    order_id: prefill?.orderId ?? '',
    valid_days: DEFAULT_VALID_DAYS,
    tax_rate: DEFAULT_TAX_RATE,
    notes: '',
  };
}

function toInput(values: CreateQuoteValues): QuoteCreateInput {
  return {
    customer_id: Number(values.customer_id),
    order_id: values.order_id ? Number(values.order_id) : undefined,
    valid_days: values.valid_days,
    tax_rate: values.tax_rate,
    notes: values.notes.trim() || undefined,
  };
}

export const CreateQuoteModal: React.FC<CreateQuoteModalProps> = ({
  open,
  onClose,
  onSubmit,
  prefill,
}) => {
  const { showToast } = useToast();
  const form = useForm<CreateQuoteValues>({
    defaultValues: defaultsFor(prefill),
    resolver: zodResolver(createQuoteSchema),
  });
  const { register, handleSubmit, reset, setValue, watch, formState } = form;
  const { errors, isDirty, isSubmitting } = formState;
  const customerId = watch('customer_id');
  const customerLabel = watch('customer_label');

  useEffect(() => {
    if (open) reset(defaultsFor(prefill));
  }, [open, prefill, reset]);

  const selectCustomer = (id: string, label: string) => {
    setValue('customer_id', id, { shouldDirty: true, shouldValidate: Boolean(id) });
    setValue('customer_label', label, { shouldDirty: true });
  };

  const submit = handleSubmit(async (values) => {
    try {
      await onSubmit(toInput(values));
      reset(defaultsFor());
    } catch {
      // The caller already showed the error; keep the dialog and the input.
    }
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Neues Angebot erstellen"
      isDirty={isDirty}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Abbrechen
          </Button>
          <Button
            type="submit"
            form={FORM_ID}
            loading={isSubmitting}
            disabled={isSubmitting || !customerId}
          >
            Angebot erstellen
          </Button>
        </>
      }
    >
      <form id={FORM_ID} className="quote-form" onSubmit={submit} noValidate>
        {/* LV-02: search instead of loading every customer (the list
            endpoint caps limit at 100 and answered 422 to limit=500). */}
        <div className={`ui-field${errors.customer_id ? ' ui-field--invalid' : ''}`}>
          <label className="ui-field__label" htmlFor={CUSTOMER_INPUT_ID}>
            Kunde
            <span className="ui-field__required" aria-hidden="true">
              Pflichtfeld
            </span>
          </label>
          {customerId ? (
            <div className="quote-form__customer">
              <span>{customerLabel}</span>
              <Button variant="secondary" onClick={() => selectCustomer('', '')}>
                Kunde ändern
              </Button>
            </div>
          ) : (
            <CustomerTypeahead
              inputId={CUSTOMER_INPUT_ID}
              onSelect={(customer) =>
                selectCustomer(
                  String(customer.id),
                  `${customer.first_name} ${customer.last_name}${
                    customer.company_name ? ` — ${customer.company_name}` : ''
                  }`,
                )
              }
              onError={() => showToast('Kundensuche fehlgeschlagen. Bitte erneut versuchen.', 'error')}
            />
          )}
          {errors.customer_id && <p className="ui-field__error">{errors.customer_id.message}</p>}
        </div>

        <Field
          label="Auftragsnummer (optional)"
          name="order_id"
          inputMode="numeric"
          help="Wird ein Auftrag angegeben, werden Positionen automatisch berechnet."
          error={errors.order_id?.message}
        >
          <input
            id="quote-order"
            type="text"
            placeholder="z. B. 42 – leer lassen für ein manuelles Angebot"
            {...register('order_id')}
          />
        </Field>

        <div className="quote-form__row">
          <Field
            label="Gültig für"
            name="valid_days"
            inputMode="numeric"
            suffix="Tage"
            error={errors.valid_days?.message}
          >
            <input id="quote-valid-days" type="number" min={1} max={365} {...register('valid_days', { valueAsNumber: true })} />
          </Field>
          <Field
            label="MwSt-Satz"
            name="tax_rate"
            inputMode="decimal"
            suffix="%"
            error={errors.tax_rate?.message}
          >
            <input
              id="quote-tax"
              type="number"
              min={0}
              max={100}
              step="0.1"
              {...register('tax_rate', { valueAsNumber: true })}
            />
          </Field>
        </div>

        <Field label="Anmerkungen" name="notes" error={errors.notes?.message}>
          <textarea
            id="quote-notes"
            rows={3}
            maxLength={MAX_NOTES_LENGTH}
            placeholder="Besondere Hinweise oder Konditionen…"
            {...register('notes')}
          />
        </Field>
      </form>
    </Modal>
  );
};
