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

// Customer preference key labels (LV-20).
//
// Customer.preferences is a free-form Record<string, string> — the intake
// form lets staff type any "key: value" pair (CustomerFormModal.tsx) — but
// db/models.py documents the two keys the app actually writes today:
// {"bevorzugt": "Platin", "style": "modern"}. The detail page was showing
// those programmatic keys verbatim ("bevorzugt Gelbgold · style klassisch").
// This maps the known keys to a German label and falls back to a humanized
// version of any other key instead of the raw dict key.
const PREFERENCE_KEY_LABELS: Readonly<Record<string, string>> = {
  bevorzugt: 'Bevorzugtes Material',
  style: 'Stil',
};

/** Humanize an unrecognized preference key: "no_gos" -> "No gos". */
function humanizePreferenceKey(key: string): string {
  const spaced = key.replace(/[_-]+/g, ' ').trim();
  if (!spaced) return key;
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Display label for a Customer.preferences key; never the raw dict key. */
export function formatPreferenceKey(key: string): string {
  return PREFERENCE_KEY_LABELS[key] ?? humanizePreferenceKey(key);
}
