import { describe, expect, it } from 'vitest';
import { formatDate, formatDateTime, parseUTC } from './formatters';

// Regression coverage for the BE-15 timezone-aware datetime rollout
// (docs/architecture/ADR-2026-09-25-numeric-and-tz.md): the backend now
// serialises datetimes with an explicit 'Z' suffix instead of a naive
// string. parseUTC() must keep treating both forms as the same UTC
// instant — never double-applying the offset by appending a second 'Z'
// or by re-interpreting an already-timezone-aware string as local time.
describe('parseUTC', () => {
  it('parses a naive (pre-BE-15) timestamp as UTC', () => {
    const date = parseUTC('2026-09-25T22:30:00');
    expect(date.getTime()).toBe(Date.UTC(2026, 8, 25, 22, 30, 0));
  });

  it('parses a Z-suffixed (post-BE-15) timestamp as the same UTC instant', () => {
    const date = parseUTC('2026-09-25T22:30:00Z');
    expect(date.getTime()).toBe(Date.UTC(2026, 8, 25, 22, 30, 0));
  });

  it('gives identical results for the naive and Z-suffixed forms of the same instant', () => {
    const naive = parseUTC('2026-01-15T09:05:00');
    const zoned = parseUTC('2026-01-15T09:05:00Z');
    expect(zoned.getTime()).toBe(naive.getTime());
  });

  it('does not double-apply the offset when a Z suffix is already present', () => {
    // A buggy implementation that always appended 'Z' regardless of the
    // input would turn '...:00Z' into '...:00ZZ', which Date() cannot
    // parse (NaN) — this is the "double-apply" regression to guard against.
    const date = parseUTC('2026-09-25T22:30:00Z');
    expect(Number.isNaN(date.getTime())).toBe(false);
  });

  it('returns an invalid Date for an empty string instead of throwing', () => {
    expect(Number.isNaN(parseUTC('').getTime())).toBe(true);
  });
});

describe('formatDate', () => {
  it('formats a naive and a Z-suffixed timestamp for the same day identically', () => {
    // Both denote the same UTC instant; only the wire format differs.
    expect(formatDate('2026-09-25T08:00:00')).toBe(
      formatDate('2026-09-25T08:00:00Z'),
    );
  });

  it('renders the German dd.mm.yyyy format for a Z-suffixed date', () => {
    expect(formatDate('2026-09-25T08:00:00Z')).toBe('25.09.2026');
  });
});

describe('formatDateTime', () => {
  it('formats a naive and a Z-suffixed timestamp for the same instant identically', () => {
    expect(formatDateTime('2026-09-25T08:00:00')).toBe(
      formatDateTime('2026-09-25T08:00:00Z'),
    );
  });
});
