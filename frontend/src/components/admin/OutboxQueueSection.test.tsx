// OutboxQueueSection — Nachrichten-Warteschlange (ARCH-04 / ARCH-12).
//
// Backend contract (tests/integration/test_admin_outbox_api.py):
// GET /admin/outbox?status=failed|dead, POST /admin/outbox/{id}/retry.
//
// Pins:
//   (a) loads failed and dead rows and shows kind label + error code.
//   (b) "Nachricht erneut senden" calls retry and reloads the lists.
//   (c) empty lists show an EmptyState.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockGet = vi.fn();
const mockRetry = vi.fn();
vi.mock('../../api/admin', () => ({
  getOutbox: (...args: unknown[]) => mockGet(...args),
  retryOutboxMessage: (...args: unknown[]) => mockRetry(...args),
}));

import { OutboxQueueSection } from './OutboxQueueSection';

const COUNTS = { pending: 0, sent: 3, failed: 0, dead: 1 };

const deadRow = {
  id: 7,
  kind: 'customer_update',
  status: 'dead',
  attempts: 6,
  payload: { update_id: 12, user_id: 1 },
  next_attempt_at: '2026-09-25T10:00:00',
  last_error: 'delivery_failed',
  created_at: '2026-09-25T09:00:00',
  sent_at: null,
};

const list = (items: unknown[]) => ({ items, counts: COUNTS, mode: 'worker' });

afterEach(() => {
  vi.clearAllMocks();
});

describe('OutboxQueueSection', () => {
  it('shows dead rows with kind label and error code', async () => {
    mockGet.mockImplementation((status: string) =>
      Promise.resolve(list(status === 'dead' ? [deadRow] : [])),
    );
    render(<OutboxQueueSection />);

    expect(await screen.findAllByText('Kundeninfo')).not.toHaveLength(0);
    expect(screen.getAllByText('delivery_failed').length).toBeGreaterThan(0);
    expect(screen.getByText('Keine fehlgeschlagenen Nachrichten')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith('failed');
    expect(mockGet).toHaveBeenCalledWith('dead');
  });

  it('retries a row and reloads', async () => {
    mockGet.mockImplementation((status: string) =>
      Promise.resolve(list(status === 'dead' ? [deadRow] : [])),
    );
    mockRetry.mockResolvedValue({ ...deadRow, status: 'pending', attempts: 0 });
    render(<OutboxQueueSection />);

    const [button] = await screen.findAllByRole('button', { name: 'Nachricht erneut senden' });
    await userEvent.click(button);

    await waitFor(() => expect(mockRetry).toHaveBeenCalledWith(7));
    expect(await screen.findByText('Nachricht 7 wird erneut gesendet.')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledTimes(4);
  });

  it('shows empty states when nothing failed', async () => {
    mockGet.mockResolvedValue(list([]));
    render(<OutboxQueueSection />);
    expect(await screen.findByText('Keine aufgegebenen Nachrichten')).toBeInTheDocument();
  });
});
