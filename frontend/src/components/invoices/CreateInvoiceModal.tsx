// "Rechnung erstellen" (W4-03): react-hook-form + zod on the Modal primitive.
// A backend rejection (order already invoiced, not eligible) stays inline in
// the dialog so the input can be fixed instead of starting over.
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import type { InvoiceCreateInput } from '../../types';
import { Button, Field, Modal } from '../../ui';
import {
  DEFAULT_PAYMENT_TERM_DAYS,
  inDaysIso,
  INVOICEABLE_ORDER_STATUSES,
  PAYMENT_METHOD_OPTIONS,
  TAX_RATE_OPTIONS,
  todayIso,
} from './invoiceFormat';
import { createInvoiceSchema, MAX_NOTES_LENGTH, toCreateInput, type CreateInvoiceValues } from './invoiceSchemas';
import { useInvoiceableOrders } from './useInvoiceQueries';

interface CreateInvoiceModalProps {
  open: boolean;
  submitError: string | null;
  onClose: () => void;
  onSubmit: (data: InvoiceCreateInput) => Promise<void>;
}

function defaults(): CreateInvoiceValues {
  return {
    order_id: '',
    due_date: inDaysIso(DEFAULT_PAYMENT_TERM_DAYS),
    tax_rate: '19',
    payment_method: '',
    notes: '',
  };
}

export const CreateInvoiceModal: React.FC<CreateInvoiceModalProps> = ({
  open,
  submitError,
  onClose,
  onSubmit,
}) => {
  const orders = useInvoiceableOrders(open);
  const form = useForm<CreateInvoiceValues>({
    defaultValues: defaults(),
    resolver: zodResolver(createInvoiceSchema),
  });
  const { register, handleSubmit, reset, watch, formState } = form;
  const { errors, isDirty, isSubmitting } = formState;
  const orderId = watch('order_id');
  const eligibleOrders = (orders.data ?? []).filter((o) => INVOICEABLE_ORDER_STATUSES.includes(o.status));

  useEffect(() => {
    if (open) reset(defaults());
  }, [open, reset]);

  const submit = handleSubmit((values) => onSubmit(toCreateInput(values)));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Rechnung erstellen"
      isDirty={isDirty}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
            Abbrechen
          </Button>
          <Button onClick={() => void submit()} loading={isSubmitting} disabled={isSubmitting || !orderId}>
            Rechnung erstellen
          </Button>
        </>
      }
    >
      <form className="invoice-form" onSubmit={submit} noValidate>
        {submitError && (
          <div role="alert" className="invoice-form__error" data-testid="invoice-create-error">
            {submitError}
          </div>
        )}

        {orders.isPending ? (
          <p className="ui-field__help" aria-live="polite">
            Aufträge werden geladen…
          </p>
        ) : (
          <Field
            label="Auftrag"
            name="order_id"
            required
            error={errors.order_id?.message}
            help={
              orders.isError
                ? 'Aufträge konnten nicht geladen werden. Bitte den Dialog schließen und erneut öffnen.'
                : eligibleOrders.length === 0
                ? 'Keine abrechenbaren Aufträge vorhanden. Aufträge brauchen den Status „Abgeschlossen“ oder „Ausgeliefert“.'
                : undefined
            }
          >
            <select id="invoice-order-select" {...register('order_id')}>
              <option value="">Auftrag wählen</option>
              {eligibleOrders.map((o) => (
                <option key={o.id} value={o.id}>
                  #{o.id} – {o.title}
                </option>
              ))}
            </select>
          </Field>
        )}

        <Field label="Fälligkeitsdatum" name="due_date" required error={errors.due_date?.message}>
          <input id="invoice-due-date" type="date" min={todayIso()} {...register('due_date')} />
        </Field>

        <Field label="MwSt-Satz" name="tax_rate">
          <select id="invoice-tax-rate" {...register('tax_rate')}>
            {TAX_RATE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Zahlungsart" name="payment_method">
          <select id="invoice-payment-method" {...register('payment_method')}>
            <option value="">Keine Angabe</option>
            {PAYMENT_METHOD_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Anmerkungen" name="notes" error={errors.notes?.message}>
          <textarea
            id="invoice-notes"
            rows={3}
            maxLength={MAX_NOTES_LENGTH}
            placeholder="Optionale Hinweise zur Rechnung…"
            {...register('notes')}
          />
        </Field>
      </form>
    </Modal>
  );
};
