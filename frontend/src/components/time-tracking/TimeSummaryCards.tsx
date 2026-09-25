// Time summary (W4-03): GET /time-tracking/summary as a query.
//
// Shares the key queryKeys.timer.summary(range) with the dashboard KPIs, so
// "Diese Woche" is one request for both, and a time_tracking_updates hint
// refreshes it (root ['timer']).
import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { endOfMonth, endOfWeek, format, startOfMonth, startOfWeek, subDays } from 'date-fns';

import { timeTrackingApi } from '../../api';
import { queryKeys, type DateRange } from '../../api/queryKeys';
import { getErrorMessage } from '../../lib/errors';
import { Button, PageState, type PageStateValue } from '../../ui';
import '../../styles/time-tracking.css';

type TimePeriod = 'week' | 'month' | '7days' | '30days';

const PERIODS: ReadonlyArray<{ id: TimePeriod; button: string; label: string }> = [
  { id: 'week', button: 'Diese Woche', label: 'Diese Woche' },
  { id: 'month', button: 'Dieser Monat', label: 'Dieser Monat' },
  { id: '7days', button: '7 Tage', label: 'Letzte 7 Tage' },
  { id: '30days', button: '30 Tage', label: 'Letzte 30 Tage' },
];

const WEEK_OPTIONS = { weekStartsOn: 1 } as const;
const DATE_FORMAT = 'yyyy-MM-dd';

function periodRange(period: TimePeriod, now = new Date()): DateRange {
  const ranges: Record<TimePeriod, [Date, Date]> = {
    week: [startOfWeek(now, WEEK_OPTIONS), endOfWeek(now, WEEK_OPTIONS)],
    month: [startOfMonth(now), endOfMonth(now)],
    '7days': [subDays(now, 7), now],
    '30days': [subDays(now, 30), now],
  };
  const [start, end] = ranges[period];
  return { start_date: format(start, DATE_FORMAT), end_date: format(end, DATE_FORMAT) };
}

const formatHours = (hours: number): string =>
  hours.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function formatComparison(comparison: number): string {
  const sign = comparison >= 0 ? '+' : '−';
  return `${sign}${formatHours(Math.abs(comparison))} % gegenüber vorher`;
}

interface TimeSummaryCardsProps {
  onPeriodChange?: (period: TimePeriod) => void;
}

export const TimeSummaryCards: React.FC<TimeSummaryCardsProps> = ({ onPeriodChange }) => {
  const [period, setPeriod] = useState<TimePeriod>('week');
  const currentRange = useMemo(() => periodRange(period), [period]);
  const summary = useQuery({
    queryKey: queryKeys.timer.summary(currentRange),
    queryFn: () => timeTrackingApi.getSummary(currentRange),
  });
  const periodLabel = PERIODS.find((p) => p.id === period)?.label ?? 'Zeitraum';

  const state: PageStateValue = summary.isPending
    ? { status: 'loading' }
    : summary.isError
      ? {
          status: 'error',
          error: getErrorMessage(summary.error, 'Übersicht konnte nicht geladen werden.'),
          retry: () => void summary.refetch(),
        }
      : { status: 'ready' };
  const stats = summary.data;

  return (
    <section className="time-summary" aria-labelledby="time-summary-title">
      <div className="time-summary__header">
        <h2 id="time-summary-title">Übersicht</h2>
        <div className="time-summary__periods" role="group" aria-label="Zeitraum">
          {PERIODS.map((p) => (
            <Button
              key={p.id}
              variant={period === p.id ? 'primary' : 'secondary'}
              aria-pressed={period === p.id}
              onClick={() => {
                setPeriod(p.id);
                onPeriodChange?.(p.id);
              }}
            >
              {p.button}
            </Button>
          ))}
        </div>
      </div>

      <PageState state={state} skeleton="cards" skeletonCount={4}>
        {stats && (
          <dl className="time-summary__stats">
            <div className="time-summary__stat">
              <dt>Gesamtstunden</dt>
              <dd className="time-summary__value">{formatHours(stats.total_hours)} h</dd>
              <dd className="time-summary__meta">
                {stats.comparison_previous_period != null
                  ? formatComparison(stats.comparison_previous_period)
                  : periodLabel}
              </dd>
            </div>
            <div className="time-summary__stat">
              <dt>Abrechenbare Stunden</dt>
              <dd className="time-summary__value">{formatHours(stats.billable_hours)} h</dd>
              <dd className="time-summary__meta">
                {stats.total_hours > 0
                  ? `${Math.round((stats.billable_hours / stats.total_hours) * 100)} % der Gesamtzeit`
                  : '0 % der Gesamtzeit'}
              </dd>
            </div>
            <div className="time-summary__stat">
              <dt>Zeiteinträge</dt>
              <dd className="time-summary__value">{stats.entries_count}</dd>
              <dd className="time-summary__meta">
                <a href="#zeiteintraege">
                  Ø {Math.round(stats.average_session_minutes)} min pro Eintrag
                </a>
              </dd>
            </div>
            <div className="time-summary__stat">
              <dt>Häufigste Aktivität</dt>
              <dd className="time-summary__value time-summary__value--text">
                {stats.most_used_activity || 'Keine Daten'}
              </dd>
              <dd className="time-summary__meta">{periodLabel}</dd>
            </div>
          </dl>
        )}
      </PageState>
    </section>
  );
};
