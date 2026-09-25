// AdminSystemPage (W4-03): panels on primitives and queries. Pins that every
// panel renders, that one failing endpoint only breaks its own panel, and
// that health is announced as text, not only colour.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';

const api = vi.hoisted(() => ({
  getSystemInfo: vi.fn(),
  getWorkshopSettings: vi.fn(),
  getEmailConfig: vi.fn(),
  getOutbox: vi.fn(),
  fetchTheme: vi.fn(),
}));

vi.mock('../lib/logError', () => ({ logError: vi.fn() }));
vi.mock('../api/admin', () => ({
  getSystemInfo: api.getSystemInfo,
  getWorkshopSettings: api.getWorkshopSettings,
  getEmailConfig: api.getEmailConfig,
  getOutbox: api.getOutbox,
  triggerBackup: vi.fn(),
  updateWorkshopSettings: vi.fn(),
  updateEmailConfig: vi.fn(),
  sendTestEmail: vi.fn(),
  retryOutboxMessage: vi.fn(),
  importCustomersCsv: vi.fn(),
  downloadCustomerCsvTemplate: vi.fn(),
}));
vi.mock('../hooks/useTheme', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/useTheme')>()),
  fetchTheme: api.fetchTheme,
  applyTheme: vi.fn(),
  saveTheme: vi.fn(),
}));

import { renderWithQuery } from '../test/queryWrapper';
import { THEME_DEFAULTS } from '../hooks/useTheme';
import { AdminSystemPage } from './AdminSystemPage';

const SYSTEM_INFO = {
  health: {
    status: 'degraded',
    version: '1.4.0',
    uptime_seconds: 7260,
    components: {
      database: { status: 'up', latency_ms: 3 },
      redis: { status: 'down', latency_ms: null, used_memory_mb: null },
      disk: { status: 'ok', used_percent: 41, free_gb: 120 },
    },
  },
  backup: { filename: null, size_mb: 0, timestamp: null, backup_count: 0, backup_dir: '/b', error: null },
  request_metrics: {
    total_requests: 1200,
    requests_per_minute: 4,
    response_time_ms: { p50: 12, p95: 80 },
    errors: { '4xx': 1, '5xx': 0 },
  },
  business_metrics: { orders_this_month: 9, completed_this_month: 4 },
};

afterEach(() => vi.clearAllMocks());

describe('AdminSystemPage', () => {
  it('renders every panel and states health in words', async () => {
    api.getSystemInfo.mockResolvedValue(SYSTEM_INFO);
    api.getWorkshopSettings.mockRejectedValue(new Error('boom'));
    api.getEmailConfig.mockResolvedValue({
      smtp_host: 'smtp.example.test',
      smtp_port: 587,
      smtp_user: null,
      smtp_from: null,
      email_notifications_enabled: false,
      password_configured: false,
    });
    api.getOutbox.mockResolvedValue({ items: [], counts: { pending: 0, sent: 0, failed: 0, dead: 0 }, mode: 'worker' });
    api.fetchTheme.mockResolvedValue(THEME_DEFAULTS);

    renderWithQuery(<AdminSystemPage />);

    expect(screen.getByRole('heading', { level: 1, name: 'Systemübersicht' })).toBeInTheDocument();
    for (const title of ['Systemstatus', 'Werkstatt-Stammdaten', 'Nachrichten-Warteschlange', 'E-Mail-Konfiguration', 'Benutzer', 'Kunden-Import (CSV)', 'Erscheinungsbild']) {
      expect(screen.getByRole('heading', { level: 2, name: title })).toBeInTheDocument();
    }

    expect(await screen.findByText('System beeinträchtigt — Überprüfung empfohlen')).toBeInTheDocument();
    expect(screen.getByText('Getrennt')).toBeInTheDocument();

    // The failing Stammdaten endpoint only breaks its own panel.
    const stammdaten = screen.getByRole('region', { name: 'Werkstatt-Stammdaten' });
    expect(await within(stammdaten).findByRole('alert')).toHaveTextContent('Stammdaten konnten nicht geladen werden.');
    expect(await screen.findByLabelText('SMTP-Server')).toHaveValue('smtp.example.test');

    expect(screen.getByRole('link', { name: /Benutzer verwalten/ })).toHaveAttribute('href', '/users');
  });
});
