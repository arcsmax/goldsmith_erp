// Month grid and event-marker helpers for CalendarPage (W4-03).
import type {
  AnyCalendarEvent,
  CalendarDeadlineEvent,
  CalendarEvent,
  CalendarEventType,
  TrafficLight,
} from '../../types';

export const DAY_NAMES = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'] as const;
export const DAY_NAMES_FULL = [
  'Montag',
  'Dienstag',
  'Mittwoch',
  'Donnerstag',
  'Freitag',
  'Samstag',
  'Sonntag',
] as const;
export const MONTH_NAMES = [
  'Januar',
  'Februar',
  'März',
  'April',
  'Mai',
  'Juni',
  'Juli',
  'August',
  'September',
  'Oktober',
  'November',
  'Dezember',
] as const;

export const EVENT_TYPE_LABELS: Readonly<Record<CalendarEventType, string>> = {
  order_deadline: 'Auftragsfrist',
  workshop_task: 'Werkstattaufgabe',
  appointment: 'Termin',
  reminder: 'Erinnerung',
};

/** Tone (--tone-*) plus a shape, so a marker never relies on colour alone. */
export type EventTone = 'done' | 'waiting' | 'danger' | 'neutral' | 'info' | 'progress' | 'check';

export interface EventMarker {
  tone: EventTone;
  symbol: string;
  label: string;
}

const DEADLINE_MARKERS: Readonly<Record<TrafficLight | 'none', EventMarker>> = {
  green: { tone: 'done', symbol: '●', label: 'Frist mehr als 5 Tage' },
  yellow: { tone: 'waiting', symbol: '▲', label: 'Frist in 2 bis 5 Tagen' },
  red: { tone: 'danger', symbol: '■', label: 'Frist in weniger als 2 Tagen' },
  grey: { tone: 'neutral', symbol: '✓', label: 'Abgeschlossen' },
  none: { tone: 'neutral', symbol: '✓', label: 'Abgeschlossen' },
};

const TYPE_MARKERS: Readonly<Record<Exclude<CalendarEventType, 'order_deadline'>, EventMarker>> = {
  workshop_task: { tone: 'info', symbol: '◆', label: EVENT_TYPE_LABELS.workshop_task },
  appointment: { tone: 'progress', symbol: '★', label: EVENT_TYPE_LABELS.appointment },
  reminder: { tone: 'check', symbol: '◇', label: EVENT_TYPE_LABELS.reminder },
};

export const LEGEND_MARKERS: readonly EventMarker[] = [
  DEADLINE_MARKERS.green,
  DEADLINE_MARKERS.yellow,
  DEADLINE_MARKERS.red,
  DEADLINE_MARKERS.grey,
  TYPE_MARKERS.workshop_task,
  TYPE_MARKERS.appointment,
  TYPE_MARKERS.reminder,
];

export function isDeadlineEvent(evt: AnyCalendarEvent): evt is CalendarDeadlineEvent {
  return evt.event_type === 'order_deadline' && 'traffic_light' in evt;
}

export function isStoredEvent(evt: AnyCalendarEvent): evt is CalendarEvent {
  return 'user_id' in evt;
}

export function getEventMarker(evt: AnyCalendarEvent): EventMarker {
  if (evt.event_type === 'order_deadline') {
    const light = isDeadlineEvent(evt) ? evt.traffic_light : undefined;
    return DEADLINE_MARKERS[light ?? 'none'] ?? DEADLINE_MARKERS.none;
  }
  return TYPE_MARKERS[evt.event_type] ?? DEADLINE_MARKERS.none;
}

export interface CalendarCell {
  date: Date;
  day: number;
  isCurrentMonth: boolean;
  isToday: boolean;
}

function startOfDay(year: number, month: number, day: number): Date {
  const date = new Date(year, month, day);
  date.setHours(0, 0, 0, 0);
  return date;
}

function getMonthStartDayOffset(year: number, month: number): number {
  const day = new Date(year, month, 1).getDay();
  // JS: 0 = Sunday. We want Monday = 0.
  return day === 0 ? 6 : day - 1;
}

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

export function buildCalendarGrid(year: number, month: number, now = new Date()): CalendarCell[][] {
  const todayTime = startOfDay(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const cell = (y: number, m: number, day: number, isCurrentMonth: boolean): CalendarCell => {
    const date = startOfDay(y, m, day);
    return { date, day, isCurrentMonth, isToday: date.getTime() === todayTime };
  };

  const daysInMonth = getDaysInMonth(year, month);
  const startOffset = getMonthStartDayOffset(year, month);
  const prevMonth = month === 0 ? 11 : month - 1;
  const prevYear = month === 0 ? year - 1 : year;
  const daysInPrevMonth = getDaysInMonth(prevYear, prevMonth);

  const leading = Array.from({ length: startOffset }, (_, i) =>
    cell(prevYear, prevMonth, daysInPrevMonth - startOffset + 1 + i, false),
  );
  const current = Array.from({ length: daysInMonth }, (_, i) => cell(year, month, i + 1, true));
  const filled = leading.length + current.length;
  const trailingCount = (7 - (filled % 7)) % 7;
  const nextMonth = month === 11 ? 0 : month + 1;
  const nextYear = month === 11 ? year + 1 : year;
  const trailing = Array.from({ length: trailingCount }, (_, i) => cell(nextYear, nextMonth, i + 1, false));

  const cells = [...leading, ...current, ...trailing];
  return Array.from({ length: cells.length / 7 }, (_, w) => cells.slice(w * 7, w * 7 + 7));
}

/** Format a Date as YYYY-MM-DD (local time). */
export function toDateString(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/** Group events by their YYYY-MM-DD start date. */
export function groupByDate(events: readonly AnyCalendarEvent[]): Record<string, AnyCalendarEvent[]> {
  return events.reduce<Record<string, AnyCalendarEvent[]>>((map, evt) => {
    const key = evt.start_datetime.substring(0, 10);
    return { ...map, [key]: [...(map[key] ?? []), evt] };
  }, {});
}
