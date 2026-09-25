// GlobalSearch (W4-03): Modal-based search on TanStack Query.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithQuery } from '../test/queryWrapper';

const mocks = vi.hoisted(() => ({
  orders: vi.fn(),
  materials: vi.fn(),
  customers: vi.fn(),
  navigate: vi.fn(),
}));
vi.mock('../api/orders', () => ({ ordersApi: { getAll: mocks.orders } }));
vi.mock('../api/materials', () => ({ materialsApi: { getAll: mocks.materials } }));
vi.mock('../api/customers', () => ({ customersApi: { search: mocks.customers } }));
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useNavigate: () => mocks.navigate,
}));

import { GlobalSearch } from './GlobalSearch';

afterEach(() => {
  vi.clearAllMocks();
});

describe('GlobalSearch (query)', () => {
  it('opens a dialog, finds orders with German status labels and navigates', async () => {
    mocks.orders.mockResolvedValue([
      { id: 12, title: 'Trauringe Demo', description: null, status: 'in_progress' },
    ]);
    mocks.materials.mockResolvedValue([]);
    mocks.customers.mockResolvedValue([]);
    renderWithQuery(<GlobalSearch />);

    await userEvent.click(screen.getByRole('button', { name: 'Suche öffnen' }));
    expect(screen.getByRole('dialog', { name: 'Suche' })).toBeInTheDocument();

    await userEvent.type(screen.getByRole('combobox'), 'Trau');
    const option = await screen.findByRole('option', { name: /Trauringe Demo/ });
    expect(option).toHaveTextContent('In Bearbeitung');

    await userEvent.click(option);
    expect(mocks.navigate).toHaveBeenCalledWith('/orders/12');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('says so when the search fails instead of showing no results', async () => {
    mocks.orders.mockRejectedValue(new Error('offline'));
    mocks.materials.mockResolvedValue([]);
    mocks.customers.mockResolvedValue([]);
    renderWithQuery(<GlobalSearch />);

    await userEvent.click(screen.getByRole('button', { name: 'Suche öffnen' }));
    await userEvent.type(screen.getByRole('combobox'), 'Ring');

    expect(await screen.findByRole('alert')).toHaveTextContent('Suche fehlgeschlagen');
  });
});
