// OrderTimeline — GET /orders/{id}/timeline as a vertical history (W2-08, DOM-16).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockGetTimeline = vi.fn();
vi.mock('../../api', () => ({
  ordersApi: { getTimeline: (...a: unknown[]) => mockGetTimeline(...a) },
}));

const mockLogError = vi.fn();
vi.mock('../../lib/logError', () => ({
  logError: (...a: unknown[]) => mockLogError(...a),
}));

import { OrderTimeline, formatRelativeGerman, parseBackendDate } from './OrderTimeline';

const NOW = new Date('2026-09-25T12:00:00Z');

const ITEMS = [
  {
    kind: 'status',
    id: 'event-1',
    at: '2026-09-20T08:00:00',
    summary: 'Angelegt: Entwurf',
    data: { to_status: 'draft' },
  },
  {
    kind: 'time_entry',
    id: 'time-3',
    at: '2026-09-24T09:00:00',
    summary: 'Zeiterfassung: Polieren',
    data: { duration_minutes: 45 },
  },
  {
    kind: 'status',
    id: 'event-2',
    at: '2026-09-25T10:00:00',
    summary: 'In Bearbeitung → Pausiert',
    data: { to_status: 'on_hold', reason: 'Stein fehlt' },
  },
  {
    kind: 'customer_update',
    id: 'update-4',
    at: '2026-09-22T11:00:00',
    summary: 'Kundeninfo: Fortschritt',
    data: { status: 'sent' },
  },
  {
    kind: 'photo',
    id: 'photo-5',
    at: '2026-09-23T11:00:00',
    summary: 'Foto aufgenommen',
    data: { photo_id: 'x' },
  },
];

afterEach(() => {
  vi.clearAllMocks();
});

describe('OrderTimeline', () => {
  it('renders mixed kinds newest first with one entry per item', async () => {
    mockGetTimeline.mockResolvedValue({ order_id: 7, items: ITEMS });
    render(<OrderTimeline orderId={7} now={NOW} />);

    const list = await screen.findByRole('list', { name: 'Auftragsverlauf' });
    const entries = within(list).getAllByRole('listitem');
    expect(entries.map((e) => e.getAttribute('data-kind'))).toEqual([
      'status',
      'time_entry',
      'photo',
      'customer_update',
      'status',
    ]);
    expect(entries[0]).toHaveTextContent('In Bearbeitung → Pausiert');
    expect(entries[0]).toHaveTextContent('Grund: Stein fehlt');
    expect(entries[1]).toHaveTextContent('45 Min.');
    // Every entry names its kind in text, not by icon alone.
    expect(entries[2]).toHaveTextContent('Foto');
    expect(entries[3]).toHaveTextContent('Kundeninfo');
  });

  it('shows German relative dates with the absolute date on the <time> element', async () => {
    mockGetTimeline.mockResolvedValue({ order_id: 7, items: [ITEMS[2]] });
    render(<OrderTimeline orderId={7} now={NOW} />);

    const time = await screen.findByText('vor 2 Stunden');
    expect(time.tagName).toBe('TIME');
    expect(time).toHaveAttribute('dateTime', '2026-09-25T10:00:00.000Z');
  });

  it('shows an empty state when there is no history yet', async () => {
    mockGetTimeline.mockResolvedValue({ order_id: 7, items: [] });
    render(<OrderTimeline orderId={7} now={NOW} />);

    expect(await screen.findByText('Noch kein Verlauf')).toBeInTheDocument();
  });

  it('shows the error with a retry that reloads', async () => {
    mockGetTimeline.mockRejectedValueOnce(new Error('offline'));
    mockGetTimeline.mockResolvedValueOnce({ order_id: 7, items: [ITEMS[0]] });
    render(<OrderTimeline orderId={7} now={NOW} />);

    expect(await screen.findByText('Verlauf konnte nicht geladen werden.')).toBeInTheDocument();
    expect(mockLogError).toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByText('Angelegt: Entwurf')).toBeInTheDocument();
  });

  it('reloads when refreshKey changes', async () => {
    mockGetTimeline.mockResolvedValue({ order_id: 7, items: [] });
    const { rerender } = render(<OrderTimeline orderId={7} now={NOW} refreshKey={0} />);
    await screen.findByText('Noch kein Verlauf');
    rerender(<OrderTimeline orderId={7} now={NOW} refreshKey={1} />);
    await vi.waitFor(() => expect(mockGetTimeline).toHaveBeenCalledTimes(2));
  });
});

describe('timeline date helpers', () => {
  it('treats naive backend timestamps as UTC', () => {
    expect(parseBackendDate('2026-09-25T10:00:00').toISOString()).toBe('2026-09-25T10:00:00.000Z');
    expect(parseBackendDate('2026-09-25T10:00:00+02:00').toISOString()).toBe(
      '2026-09-25T08:00:00.000Z'
    );
  });

  it('formats relative German dates', () => {
    expect(formatRelativeGerman(new Date('2026-09-25T11:59:40Z'), NOW)).toBe('gerade eben');
    expect(formatRelativeGerman(new Date('2026-09-25T11:55:00Z'), NOW)).toBe('vor 5 Minuten');
    expect(formatRelativeGerman(new Date('2026-09-24T12:00:00Z'), NOW)).toBe('gestern');
    expect(formatRelativeGerman(new Date('2026-09-10T12:00:00Z'), NOW)).toBe('vor 2 Wochen');
  });
});
