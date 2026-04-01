// Admin System Page — displays health, backup, metrics and alerts for ADMINs
import React, { useCallback, useEffect, useState } from 'react';
import {
  BackupInfo,
  BusinessMetrics,
  EmailConfig,
  EmailConfigUpdate,
  EmailTestResult,
  FullHealth,
  RequestMetrics,
  SystemInfo,
  getEmailConfig,
  getSystemInfo,
  sendTestEmail,
  triggerBackup,
  updateEmailConfig,
} from '../api/admin';
import '../styles/admin.css';

const AUTO_REFRESH_MS = 60_000; // 60 seconds

// ---------------------------------------------------------------------------
// Small helper components
// ---------------------------------------------------------------------------

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const labels: Record<string, string> = {
    up: 'Verbunden',
    down: 'Getrennt',
    ok: 'OK',
    warning: 'Warnung',
    critical: 'Kritisch',
    healthy: 'Gesund',
    degraded: 'Beeinträchtigt',
    unhealthy: 'Fehler',
  };
  return (
    <span className={`status-card status-${status}`} style={{ padding: '2px 8px', borderRadius: '0.375rem', fontSize: '0.78rem', fontWeight: 600, border: '1px solid currentColor', display: 'inline-block' }}>
      {labels[status] ?? status}
    </span>
  );
};

const formatUptime = (seconds: number): string => {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
};

const formatTimestamp = (iso: string | null): string => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('de-DE');
};

// ---------------------------------------------------------------------------
// Section: System Status Cards
// ---------------------------------------------------------------------------

const SystemStatusSection: React.FC<{ health: FullHealth }> = ({ health }) => {
  const { components } = health;

  const overallLabels: Record<string, string> = {
    healthy: 'Alle Systeme betriebsbereit',
    degraded: 'System beeinträchtigt — Überprüfung empfohlen',
    unhealthy: 'Kritischer Systemfehler — sofortiger Handlungsbedarf',
  };

  return (
    <div className="admin-section">
      <h2>Systemstatus</h2>

      <div className={`overall-status-banner ${health.status}`}>
        <span>{health.status === 'healthy' ? '✓' : health.status === 'degraded' ? '⚠' : '✗'}</span>
        <span>{overallLabels[health.status] ?? health.status}</span>
        <span style={{ marginLeft: 'auto', fontSize: '0.78rem', opacity: 0.7 }}>
          Version {health.version} · Laufzeit {formatUptime(health.uptime_seconds)}
        </span>
      </div>

      <div className="status-cards-grid">
        {/* Database */}
        <div className={`status-card status-${components.database.status}`}>
          <span className="status-card-label">Datenbank</span>
          <span className="status-card-value">
            {components.database.status === 'up' ? `${components.database.latency_ms} ms` : '—'}
          </span>
          <span className="status-card-sub">
            <StatusBadge status={components.database.status} />
          </span>
          {components.database.error && (
            <span className="status-card-sub" style={{ color: '#ef4444', fontSize: '0.72rem' }}>
              {components.database.error}
            </span>
          )}
        </div>

        {/* Redis */}
        <div className={`status-card status-${components.redis.status}`}>
          <span className="status-card-label">Redis</span>
          <span className="status-card-value">
            {components.redis.status === 'up' ? `${components.redis.latency_ms} ms` : '—'}
          </span>
          <span className="status-card-sub">
            <StatusBadge status={components.redis.status} />
            {components.redis.status === 'up' && ` · ${components.redis.used_memory_mb} MB`}
          </span>
        </div>

        {/* Disk */}
        <div className={`status-card status-${components.disk.status}`}>
          <span className="status-card-label">Festplatte</span>
          <span className="status-card-value">{components.disk.used_percent ?? '—'}%</span>
          <span className="status-card-sub">
            <StatusBadge status={components.disk.status} />
            {` · ${components.disk.free_gb} GB frei`}
          </span>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Section: Backup Status
// ---------------------------------------------------------------------------

const BackupSection: React.FC<{
  backup: BackupInfo;
  onTrigger: () => Promise<void>;
  isTriggering: boolean;
}> = ({ backup, onTrigger, isTriggering }) => (
  <div className="admin-section">
    <h2>Backup</h2>
    <div className="backup-card">
      <div className="backup-info-group">
        {backup.filename ? (
          <>
            <span className="backup-filename">{backup.filename}</span>
            <span className="backup-meta">
              {backup.size_mb.toFixed(1)} MB · {formatTimestamp(backup.timestamp)}
            </span>
            <span className="backup-meta">
              {backup.backup_count} Backup{backup.backup_count !== 1 ? 's' : ''} gesamt · {backup.backup_dir}
            </span>
          </>
        ) : (
          <span className="backup-no-data">Kein Backup gefunden</span>
        )}
        {backup.error && (
          <span style={{ fontSize: '0.78rem', color: '#ef4444' }}>{backup.error}</span>
        )}
      </div>
      <button
        className="btn-backup-trigger"
        onClick={onTrigger}
        disabled={isTriggering}
        title="Manuelles Backup auslösen"
      >
        {isTriggering ? 'Wird gestartet…' : 'Backup starten'}
      </button>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Section: Application Metrics
// ---------------------------------------------------------------------------

const MetricsSection: React.FC<{
  metrics: RequestMetrics;
  business: BusinessMetrics;
}> = ({ metrics, business }) => (
  <div className="admin-section">
    <h2>Metriken</h2>
    <div className="metrics-grid">
      <div className="metric-card">
        <span className="metric-label">Aufträge diesen Monat</span>
        <span className="metric-value">{business.orders_this_month}</span>
        <span className="metric-unit">Gesamt</span>
      </div>
      <div className="metric-card">
        <span className="metric-label">Abgeschlossen</span>
        <span className="metric-value">{business.completed_this_month}</span>
        <span className="metric-unit">diesen Monat</span>
      </div>
      <div className="metric-card">
        <span className="metric-label">Anfragen gesamt</span>
        <span className="metric-value">{metrics.total_requests.toLocaleString('de-DE')}</span>
        <span className="metric-unit">seit Start</span>
      </div>
      <div className="metric-card">
        <span className="metric-label">Anfragen/Min</span>
        <span className="metric-value">{metrics.requests_per_minute}</span>
        <span className="metric-unit">Ø letzte Stunde</span>
      </div>
      <div className="metric-card">
        <span className="metric-label">Antwortzeit p50</span>
        <span className="metric-value">{metrics.response_time_ms.p50}</span>
        <span className="metric-unit">ms Median</span>
      </div>
      <div className="metric-card">
        <span className="metric-label">Antwortzeit p95</span>
        <span className="metric-value">{metrics.response_time_ms.p95}</span>
        <span className="metric-unit">ms p95</span>
      </div>
      <div className="metric-card">
        <span className="metric-label">Fehler 4xx</span>
        <span className="metric-value" style={{ color: metrics.errors['4xx'] > 0 ? '#f59e0b' : undefined }}>
          {metrics.errors['4xx']}
        </span>
        <span className="metric-unit">seit Start</span>
      </div>
      <div className="metric-card">
        <span className="metric-label">Fehler 5xx</span>
        <span className="metric-value" style={{ color: metrics.errors['5xx'] > 0 ? '#ef4444' : undefined }}>
          {metrics.errors['5xx']}
        </span>
        <span className="metric-unit">seit Start</span>
      </div>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Section: Email / SMTP Configuration
// ---------------------------------------------------------------------------

const EmailConfigSection: React.FC = () => {
  const [config, setConfig] = useState<EmailConfig | null>(null);
  const [draft, setDraft] = useState<EmailConfigUpdate>({});
  const [testEmail, setTestEmail] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    getEmailConfig()
      .then((c) => {
        setConfig(c);
        setDraft({
          smtp_host: c.smtp_host ?? '',
          smtp_port: c.smtp_port,
          smtp_user: c.smtp_user ?? '',
          smtp_from: c.smtp_from ?? '',
          email_notifications_enabled: c.email_notifications_enabled,
        });
      })
      .catch(() => {
        setMessage({ text: 'E-Mail-Konfiguration konnte nicht geladen werden.', ok: false });
      });
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    setMessage(null);
    try {
      const updated = await updateEmailConfig(draft);
      setConfig(updated);
      setMessage({ text: 'Einstellungen gespeichert.', ok: true });
    } catch {
      setMessage({ text: 'Speichern fehlgeschlagen.', ok: false });
    } finally {
      setIsSaving(false);
    }
  };

  const handleTest = async () => {
    if (!testEmail.trim()) {
      setMessage({ text: 'Bitte eine Empfängeradresse eingeben.', ok: false });
      return;
    }
    setIsTesting(true);
    setMessage(null);
    try {
      const result: EmailTestResult = await sendTestEmail(testEmail.trim());
      setMessage({ text: result.message, ok: result.success });
    } catch {
      setMessage({ text: 'Test-E-Mail konnte nicht gesendet werden.', ok: false });
    } finally {
      setIsTesting(false);
    }
  };

  const field = (label: string, node: React.ReactNode) => (
    <div style={{ marginBottom: '12px' }}>
      <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#5a4a2a', marginBottom: '4px' }}>
        {label}
      </label>
      {node}
    </div>
  );

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '7px 10px',
    border: '1px solid #d5c9ae',
    borderRadius: '5px',
    fontSize: '0.9rem',
    background: '#fefcf7',
    color: '#2c2416',
    boxSizing: 'border-box',
  };

  return (
    <div className="admin-section">
      <h2>E-Mail-Konfiguration</h2>

      {message && (
        <div
          className="admin-error-banner"
          style={{
            background: message.ok ? '#f0fdf4' : '#fef2f2',
            borderColor: message.ok ? '#86efac' : '#fca5a5',
            color: message.ok ? '#15803d' : '#b91c1c',
            marginBottom: '16px',
          }}
        >
          {message.text}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 24px' }}>
        <div>
          {field('SMTP Host',
            <input
              style={inputStyle}
              type="text"
              placeholder="z. B. smtp.gmail.com"
              value={draft.smtp_host ?? ''}
              onChange={(e) => setDraft((d) => ({ ...d, smtp_host: e.target.value }))}
            />
          )}
          {field('SMTP Port',
            <input
              style={inputStyle}
              type="number"
              min={1}
              max={65535}
              value={draft.smtp_port ?? 587}
              onChange={(e) => setDraft((d) => ({ ...d, smtp_port: Number(e.target.value) }))}
            />
          )}
          {field('SMTP Benutzer',
            <input
              style={inputStyle}
              type="text"
              placeholder="user@domain.de"
              value={draft.smtp_user ?? ''}
              onChange={(e) => setDraft((d) => ({ ...d, smtp_user: e.target.value }))}
            />
          )}
        </div>
        <div>
          {field(
            `SMTP Passwort${config?.password_configured ? ' (gesetzt — zum Ändern neu eingeben)' : ''}`,
            <input
              style={inputStyle}
              type="password"
              placeholder={config?.password_configured ? '••••••••' : 'Passwort eingeben'}
              onChange={(e) => setDraft((d) => ({ ...d, smtp_password: e.target.value || undefined }))}
            />
          )}
          {field('Absender-Adresse',
            <input
              style={inputStyle}
              type="email"
              placeholder="werkstatt@goldschmiede.de"
              value={draft.smtp_from ?? ''}
              onChange={(e) => setDraft((d) => ({ ...d, smtp_from: e.target.value }))}
            />
          )}
          <div style={{ marginTop: '20px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontWeight: 600, color: '#5a4a2a' }}>
              <input
                type="checkbox"
                checked={draft.email_notifications_enabled ?? false}
                onChange={(e) => setDraft((d) => ({ ...d, email_notifications_enabled: e.target.checked }))}
                style={{ width: '18px', height: '18px', accentColor: '#7c5c1e' }}
              />
              Kunden-E-Mails aktivieren
            </label>
            <p style={{ fontSize: '0.76rem', color: '#8a7a5a', marginTop: '4px', marginLeft: '28px' }}>
              Sendet automatisch E-Mails bei Auftragsbestätigung, Abholbereitschaft und Anproben.
            </p>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '12px', marginTop: '20px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <button
          className="btn-backup-trigger"
          onClick={handleSave}
          disabled={isSaving}
          style={{ minWidth: '160px' }}
        >
          {isSaving ? 'Wird gespeichert…' : 'Einstellungen speichern'}
        </button>

        <div style={{ display: 'flex', gap: '8px', flexGrow: 1, maxWidth: '420px' }}>
          <input
            style={{ ...inputStyle, flexGrow: 1 }}
            type="email"
            placeholder="Test-Empfänger: name@domain.de"
            value={testEmail}
            onChange={(e) => setTestEmail(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleTest()}
          />
          <button
            className="btn-backup-trigger"
            onClick={handleTest}
            disabled={isTesting}
            style={{ whiteSpace: 'nowrap' }}
          >
            {isTesting ? 'Wird gesendet…' : 'Test-E-Mail senden'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export const AdminSystemPage: React.FC = () => {
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [isTriggering, setIsTriggering] = useState(false);
  const [backupMessage, setBackupMessage] = useState<string | null>(null);

  const fetchSystemInfo = useCallback(async () => {
    try {
      const data = await getSystemInfo();
      setSystemInfo(data);
      setLastUpdated(new Date());
      setError(null);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ?? 'Systemdaten konnten nicht geladen werden.'
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSystemInfo();
    const timer = setInterval(fetchSystemInfo, AUTO_REFRESH_MS);
    return () => clearInterval(timer);
  }, [fetchSystemInfo]);

  const handleTriggerBackup = async () => {
    setIsTriggering(true);
    setBackupMessage(null);
    try {
      const result = await triggerBackup();
      setBackupMessage(
        result.note
          ? `Backup gestartet (Hinweis: ${result.note})`
          : 'Backup wurde gestartet. Ergebnis erscheint als Benachrichtigung.'
      );
    } catch {
      setBackupMessage('Backup konnte nicht gestartet werden.');
    } finally {
      setIsTriggering(false);
    }
  };

  if (isLoading) {
    return (
      <div className="admin-system-page">
        <div className="admin-loading">Systemdaten werden geladen…</div>
      </div>
    );
  }

  return (
    <div className="admin-system-page">
      <div className="admin-page-header">
        <h1>Systemübersicht</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {lastUpdated && (
            <span className="admin-last-updated">
              Aktualisiert: {lastUpdated.toLocaleTimeString('de-DE')}
            </span>
          )}
          <div className="admin-refresh-indicator">
            Auto-Refresh 60s
          </div>
        </div>
      </div>

      {error && (
        <div className="admin-error-banner">
          Fehler: {error}
        </div>
      )}

      {backupMessage && (
        <div className="admin-error-banner" style={{ background: '#eff6ff', borderColor: '#93c5fd', color: '#1e40af' }}>
          {backupMessage}
        </div>
      )}

      {systemInfo && (
        <>
          <SystemStatusSection health={systemInfo.health} />
          <BackupSection
            backup={systemInfo.backup}
            onTrigger={handleTriggerBackup}
            isTriggering={isTriggering}
          />
          <MetricsSection
            metrics={systemInfo.request_metrics}
            business={systemInfo.business_metrics}
          />
        </>
      )}

      <EmailConfigSection />
    </div>
  );
};
