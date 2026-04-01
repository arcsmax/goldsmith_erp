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
  error: 'Fehler',
};

export const HealthDot: React.FC = () => {
  const { hasRole } = useAuth();
  const navigate = useNavigate();
  const [healthStatus, setHealthStatus] = useState<HealthStatus>('loading');

  // Only render for ADMIN users
  if (!hasRole(['ADMIN'])) return null;

  const fetchHealth = async () => {
    try {
      const data = await getHealth();
      setHealthStatus(data.status as HealthStatus);
    } catch {
      setHealthStatus('error');
    }
  };

  useEffect(() => {
    fetchHealth();
    const timer = setInterval(fetchHealth, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  const handleClick = () => {
    navigate('/admin/system');
  };

  return (
    <button
      className="health-dot-wrapper"
      onClick={handleClick}
      title={`Systemstatus: ${statusLabel[healthStatus]} — zum Admin-Dashboard`}
      aria-label={`Systemstatus: ${statusLabel[healthStatus]}`}
      style={{ background: 'none', border: 'none' }}
    >
      <span
        className={`health-dot ${healthStatus === 'error' ? 'unhealthy' : healthStatus}`}
        aria-hidden="true"
      />
      <span className="health-dot-label">System</span>
    </button>
  );
};
