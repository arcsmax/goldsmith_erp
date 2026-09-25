// Werkstatt-Stammdaten form model (W2-04, DOM-24; W4-03 react-hook-form).
// The zod schema catches what the user can fix before the request; the
// backend stays the authority (§ 14 UStG completeness, IBAN check).
import { z } from 'zod';
import type { WorkshopSettings, WorkshopSettingsInput } from '../../api/admin';

const MAX_VAT_RATE = 100;
const DEFAULT_VAT_RATE = 19;

export type TextFieldKey = Exclude<
  keyof WorkshopSettingsInput,
  'is_kleinunternehmer' | 'default_vat_rate'
>;

export interface TextFieldSpec {
  key: TextFieldKey;
  label: string;
  help?: string;
  type?: 'text' | 'tel' | 'email';
  inputMode?: 'numeric' | 'tel' | 'email';
  required?: boolean;
}

export const TEXT_FIELDS: TextFieldSpec[] = [
  { key: 'name', label: 'Name der Werkstatt', help: 'Erscheint als Rechnungssteller.', required: true },
  { key: 'owner_name', label: 'Inhaberin oder Inhaber' },
  { key: 'street', label: 'Straße und Hausnummer' },
  { key: 'postal_code', label: 'PLZ', inputMode: 'numeric' },
  { key: 'city', label: 'Ort' },
  { key: 'country', label: 'Land' },
  { key: 'phone', label: 'Telefon', type: 'tel', inputMode: 'tel' },
  { key: 'email', label: 'E-Mail', type: 'email', inputMode: 'email' },
  { key: 'tax_number', label: 'Steuernummer', help: 'Steuernummer oder USt-IdNr. ist Pflicht (§ 14 UStG).' },
  { key: 'vat_id', label: 'USt-IdNr.', help: 'z. B. DE123456789' },
  { key: 'iban', label: 'IBAN' },
  { key: 'bic', label: 'BIC' },
  { key: 'bank_name', label: 'Bank' },
  { key: 'invoice_footer', label: 'Fußzeile der Rechnung', help: 'z. B. Dank oder Zahlungsbedingungen.' },
];

const optionalText = z.string();

export const workshopSettingsSchema = z.object({
  name: z.string().trim().min(1, 'Name der Werkstatt fehlt. Er steht auf jeder Rechnung.'),
  owner_name: optionalText,
  street: optionalText,
  postal_code: z
    .string()
    .trim()
    .regex(/^\d{0,10}$/, 'PLZ bitte nur mit Ziffern eingeben.'),
  city: optionalText,
  country: optionalText,
  phone: optionalText,
  email: z
    .string()
    .trim()
    .refine((v) => v === '' || z.email().safeParse(v).success, {
      message: 'E-Mail-Adresse ist ungültig. Bitte im Format name@beispiel.de eingeben.',
    }),
  tax_number: optionalText,
  vat_id: optionalText,
  iban: optionalText,
  bic: optionalText,
  bank_name: optionalText,
  invoice_footer: optionalText,
  is_kleinunternehmer: z.boolean(),
  default_vat_rate: z
    .string()
    .trim()
    .refine((v) => {
      const rate = Number(v.replace(',', '.'));
      return v !== '' && Number.isFinite(rate) && rate >= 0 && rate <= MAX_VAT_RATE;
    }, `Umsatzsteuersatz bitte als Zahl zwischen 0 und ${MAX_VAT_RATE} eingeben.`),
});

export type WorkshopSettingsValues = z.infer<typeof workshopSettingsSchema>;

export const toFormValues = (s: WorkshopSettings): WorkshopSettingsValues => ({
  name: s.name ?? '',
  owner_name: s.owner_name ?? '',
  street: s.street ?? '',
  postal_code: s.postal_code ?? '',
  city: s.city ?? '',
  country: s.country ?? '',
  phone: s.phone ?? '',
  email: s.email ?? '',
  tax_number: s.tax_number ?? '',
  vat_id: s.vat_id ?? '',
  iban: s.iban ?? '',
  bic: s.bic ?? '',
  bank_name: s.bank_name ?? '',
  invoice_footer: s.invoice_footer ?? '',
  is_kleinunternehmer: s.is_kleinunternehmer,
  default_vat_rate: String(s.default_vat_rate ?? DEFAULT_VAT_RATE),
});

/** Blank optional fields go out as null, the rate as a number. */
export const toPayload = (v: WorkshopSettingsValues): WorkshopSettingsInput => {
  const text = (value: string) => value.trim() || null;
  return {
    name: v.name.trim(),
    owner_name: text(v.owner_name),
    street: text(v.street),
    postal_code: text(v.postal_code),
    city: text(v.city),
    country: text(v.country),
    phone: text(v.phone),
    email: text(v.email),
    tax_number: text(v.tax_number),
    vat_id: text(v.vat_id),
    iban: text(v.iban),
    bic: text(v.bic),
    bank_name: text(v.bank_name),
    invoice_footer: text(v.invoice_footer),
    is_kleinunternehmer: v.is_kleinunternehmer,
    default_vat_rate: Number(v.default_vat_rate.replace(',', '.')),
  };
};
