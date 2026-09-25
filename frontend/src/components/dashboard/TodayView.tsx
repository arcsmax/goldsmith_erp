// "Heute" start-of-day view (W2-03; FE-05, DOM-14, DOM-15, DOM-15b).
//
// One server summary (GET /dashboard/today) spanning orders and repairs:
// Überfällig first in the danger style, then Bald fällig, Wartet auf Kunde
// and today's timers. Every row links to its next action. Refetches on
// live order and time-tracking hints (refetch bus) and never shows
// "alles erledigt" when loading failed.
//
// W3-03: one useQuery per mount (['dashboard', 'today']). Live order and
// time-tracking hints invalidate ['dashboard'] in lib/realtimeInvalidation.
import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { dashboardApi, type DashboardToday } from '../../api/dashboard';
import { queryKeys } from '../../api/queryKeys';
import { logError } from '../../lib/logError';
import { TodayLane, TodayRow } from './TodayLane';
import {
  PENDING_KIND_LABEL,
  PENDING_KIND_TONE,
  daysSince,
  formatAmount,
  formatDate,
  formatDaysOverdue,
  formatTime,
  parseUtc,
  pendingAction,
  timerAction,
  workItemAction,
} from './todayLanes';

interface TodayViewProps {
  role?: string | null;
}

async function fetchToday(): Promise<DashboardToday> {
  try {
    return await dashboardApi.getToday();
  } catch (err) {
    logError('Heute-Übersicht konnte nicht geladen werden', err);
    throw err;
  }
}

function useTodaySummary() {
  return useQuery({ queryKey: queryKeys.dashboard.today(), queryFn: fetchToday });
}

const SummaryTiles: React.FC<{ data: DashboardToday }> = ({ data }) => {
  const tiles = [
    { href: '#heute-ueberfaellig', value: data.counts.overdue, label: 'überfällig' },
    { href: '#heute-bald-faellig', value: data.counts.due_soon, label: 'in den nächsten 3 Tagen' },
    { href: '#heute-wartet-auf-kunde', value: data.counts.customer_pending, label: 'wartet auf Kunde' },
    { href: '#heute-timer', value: data.counts.timers, label: 'Zeiten heute' },
  ];
  return (
    <nav className="dashboard-kpis today-tiles" aria-label="Heute im Überblick">
      {tiles.map((tile) => (
        <a key={tile.href} href={tile.href} className="kpi-card clickable today-tile">
          <span className="kpi-value today-tabular">{tile.value}</span>
          <span className="kpi-title">{tile.label} ›</span>
        </a>
      ))}
    </nav>
  );
};

function Lanes({ data, role }: { data: DashboardToday; role?: string | null }) {
  return (
    <>
      <TodayLane
        id="heute-ueberfaellig"
        title="Überfällig"
        count={data.overdue.length}
        emptyText="Nichts überfällig."
      >
        {data.overdue.map((item) => (
          <TodayRow
            key={`${item.kind}-${item.id}`}
            tone="urgent"
            badge={String(item.days_overdue)}
            badgeLabel={item.days_overdue === 1 ? 'Tag' : 'Tage'}
            title={item.title}
            meta={[
              `${item.kind === 'repair' ? 'Reparatur' : 'Auftrag'} ${item.reference}`,
              item.customer_name,
              item.bag_number ? `Tüte ${item.bag_number}` : null,
              `${formatDaysOverdue(item.days_overdue)} (${formatDate(item.due_date)})`,
            ]}
            action={workItemAction(item, role)}
          />
        ))}
      </TodayLane>

      <TodayLane
        id="heute-bald-faellig"
        title="Bald fällig"
        count={data.due_soon.length}
        emptyText="In den nächsten 3 Tagen ist nichts fällig."
        emptyAction={{ to: '/orders', label: 'Aufträge öffnen' }}
      >
        {data.due_soon.map((item) => (
          <TodayRow
            key={`${item.kind}-${item.id}`}
            tone="soon"
            badge={String(Math.abs(item.days_overdue))}
            badgeLabel={item.days_overdue === 0 ? 'heute' : 'Tage'}
            title={item.title}
            meta={[
              `${item.kind === 'repair' ? 'Reparatur' : 'Auftrag'} ${item.reference}`,
              item.customer_name,
              item.bag_number ? `Tüte ${item.bag_number}` : null,
              `${formatDaysOverdue(item.days_overdue)} (${formatDate(item.due_date)})`,
            ]}
            action={workItemAction(item, role)}
          />
        ))}
      </TodayLane>

      <TodayLane
        id="heute-wartet-auf-kunde"
        title="Wartet auf Kunde"
        count={data.customer_pending.length}
        emptyText="Keine offenen Rückmeldungen oder Abholungen."
      >
        {data.customer_pending.map((item) => (
          <TodayRow
            key={`${item.kind}-${item.id}`}
            tone={PENDING_KIND_TONE[item.kind]}
            badge={String(daysSince(item.since))}
            badgeLabel={daysSince(item.since) === 1 ? 'Tag' : 'Tage'}
            title={item.title}
            meta={[
              PENDING_KIND_LABEL[item.kind],
              item.reference,
              item.customer_name,
              item.bag_number ? `Tüte ${item.bag_number}` : null,
              `seit ${parseUtc(item.since).toLocaleDateString('de-DE')}`,
              item.valid_until ? `gültig bis ${formatDate(item.valid_until)}` : null,
              data.can_view_financials && typeof item.amount === 'number'
                ? formatAmount(item.amount)
                : null,
            ]}
            action={pendingAction(item, role)}
          />
        ))}
      </TodayLane>

      <TodayLane
        id="heute-timer"
        title="Zeiten heute"
        count={data.timers.length}
        emptyText="Heute noch keine Zeit erfasst."
        emptyAction={{ to: '/time-tracking', label: 'Zeiterfassung öffnen' }}
      >
        {data.timers.map((timer) => (
          <TodayRow
            key={timer.id}
            tone={timer.is_running ? 'soon' : 'ok'}
            badge={formatTime(timer.start_time)}
            badgeLabel={timer.is_running ? 'läuft' : 'Start'}
            title={timer.order_title ?? `Auftrag #${timer.order_id}`}
            meta={[
              timer.activity_name,
              timer.user_name,
              timer.duration_minutes != null ? `${timer.duration_minutes} min` : null,
            ]}
            action={timerAction(timer)}
          />
        ))}
      </TodayLane>
    </>
  );
}

export const TodayView: React.FC<TodayViewProps> = ({ role }) => {
  const { data, isPending, isRefetching, refetch } = useTodaySummary();

  // A failed background refetch keeps the summary on screen.
  if (isPending || (!data && isRefetching)) {
    return <div className="deadlines-loading" role="status">Heute-Übersicht wird geladen…</div>;
  }
  if (!data) {
    return (
      <div className="deadlines-error" role="alert">
        <p>Die Heute-Übersicht konnte nicht geladen werden.</p>
        <button type="button" className="btn btn-primary" onClick={() => void refetch()}>
          Übersicht neu laden
        </button>
      </div>
    );
  }

  return (
    <div className="today-view">
      <p className="dashboard-timestamp">
        <span className="timestamp-label">Zuletzt aktualisiert:</span>{' '}
        <span className="timestamp-value today-tabular">
          {parseUtc(data.generated_at).toLocaleString('de-DE')}
        </span>
      </p>
      {data.truncated && (
        <p className="deadlines-error" role="note">
          Nicht alle Einträge werden angezeigt. Bitte die Listen Aufträge und Reparaturen nutzen.
        </p>
      )}
      <SummaryTiles data={data} />
      <Lanes data={data} role={role} />
    </div>
  );
};
