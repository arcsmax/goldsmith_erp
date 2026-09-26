// "Als bezahlt markieren" (W4-03): react-hook-form + zod on the Modal primitive.
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import type { InvoiceListItem, MarkPaidInput } from '../../types';
import { Button, Field, Modal } from '../../ui';
import { PAYMENT_METHOD_OPTIONS, todayIso } from './invoiceFormat';
import { markPaidSchema, toMarkPaidInput, type MarkPaidValues } from './invoiceSchemas';

interface MarkPaidModalProps {
  invoice: Pick<InvoiceListItem, 'id' | 'invoice_number' | 'total'> | null;
  onClose: () => void;
  onSubmit: (data: MarkPaidInput) => Promise<void>;
}

function defaults(): MarkPaidValues {
  return { paid_date: todayIso(), payment_method: '' };
}

export const MarkPaidModal: React.FC<MarkPaidModalProps> = ({ invoice, onClose, onSubmit }) => {
  const form = useForm<MarkPaidValues>({ defaultValues: defaults(), resolver: zodResolver(markPaidSchema) });
  const { register, handleSubmit, reset, formState } = form;
  const { errors, isDirty, isSubmitting } = formState;

  useEffect(() => {
    if (invoice) reset(defaults());
  }, [invoice, reset]);

  const submit = handleSubmit((values) => onSubmit(toMarkPaidInput(values)));

  return (
    <Modal
      open={invoice !== null}
      onClose={onClose}
      title="Als bezahlt markieren"
      size="sm"
      isDirty={isDirty}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
            Abbrechen
          </Button>
          <Button onClick={() => void submit()} loading={isSubmitting} disabled={isSubmitting}>
            Zahlung erfassen
          </Button>
        </>
      }
    >
      {invoice && (
        <form className="invoice-form" onSubmit={submit} noValidate>
          <dl className="invoice-summary">
            <div>
              <dt>Rechnungsnummer</dt>
              <dd className="ui-num">{invoice.invoice_number}</dd>
            </div>
            <div>
              <dt>Gesamtbetrag</dt>
              <dd className={`ui-num ${MONEY_CLASS}`}>{formatEur(invoice.total)}</dd>
            </div>
          </dl>

          <Field label="Zahlungsdatum" name="paid_date" required error={errors.paid_date?.message}>
            <input id="paid-date" type="date" max={todayIso()} {...register('paid_date')} />
          </Field>

          <Field label="Zahlungsart" name="payment_method">
            <select id="paid-method" {...register('payment_method')}>
              <option value="">Keine Angabe</option>
              {PAYMENT_METHOD_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </Field>
        </form>
      )}
    </Modal>
  );
};
