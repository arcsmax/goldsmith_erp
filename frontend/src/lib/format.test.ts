// formatEur: one German money format everywhere (LV-10).
// formatPreferenceKey: never show a raw Customer.preferences dict key (LV-20).
import { describe, expect, it } from 'vitest';
import { formatEur, formatPreferenceKey, MONEY_CLASS } from './format';

// Intl puts a no-break space (U+00A0) between amount and "€", so the sign
// never wraps onto its own line.
const NBSP = ' ';

describe('formatEur', () => {
  it('formats with German separators and a trailing euro sign', () => {
    expect(formatEur(2100)).toBe(`2.100,00${NBSP}€`);
    expect(formatEur(1450.5)).toBe(`1.450,50${NBSP}€`);
  });

  it('keeps two decimals and rounds half away from zero', () => {
    expect(formatEur(45)).toBe(`45,00${NBSP}€`);
    expect(formatEur(0.125)).toBe(`0,13${NBSP}€`);
  });

  it('formats zero and negative amounts', () => {
    expect(formatEur(0)).toBe(`0,00${NBSP}€`);
    expect(formatEur(-12.3)).toBe(`-12,30${NBSP}€`);
  });

  it('accepts numeric strings from Decimal fields', () => {
    expect(formatEur('800.00')).toBe(`800,00${NBSP}€`);
  });

  it('returns a dash for missing or invalid values', () => {
    expect(formatEur(null)).toBe('—');
    expect(formatEur(undefined)).toBe('—');
    expect(formatEur('abc')).toBe('—');
    expect(formatEur(Number.NaN)).toBe('—');
  });

  it('exposes the tabular-nums styling hook', () => {
    expect(MONEY_CLASS).toBe('money');
  });
});

describe('formatPreferenceKey', () => {
  it('maps the known db/models.py keys to a German label', () => {
    expect(formatPreferenceKey('bevorzugt')).toBe('Bevorzugtes Material');
    expect(formatPreferenceKey('style')).toBe('Stil');
  });

  it('humanizes an unrecognized key instead of showing the raw dict key', () => {
    expect(formatPreferenceKey('no_gos')).toBe('No gos');
    expect(formatPreferenceKey('ring-groesse')).toBe('Ring groesse');
  });

  it('falls back to the key itself when it has no readable content', () => {
    expect(formatPreferenceKey('')).toBe('');
  });
});
