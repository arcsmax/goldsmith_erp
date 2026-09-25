// zod schemas for the quote forms (W4-03, review 04 section F item 6).
// Used through react-hook-form's zodResolver. Messages say what is wrong and
// how to fix it (UI-UX-PLAYBOOK 4.4). Limits mirror the backend models
// (models/quote.py: quantity > 0, unit_price >= 0, notes <= 2000).
import { z } from 'zod';
import { LINE_TYPES } from './quoteFormat';
import type { QuoteLineType } from '../../types';

export const MAX_NOTES_LENGTH = 2000;
export const MAX_DESCRIPTION_LENGTH = 500;
const MAX_VALID_DAYS = 365;
const MAX_TAX_RATE = 100;

export const lineItemSchema = z.object({
  line_type: z.enum(LINE_TYPES as [QuoteLineType, ...QuoteLineType[]]),
  description: z
    .string()
    .trim()
    .min(1, 'Beschreibung fehlt. Bitte die Position benennen.')
    .max(MAX_DESCRIPTION_LENGTH, `Beschreibung zu lang (höchstens ${MAX_DESCRIPTION_LENGTH} Zeichen).`),
  quantity: z
    .number({ message: 'Menge fehlt. Bitte eine Zahl eingeben.' })
    .positive('Menge muss größer als 0 sein.'),
  unit_price: z
    .number({ message: 'Einzelpreis fehlt. Bitte einen Betrag in Euro eingeben.' })
    .min(0, 'Einzelpreis darf nicht negativ sein.'),
});

export type LineItemValues = z.infer<typeof lineItemSchema>;

/** One editable row; `itemId` binds the row to its database line item. */
export const lineItemRowSchema = lineItemSchema.extend({ itemId: z.number().int() });
export type LineItemRowValues = z.infer<typeof lineItemRowSchema>;

export const lineItemsFormSchema = z.object({ items: z.array(lineItemRowSchema) });
export type LineItemsFormValues = z.infer<typeof lineItemsFormSchema>;

export const EMPTY_LINE_ITEM: LineItemValues = {
  line_type: 'labor',
  description: '',
  quantity: 1,
  unit_price: 0,
};

export const createQuoteSchema = z.object({
  customer_id: z.string().min(1, 'Kunde fehlt. Bitte einen Kunden suchen und auswählen.'),
  customer_label: z.string(),
  order_id: z
    .string()
    .trim()
    .regex(/^\d*$/, 'Auftragsnummer bitte als Zahl eingeben oder leer lassen.'),
  valid_days: z
    .number({ message: 'Gültigkeit fehlt. Bitte die Anzahl Tage eingeben.' })
    .int('Gültigkeit bitte in ganzen Tagen angeben.')
    .min(1, 'Gültigkeit muss mindestens 1 Tag sein.')
    .max(MAX_VALID_DAYS, `Gültigkeit höchstens ${MAX_VALID_DAYS} Tage.`),
  tax_rate: z
    .number({ message: 'MwSt-Satz fehlt. Bitte einen Prozentsatz eingeben.' })
    .min(0, 'MwSt-Satz darf nicht negativ sein.')
    .max(MAX_TAX_RATE, `MwSt-Satz höchstens ${MAX_TAX_RATE} %.`),
  notes: z.string().max(MAX_NOTES_LENGTH, `Anmerkungen höchstens ${MAX_NOTES_LENGTH} Zeichen.`),
});

export type CreateQuoteValues = z.infer<typeof createQuoteSchema>;

export const DEFAULT_VALID_DAYS = 14;
export const DEFAULT_TAX_RATE = 19;
