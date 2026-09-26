// OrdersPage on TanStack Query (W3-03): server-side paging, status filter
// and `q` search go into the request params; a realtime order hint causes
// exactly one refetch; mutations invalidate the list.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithQuery } from '../test/queryWrapper';

const mockGet = vi.fn();
const mockDelete = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...a: unknown[]) => mockGet(...a),
    delete: (...a: unknown[]) => mockDelete(...a),
  },
}));

let mockRole = 'ADMIN';
const mockShowConfirm = vi.fn();
const mockShowToast = vi.fn();
vi.mock('../contexts', () => ({
  useAuth: () => ({ user: { id: 1, role: mockRole } }),
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: mockShowConfirm }),
}));
vi.mock('../components/orders/OrderFormModal', () => ({ OrderFormModal: () => null }));
vi.mock('../components/AuthenticatedImage', () => ({
  default: ({ src, alt }: { src: string; alt: string }) => (
    <img data-testid="auth-img" data-src={src} alt={alt} />
  ),
}));

import { OrdersPage } from './OrdersPage';
import { invalidateForChannel } from '../lib/realtimeInvalidation';

function order(id: number, overrides: Record<string, unknown> = {}) {
  return {
    id,
    title: `Auftrag ${id}`,
    description: 'Ring',
    status: 'in_progress',
    customer_id: 1,
    price: 2100,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    first_photo_id: null,
    ...overrides,
  };
}

function page(items: unknown[], { total = items.length, limit = 25, offset = 0 } = {}) {
  const following = offset + limit;
  return {
    data: { items, total, limit, offset, next_offset: following < total ? following : null },
  };
}

function orderCalls() {
  return mockGet.mock.calls.filter(([url]) => url === '/orders/');
}

function lastOrderParams() {
  const calls = orderCalls();
  return calls[calls.length - 1]?.[1]?.params;
}

afterEach(() => {
  mockGet.mockReset();
  mockDelete.mockReset();
  mockShowConfirm.mockReset();
  mockShowToast.mockReset();
  mockRole = 'ADMIN';
});

describe('OrdersPage (paged queries)', () => {
  it('requests the first page with limit and offset and renders the Page items', async () => {
    mockGet.mockResolvedValue(page([order(1), order(2)], { total: 60 }));
    renderWithQuery(<OrdersPage />, { route: '/orders' });

    expect(await screen.findByText('Auftrag 1')).toBeInTheDocument();
    expect(screen.getByText('Auftrag 2')).toBeInTheDocument();
    expect(lastOrderParams()).toEqual({ limit: 25, offset: 0 });
    // total comes from the envelope, not from the rows on screen
    expect(screen.getByText(/60 Aufträge/)).toBeInTheDocument();
    expect(screen.getByText(/Seite 1 von 3/)).toBeInTheDocument();
  });

  it('renders the StatusBadge and the thumbnail per row', async () => {
    mockGet.mockResolvedValue(page([order(1, { first_photo_id: 'photo-1' })]));
    renderWithQuery(<OrdersPage />, { route: '/orders' });

    const row = (await screen.findByText('Auftrag 1')).closest('tr') as HTMLElement;
    expect(within(row).getByTestId('auth-img')).toHaveAttribute(
      'data-src',
      expect.stringContaining('photo-1'),
    );
    expect(within(row).getByText('In Bearbeitung')).toBeInTheDocument();
  });

  it('sends the status filter to the server and resets to the first page', async () => {
    mockGet.mockResolvedValue(page([order(1)], { total: 60 }));
    renderWithQuery(<OrdersPage />, { route: '/orders' });
    await screen.findByText('Auftrag 1');

    await userEvent.click(screen.getByRole('button', { name: /Nächste Seite/ }));
    await waitFor(() => expect(lastOrderParams()).toEqual({ limit: 25, offset: 25 }));

    await userEvent.selectOptions(screen.getByLabelText(/Status/), 'completed');
    await waitFor(() =>
      expect(lastOrderParams()).toEqual({ limit: 25, offset: 0, status: 'completed' }),
    );
  });

  it('takes the status filter from the URL (dashboard deep link)', async () => {
    mockGet.mockResolvedValue(page([order(1)]));
    renderWithQuery(<OrdersPage />, { route: '/orders?status=in_progress' });
    await screen.findByText('Auftrag 1');
    expect(lastOrderParams()).toEqual({ limit: 25, offset: 0, status: 'in_progress' });
  });

  it('sends the search text as q (debounced, trimmed)', async () => {
    mockGet.mockResolvedValue(page([order(1)]));
    renderWithQuery(<OrdersPage />, { route: '/orders' });
    await screen.findByText('Auftrag 1');

    await userEvent.type(screen.getByRole('searchbox', { name: /Aufträge durchsuchen/ }), ' Ring ');
    await waitFor(() => expect(lastOrderParams()).toEqual({ limit: 25, offset: 0, q: 'Ring' }));
    // no request per keystroke
    expect(orderCalls().filter(([, cfg]) => cfg.params.q !== undefined)).toHaveLength(1);
  });

  it('refetches exactly once on a realtime order hint', async () => {
    mockGet.mockResolvedValue(page([order(1)]));
    const { client } = renderWithQuery(<OrdersPage />, { route: '/orders' });
    await screen.findByText('Auftrag 1');
    expect(orderCalls()).toHaveLength(1);

    mockGet.mockResolvedValue(page([order(1, { title: 'Auftrag 1 geändert' })]));
    await act(() => invalidateForChannel(client, 'order_updates'));

    expect(await screen.findByText('Auftrag 1 geändert')).toBeInTheDocument();
    expect(orderCalls()).toHaveLength(2);
  });

  it('keeps prices away from a VIEWER', async () => {
    mockRole = 'VIEWER';
    mockGet.mockResolvedValue(page([order(1, { price: undefined })]));
    renderWithQuery(<OrdersPage />, { route: '/orders' });

    await screen.findByText('Auftrag 1');
    expect(screen.queryByRole('columnheader', { name: 'Preis' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Gesamtwert/)).not.toBeInTheDocument();
    expect(screen.queryByText('Wird berechnet')).not.toBeInTheDocument();
  });

  it('shows an error with retry when the page fails to load', async () => {
    mockGet.mockRejectedValueOnce(new Error('network'));
    renderWithQuery(<OrdersPage />, { route: '/orders' });

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    mockGet.mockResolvedValue(page([order(1)]));
    await userEvent.click(screen.getByRole('button', { name: /Erneut versuchen/ }));
    expect(await screen.findByText('Auftrag 1')).toBeInTheDocument();
  });

  it('deletes through a mutation and refetches the list once', async () => {
    mockGet.mockResolvedValue(page([order(1)]));
    mockShowConfirm.mockResolvedValue(true);
    mockDelete.mockResolvedValue({ data: { success: true, message: 'ok' } });
    renderWithQuery(<OrdersPage />, { route: '/orders' });
    await screen.findByText('Auftrag 1');

    await userEvent.click(screen.getByRole('button', { name: 'Auftrag löschen' }));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/orders/1'));
    await waitFor(() => expect(orderCalls()).toHaveLength(2));
    expect(mockShowToast).toHaveBeenCalledWith('Auftrag gelöscht', 'success');
  });
});
