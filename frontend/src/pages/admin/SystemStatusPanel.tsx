// Systemstatus (W4-03): health, backup and metrics from GET /admin/system,
// refreshed every minute through TanStack Query. The health state is shown as
// icon plus text, never by colour alone.
import React from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { triggerBackup, type BackupInfo, type SystemInfo } from '../../api/admin';
import { systemInfoQuery } from '../../api/adminQueries';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import { Button, Card, Icon, PageState, type CardTone } from '../../ui';
import type { IconName } from '../../ui/Icon';

type Tone = 'done' | 'waiting' | 'danger';

const HEALTH: Record<string, { label: string; tone: Tone; icon: IconName }> = {
  up: { label: 'Verbunden', tone: 'done', icon: 'circle-check' },
  ok: { label: 'OK', tone: 'done', icon: 'circle-check' },
  healthy: { label: 'Alle Systeme betriebsbereit', tone: 'done', icon: 'circle-check' },
  warning: { label: 'Warnung', tone: 'waiting', icon: 'triangle-alert' },
  degraded: { label: 'System beeinträchtigt — Überprüfung empfohlen', tone: 'waiting', icon: 'triangle-alert' },
  down: { label: 'Getrennt', tone: 'danger', icon: 'circle-x' },
  critical: { label: 'Kritisch', tone: 'danger', icon: 'circle-x' },
  unhealthy: { label: 'Kritischer Systemfehler — sofortiger Handlungsbedarf', tone: 'danger', icon: 'circle-x' },
};

const healthOf = (status: string) => HEALTH[status] ?? { label: status, tone: 'waiting' as Tone, icon: 'circle-help' as IconName };

const HealthLabel: React.FC<{ status: string }> = ({ status }) => {
  const health = healthOf(status);
  return (
    <span className={`admin-health admin-health--${health.tone}`}>
      <Icon name={health.icon} />
      {health.label}
    </span>
  );
};

const formatUptime = (seconds: number): string =>
  `${Math.floor(seconds / 3600)} h ${Math.floor((seconds % 3600) / 60)} min`;

const formatTimestamp = (iso: string | null): string =>
  iso ? new Date(iso).toLocaleString('de-DE') : '—';

interface Metric {
  label: string;
  value: React.ReactNode;
  unit: string;
}

const MetricList: React.FC<{ items: Metric[] }> = ({ items }) => (
  <dl className="admin-metrics">
    {items.map((item) => (
      <div key={item.label} className="admin-metrics__item">
        <dt>{item.label}</dt>
        <dd>
          <span className="admin-metrics__value">{item.value}</span> {item.unit}
        </dd>
      </div>
    ))}
  </dl>
);

const componentMetrics = ({ components }: SystemInfo['health']): Metric[] => [
  {
    label: 'Datenbank',
    value: components.database.status === 'up' ? components.database.latency_ms : '—',
    unit: components.database.status === 'up' ? 'ms' : '',
  },
  {
    label: 'Redis',
    value: components.redis.status === 'up' ? components.redis.latency_ms : '—',
    unit: components.redis.status === 'up' ? `ms · ${components.redis.used_memory_mb} MB` : '',
  },
  {
    label: 'Festplatte',
    value: components.disk.used_percent ?? '—',
    unit: `% belegt · ${components.disk.free_gb} GB frei`,
  },
];

const requestMetrics = (info: SystemInfo): Metric[] => {
  const { request_metrics: m, business_metrics: b } = info;
  return [
    { label: 'Aufträge diesen Monat', value: b.orders_this_month, unit: 'gesamt' },
    { label: 'Abgeschlossen', value: b.completed_this_month, unit: 'diesen Monat' },
    { label: 'Anfragen gesamt', value: m.total_requests.toLocaleString('de-DE'), unit: 'seit Start' },
    { label: 'Anfragen pro Minute', value: m.requests_per_minute, unit: 'Ø letzte Stunde' },
    { label: 'Antwortzeit p50', value: m.response_time_ms.p50, unit: 'ms' },
    { label: 'Antwortzeit p95', value: m.response_time_ms.p95, unit: 'ms' },
    { label: 'Fehler 4xx', value: m.errors['4xx'], unit: 'seit Start' },
    { label: 'Fehler 5xx', value: m.errors['5xx'], unit: 'seit Start' },
  ];
};

const BackupCard: React.FC<{ backup: BackupInfo }> = ({ backup }) => {
  const start = useMutation({
    mutationFn: triggerBackup,
    onError: (err) => logError('SystemStatusPanel.backup', err),
  });
  return (
    <Card
      title="Backup"
      headingLevel={3}
      action={
        <Button variant="secondary" icon="archive" loading={start.isPending} onClick={() => start.mutate()}>
          Backup starten
        </Button>
      }
    >
      {backup.filename ? (
        <p className="admin-panel__hint">
          <strong>{backup.filename}</strong> · {backup.size_mb.toFixed(1)} MB · {formatTimestamp(backup.timestamp)}
          <br />
          {backup.backup_count} {backup.backup_count === 1 ? 'Backup' : 'Backups'} gesamt · {backup.backup_dir}
        </p>
      ) : (
        <p className="admin-panel__hint">Kein Backup gefunden</p>
      )}
      {backup.error && <p className="admin-notice admin-notice--danger">{backup.error}</p>}
      {start.isSuccess && (
        <p role="status" className="admin-panel__hint">
          {start.data.note
            ? `Backup gestartet (Hinweis: ${start.data.note})`
            : 'Backup wurde gestartet. Ergebnis erscheint als Benachrichtigung.'}
        </p>
      )}
      {start.isError && (
        <p role="alert" className="admin-notice admin-notice--danger">
          {getErrorMessage(start.error, 'Backup konnte nicht gestartet werden.')}
        </p>
      )}
    </Card>
  );
};

export const SystemStatusPanel: React.FC = () => {
  const info = useQuery(systemInfoQuery());
  const health = info.data?.health;
  const tone: CardTone | undefined = health ? healthOf(health.status).tone : undefined;
  const updatedAt = info.dataUpdatedAt ? new Date(info.dataUpdatedAt).toLocaleTimeString('de-DE') : null;

  return (
    <Card title="Systemstatus" className="admin-panel" tone={tone}>
      <PageState
        state={
          info.isError && !info.data
            ? {
                status: 'error',
                error: getErrorMessage(info.error, 'Systemdaten konnten nicht geladen werden.'),
                retry: () => void info.refetch(),
              }
            : { status: info.data ? 'ready' : 'loading' }
        }
        skeleton="cards"
        skeletonCount={3}
      >
        {info.data && health && (
          <>
            <p className="admin-panel__intro">
              <HealthLabel status={health.status} />
              <span className="admin-panel__meta">
                Version {health.version} · Laufzeit {formatUptime(health.uptime_seconds)}
                {updatedAt && ` · Aktualisiert ${updatedAt} (automatisch jede Minute)`}
              </span>
            </p>
            <MetricList items={componentMetrics(health)} />
            <ul className="admin-health-list">
              <li>Datenbank: <HealthLabel status={health.components.database.status} /></li>
              <li>Redis: <HealthLabel status={health.components.redis.status} /></li>
              <li>Festplatte: <HealthLabel status={health.components.disk.status} /></li>
            </ul>
            {health.components.database.error && (
              <p className="admin-notice admin-notice--danger">{health.components.database.error}</p>
            )}
            <BackupCard backup={info.data.backup} />
            <h3 className="admin-panel__subheading">Metriken</h3>
            <MetricList items={requestMetrics(info.data)} />
          </>
        )}
      </PageState>
    </Card>
  );
};

export default SystemStatusPanel;
