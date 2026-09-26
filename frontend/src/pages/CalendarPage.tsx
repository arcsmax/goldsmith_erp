// Calendar page — month grid with deadline markers and stored events (W4-03).
//
// Data: one query per visible date range (stored events + order deadlines).
// Order hints invalidate ['calendar'] (lib/realtimeInvalidation.ts), because
// deadlines are derived from order delivery dates. Create, update and delete
// go through useMutation and invalidate ['calendar'].
import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { calendarApi } from '../api/calendar';
import { queryKeys, type DateRange } from '../api/queryKeys';
import { CalendarEventModal } from '../components/CalendarEventModal';
import {
  DAY_NAMES,
  DAY_NAMES_FULL,
  LEGEND_MARKERS,
  MONTH_NAMES,
  buildCalendarGrid,
  getEventMarker,
  groupByDate,
  isDeadlineEvent,
  isStoredEvent,
  toDateString,
  type CalendarCell,
} from '../components/calendar/calendarGrid';
import { getErrorMessage } from '../lib/errors';
import { logError } from '../lib/logError';
import type {
  AnyCalendarEvent,
  CalendarEvent,
  CalendarEventCreate,
  CalendarEventUpdate,
} from '../types';
import { Button, PageHeader, PageState, type PageStateValue } from '../ui';
import '../styles/calendar.css';

/** Maximum events per day cell before "+N weitere". */
const MAX_EVENTS_PER_CELL = 3;

type ModalState =
  | { mode: 'closed' }
  | { mode: 'create'; defaultDate: string }
  | { mode: 'edit'; event: CalendarEvent };

async function fetchCalendar(range: DateRange): Promise<AnyCalendarEvent[]> {
  try {
    const [storedEvents, deadlines] = await Promise.all([
      calendarApi.getEvents(range.start_date, range.end_date),
      calendarApi.getDeadlines(range.start_date, range.end_date),
    ]);
    return [...storedEvents, ...deadlines].sort((a, b) =>
      a.start_datetime.localeCompare(b.start_datetime),
    );
  } catch (err) {
    logError('CalendarPage.fetchCalendar', err);
    throw err;
  }
}

function gridRange(grid: CalendarCell[][]): DateRange {
  const lastWeek = grid[grid.length - 1];
  return {
    start_date: toDateString(grid[0][0].date),
    end_date: toDateString(lastWeek[lastWeek.length - 1].date),
  };
}

function eventTitle(evt: AnyCalendarEvent): string {
  const marker = getEventMarker(evt);
  if (isDeadlineEvent(evt)) {
    return `${evt.title} — ${marker.label}, noch ${evt.days_until_deadline} Tag(e)`;
  }
  return `${evt.title} — ${marker.label}`;
}

interface DayCellProps {
  cell: CalendarCell;
  events: AnyCalendarEvent[];
  onCreate: (dateKey: string) => void;
  onOpenEvent: (evt: AnyCalendarEvent) => void;
}

const DayCell: React.FC<DayCellProps> = ({ cell, events, onCreate, onOpenEvent }) => {
  const dateKey = toDateString(cell.date);
  const visible = events.slice(0, MAX_EVENTS_PER_CELL);
  const hiddenCount = events.length - visible.length;
  const dateLabel = cell.date.toLocaleDateString('de-DE', { day: 'numeric', month: 'long' });
  const cellClass = [
    'calendar-day',
    cell.isCurrentMonth ? 'current-month' : 'other-month',
    cell.isToday ? 'today' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <td aria-current={cell.isToday ? 'date' : undefined}>
      <div className={cellClass}>
        {cell.isCurrentMonth ? (
          <button
            type="button"
            className="calendar-day-number"
            onClick={() => onCreate(dateKey)}
            aria-label={`${dateLabel}: Termin anlegen`}
          >
            {cell.day}
          </button>
        ) : (
          <span className="calendar-day-number">{cell.day}</span>
        )}

        <div className="calendar-day-orders">
          {visible.map((evt) => {
            const marker = getEventMarker(evt);
            return (
              <button
                type="button"
                key={`${evt.event_type}-${evt.id}`}
                className="calendar-event"
                onClick={() => onOpenEvent(evt)}
                title={eventTitle(evt)}
              >
                <span className={`calendar-marker calendar-marker--${marker.tone}`} aria-hidden="true">
                  {marker.symbol}
                </span>
                <span className="ui-visually-hidden">{marker.label}: </span>
                <span className="calendar-event__title">{evt.title}</span>
              </button>
            );
          })}
          {hiddenCount > 0 && <span className="calendar-more">+{hiddenCount} weitere</span>}
        </div>
      </div>
    </td>
  );
};

function useCalendarMutations(modal: ModalState) {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: queryKeys.calendar.all });

  const save = useMutation({
    mutationFn: (data: CalendarEventCreate | CalendarEventUpdate) =>
      modal.mode === 'edit'
        ? calendarApi.updateEvent(modal.event.id, data as CalendarEventUpdate)
        : calendarApi.createEvent(data as CalendarEventCreate),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: number) => calendarApi.deleteEvent(id),
    onSuccess: invalidate,
  });

  return { save, remove };
}

export const CalendarPage: React.FC = () => {
  const navigate = useNavigate();
  const [month, setMonth] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() };
  });
  const [modal, setModal] = useState<ModalState>({ mode: 'closed' });

  const grid = useMemo(() => buildCalendarGrid(month.year, month.month), [month]);
  const range = useMemo(() => gridRange(grid), [grid]);

  const calendarQuery = useQuery({
    queryKey: queryKeys.calendar.events(range),
    queryFn: () => fetchCalendar(range),
  });
  const eventsByDate = useMemo(() => groupByDate(calendarQuery.data ?? []), [calendarQuery.data]);
  const { save, remove } = useCalendarMutations(modal);

  const shiftMonth = (delta: number) =>
    setMonth(({ year, month: m }) => {
      const next = new Date(year, m + delta, 1);
      return { year: next.getFullYear(), month: next.getMonth() };
    });
  const goToToday = () => {
    const now = new Date();
    setMonth({ year: now.getFullYear(), month: now.getMonth() });
  };

  const openEvent = (evt: AnyCalendarEvent) => {
    if (isDeadlineEvent(evt)) {
      // Deadline events belong to an order: open the order instead of editing.
      navigate(`/orders/${evt.order_id}`);
      return;
    }
    if (isStoredEvent(evt)) setModal({ mode: 'edit', event: evt });
  };

  const handleSave = async (data: CalendarEventCreate | CalendarEventUpdate): Promise<void> => {
    await save.mutateAsync(data);
  };
  const handleDelete = async (): Promise<void> => {
    if (modal.mode === 'edit') await remove.mutateAsync(modal.event.id);
  };
  const closeModal = () => setModal({ mode: 'closed' });

  const state: PageStateValue = calendarQuery.isError
    ? {
        status: 'error',
        error: getErrorMessage(calendarQuery.error, 'Kalender konnte nicht geladen werden'),
        retry: () => void calendarQuery.refetch(),
      }
    : { status: 'ready' };
  const monthLabel = `${MONTH_NAMES[month.month]} ${month.year}`;

  return (
    <div className="calendar-page">
      <PageHeader
        title="Kalender"
        meta={calendarQuery.isFetching ? 'Wird geladen…' : undefined}
        primaryAction={
          <Button
            icon="plus"
            onClick={() => setModal({ mode: 'create', defaultDate: toDateString(new Date()) })}
          >
            Termin anlegen
          </Button>
        }
      />

      <nav className="calendar-nav" aria-label="Monat wählen">
        <Button variant="secondary" icon="arrow-left" onClick={() => shiftMonth(-1)}>
          Zurück
        </Button>
        <Button variant="ghost" onClick={goToToday}>
          Heute
        </Button>
        <h2 className="calendar-month-label" aria-live="polite">
          {monthLabel}
        </h2>
        <Button variant="secondary" onClick={() => shiftMonth(1)}>
          Weiter
        </Button>
      </nav>

      <ul className="calendar-legend" aria-label="Legende">
        {LEGEND_MARKERS.map((marker) => (
          <li key={marker.label} className="legend-item">
            <span className={`calendar-marker calendar-marker--${marker.tone}`} aria-hidden="true">
              {marker.symbol}
            </span>
            {marker.label}
          </li>
        ))}
      </ul>

      <PageState state={state}>
        <div className="calendar-grid">
          <table className="calendar-table">
            <caption className="ui-visually-hidden">Kalender {monthLabel}</caption>
            <thead>
              <tr>
                {DAY_NAMES.map((name, i) => (
                  <th key={name} scope="col">
                    <abbr title={DAY_NAMES_FULL[i]}>{name}</abbr>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.map((week) => (
                <tr key={toDateString(week[0].date)}>
                  {week.map((cell) => (
                    <DayCell
                      key={toDateString(cell.date)}
                      cell={cell}
                      events={eventsByDate[toDateString(cell.date)] ?? []}
                      onCreate={(defaultDate) => setModal({ mode: 'create', defaultDate })}
                      onOpenEvent={openEvent}
                    />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </PageState>

      {modal.mode !== 'closed' && (
        <CalendarEventModal
          event={modal.mode === 'edit' ? modal.event : undefined}
          defaultDate={modal.mode === 'create' ? modal.defaultDate : undefined}
          onSave={handleSave}
          onDelete={modal.mode === 'edit' ? handleDelete : undefined}
          onClose={closeModal}
        />
      )}
    </div>
  );
};
