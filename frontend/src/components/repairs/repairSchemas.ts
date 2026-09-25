// zod schemas for the repair forms (W4-03), used through react-hook-form's
// zodResolver. Messages say what is wrong and how to fix it (playbook 4.4).
// Limits mirror the backend models (models/repair.py): description <= 2000,
// metal <= 100, customer problem <= 1000, at most 12 condition chips,
// diagnosis <= 5000, costs >= 0.
import { z } from 'zod';
import type { RepairItemType } from '../../types';
import { INTAKE_MESSAGES, ITEM_TYPE_OPTIONS, parsePrice } from './intakeOptions';

export const MAX_DESCRIPTION_LENGTH = 2000;
export const MAX_METAL_LENGTH = 100;
export const MAX_PROBLEM_LENGTH = 1000;
export const MAX_CONDITIONS = 12;
export const MAX_DIAGNOSIS_LENGTH = 5000;

const ITEM_TYPES = ITEM_TYPE_OPTIONS.map((option) => option.value) as [
  RepairItemType,
  ...RepairItemType[],
];

/** '' (no price) or a valid amount; garbage is rejected. */
const isOptionalAmount = (raw: string): boolean => !Number.isNaN(parsePrice(raw));
/** A required amount: present and valid. */
const isRequiredAmount = (raw: string): boolean => {
  const value = parsePrice(raw);
  return value !== null && !Number.isNaN(value);
};

/**
 * Counter intake. The price indication is only checked when the caller may
 * see prices (FINANCIAL_VIEW); a VIEWER never gets the field.
 */
export function intakeSchema(withPrice: boolean) {
  return z.object({
    customerId: z
      .number()
      .int()
      .nullable()
      .refine((id) => id !== null, INTAKE_MESSAGES.customerMissing),
    itemType: z.enum(ITEM_TYPES),
    metal: z
      .string()
      .max(MAX_METAL_LENGTH, `Metall zu lang (höchstens ${MAX_METAL_LENGTH} Zeichen).`),
    description: z
      .string()
      .refine((text) => text.trim().length > 0, INTAKE_MESSAGES.descriptionMissing)
      .refine(
        (text) => text.trim().length <= MAX_DESCRIPTION_LENGTH,
        `Beschreibung zu lang (höchstens ${MAX_DESCRIPTION_LENGTH} Zeichen).`,
      ),
    conditions: z
      .array(z.string())
      .max(MAX_CONDITIONS, `Höchstens ${MAX_CONDITIONS} Zustandsangaben.`),
    problem: z
      .string()
      .max(MAX_PROBLEM_LENGTH, `Kundenangabe zu lang (höchstens ${MAX_PROBLEM_LENGTH} Zeichen).`),
    price: z
      .string()
      .refine((raw) => !withPrice || isOptionalAmount(raw), INTAKE_MESSAGES.priceInvalid),
    promisedDate: z.string(),
  });
}

export const diagnoseSchema = z.object({
  diagnosisNotes: z
    .string()
    .refine((text) => text.trim().length > 0, 'Befund fehlt. Bitte beschreiben, was festgestellt wurde.')
    .refine(
      (text) => text.trim().length <= MAX_DIAGNOSIS_LENGTH,
      `Befund zu lang (höchstens ${MAX_DIAGNOSIS_LENGTH} Zeichen).`,
    ),
  estimatedCost: z
    .string()
    .refine(isRequiredAmount, 'Kostenvoranschlag fehlt. Bitte als Betrag eingeben, z. B. 45,00.'),
  estimatedCompletionDate: z.string(),
});
export type DiagnoseValues = z.infer<typeof diagnoseSchema>;

export const completeSchema = z.object({
  actualCost: z
    .string()
    .refine(isRequiredAmount, 'Tatsächliche Kosten fehlen. Bitte als Betrag eingeben, z. B. 45,00.'),
});
export type CompleteValues = z.infer<typeof completeSchema>;

/** 45.5 -> "45,50" for a money input's default value. */
export function toAmountInput(value: number | null | undefined): string {
  return value == null ? '' : value.toFixed(2).replace('.', ',');
}
