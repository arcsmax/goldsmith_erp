// Berichte (W4-03): charts over the signed-in user's last 30 days.
//
// Data: one page (at most 200 rows) of GET /time-tracking/user/{id} filtered to
// the last 30 days, as a query under ['timer'] (refreshes on timer events),
// plus the shared activities query. The aggregation runs during render
// (useMemo), never copied into state. Chart colours are semantic tokens.
import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format, getDay, startOfWeek, subDays } from 'date-fns';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { activitiesQuery, userEntriesQuery } from '../../api/timeTrackingQueries';
import { useAuth } from '../../contexts/AuthContext';
import { getErrorMessage } from '../../lib/errors';
import { Button, PageState, type PageStateValue } from '../../ui';
import { parseUTC } from '../../utils/formatters';
import type { Activity, ActivityBreakdownData, TimeEntry } from '../../types';
import '../../styles/time-tracking.css';

type ChartType = 'weekly' | 'activity' | 'daily';

const REPORT_DAYS = 30;
const REPORT_WEEKS = 4;
const REPORT_ROW_LIMIT = 200;
const CHART_HEIGHT = 320;
const DAY_NAMES = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
const MONDAY_FIRST = [1, 2, 3, 4, 5, 6, 0];
const WEEK_OPTIONS = { weekStartsOn: 1 } as const;

const CHART_COLORS = [
  'var(--tone-info-fg)',
  'var(--tone-done-fg)',
  'var(--tone-waiting-fg)',
  'var(--tone-progress-fg)',
  'var(--tone-check-fg)',
  'var(--tone-handover-fg)',
  'var(--tone-danger-fg)',
  'var(--tone-neutral-fg)',
];
const AXIS = 'var(--chart-label-color)';
const GRID = 'var(--chart-grid-color)';
const LINE = 'var(--chart-line-color)';
const TOOLTIP_STYLE = {
  background: 'var(--color-surface-raised)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-md)',
};

const CHARTS: ReadonlyArray<{ id: ChartType; label: string; title: string }> = [
  { id: 'weekly', label: 'Wochenverlauf', title: 'Stundenverlauf (letzte 4 Wochen)' },
  { id: 'activity', label: 'Aktivitäten', title: 'Zeit nach Aktivität (letzte 30 Tage)' },
  { id: 'daily', label: 'Tagesverteilung', title: 'Ø Stunden pro Wochentag (letzte 30 Tage)' },
];

const round1 = (value: number): number => Math.round(value * 10) / 10;
const hoursOf = (entry: TimeEntry): number => (entry.duration_minutes || 0) / 60;

function weeklyTrend(entries: TimeEntry[], now: Date) {
  const buckets = new Map<string, number>();
  for (let i = REPORT_WEEKS - 1; i >= 0; i--) {
    buckets.set(format(startOfWeek(subDays(now, i * 7), WEEK_OPTIONS), 'dd.MM'), 0);
  }
  for (const entry of entries) {
    const key = format(startOfWeek(parseUTC(entry.start_time), WEEK_OPTIONS), 'dd.MM');
    const current = buckets.get(key);
    if (current !== undefined) buckets.set(key, current + hoursOf(entry));
  }
  return Array.from(buckets, ([week, hours]) => ({ week, hours: round1(hours) }));
}

function activityBreakdown(entries: TimeEntry[], activities: Activity[]): ActivityBreakdownData[] {
  const byId = new Map(activities.map((a) => [a.id, a]));
  const minutes = new Map<number, number>();
  let total = 0;
  for (const entry of entries) {
    const mins = entry.duration_minutes || 0;
    minutes.set(entry.activity_id, (minutes.get(entry.activity_id) || 0) + mins);
    total += mins;
  }
  return Array.from(minutes, ([activityId, mins]) => {
    const activity = byId.get(activityId);
    return {
      activity_name: activity ? activity.name : `Aktivität #${activityId}`,
      hours: round1(mins / 60),
      percentage: total > 0 ? (mins / total) * 100 : 0,
      // Runtime value from the activity record (the user picks it).
      color: activity?.color || '',
    };
  }).sort((a, b) => b.hours - a.hours);
}

function dailyAverage(entries: TimeEntry[]) {
  const totals = new Array<number>(7).fill(0);
  const days = Array.from({ length: 7 }, () => new Set<string>());
  for (const entry of entries) {
    const date = parseUTC(entry.start_time);
    const index = getDay(date);
    totals[index] += hoursOf(entry);
    days[index].add(format(date, 'yyyy-MM-dd'));
  }
  return MONDAY_FIRST.map((i) => ({
    day: DAY_NAMES[i],
    hours: round1(days[i].size > 0 ? totals[i] / days[i].size : 0),
  }));
}

export const TimeReportsSection: React.FC = () => {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const [activeChart, setActiveChart] = useState<ChartType>('weekly');
  const [now] = useState(() => new Date());
  const params = useMemo(
    () => ({
      limit: REPORT_ROW_LIMIT,
      offset: 0,
      sort: '-start_time',
      start_date: format(subDays(now, REPORT_DAYS), 'yyyy-MM-dd'),
    }),
    [now],
  );
  const entriesQuery = useQuery({
    ...userEntriesQuery(userId ?? 0, params),
    enabled: userId !== null,
  });
  const activities = useQuery(activitiesQuery(false));

  const completed = useMemo(
    () => (entriesQuery.data?.items ?? []).filter((e) => e.end_time && e.duration_minutes),
    [entriesQuery.data],
  );
  const weekly = useMemo(() => weeklyTrend(completed, now), [completed, now]);
  const breakdown = useMemo(
    () => activityBreakdown(completed, activities.data ?? []),
    [completed, activities.data],
  );
  const daily = useMemo(() => dailyAverage(completed), [completed]);

  const state: PageStateValue =
    entriesQuery.isPending
      ? { status: 'loading' }
      : entriesQuery.isError
        ? {
            status: 'error',
            error: getErrorMessage(entriesQuery.error, 'Berichte konnten nicht geladen werden.'),
            retry: () => void entriesQuery.refetch(),
          }
        : { status: completed.length > 0 ? 'ready' : 'empty' };
  const chart = CHARTS.find((c) => c.id === activeChart) ?? CHARTS[0];
  const busiest = daily.reduce((max, day) => (day.hours > max.hours ? day : max), daily[0]);

  return (
    <section className="time-reports" aria-labelledby="time-reports-title">
      <div className="time-reports__header">
        <h2 id="time-reports-title">Berichte</h2>
        <div className="time-reports__tabs" role="group" aria-label="Diagramm">
          {CHARTS.map((c) => (
            <Button
              key={c.id}
              variant={activeChart === c.id ? 'primary' : 'secondary'}
              aria-pressed={activeChart === c.id}
              onClick={() => setActiveChart(c.id)}
            >
              {c.label}
            </Button>
          ))}
        </div>
      </div>

      <PageState
        state={state}
        skeleton="detail"
        empty={{
          icon: 'clock',
          title: 'Noch keine abgeschlossenen Zeiteinträge',
          body: 'Starten Sie einen Timer über „Zeiterfassung starten“ unten rechts.',
          headingLevel: 3,
        }}
      >
        <figure className="time-reports__chart">
          <figcaption>{chart.title}</figcaption>
          <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
            {activeChart === 'weekly' ? (
              <LineChart data={weekly}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis dataKey="week" stroke={AXIS} />
                <YAxis stroke={AXIS} label={{ value: 'Stunden', angle: -90, position: 'insideLeft' }} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend />
                <Line type="monotone" dataKey="hours" name="Stunden" stroke={LINE} strokeWidth={3} />
              </LineChart>
            ) : activeChart === 'activity' ? (
              <PieChart>
                <Pie data={breakdown} dataKey="hours" nameKey="activity_name" outerRadius={120} label>
                  {breakdown.map((row, index) => (
                    <Cell key={row.activity_name} fill={row.color || CHART_COLORS[index % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  formatter={(value) => `${Number(value).toLocaleString('de-DE')} h`}
                />
                <Legend />
              </PieChart>
            ) : (
              <BarChart data={daily}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis dataKey="day" stroke={AXIS} />
                <YAxis stroke={AXIS} label={{ value: 'Stunden', angle: -90, position: 'insideLeft' }} />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(value) => `${String(value)} h`} />
                <Legend />
                <Bar dataKey="hours" name="Stunden" fill={LINE} />
              </BarChart>
            )}
          </ResponsiveContainer>
        </figure>
        <p className="time-reports__insight">
          {activeChart === 'weekly' &&
            `Diese Woche: ${(weekly[weekly.length - 1]?.hours ?? 0).toLocaleString('de-DE')} h erfasst`}
          {activeChart === 'activity' &&
            breakdown[0] &&
            `Meiste Zeit: ${breakdown[0].activity_name} (${breakdown[0].hours.toLocaleString('de-DE')} h)`}
          {activeChart === 'daily' &&
            busiest &&
            `Stärkster Tag: ${busiest.day} (${busiest.hours.toLocaleString('de-DE')} h)`}
        </p>
      </PageState>
    </section>
  );
};
