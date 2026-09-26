// ConsumeMetalModal tests — W7 hygiene follow-up.
//
// docs/review/2026-09-25 open follow-up: the order picker used to fetch up
// to 500 orders unconditionally (`ordersApi.getAll({ limit: 500 })`) to
// populate a plain <select>. It now fetches the same 100-row page other
// order pickers use via the paged `/orders/?offset=…&q=…` endpoint, plus a
// debounced search box so an order outside that first page is still
// reachable by number/title/customer.
//
// Pins:
//   (a) opening the modal requests the paged endpoint with a bounded limit
//       (not the old 500) and no search term.
//   (b) typing in "Auftrag suchen" re-queries the paged endpoint with `q`
//       set to the (debounced, trimmed) search text.
import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithQuery } from '../../test/queryWrapper';
import type { OrderPageParams } from '../../api/paged';

const mockOrdersPage = vi.fn();
vi.mock('../../api/paged', () => ({
  pagedApi: { orders: (...args: unknown[]) => mockOrdersPage(...args) },
}));

const mockListPurchases = vi.fn();
const mockPreviewAllocation = vi.fn();
const mockConsumeMaterial = vi.fn();
vi.mock('../../api/metal-inventory', () => ({
  metalInventoryApi: {
    listPurchases: (...args: unknown[]) => mockListPurchases(...args),
    previewAllocation: (...args: unknown[]) => mockPreviewAllocation(...args),
    consumeMaterial: (...args: unknown[]) => mockConsumeMaterial(...args),
  },
}));

vi.mock('../../hooks/useMetalTypes', () => ({
  useMetalTypes: () => ({ metalTypes: [], groupedMetalTypes: {}, isLoading: false, error: null }),
}));

import { ConsumeMetalModal } from './ConsumeMetalModal';

function makeOrder(overrides: Partial<{ id: number; title: string; status: string }> = {}) {
  return { id: 1, title: 'Ring', status: 'in_progress', ...overrides };
}

describe('ConsumeMetalModal order picker', () => {
  it('loads a bounded page (not 500 rows) with no search term on open', async () => {
    mockOrdersPage.mockResolvedValue({ items: [makeOrder()], total: 1, limit: 100, offset: 0 });
    mockListPurchases.mockResolvedValue([]);

    renderWithQuery(
      <ConsumeMetalModal isOpen onClose={() => {}} onSuccess={() => {}} />,
      { route: null },
    );

    await waitFor(() => expect(mockOrdersPage).toHaveBeenCalled());
    const params = mockOrdersPage.mock.calls[0][0] as OrderPageParams;
    expect(params.limit).toBeLessThanOrEqual(100);
    expect(params.q).toBeUndefined();
    expect(await screen.findByText(/Ring/)).toBeInTheDocument();
  });

  it('searches the paged endpoint by the typed order text', async () => {
    mockOrdersPage.mockResolvedValue({ items: [makeOrder()], total: 1, limit: 100, offset: 0 });
    mockListPurchases.mockResolvedValue([]);
    const user = userEvent.setup();

    renderWithQuery(
      <ConsumeMetalModal isOpen onClose={() => {}} onSuccess={() => {}} />,
      { route: null },
    );
    await waitFor(() => expect(mockOrdersPage).toHaveBeenCalled());
    mockOrdersPage.mockClear();

    await user.type(screen.getByPlaceholderText('Titel, Kunde oder Nr. …'), 'Ehering');

    await waitFor(() => {
      const calls = mockOrdersPage.mock.calls;
      const params = calls[calls.length - 1][0] as OrderPageParams;
      expect(params.q).toBe('Ehering');
    });
  });
});
