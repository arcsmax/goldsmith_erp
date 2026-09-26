// Pure helpers of the "Timer bearbeiten" sheet: start-time parsing and
// bounds, notes split, and the minimal PATCH payload.
import type { RunningTimeEntry, RunningTimeEntryEditInput } from '../../api/time-tracking';
import { parseUTC } from '../../utils/formatters';

/** Mirrors services/running_timer_edit.py EDIT_LOG_MARKER. */
export const EDIT_LOG_MARKER = '--- Änderungsprotokoll ---';
export const MAX_START_AGE_MS = 24 * 60 * 60 * 1000;
/** Same tolerance as the server: a start "a minute ahead" is a tap on now. */
export const FUTURE_TOLERANCE_MS = 60 * 1000;
const TIME_PATTERN = /^([01]\d|2[0-3]):([0-5]\d)$/;

export const START_TIME_MESSAGES = {
  invalid: 'Bitte eine Startzeit im Format HH:MM eingeben.',
  future: 'Die Startzeit darf nicht in der Zukunft liegen.',
  tooOld: 'Die Startzeit darf höchstens 24 Stunden zurückliegen.',
} as const;

export interface EditDraft {
  activityId: number;
  orderId: number;
  location: string | null;
  /** Standort id (dropdown-backed); null clears it or a legacy name has no match. */
  locationId: number | null;
  notes: string;
  /** Local wall-clock "HH:MM". */
  startTime: string;
}

/** `(userText, editLog)`; the client only ever edits the user text. */
export function splitNotes(notes: string | null | undefined): [string, string] {
  if (!notes) return ['', ''];
  const index = notes.indexOf(EDIT_LOG_MARKER);
  if (index < 0) return [notes, ''];
  return [notes.slice(0, index).replace(/\n+$/, ''), notes.slice(index + EDIT_LOG_MARKER.length).trim()];
}

function pad(value: number): string {
  return value.toString().padStart(2, '0');
}

export function toLocalTime(date: Date): string {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function draftFromEntry(entry: RunningTimeEntry): EditDraft {
  return {
    activityId: entry.activity_id,
    orderId: entry.order_id,
    location: entry.location ?? null,
    locationId: entry.location_id ?? null,
    notes: splitNotes(entry.notes)[0],
    startTime: toLocalTime(parseUTC(entry.start_time)),
  };
}

/**
 * The new start as a Date on the local day the timer started, or a German
 * error. The server checks the previous entry's end as well.
 */
export function resolveStartTime(
  value: string,
  originalStart: Date,
  now: Date = new Date(),
): { date: Date } | { error: string } {
  const match = TIME_PATTERN.exec(value.trim());
  if (!match) return { error: START_TIME_MESSAGES.invalid };
  const date = new Date(originalStart);
  date.setHours(Number(match[1]), Number(match[2]), 0, 0);
  if (date.getTime() > now.getTime() + FUTURE_TOLERANCE_MS) return { error: START_TIME_MESSAGES.future };
  if (now.getTime() - date.getTime() > MAX_START_AGE_MS) return { error: START_TIME_MESSAGES.tooOld };
  return { date };
}

/** Only the changed fields; `null` when nothing changed. */
export function buildEditPayload(
  entry: RunningTimeEntry,
  draft: EditDraft,
  now: Date = new Date(),
): { payload: RunningTimeEntryEditInput | null } | { error: string } {
  const initial = draftFromEntry(entry);
  const payload: RunningTimeEntryEditInput = {};
  if (draft.activityId !== initial.activityId) payload.activity_id = draft.activityId;
  if (draft.orderId !== initial.orderId) payload.order_id = draft.orderId;
  // The dropdown hands back an id; sending it alone is enough (the server
  // resolves the name from it -- see services/running_timer_edit.py). Only
  // "cleared to no Standort" needs the null sent explicitly.
  if (draft.locationId !== initial.locationId) payload.location_id = draft.locationId;
  if (draft.notes.trim() !== initial.notes.trim()) payload.notes = draft.notes.trim();
  if (draft.startTime !== initial.startTime) {
    const resolved = resolveStartTime(draft.startTime, parseUTC(entry.start_time), now);
    if ('error' in resolved) return resolved;
    payload.start_time = resolved.date.toISOString();
  }
  return { payload: Object.keys(payload).length > 0 ? payload : null };
}
