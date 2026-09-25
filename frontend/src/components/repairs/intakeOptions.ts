// Counter intake (W2-12): options, parsing and payload building, kept
// free of React so the rules are easy to read and test.
import type { RepairIntakeInput } from '../../api/repairs';
import type { RepairItemType } from '../../types';

export const ITEM_TYPE_OPTIONS: ReadonlyArray<{ value: RepairItemType; label: string }> = [
  { value: 'ring', label: 'Ring' },
  { value: 'chain', label: 'Kette' },
  { value: 'bracelet', label: 'Armband' },
  { value: 'earring', label: 'Ohrringe' },
  { value: 'watch', label: 'Uhr' },
  { value: 'brooch', label: 'Brosche' },
  { value: 'other', label: 'Sonstiges' },
];

export const METAL_OPTIONS: readonly string[] = [
  '585 Gelbgold',
  '750 Gelbgold',
  '585 Weißgold',
  '925 Silber',
  '950 Platin',
];

export const CONDITION_OPTIONS: readonly string[] = [
  'Kratzer',
  'Dellen',
  'Verbogen',
  'Tragespuren',
  'Stein fehlt',
  'Stein locker',
  'Verfärbt',
];

export const PROBLEM_OPTIONS: readonly string[] = [
  'Stein locker',
  'Kette gerissen',
  'Verschluss defekt',
  'Größe ändern',
  'Reinigen und polieren',
  'Gravur',
];

export const PROMISE_OPTIONS: ReadonlyArray<{ days: number; label: string }> = [
  { days: 3, label: 'In 3 Tagen' },
  { days: 7, label: 'In 1 Woche' },
  { days: 14, label: 'In 2 Wochen' },
];

export const INTAKE_MESSAGES = {
  customerMissing: 'Kundin oder Kunde fehlt. Bitte suchen oder neu anlegen.',
  descriptionMissing: 'Beschreibung fehlt. Bitte das Stück kurz beschreiben.',
  priceInvalid: 'Preis ungültig. Bitte als Zahl eingeben, z. B. 45,00.',
} as const;

export interface IntakeForm {
  customerId: number | null;
  itemType: RepairItemType;
  metal: string;
  description: string;
  conditions: string[];
  problem: string;
  price: string;
  promisedDate: string; // yyyy-mm-dd from <input type="date">, or ''
}

// Validation lives in repairSchemas.ts (intakeSchema, zod + react-hook-form).

export const EMPTY_INTAKE: IntakeForm = {
  customerId: null,
  itemType: 'ring',
  metal: '',
  description: '',
  conditions: [],
  problem: '',
  price: '',
  promisedDate: '',
};

/** "45,50", "45.50", "1.200,00" -> number; '' -> null; garbage -> NaN. */
export function parsePrice(raw: string): number | null {
  const text = raw.trim().replace(/\s|€/g, '');
  if (!text) return null;
  const normalised = text.includes(',') ? text.replace(/\./g, '').replace(',', '.') : text;
  if (!/^\d+(\.\d{1,2})?$/.test(normalised)) return Number.NaN;
  return Number(normalised);
}

/** Local calendar date `days` from `now`, as yyyy-mm-dd. */
export function dateInDays(days: number, now: Date = new Date()): string {
  const target = new Date(now.getFullYear(), now.getMonth(), now.getDate() + days);
  const month = String(target.getMonth() + 1).padStart(2, '0');
  const day = String(target.getDate()).padStart(2, '0');
  return `${target.getFullYear()}-${month}-${day}`;
}

/** Toggle `value` in a list without mutating it. */
export function toggle(list: readonly string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/** Append a problem chip to the free text (once). */
export function appendProblem(current: string, chip: string): string {
  const parts = current
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean);
  if (parts.includes(chip)) return current;
  return [...parts, chip].join(', ');
}

/** The POST /repairs/ body. Empty optional fields are left out. */
export function buildIntakePayload(form: IntakeForm, withPrice: boolean): RepairIntakeInput {
  const price = withPrice ? parsePrice(form.price) : null;
  return {
    customer_id: form.customerId,
    item_type: form.itemType,
    item_description: form.description.trim(),
    ...(form.metal.trim() ? { metal_type: form.metal.trim() } : {}),
    ...(form.conditions.length ? { condition_notes: form.conditions } : {}),
    ...(form.problem.trim() ? { customer_problem: form.problem.trim() } : {}),
    ...(price !== null ? { estimated_cost: price } : {}),
    ...(form.promisedDate
      ? { estimated_completion_date: new Date(form.promisedDate).toISOString() }
      : {}),
  };
}
