// zod schemas for the invoice forms (W4-03, review 04 section F item 6),
// used through react-hook-form's zodResolver. Dates are the YYYY-MM-DD
// values of <input type="date">, compared as strings (same format).
import { z } from 'zod';
import type { InvoiceCreateInput, MarkPaidInput } from '../../types';
import { todayIso } from './invoiceFormat';

export const MAX_NOTES_LENGTH = 2000;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export const createInvoiceSchema = z.object({
  order_id: z.string().min(1, 'Auftrag fehlt. Bitte einen abrechenbaren Auftrag wählen.'),
  due_date: z
    .string()
    .regex(DATE_PATTERN, 'Fälligkeitsdatum fehlt. Bitte ein Datum wählen.')
    .refine((value) => value >= todayIso(), 'Fälligkeitsdatum liegt in der Vergangenheit. Bitte ein Datum ab heute wählen.'),
  tax_rate: z.enum(['19', '7', '0']),
  payment_method: z.string(),
  notes: z.string().max(MAX_NOTES_LENGTH, `Anmerkungen höchstens ${MAX_NOTES_LENGTH} Zeichen.`),
});

export type CreateInvoiceValues = z.infer<typeof createInvoiceSchema>;

export function toCreateInput(values: CreateInvoiceValues): InvoiceCreateInput {
  return {
    order_id: Number(values.order_id),
    due_date: new Date(values.due_date).toISOString(),
    tax_rate: Number(values.tax_rate),
    notes: values.notes.trim() || undefined,
    payment_method: values.payment_method || undefined,
  };
}

export const markPaidSchema = z.object({
  paid_date: z
    .string()
    .regex(DATE_PATTERN, 'Zahlungsdatum fehlt. Bitte ein Datum wählen.')
    .refine((value) => value <= todayIso(), 'Zahlungsdatum liegt in der Zukunft. Bitte ein Datum bis heute wählen.'),
  payment_method: z.string(),
});

export type MarkPaidValues = z.infer<typeof markPaidSchema>;

export function toMarkPaidInput(values: MarkPaidValues): MarkPaidInput {
  return {
    paid_date: new Date(values.paid_date).toISOString(),
    payment_method: values.payment_method || undefined,
  };
}
