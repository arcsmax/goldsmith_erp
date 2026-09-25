// HealthDot — small status indicator in the sidebar footer (ADMIN only)
// Polls /health every 60 s and shows a green/yellow/red dot.
// Clicking navigates to /admin/system.
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts';
import { getHealth } from '../api/admin';
import '../styles/admin.css';

type HealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'loading' | 'error';

const POLL_INTERVAL_MS = 60_000; // 60 seconds

const statusLabel: Record<HealthStatus, string> = {
  healthy: 'OK',
  degraded: 'Warnung',
  unhealthy: 'Kritisch',
  loading: '…',
  error: 'unbekannt',
};

const KNOWN_STATUSES: ReadonlyArray<HealthStatus> = ['healthy', 'degraded', 'unhealthy'];

const isKnownStatus = (value: unknown): value is HealthStatus =>
  typeof value === 'string' && (KNOWN_STATUSES as ReadonlyArray<string>).includes(value);

/** Inner component — only rendered when the user IS an admin. */
const HealthDotInner: React.FC = () => {
  const navigate = useNavigate();
  const [healthStatus, setHealthStatus] = useState<HealthStatus>('loading');

  const fetchHealth = async () => {
    try {
      const data = await getHealth();
      // A proxy miss (e.g. /health falling through to the SPA's index.html)
      // returns 200 with an unrelated body — never trust the shape, and
      // never surface a raw "undefined" status to the user.
      setHealthStatus(isKnownStatus(data?.status) ? data.status : 'error');
    } catch {
      setHealthStatus('error');
    }
  };

  useEffect(() => {
    fetchHealth();
    const timer = setInterval(fetchHealth, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  return (
    <button
      className="health-dot-wrapper"
      onClick={() => navigate('/admin/system')}
      title={`Systemstatus: ${statusLabel[healthStatus]} — zum Admin-Dashboard`}
      aria-label={`Systemstatus: ${statusLabel[healthStatus]}`}
      style={{ background: 'none', border: 'none' }}
    >
      <span
        // Unknown/failed fetch means we don't actually know the backend is
        // down — show the warning (amber) colour, not the critical (red)
        // one reserved for a confirmed "unhealthy" response.
        className={`health-dot ${healthStatus === 'error' ? 'degraded' : healthStatus}`}
        aria-hidden="true"
      />
      <span className="health-dot-label">System</span>
    </button>
  );
};

/** Public component — renders nothing for non-admin users. */
export const HealthDot: React.FC = () => {
  const { hasRole } = useAuth();
  if (!hasRole(['ADMIN'])) return null;
  return <HealthDotInner />;
};
