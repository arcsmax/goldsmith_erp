// CalendarPage on TanStack Query (W4-03): one query per visible range,
// order hints invalidate ['calendar'], errors show a retry.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithQuery } from '../test/queryWrapper';
import { invalidateForChannel } from '../lib/realtimeInvalidation';
import { buildCalendarGrid, getEventMarker } from '../components/calendar/calendarGrid';

const mockGet = vi.fn();
vi.mock('../api/client', () => ({
  default: { get: (...a: unknown[]) => mockGet(...a) },
}));

import { CalendarPage } from './CalendarPage';

function todayIso(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}T10:00:00`;
}

function respond(url: string) {
  if (url.startsWith('/calendar/events')) {
    return Promise.resolve({
      data: [
        {
          id: 1,
          user_id: 1,
          title: 'Kundentermin Demo',
          event_type: 'appointment',
          start_datetime: todayIso(),
          end_datetime: null,
          all_day: false,
          description: null,
        },
      ],
    });
  }
  return Promise.resolve({
    data: [
      {
        id: 7,
        order_id: 7,
        title: 'Trauringe Demo',
        event_type: 'order_deadline',
        start_datetime: todayIso(),
        traffic_light: 'red',
        days_until_deadline: 1,
      },
    ],
  });
}

function eventCalls() {
  return mockGet.mock.calls.filter(([url]) => String(url).startsWith('/calendar/events'));
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('CalendarPage (query)', () => {
  it('shows stored events and deadlines with a text label, not colour alone', async () => {
    mockGet.mockImplementation(respond);
    renderWithQuery(<CalendarPage />);

    expect(await screen.findByText('Kundentermin Demo')).toBeInTheDocument();
    expect(screen.getByText('Trauringe Demo')).toBeInTheDocument();
    expect(screen.getAllByText(/Frist in weniger als 2 Tagen/).length).toBeGreaterThan(0);
  });

  it('refetches on an order_updates hint (deadlines come from orders)', async () => {
    mockGet.mockImplementation(respond);
    const { client } = renderWithQuery(<CalendarPage />);
    await screen.findByText('Trauringe Demo');
    const before = eventCalls().length;

    await act(() => invalidateForChannel(client, 'order_updates'));

    await waitFor(() => expect(eventCalls().length).toBeGreaterThan(before));
  });

  it('loads the next month range when "Weiter" is pressed', async () => {
    mockGet.mockImplementation(respond);
    renderWithQuery(<CalendarPage />);
    await screen.findByText('Trauringe Demo');
    const before = eventCalls().length;

    await userEvent.click(screen.getByRole('button', { name: 'Weiter' }));

    await waitFor(() => expect(eventCalls().length).toBe(before + 1));
  });

  it('shows an error with a retry instead of silently empty days', async () => {
    mockGet.mockRejectedValue(new Error('offline'));
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    renderWithQuery(<CalendarPage />);

    expect(await screen.findByRole('button', { name: 'Erneut versuchen' })).toBeInTheDocument();
  });
});

describe('calendarGrid helpers', () => {
  it('builds whole weeks starting on Monday', () => {
    const grid = buildCalendarGrid(2026, 8); // September 2026 starts on a Tuesday
    expect(grid.every((week) => week.length === 7)).toBe(true);
    expect(grid[0][0].date.getDay()).toBe(1);
    expect(grid[0][1].day).toBe(1);
  });

  it('gives every marker a shape and a label', () => {
    const marker = getEventMarker({
      id: 1,
      title: 'x',
      event_type: 'reminder',
      start_datetime: '2026-09-01T00:00:00',
      user_id: 1,
    } as never);
    expect(marker.symbol).not.toBe('');
    expect(marker.label).toBe('Erinnerung');
  });
});
