// Formatting and label helpers shared by the quote components (W4-03).
import type { QuoteApprovalMethod, QuoteWithDelivery } from '../../api/quotes';
import type { QuoteLineType, QuoteStatus } from '../../types';

const DAY_MS = 1000 * 60 * 60 * 24;
/** A quote that runs out within this many days is flagged as "läuft bald ab". */
const EXPIRY_WARNING_DAYS = 3;
const CLOSED_STATUSES: ReadonlySet<QuoteStatus> = new Set<QuoteStatus>([
  'approved',
  'converted',
  'rejected',
]);

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('de-DE');
}

export type ValidityTone = 'expired' | 'soon' | 'ok';

/** How close an open quote is to its "Gültig bis" date; closed quotes are always ok. */
export function validityTone(
  validUntilIso: string,
  status: QuoteStatus,
  now = Date.now(),
): ValidityTone {
  if (CLOSED_STATUSES.has(status)) return 'ok';
  const daysLeft = Math.ceil((new Date(validUntilIso).getTime() - now) / DAY_MS);
  if (daysLeft < 0) return 'expired';
  if (daysLeft <= EXPIRY_WARNING_DAYS) return 'soon';
  return 'ok';
}

/** Text next to the date, so the warning is not carried by colour alone. */
export const VALIDITY_HINT: Record<ValidityTone, string | null> = {
  expired: 'abgelaufen',
  soon: 'läuft bald ab',
  ok: null,
};

/** DOM-11: German toast for the outcome of "Versenden". */
export function sendOutcomeMessage(quote: QuoteWithDelivery): string {
  if (quote.delivery_method === 'email') {
    return 'Kostenvoranschlag per E-Mail versendet.';
  }
  return 'Kostenvoranschlag als versendet vermerkt. Das PDF wurde heruntergeladen, bitte an den Kunden übergeben.';
}

/** DOM-11d: how the customer agreed (backend CostChangeResponseMethod). */
export const APPROVAL_METHOD_OPTIONS: ReadonlyArray<{ value: QuoteApprovalMethod; label: string }> = [
  { value: 'in_person', label: 'Persönlich vor Ort' },
  { value: 'email_reply', label: 'Per E-Mail' },
  { value: 'phone', label: 'Telefonisch' },
];

export const LINE_TYPE_LABELS: Record<QuoteLineType, string> = {
  material: 'Material',
  labor: 'Arbeit',
  gemstone: 'Edelstein',
  other: 'Sonstiges',
};

export const LINE_TYPES = Object.keys(LINE_TYPE_LABELS) as QuoteLineType[];
