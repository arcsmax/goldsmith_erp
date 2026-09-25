// DashboardPage request budget (W3-03, FE-20): the admin dashboard used to
// fire GET /orders/?limit=100 up to four times per mount and GET
// /dashboard/today on its own. With TanStack Query every resource is one
// query, so each URL is requested once per mount; a realtime hint refetches
// the summary once.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, screen } from '@testing-library/react';
import { renderWithQuery } from '../test/queryWrapper';

const mockGet = vi.fn();
vi.mock('../api/client', () => ({
  default: { get: (...a: unknown[]) => mockGet(...a) },
}));

const mockUseAuth = vi.fn();
vi.mock('../contexts', () => ({ useAuth: () => mockUseAuth() }));

import { DashboardPage } from './DashboardPage';
import { invalidateForChannel } from '../lib/realtimeInvalidation';

const SUMMARY = {
  today: '2026-09-25',
  generated_at: '2026-09-25T06:30:00',
  can_view_financials: true,
  truncated: false,
  overdue: [],
  due_soon: [],
  customer_pending: [],
  timers: [],
  counts: { overdue: 0, due_soon: 0, customer_pending: 0, timers: 0 },
};

function respond(url: string) {
  if (url === '/dashboard/today') return { data: SUMMARY };
  if (url === '/orders/') return { data: [] };
  if (url === '/handoffs/pending') return { data: [] };
  if (url.includes('statistics')) return { data: { total_value: 0 } };
  if (url.includes('summary')) return { data: { total_hours: 0 } };
  return { data: [] };
}

function callsTo(url: string): number {
  return mockGet.mock.calls.filter(([called]) => called === url).length;
}

function renderDashboard(role: string) {
  mockUseAuth.mockReturnValue({ user: { role, first_name: 'Anne' } });
  mockGet.mockImplementation(async (url: string) => respond(url));
  return renderWithQuery(<DashboardPage />);
}

afterEach(() => {
  mockGet.mockReset();
  mockUseAuth.mockReset();
});

describe('DashboardPage requests per mount', () => {
  it('fetches /dashboard/today exactly once for a GOLDSMITH', async () => {
    renderDashboard('GOLDSMITH');
    await screen.findByRole('heading', { name: /Überfällig/ });
    expect(callsTo('/dashboard/today')).toBe(1);
    expect(callsTo('/orders/')).toBe(0);
  });

  it('fetches /dashboard/today and /orders/ once each for an ADMIN (KPIs and alerts share one query)', async () => {
    renderDashboard('ADMIN');
    await screen.findByRole('heading', { name: /Überfällig/ });
    await screen.findByText('Aktive Aufträge');
    await screen.findByText(/Alles in Ordnung|Überfällige Aufträge/);

    expect(callsTo('/dashboard/today')).toBe(1);
    expect(callsTo('/orders/')).toBe(1);
    expect(callsTo('/handoffs/pending')).toBe(1);
  });

  it('refetches the summary exactly once on a realtime order hint', async () => {
    const { client } = renderDashboard('GOLDSMITH');
    await screen.findByRole('heading', { name: /Überfällig/ });

    await act(() => invalidateForChannel(client, 'order_updates'));
    expect(callsTo('/dashboard/today')).toBe(2);

    await act(() => invalidateForChannel(client, 'time_tracking_updates'));
    expect(callsTo('/dashboard/today')).toBe(3);
  });
});
