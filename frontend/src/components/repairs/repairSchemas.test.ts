// repairSchemas — zod rules of the counter intake and the status dialogs
// (W4-03). The messages are the German texts the form shows next to the
// field, so they are pinned here word for word.
import { describe, expect, it } from 'vitest';
import { EMPTY_INTAKE, INTAKE_MESSAGES, type IntakeForm } from './intakeOptions';
import {
  completeSchema,
  diagnoseSchema,
  intakeSchema,
  MAX_CONDITIONS,
  MAX_DESCRIPTION_LENGTH,
  toAmountInput,
} from './repairSchemas';

const VALID: IntakeForm = { ...EMPTY_INTAKE, customerId: 7, description: 'Ehering' };

function messages(result: { success: boolean; error?: { issues: Array<{ path: PropertyKey[]; message: string }> } }) {
  return Object.fromEntries((result.error?.issues ?? []).map((i) => [String(i.path[0]), i.message]));
}

describe('intakeSchema', () => {
  it('accepts a complete intake', () => {
    expect(intakeSchema(true).safeParse({ ...VALID, price: '45,50' }).success).toBe(true);
  });

  it('names a missing customer and a missing description', () => {
    const result = intakeSchema(true).safeParse({ ...EMPTY_INTAKE, description: '   ' });
    expect(result.success).toBe(false);
    expect(messages(result)).toMatchObject({
      customerId: INTAKE_MESSAGES.customerMissing,
      description: INTAKE_MESSAGES.descriptionMissing,
    });
  });

  it('rejects a price that is not an amount, but allows an empty one', () => {
    expect(messages(intakeSchema(true).safeParse({ ...VALID, price: 'abc' }))).toEqual({
      price: INTAKE_MESSAGES.priceInvalid,
    });
    expect(intakeSchema(true).safeParse({ ...VALID, price: '' }).success).toBe(true);
    expect(intakeSchema(true).safeParse({ ...VALID, price: '1.200,00' }).success).toBe(true);
  });

  it('ignores the price for roles without FINANCIAL_VIEW (the field is not shown)', () => {
    expect(intakeSchema(false).safeParse({ ...VALID, price: 'abc' }).success).toBe(true);
  });

  it('enforces the backend limits', () => {
    const tooLong = 'x'.repeat(MAX_DESCRIPTION_LENGTH + 1);
    expect(messages(intakeSchema(true).safeParse({ ...VALID, description: tooLong })).description).toBe(
      `Beschreibung zu lang (höchstens ${MAX_DESCRIPTION_LENGTH} Zeichen).`,
    );
    const conditions = Array.from({ length: MAX_CONDITIONS + 1 }, (_, i) => `c${i}`);
    expect(messages(intakeSchema(true).safeParse({ ...VALID, conditions })).conditions).toBe(
      `Höchstens ${MAX_CONDITIONS} Zustandsangaben.`,
    );
  });

  it('rejects an unknown piece type', () => {
    expect(intakeSchema(true).safeParse({ ...VALID, itemType: 'crown' }).success).toBe(false);
  });
});

describe('diagnoseSchema and completeSchema', () => {
  it('needs a finding and a cost estimate', () => {
    const result = diagnoseSchema.safeParse({
      diagnosisNotes: ' ',
      estimatedCost: '',
      estimatedCompletionDate: '',
    });
    expect(messages(result)).toEqual({
      diagnosisNotes: 'Befund fehlt. Bitte beschreiben, was festgestellt wurde.',
      estimatedCost: 'Kostenvoranschlag fehlt. Bitte als Betrag eingeben, z. B. 45,00.',
    });
  });

  it('accepts comma amounts and needs the final cost', () => {
    expect(
      diagnoseSchema.safeParse({ diagnosisNotes: 'Öse gebrochen', estimatedCost: '45,50', estimatedCompletionDate: '' })
        .success,
    ).toBe(true);
    expect(messages(completeSchema.safeParse({ actualCost: 'viel' }))).toEqual({
      actualCost: 'Tatsächliche Kosten fehlen. Bitte als Betrag eingeben, z. B. 45,00.',
    });
  });

  it('formats a stored amount for the input', () => {
    expect(toAmountInput(45.5)).toBe('45,50');
    expect(toAmountInput(null)).toBe('');
  });
});
