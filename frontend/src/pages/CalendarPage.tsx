// Calendar Page Component - Monthly calendar with traffic light deadline indicators
import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { calendarApi } from '../api/calendar';
import { OrderType } from '../types';
import '../styles/calendar.css';

const DAY_NAMES = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
const DAY_NAMES_FULL = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'];
const MONTH_NAMES = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
];

/** Maximum orders to show per day cell before showing "+N weitere" */
const MAX_ORDERS_PER_CELL = 3;

/**
 * Determine traffic light color based on days remaining until deadline.
 * - green:  > 5 days remaining
 * - yellow: 2-5 days remaining
 * - red:    < 2 days remaining
 * - grey:   completed or delivered
 */
function getTrafficClass(order: OrderType): string {
  if (order.status === 'completed' || order.status === 'delivered') {
    return 'traffic-grey';
  }
  if (!order.deadline) return 'traffic-grey';

  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const deadlineDate = new Date(order.deadline);
  deadlineDate.setHours(0, 0, 0, 0);

  const diffMs = deadlineDate.getTime() - now.getTime();
  const diffDays = diffMs / (1000 * 60 * 60 * 24);

  if (diffDays < 2) return 'traffic-red';
  if (diffDays <= 5) return 'traffic-yellow';
  return 'traffic-green';
}

/** Get first day of the month (Monday = 0 based for our grid) */
function getMonthStartDayOffset(year: number, month: number): number {
  const day = new Date(year, month, 1).getDay();
  // JS: 0 = Sunday. We want Monday = 0.
  return day === 0 ? 6 : day - 1;
}

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

/** Build calendar grid weeks for the given month */
interface CalendarCell {
  date: Date;
  day: number;
  isCurrentMonth: boolean;
  isToday: boolean;
}

function buildCalendarGrid(year: number, month: number): CalendarCell[][] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const daysInMonth = getDaysInMonth(year, month);
  const startOffset = getMonthStartDayOffset(year, month);

  // Days from previous month
  const prevMonth = month === 0 ? 11 : month - 1;
  const prevYear = month === 0 ? year - 1 : year;
  const daysInPrevMonth = getDaysInMonth(prevYear, prevMonth);

  const cells: CalendarCell[] = [];

  // Fill in previous month days
  for (let i = startOffset - 1; i >= 0; i--) {
    const day = daysInPrevMonth - i;
    const date = new Date(prevYear, prevMonth, day);
    date.setHours(0, 0, 0, 0);
    cells.push({
      date,
      day,
      isCurrentMonth: false,
      isToday: date.getTime() === today.getTime(),
    });
  }

  // Fill in current month days
  for (let day = 1; day <= daysInMonth; day++) {
    const date = new Date(year, month, day);
    date.setHours(0, 0, 0, 0);
    cells.push({
      date,
      day,
      isCurrentMonth: true,
      isToday: date.getTime() === today.getTime(),
    });
  }

  // Fill in next month days to complete last week
  const remaining = 7 - (cells.length % 7);
  if (remaining < 7) {
    const nextMonth = month === 11 ? 0 : month + 1;
    const nextYear = month === 11 ? year + 1 : year;
    for (let day = 1; day <= remaining; day++) {
      const date = new Date(nextYear, nextMonth, day);
      date.setHours(0, 0, 0, 0);
      cells.push({
        date,
        day,
        isCurrentMonth: false,
        isToday: date.getTime() === today.getTime(),
      });
    }
  }

  // Split into weeks
  const weeks: CalendarCell[][] = [];
  for (let i = 0; i < cells.length; i += 7) {
    weeks.push(cells.slice(i, i + 7));
  }

  return weeks;
}

/** Format a date as YYYY-MM-DD */
function toDateString(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export const CalendarPage: React.FC = () => {
  const navigate = useNavigate();
  const today = new Date();

  const [currentYear, setCurrentYear] = useState(today.getFullYear());
  const [currentMonth, setCurrentMonth] = useState(today.getMonth());
  const [orders, setOrders] = useState<OrderType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const grid = useMemo(
    () => buildCalendarGrid(currentYear, currentMonth),
    [currentYear, currentMonth]
  );

  // Build a map from date string -> orders for fast lookup
  const ordersByDate = useMemo(() => {
    const map: Record<string, OrderType[]> = {};
    for (const order of orders) {
      if (!order.deadline) continue;
      const dateKey = order.deadline.substring(0, 10); // YYYY-MM-DD
      if (!map[dateKey]) map[dateKey] = [];
      map[dateKey].push(order);
    }
    return map;
  }, [orders]);

  const fetchDeadlines = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Compute the visible date range from the grid
      const firstCell = grid[0][0];
      const lastWeek = grid[grid.length - 1];
      const lastCell = lastWeek[lastWeek.length - 1];
      const start = toDateString(firstCell.date);
      const end = toDateString(lastCell.date);

      const data = await calendarApi.getDeadlines(start, end);
      setOrders(data);
    } catch (err: any) {
      // Fallback: if dedicated calendar endpoint is not available,
      // load all orders and filter client-side
      try {
        const { ordersApi } = await import('../api');
        const allOrders = await ordersApi.getAll({ limit: 500 });
        setOrders(allOrders.filter((o) => o.deadline));
        setError(null);
      } catch (fallbackErr: any) {
        setError(
          fallbackErr.response?.data?.detail ||
            'Fehler beim Laden der Kalender-Daten'
        );
      }
    } finally {
      setIsLoading(false);
    }
  }, [grid]);

  useEffect(() => {
    fetchDeadlines();
  }, [fetchDeadlines]);

  const goToPrevMonth = () => {
    if (currentMonth === 0) {
      setCurrentMonth(11);
      setCurrentYear(currentYear - 1);
    } else {
      setCurrentMonth(currentMonth - 1);
    }
  };

  const goToNextMonth = () => {
    if (currentMonth === 11) {
      setCurrentMonth(0);
      setCurrentYear(currentYear + 1);
    } else {
      setCurrentMonth(currentMonth + 1);
    }
  };

  const goToToday = () => {
    const now = new Date();
    setCurrentMonth(now.getMonth());
    setCurrentYear(now.getFullYear());
  };

  if (isLoading) {
    return <div className="calendar-loading">Lade Kalender...</div>;
  }

  if (error) {
    return <div className="calendar-error">{error}</div>;
  }

  return (
    <div className="calendar-page">
      {/* Header */}
      <header className="calendar-header">
        <h1>Kalender</h1>
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
      </header>

      {/* Legend */}
      <div className="calendar-legend">
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
      </div>

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
                  const dayOrders = ordersByDate[dateKey] || [];
                  const visibleOrders = dayOrders.slice(0, MAX_ORDERS_PER_CELL);
                  const hiddenCount = dayOrders.length - visibleOrders.length;

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
                        <div className="calendar-day-number">{cell.day}</div>
                        <div className="calendar-day-orders">
                          {visibleOrders.map((order) => (
                            <div
                              key={order.id}
                              className="calendar-order-item"
                              onClick={() => navigate(`/orders/${order.id}`)}
                              title={`${order.title} (#${order.id})`}
                            >
                              <span
                                className={`traffic-dot ${getTrafficClass(order)}`}
                              />
                              <span className="order-title">{order.title}</span>
                            </div>
                          ))}
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
    </div>
  );
};
