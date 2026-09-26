// getErrorMessage / getErrorCode (review 04 section F item 5; FE-16 raw
// axios messages): one place that turns any thrown value into German text
// for the UI.
//
// Understands, in order:
// 1. the backend domain envelope `{detail, code, extra}`
//    (src/goldsmith_erp/core/errors.py): `detail` is the German message;
// 2. legacy structured detail `{detail: {code, message?}}`;
// 3. FastAPI/Pydantic 422 `{detail: [{loc, msg, type}]}`: names the fields
//    (the English `msg` is never shown);
// 4. axios transport failures (no response, timeout);
// 5. HTTP status defaults.
// Anything else (plain Error, string) returns the caller's fallback: raw
// JavaScript or English messages never reach the workshop UI.
// The payload is untrusted input: every field is type-checked, and an
// oversized detail is ignored rather than rendered.

export const DEFAULT_ERROR_MESSAGE = 'Unbekannter Fehler. Bitte erneut versuchen.';
const MAX_DETAIL_LENGTH = 500;

const STATUS_MESSAGES: Record<number, string> = {
  400: 'Die Anfrage war ungültig. Bitte Eingaben prüfen.',
  401: 'Sitzung abgelaufen. Bitte erneut anmelden.',
  403: 'Dafür fehlt die Berechtigung.',
  404: 'Der Eintrag wurde nicht gefunden.',
  409: 'Die Aktion ist im aktuellen Zustand nicht möglich. Bitte Seite neu laden.',
  413: 'Die Datei ist zu groß.',
  422: 'Eingaben prüfen. Bitte korrigieren und erneut speichern.',
  429: 'Zu viele Anfragen. Bitte kurz warten und erneut versuchen.',
};
const SERVER_ERROR_MESSAGE = 'Der Server hat einen Fehler gemeldet. Bitte später erneut versuchen.';
const NETWORK_MESSAGE = 'Keine Verbindung zum Server. Bitte Netzwerk prüfen und erneut versuchen.';
const TIMEOUT_MESSAGE = 'Der Server antwortet nicht. Bitte erneut versuchen.';
const TIMEOUT_CODES = new Set(['ECONNABORTED', 'ETIMEDOUT']);

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null;
}

function usableText(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  return text.length > 0 && text.length <= MAX_DETAIL_LENGTH ? text : null;
}

interface HttpErrorShape {
  isHttpError: boolean;
  status: number | null;
  data: unknown;
  code: string | null;
}

function readHttpError(err: unknown): HttpErrorShape {
  if (!isRecord(err) || err.isAxiosError !== true) {
    return { isHttpError: false, status: null, data: undefined, code: null };
  }
  const response = isRecord(err.response) ? err.response : null;
  return {
    isHttpError: true,
    status: response && typeof response.status === 'number' ? response.status : null,
    data: response?.data,
    code: typeof err.code === 'string' ? err.code : null,
  };
}

function fieldName(loc: unknown): string | null {
  if (!Array.isArray(loc)) return null;
  const parts = loc.filter((part) => part !== 'body' && part !== 'query' && part !== 'path');
  const last = parts[parts.length - 1];
  return typeof last === 'string' || typeof last === 'number' ? String(last) : null;
}

function validationMessage(detail: unknown[]): string {
  const fields = detail
    .map((item) => (isRecord(item) ? fieldName(item.loc) : null))
    .filter((name): name is string => name !== null);
  const unique = Array.from(new Set(fields));
  if (unique.length === 0) return STATUS_MESSAGES[422];
  return `Eingaben prüfen: ${unique.join(', ')}. Bitte korrigieren und erneut speichern.`;
}

function messageFromDetail(detail: unknown): string | null {
  const text = usableText(detail);
  if (text) return text;
  if (Array.isArray(detail)) return validationMessage(detail);
  if (isRecord(detail)) return usableText(detail.message);
  return null;
}

function statusMessage(status: number | null): string | null {
  if (status === null) return null;
  if (status >= 500) return SERVER_ERROR_MESSAGE;
  return STATUS_MESSAGES[status] ?? null;
}

/**
 * German, user-facing text for any error.
 * `fallback` (e.g. "Auftrag konnte nicht gespeichert werden.") wins over the
 * generic status texts but never over a message the backend wrote.
 */
export function getErrorMessage(err: unknown, fallback?: string): string {
  const http = readHttpError(err);
  if (!http.isHttpError) return fallback ?? DEFAULT_ERROR_MESSAGE;

  if (http.status === null) {
    if (http.code && TIMEOUT_CODES.has(http.code)) return TIMEOUT_MESSAGE;
    return NETWORK_MESSAGE;
  }

  const fromBody = isRecord(http.data) ? messageFromDetail(http.data.detail) : null;
  if (fromBody) return fromBody;

  return fallback ?? statusMessage(http.status) ?? DEFAULT_ERROR_MESSAGE;
}

/**
 * Machine-readable error code: the envelope `code` ("order.already_completed"),
 * else a legacy `detail.code` ("TIMER_POSSIBLY_STALE"), else null.
 */
export function getErrorCode(err: unknown): string | null {
  const http = readHttpError(err);
  if (!isRecord(http.data)) return null;
  if (typeof http.data.code === 'string') return http.data.code;
  const detail = http.data.detail;
  return isRecord(detail) && typeof detail.code === 'string' ? detail.code : null;
}

/** HTTP status of an axios error, or null. */
export function getErrorStatus(err: unknown): number | null {
  return readHttpError(err).status;
}

/**
 * The envelope's `extra` object (non-sensitive context such as an order id
 * or the allowed next states — see core/errors.py), or null when absent.
 * Pair with `getErrorCode` to branch on a specific error before reading it.
 */
export function getErrorExtra(err: unknown): Record<string, unknown> | null {
  const http = readHttpError(err);
  if (!isRecord(http.data)) return null;
  return isRecord(http.data.extra) ? (http.data.extra as Record<string, unknown>) : null;
}
