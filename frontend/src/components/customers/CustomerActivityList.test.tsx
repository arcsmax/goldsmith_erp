// CustomerActivityList — customer 360 "Verlauf" (W2-12, DOM-38).
//
// Pins: one chronological list from GET /customers/{id}/activity, a
// StatusBadge per row (German label from src/design/status.ts), money via
// formatEur, every row a link to its detail (invoices and customer updates
// link to their order or repair), paging with "Weitere laden", an empty
// state with an action, and an error with retry.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

const mockGetActivity = vi.fn();
vi.mock('../../api/customers', () => ({
  customersApi: {
    getActivity: (...a: unknown[]) => mockGetActivity(...a),
  },
}));

import { CustomerActivityList } from './CustomerActivityList';

const ROWS = [
  {
    kind: 'customer_update',
    id: 5,
    occurred_at: '2026-09-06T10:00:00',
    status: 'send_failed',
    title: 'Ihre Kette ist abholbereit',
    reference: null,
    repair_job_id: 2,
    order_id: null,
  },
  {
    kind: 'invoice',
    id: 4,
    occurred_at: '2026-09-05T10:00:00',
    status: 'paid',
    title: 'Rechnung RE-2026-0901',
    reference: 'RE-2026-0901',
    amount: 1200,
    order_id: 1,
  },
  {
    kind: 'quote',
    id: 3,
    occurred_at: '2026-09-04T10:00:00',
    status: 'sent',
    title: 'Kostenvoranschlag KV-2026-0901',
    reference: 'KV-2026-0901',
    amount: 950,
    order_id: null,
  },
  {
    kind: 'repair',
    id: 2,
    occurred_at: '2026-09-03T10:00:00',
    status: 'received',
    title: 'Kette gerissen',
    reference: 'REP-2026-0901',
    amount: 40,
    repair_job_id: 2,
  },
  {
    kind: 'order',
    id: 1,
    occurred_at: '2026-09-02T10:00:00',
    status: 'in_progress',
    title: 'Trauring Meier',
    reference: '#1',
    amount: 1200,
    order_id: 1,
  },
];

function page(items: unknown[], nextOffset: number | null, total = items.length) {
  return { items, total, limit: 50, offset: 0, next_offset: nextOffset };
}

function renderList() {
  return render(
    <MemoryRouter>
      <CustomerActivityList customerId={11} />
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe('CustomerActivityList', () => {
  it('lists every kind newest first with badge, money and a link to its detail', async () => {
    mockGetActivity.mockResolvedValue(page(ROWS, null));
    renderList();

    const links = await screen.findAllByRole('link');
    expect(mockGetActivity).toHaveBeenCalledWith(11, { offset: 0, limit: 50 });
    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      '/repairs/2',
      '/orders/1',
      '/quotes?quote_id=3',
      '/repairs/2',
      '/orders/1',
    ]);
    const order = links[4];
    expect(within(order).getByText('Trauring Meier')).toBeInTheDocument();
    expect(within(order).getByText('In Bearbeitung')).toBeInTheDocument();
    expect(within(order).getByText('1.200,00 €')).toBeInTheDocument();
    expect(within(links[0]).getByText('Versand fehlgeschlagen')).toBeInTheDocument();
    expect(within(links[1]).getByText('Bezahlt')).toBeInTheDocument();
    expect(within(links[2]).getByText('950,00 €')).toBeInTheDocument();
    expect(within(links[3]).getByText('Eingang')).toBeInTheDocument();
    expect(within(links[3]).getByText('Reparatur')).toBeInTheDocument();
  });

  it('shows no amount when the server projected it away (VIEWER)', async () => {
    const { amount: _amount, ...orderWithoutAmount } = ROWS[4] as Record<string, unknown>;
    mockGetActivity.mockResolvedValue(page([orderWithoutAmount], null));
    renderList();

    const link = await screen.findByRole('link');
    expect(within(link).queryByText(/€/)).not.toBeInTheDocument();
  });

  it('loads the next page on "Weitere laden"', async () => {
    const user = userEvent.setup();
    mockGetActivity
      .mockResolvedValueOnce(page(ROWS.slice(0, 2), 2, 5))
      .mockResolvedValueOnce({ ...page(ROWS.slice(2), null, 5), offset: 2 });
    renderList();

    await user.click(await screen.findByRole('button', { name: 'Weitere laden' }));

    expect(mockGetActivity).toHaveBeenLastCalledWith(11, { offset: 2, limit: 50 });
    expect(await screen.findAllByRole('link')).toHaveLength(5);
    expect(screen.queryByRole('button', { name: 'Weitere laden' })).not.toBeInTheDocument();
    expect(screen.getByText('5 Einträge')).toBeInTheDocument();
  });

  it('shows an empty state with a next action', async () => {
    mockGetActivity.mockResolvedValue(page([], null));
    renderList();

    expect(await screen.findByText('Noch kein Verlauf')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Neue Reparatur annehmen' })).toHaveAttribute(
      'href',
      '/repairs?neu=1&customer_id=11',
    );
  });

  it('shows an error with retry', async () => {
    const user = userEvent.setup();
    mockGetActivity
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(page(ROWS.slice(4), null));
    renderList();

    expect(await screen.findByText('Verlauf konnte nicht geladen werden.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Erneut versuchen' }));

    expect(await screen.findByText('Trauring Meier')).toBeInTheDocument();
  });
});
