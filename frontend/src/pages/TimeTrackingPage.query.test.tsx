// W4-03: TimeTrackingPage on TanStack Query — the paged per-user endpoint,
// the "Pausiert" state of a running entry, the Werkbank-Modus toggle and a
// realtime refresh through the one bridge.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { act, screen, waitFor, within } from '@testing-library/react';

import type { TimeEntry } from '../types';

const mocks = vi.hoisted(() => ({
  getUserPage: vi.fn(),
  getSummary: vi.fn(),
  runningEntry: null as TimeEntry | null,
}));

vi.mock('../api/time-tracking', () => ({
  timeTrackingApi: {
    getUserPage: mocks.getUserPage,
    getSummary: mocks.getSummary,
    createManual: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}));
vi.mock('../api', () => ({ timeTrackingApi: { getSummary: mocks.getSummary } }));
vi.mock('../api/activities', () => ({ activitiesApi: { getAll: vi.fn(async () => []) } }));
vi.mock('../api/orders', () => ({ ordersApi: { getAll: vi.fn(async () => []) } }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 5, role: 'goldsmith' } }) }));
vi.mock('../contexts', () => ({
  useAuth: () => ({ user: { id: 5, role: 'goldsmith' } }),
  useConfirm: () => ({ showConfirm: vi.fn(async () => false) }),
  useToast: () => ({ showToast: vi.fn() }),
  useTimeTracking: () => ({
    runningEntry: mocks.runningEntry,
    activities: [{ id: 2, name: 'Polieren', category: 'fabrication', usage_count: 3 }],
  }),
}));
vi.mock('recharts', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  };
});

import { TimeTrackingPage } from './TimeTrackingPage';
import { invalidateForChannel } from '../lib/realtimeInvalidation';
import { renderWithQuery } from '../test/queryWrapper';

const base = {
  user_id: 5,
  activity_id: 2,
  location: null,
  complexity_rating: null,
  quality_rating: null,
  rework_required: false,
  notes: null,
  extra_metadata: null,
  created_at: '2026-09-25T08:00:00',
};

const PAUSED: TimeEntry = {
  ...base,
  id: 'running-1',
  order_id: 42,
  start_time: '2026-09-25T08:00:00',
  end_time: null,
  duration_minutes: null,
  is_paused: true,
} as TimeEntry;

const DONE: TimeEntry = {
  ...base,
  id: 'done-1',
  order_id: 41,
  start_time: '2026-09-24T08:00:00',
  end_time: '2026-09-24T09:30:00',
  duration_minutes: 90,
  is_paused: false,
} as TimeEntry;

const page = (items: TimeEntry[]) => ({ items, total: items.length, limit: 25, offset: 0, next_offset: null });

beforeEach(() => {
  mocks.getUserPage.mockReset();
  mocks.getSummary.mockReset();
  mocks.getSummary.mockResolvedValue({
    total_hours: 1.5,
    billable_hours: 1.5,
    entries_count: 1,
    average_session_minutes: 90,
    most_used_activity: 'Polieren',
  });
  mocks.getUserPage.mockResolvedValue(page([PAUSED, DONE]));
  mocks.runningEntry = PAUSED;
});

describe('TimeTrackingPage (W4-03)', () => {
  it('loads the signed-in user entries as a server page sorted by start time', async () => {
    renderWithQuery(<TimeTrackingPage />, { route: '/time-tracking' });
    await screen.findAllByText('Auftrag #41');
    const listCall = mocks.getUserPage.mock.calls.find(([, params]) => params.limit === 25);
    expect(listCall?.[0]).toBe(5);
    expect(listCall?.[1]).toMatchObject({ offset: 0, limit: 25, sort: '-start_time' });
  });

  it('renders the paused running entry with the Pausiert badge', async () => {
    renderWithQuery(<TimeTrackingPage />, { route: '/time-tracking' });
    const card = await screen.findByRole('region', { name: 'Läuft gerade' });
    expect(within(card).getByText('Pausiert')).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText('Pausiert').length).toBeGreaterThan(1));
    expect(screen.getAllByRole('button', { name: 'Timer öffnen' }).length).toBeGreaterThan(0);
  });

  it('offers the Werkbank-Modus toggle in the page header', async () => {
    renderWithQuery(<TimeTrackingPage />, { route: '/time-tracking' });
    expect(await screen.findByRole('button', { name: 'Werkbank-Modus' })).toHaveAttribute(
      'aria-pressed',
    );
  });

  it('shows the empty state with its next action', async () => {
    mocks.runningEntry = null;
    mocks.getUserPage.mockResolvedValue(page([]));
    renderWithQuery(<TimeTrackingPage />, { route: '/time-tracking' });
    expect(await screen.findByText('Noch keine Zeiteinträge')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Eintrag anlegen' }).length).toBeGreaterThan(1);
  });

  it('refetches the entries on a time_tracking_updates hint', async () => {
    const { client } = renderWithQuery(<TimeTrackingPage />, { route: '/time-tracking' });
    await screen.findAllByText('Auftrag #41');
    const before = mocks.getUserPage.mock.calls.length;
    await act(() => invalidateForChannel(client, 'time_tracking_updates'));
    await waitFor(() => expect(mocks.getUserPage.mock.calls.length).toBeGreaterThan(before));
  });
});
