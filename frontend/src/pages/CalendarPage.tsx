// Calendar Page Component - Monthly calendar with traffic light deadline indicators
// and full create/edit/delete support for calendar events.
import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { calendarApi } from '../api/calendar';
import { CalendarEventModal } from '../components/CalendarEventModal';
import {
  AnyCalendarEvent,
  CalendarDeadlineEvent,
  CalendarEvent,
  CalendarEventCreate,
  CalendarEventType,
  CalendarEventUpdate,
  TrafficLight,
} from '../types';
import '../styles/calendar.css';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DAY_NAMES = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
const DAY_NAMES_FULL = [
  'Montag',
  'Dienstag',
  'Mittwoch',
  'Donnerstag',
  'Freitag',
  'Samstag',
  'Sonntag',
];
const MONTH_NAMES = [
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
];

/** Maximum events to show per day cell before showing "+N weitere" */
const MAX_EVENTS_PER_CELL = 3;

// ---------------------------------------------------------------------------
// Event type color coding
// ---------------------------------------------------------------------------

/**
 * Returns a CSS class suffix for each CalendarEventType.
 * ORDER_DEADLINE uses the traffic-light system; others have fixed colours.
 */
function getEventTypeClass(
  eventType: CalendarEventType,
  trafficLight?: TrafficLight
): string {
  switch (eventType) {
    case 'ORDER_DEADLINE':
      switch (trafficLight) {
        case 'red':
          return 'traffic-red';
        case 'yellow':
          return 'traffic-yellow';
        case 'green':
          return 'traffic-green';
        default:
          return 'traffic-grey';
      }
    case 'WORKSHOP_TASK':
      return 'event-blue';
    case 'APPOINTMENT':
      return 'event-purple';
    case 'REMINDER':
      return 'event-yellow';
    default:
      return 'traffic-grey';
  }
}

/** Human-readable label for event type legend */
const EVENT_TYPE_LABELS: Record<CalendarEventType, string> = {
  ORDER_DEADLINE: 'Auftragsdeadline',
  WORKSHOP_TASK: 'Werkstattaufgabe',
  APPOINTMENT: 'Termin',
  REMINDER: 'Erinnerung',
};

// ---------------------------------------------------------------------------
// Calendar grid helpers
// ---------------------------------------------------------------------------

interface CalendarCell {
  date: Date;
  day: number;
  isCurrentMonth: boolean;
  isToday: boolean;
}

function getMonthStartDayOffset(year: number, month: number): number {
  const day = new Date(year, month, 1).getDay();
  // JS: 0 = Sunday. We want Monday = 0.
  return day === 0 ? 6 : day - 1;
}

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

function buildCalendarGrid(year: number, month: number): CalendarCell[][] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const daysInMonth = getDaysInMonth(year, month);
  const startOffset = getMonthStartDayOffset(year, month);

  const prevMonth = month === 0 ? 11 : month - 1;
  const prevYear = month === 0 ? year - 1 : year;
  const daysInPrevMonth = getDaysInMonth(prevYear, prevMonth);

  const cells: CalendarCell[] = [];

  for (let i = startOffset - 1; i >= 0; i--) {
    const day = daysInPrevMonth - i;
    const date = new Date(prevYear, prevMonth, day);
    date.setHours(0, 0, 0, 0);
    cells.push({ date, day, isCurrentMonth: false, isToday: date.getTime() === today.getTime() });
  }

  for (let day = 1; day <= daysInMonth; day++) {
    const date = new Date(year, month, day);
    date.setHours(0, 0, 0, 0);
    cells.push({ date, day, isCurrentMonth: true, isToday: date.getTime() === today.getTime() });
  }

  const remaining = 7 - (cells.length % 7);
  if (remaining < 7) {
    const nextMonth = month === 11 ? 0 : month + 1;
    const nextYear = month === 11 ? year + 1 : year;
    for (let day = 1; day <= remaining; day++) {
      const date = new Date(nextYear, nextMonth, day);
      date.setHours(0, 0, 0, 0);
      cells.push({ date, day, isCurrentMonth: false, isToday: date.getTime() === today.getTime() });
    }
  }

  const weeks: CalendarCell[][] = [];
  for (let i = 0; i < cells.length; i += 7) {
    weeks.push(cells.slice(i, i + 7));
  }

  return weeks;
}

/** Format a Date as YYYY-MM-DD */
function toDateString(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

// ---------------------------------------------------------------------------
// Type guards
// ---------------------------------------------------------------------------

function isDeadlineEvent(evt: AnyCalendarEvent): evt is CalendarDeadlineEvent {
  return evt.event_type === 'ORDER_DEADLINE' && 'traffic_light' in evt;
}

function isStoredEvent(evt: AnyCalendarEvent): evt is CalendarEvent {
  return 'user_id' in evt;
}

// ---------------------------------------------------------------------------
// Modal state
// ---------------------------------------------------------------------------

type ModalState =
  | { mode: 'closed' }
  | { mode: 'create'; defaultDate: string }
  | { mode: 'edit'; event: CalendarEvent };

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const CalendarPage: React.FC = () => {
  const navigate = useNavigate();
  const today = new Date();

  const [currentYear, setCurrentYear] = useState(today.getFullYear());
  const [currentMonth, setCurrentMonth] = useState(today.getMonth());

  // Merged list of stored events + deadline virtual events
  const [events, setEvents] = useState<AnyCalendarEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [modal, setModal] = useState<ModalState>({ mode: 'closed' });

  const grid = useMemo(
    () => buildCalendarGrid(currentYear, currentMonth),
    [currentYear, currentMonth]
  );

  // Build a map from YYYY-MM-DD → events for fast lookup
  const eventsByDate = useMemo(() => {
    const map: Record<string, AnyCalendarEvent[]> = {};
    for (const evt of events) {
      const dateKey = evt.start_datetime.substring(0, 10);
      if (!map[dateKey]) map[dateKey] = [];
      map[dateKey].push(evt);
    }
    return map;
  }, [events]);

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const firstCell = grid[0][0];
      const lastWeek = grid[grid.length - 1];
      const lastCell = lastWeek[lastWeek.length - 1];
      const start = toDateString(firstCell.date);
      const end = toDateString(lastCell.date);

      // Fetch stored events and deadline virtual events in parallel
      const [storedEvents, deadlines] = await Promise.all([
        calendarApi.getEvents(start, end).catch(() => [] as CalendarEvent[]),
        calendarApi.getDeadlines(start, end).catch(() => [] as CalendarDeadlineEvent[]),
      ]);

      // Merge and sort by start_datetime ascending
      const merged: AnyCalendarEvent[] = [...storedEvents, ...deadlines];
      merged.sort((a, b) =>
        a.start_datetime.localeCompare(b.start_datetime)
      );

      setEvents(merged);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ?? 'Fehler beim Laden der Kalender-Daten'
      );
    } finally {
      setIsLoading(false);
    }
  }, [grid]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // ---------------------------------------------------------------------------
  // Navigation
  // ---------------------------------------------------------------------------

  const goToPrevMonth = () => {
    if (currentMonth === 0) {
      setCurrentMonth(11);
      setCurrentYear((y) => y - 1);
    } else {
      setCurrentMonth((m) => m - 1);
    }
  };

  const goToNextMonth = () => {
    if (currentMonth === 11) {
      setCurrentMonth(0);
      setCurrentYear((y) => y + 1);
    } else {
      setCurrentMonth((m) => m + 1);
    }
  };

  const goToToday = () => {
    const now = new Date();
    setCurrentMonth(now.getMonth());
    setCurrentYear(now.getFullYear());
  };

  // ---------------------------------------------------------------------------
  // Event handlers (modal)
  // ---------------------------------------------------------------------------

  const handleEventClick = (evt: AnyCalendarEvent) => {
    if (isDeadlineEvent(evt)) {
      // Deadline virtual events: navigate to the order instead of editing
      navigate(`/orders/${evt.order_id}`);
      return;
    }
    if (isStoredEvent(evt)) {
      setModal({ mode: 'edit', event: evt });
    }
  };

  const handleDayClick = (dateKey: string) => {
    setModal({ mode: 'create', defaultDate: dateKey });
  };

  const handleSave = async (
    data: CalendarEventCreate | CalendarEventUpdate
  ) => {
    if (modal.mode === 'create') {
      await calendarApi.createEvent(data as CalendarEventCreate);
    } else if (modal.mode === 'edit') {
      await calendarApi.updateEvent(modal.event.id, data as CalendarEventUpdate);
    }
    await fetchData();
  };

  const handleDelete = async () => {
    if (modal.mode !== 'edit') return;
    await calendarApi.deleteEvent(modal.event.id);
    await fetchData();
  };

  const closeModal = () => setModal({ mode: 'closed' });

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="calendar-page">
      {/* Header */}
      <header className="calendar-header">
        <h1>Kalender</h1>
        <div className="calendar-header-actions">
          <button
            className="btn btn-primary calendar-new-btn"
            onClick={() =>
              setModal({ mode: 'create', defaultDate: toDateString(new Date()) })
            }
          >
            + Neuer Termin
          </button>
          <div className="calendar-nav">
            <button className="calendar-nav-btn" onClick={goToPrevMonth}>
              &lsaquo; Zurück
            </button>
            <button className="calendar-nav-btn" onClick={goToToday}>
              Heute
            </button>
            <span className="calendar-month-label">
              {MONTH_NAMES[currentMonth]} {currentYear}
            </span>
            <button className="calendar-nav-btn" onClick={goToNextMonth}>
              Weiter &rsaquo;
            </button>
          </div>
        </div>
      </header>

      {/* Legend */}
      <div className="calendar-legend">
        {/* Traffic light legend for deadlines */}
        <div className="legend-item">
          <span className="traffic-dot traffic-green" />
          Mehr als 5 Tage
        </div>
        <div className="legend-item">
          <span className="traffic-dot traffic-yellow" />
          2–5 Tage
        </div>
        <div className="legend-item">
          <span className="traffic-dot traffic-red" />
          Weniger als 2 Tage
        </div>
        <div className="legend-item">
          <span className="traffic-dot traffic-grey" />
          Abgeschlossen
        </div>
        {/* Fixed event type colours */}
        <div className="legend-item">
          <span className="traffic-dot event-blue" />
          {EVENT_TYPE_LABELS.WORKSHOP_TASK}
        </div>
        <div className="legend-item">
          <span className="traffic-dot event-purple" />
          {EVENT_TYPE_LABELS.APPOINTMENT}
        </div>
        <div className="legend-item">
          <span className="traffic-dot event-yellow" />
          {EVENT_TYPE_LABELS.REMINDER}
        </div>
      </div>

      {/* Status bar */}
      {isLoading && (
        <div className="calendar-status-bar">Lade Kalender...</div>
      )}
      {error && (
        <div className="calendar-status-bar calendar-status-bar--error">
          {error}
        </div>
      )}

      {/* Calendar Grid */}
      <div className="calendar-grid">
        <table className="calendar-table">
          <thead>
            <tr>
              {DAY_NAMES.map((name, i) => (
                <th key={name} title={DAY_NAMES_FULL[i]}>
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.map((week, wi) => (
              <tr key={wi}>
                {week.map((cell) => {
                  const dateKey = toDateString(cell.date);
                  const dayEvents = eventsByDate[dateKey] || [];
                  const visibleEvents = dayEvents.slice(0, MAX_EVENTS_PER_CELL);
                  const hiddenCount = dayEvents.length - visibleEvents.length;

                  const cellClass = [
                    'calendar-day',
                    cell.isCurrentMonth ? 'current-month' : 'other-month',
                    cell.isToday ? 'today' : '',
                  ]
                    .filter(Boolean)
                    .join(' ');

                  return (
                    <td key={dateKey}>
                      <div className={cellClass}>
                        {/* Clicking the day number opens a new-event modal */}
                        <div
                          className="calendar-day-number"
                          onClick={() =>
                            cell.isCurrentMonth && handleDayClick(dateKey)
                          }
                          title={
                            cell.isCurrentMonth ? 'Neuer Termin' : undefined
                          }
                          style={
                            cell.isCurrentMonth ? { cursor: 'pointer' } : undefined
                          }
                          role={cell.isCurrentMonth ? 'button' : undefined}
                          tabIndex={cell.isCurrentMonth ? 0 : undefined}
                          onKeyDown={(e) => {
                            if (
                              cell.isCurrentMonth &&
                              (e.key === 'Enter' || e.key === ' ')
                            )
                              handleDayClick(dateKey);
                          }}
                        >
                          {cell.day}
                        </div>

                        <div className="calendar-day-orders">
                          {visibleEvents.map((evt) => {
                            const trafficLight = isDeadlineEvent(evt)
                              ? evt.traffic_light
                              : undefined;
                            const dotClass = getEventTypeClass(
                              evt.event_type,
                              trafficLight
                            );

                            return (
                              <div
                                key={`${evt.event_type}-${evt.id}`}
                                className={`calendar-order-item calendar-event-item--${evt.event_type.toLowerCase()}`}
                                onClick={() => handleEventClick(evt)}
                                title={
                                  isDeadlineEvent(evt)
                                    ? `${evt.title} — ${evt.days_until_deadline} Tag(e) verbleibend`
                                    : evt.title
                                }
                                role="button"
                                tabIndex={0}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter' || e.key === ' ')
                                    handleEventClick(evt);
                                }}
                              >
                                <span className={`traffic-dot ${dotClass}`} />
                                <span className="order-title">{evt.title}</span>
                              </div>
                            );
                          })}
                          {hiddenCount > 0 && (
                            <div className="calendar-more">
                              +{hiddenCount} weitere
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Event modal */}
      {modal.mode !== 'closed' && (
        <CalendarEventModal
          event={modal.mode === 'edit' ? modal.event : undefined}
          defaultDate={
            modal.mode === 'create' ? modal.defaultDate : undefined
          }
          onSave={handleSave}
          onDelete={modal.mode === 'edit' ? handleDelete : undefined}
          onClose={closeModal}
        />
      )}
    </div>
  );
};
