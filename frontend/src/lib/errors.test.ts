import { AxiosError, AxiosHeaders, type AxiosResponse } from 'axios';
import { describe, expect, it } from 'vitest';

import { getErrorCode, getErrorMessage } from './errors';

function axiosError(status: number | null, data?: unknown, code?: string): AxiosError {
  const config = { headers: new AxiosHeaders() };
  const response =
    status === null
      ? undefined
      : ({ status, statusText: '', data, headers: {}, config } as AxiosResponse);
  return new AxiosError('Request failed', code, config, {}, response);
}

describe('getErrorMessage', () => {
  it('returns the German detail of the domain envelope', () => {
    const err = axiosError(409, {
      detail: 'Auftrag ist bereits abgeschlossen.',
      code: 'order.already_completed',
      extra: { order_id: 1 },
    });
    expect(getErrorMessage(err)).toBe('Auftrag ist bereits abgeschlossen.');
    expect(getErrorCode(err)).toBe('order.already_completed');
  });

  it('reads a legacy structured detail with message and code', () => {
    const err = axiosError(409, {
      detail: { code: 'TIMER_POSSIBLY_STALE', message: 'Der Timer läuft seit 9 Stunden.' },
      code: 'timer.possibly_stale',
    });
    expect(getErrorMessage(err)).toBe('Der Timer läuft seit 9 Stunden.');
    // Top-level envelope code wins over the legacy one.
    expect(getErrorCode(err)).toBe('timer.possibly_stale');
  });

  it('falls back to the legacy detail code when there is no envelope code', () => {
    const err = axiosError(409, { detail: { code: 'TIMER_POSSIBLY_STALE' } });
    expect(getErrorCode(err)).toBe('TIMER_POSSIBLY_STALE');
    expect(getErrorMessage(err)).toBe(
      'Die Aktion ist im aktuellen Zustand nicht möglich. Bitte Seite neu laden.',
    );
  });

  it('summarises a FastAPI 422 validation list in German', () => {
    const err = axiosError(422, {
      detail: [
        { loc: ['body', 'weight'], msg: 'Input should be greater than 0', type: 'greater_than' },
        { loc: ['body', 'title'], msg: 'Field required', type: 'missing' },
      ],
    });
    expect(getErrorMessage(err)).toBe(
      'Eingaben prüfen: weight, title. Bitte korrigieren und erneut speichern.',
    );
  });

  it('maps statuses without a detail to German text', () => {
    expect(getErrorMessage(axiosError(401, {}))).toBe(
      'Sitzung abgelaufen. Bitte erneut anmelden.',
    );
    expect(getErrorMessage(axiosError(403, {}))).toBe('Dafür fehlt die Berechtigung.');
    expect(getErrorMessage(axiosError(404, {}))).toBe('Der Eintrag wurde nicht gefunden.');
    expect(getErrorMessage(axiosError(413, {}))).toBe('Die Datei ist zu groß.');
    expect(getErrorMessage(axiosError(429, {}))).toBe(
      'Zu viele Anfragen. Bitte kurz warten und erneut versuchen.',
    );
    expect(getErrorMessage(axiosError(503, '<html>'))).toBe(
      'Der Server hat einen Fehler gemeldet. Bitte später erneut versuchen.',
    );
  });

  it('explains network failures and timeouts', () => {
    expect(getErrorMessage(axiosError(null, undefined, AxiosError.ERR_NETWORK))).toBe(
      'Keine Verbindung zum Server. Bitte Netzwerk prüfen und erneut versuchen.',
    );
    expect(getErrorMessage(axiosError(null, undefined, AxiosError.ECONNABORTED))).toBe(
      'Der Server antwortet nicht. Bitte erneut versuchen.',
    );
  });

  it('never surfaces raw English error messages; uses the fallback', () => {
    expect(getErrorMessage(new Error('Cannot read properties of undefined'))).toBe(
      'Unbekannter Fehler. Bitte erneut versuchen.',
    );
    expect(getErrorMessage(new Error('x'), 'Auftrag konnte nicht gespeichert werden.')).toBe(
      'Auftrag konnte nicht gespeichert werden.',
    );
    expect(getErrorMessage('boom')).toBe('Unbekannter Fehler. Bitte erneut versuchen.');
    expect(getErrorMessage(null)).toBe('Unbekannter Fehler. Bitte erneut versuchen.');
    expect(getErrorCode(null)).toBeNull();
  });

  it('prefers the caller fallback over a generic status text', () => {
    expect(getErrorMessage(axiosError(500, {}), 'Rechnung konnte nicht erstellt werden.')).toBe(
      'Rechnung konnte nicht erstellt werden.',
    );
  });

  it('accepts axios-like plain objects (mocked clients)', () => {
    const err = { isAxiosError: true, response: { status: 400, data: { detail: 'Ungültige Legierung.' } } };
    expect(getErrorMessage(err)).toBe('Ungültige Legierung.');
  });

  it('ignores an empty or oversized detail', () => {
    expect(getErrorMessage(axiosError(400, { detail: '' }))).toBe(
      'Die Anfrage war ungültig. Bitte Eingaben prüfen.',
    );
    expect(getErrorMessage(axiosError(400, { detail: 'x'.repeat(2000) }))).toBe(
      'Die Anfrage war ungültig. Bitte Eingaben prüfen.',
    );
  });
});
