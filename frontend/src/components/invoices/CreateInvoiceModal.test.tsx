// CreateInvoiceModal tests — W7 hygiene follow-up.
//
// The "Rechnung erstellen" order picker used to fetch up to 500 orders
// unconditionally (INVOICE_ORDER_PICKER_LIMIT, legacy list) to populate a
// plain <select>. It now fetches a bounded page (useInvoiceableOrders) with
// a debounced search box, so typing a number/title/customer re-queries the
// server instead of scrolling a 500-row dropdown.
import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithQuery } from '../../test/queryWrapper';

const mockUseInvoiceableOrders = vi.fn();
vi.mock('./useInvoiceQueries', () => ({
  useInvoiceableOrders: (...args: unknown[]) => mockUseInvoiceableOrders(...args),
}));

import { CreateInvoiceModal } from './CreateInvoiceModal';

function makeOrder(overrides: Partial<{ id: number; title: string; status: string }> = {}) {
  return { id: 7, title: 'Kette', status: 'completed', ...overrides };
}

describe('CreateInvoiceModal order picker', () => {
  it('re-queries useInvoiceableOrders with the debounced search text', async () => {
    mockUseInvoiceableOrders.mockReturnValue({
      data: { items: [makeOrder()], total: 1, limit: 100, offset: 0 },
      isPending: false,
      isError: false,
    });
    const user = userEvent.setup();

    renderWithQuery(
      <CreateInvoiceModal open submitError={null} onClose={() => {}} onSubmit={async () => {}} />,
      { route: null },
    );

    expect(await screen.findByText(/Kette/)).toBeInTheDocument();
    expect(mockUseInvoiceableOrders).toHaveBeenCalledWith(true, '');

    await user.type(screen.getByPlaceholderText('Titel, Kunde oder Nr. …'), 'Kette');

    await waitFor(() => {
      const calls = mockUseInvoiceableOrders.mock.calls;
      expect(calls[calls.length - 1]).toEqual([true, 'Kette']);
    });
  });
});
