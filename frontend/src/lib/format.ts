// Shared display formatters (LV-10).
//
// One money format for the whole app: de-DE, euro sign after the amount,
// always two decimals ("2.100,00 €"). Intl separates amount and sign with a
// no-break space, so the sign never wraps; cells that hold money also get
// MONEY_CLASS (tabular-nums + nowrap, styles/utilities.css).

const EUR_FORMATTER = new Intl.NumberFormat('de-DE', {
  style: 'currency',
  currency: 'EUR',
});

/** CSS class for any element that shows a money amount. */
export const MONEY_CLASS = 'money';

/** Placeholder for a missing amount. */
export const MISSING_VALUE = '—';

/**
 * Format a euro amount. Accepts numbers and the numeric strings Pydantic
 * sends for Decimal fields; null, undefined and non-numeric input give "—".
 */
export function formatEur(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return MISSING_VALUE;
  const amount = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(amount)) return MISSING_VALUE;
  return EUR_FORMATTER.format(amount);
}
