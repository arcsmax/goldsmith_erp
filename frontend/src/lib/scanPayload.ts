// Scan payload grammar shared by the scanner router and scan tracking.
//
// Labels print `ORDER:<id>` / `REPAIR:<id>` (backend label_service). The
// prefix list MUST equal backend scanner_service.KNOWN_PREFIXES_V1_1; the
// backend contract test tests/unit/test_scan_prefix_sync.py reads this file
// and fails on drift (SC-06).
//
// Tolerated variants (hand-typed or older wedge scanners): lower/mixed case
// prefix ("order:42"), whitespace around the colon ("ORDER : 42") and a bare
// number (treated as an order, SC-07: labels always carry a prefix, so a
// bare number only comes from typing the order number). Anything else is
// "unrecognised": the server still gets it (it answers resolved=false) and
// the scan is logged as `unrecognised`.

export const KNOWN_SCAN_PREFIXES = [
  'ORDER',
  'REPAIR',
  'METAL',
  'MATERIAL',
  'ACTIVITY',
  'INTERRUPT',
] as const;

export type ScanPrefix = (typeof KNOWN_SCAN_PREFIXES)[number];

export type PayloadKind = 'prefix' | 'numeric' | 'unrecognised';

export interface ClassifiedPayload {
  kind: PayloadKind;
  /** Canonical `PREFIX:rest` for prefix / numeric hits, else null. */
  canonical: string | null;
}

const PREFIX_SET: ReadonlySet<string> = new Set(KNOWN_SCAN_PREFIXES);
const PREFIX_SHAPE = /^([A-Za-z]+)\s*:\s*(\S.*)$/;
const NUMERIC_ONLY = /^\d+$/;

/** Classify a trimmed payload; see the module header for the grammar. */
export function classifyPayload(raw: string): ClassifiedPayload {
  const trimmed = raw.trim();
  const prefixMatch = trimmed.match(PREFIX_SHAPE);
  if (prefixMatch !== null) {
    const prefix = prefixMatch[1].toUpperCase();
    if (PREFIX_SET.has(prefix)) {
      return { kind: 'prefix', canonical: `${prefix}:${prefixMatch[2].trim()}` };
    }
    // Unknown prefix: never guess (FOO:42 must not become ORDER:42).
    return { kind: 'unrecognised', canonical: null };
  }
  if (NUMERIC_ONLY.test(trimmed)) {
    return { kind: 'numeric', canonical: `ORDER:${trimmed}` };
  }
  return { kind: 'unrecognised', canonical: null };
}

/** German message for a code the workshop does not know. */
export function unrecognisedMessage(raw: string): string {
  const shown = raw.trim().slice(0, 40);
  return `Code „${shown}“ nicht erkannt. Bitte die Auftrags- oder Reparaturnummer eintippen.`;
}
