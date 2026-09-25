// CustomersPage on TanStack Query (W3-03). GET /customers/ has no Page
// envelope yet, so the page keeps the legacy skip/limit call inside useQuery;
// search, type and status filters go to the server as params.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
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

const mockShowConfirm = vi.fn();
const mockShowToast = vi.fn();
vi.mock('../contexts', () => ({
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: mockShowConfirm }),
}));
vi.mock('../components/CustomerFormModal', () => ({ CustomerFormModal: () => null }));

import { CustomersPage } from './CustomersPage';

function customer(id: number, lastName = `Muster${id}`) {
  return {
    id,
    first_name: 'Maria',
    last_name: lastName,
    email: `kundin${id}@example.test`,
    phone: null,
    company_name: null,
    customer_type: 'private',
    is_active: true,
    tags: [],
  };
}

function customerCalls() {
  return mockGet.mock.calls.filter(([url]) => url === '/customers/');
}

function lastParams() {
  const calls = customerCalls();
  return calls[calls.length - 1]?.[1]?.params;
}

afterEach(() => {
  mockGet.mockReset();
  mockDelete.mockReset();
  mockShowConfirm.mockReset();
  mockShowToast.mockReset();
});

describe('CustomersPage (queries)', () => {
  it('loads the first page once with skip and limit', async () => {
    mockGet.mockResolvedValue({ data: [customer(1), customer(2)] });
    renderWithQuery(<CustomersPage />, { route: '/customers' });

    expect(await screen.findByText('Maria Muster1')).toBeInTheDocument();
    expect(lastParams()).toEqual({ skip: 0, limit: 25 });
    expect(customerCalls()).toHaveLength(1);
  });

  it('sends the search text as the server-side search param (debounced)', async () => {
    mockGet.mockResolvedValue({ data: [customer(1)] });
    renderWithQuery(<CustomersPage />, { route: '/customers' });
    await screen.findByText('Maria Muster1');

    mockGet.mockResolvedValue({ data: [customer(7, 'Meier')] });
    await userEvent.type(screen.getByRole('searchbox', { name: /Kunden durchsuchen/ }), 'Meier');

    expect(await screen.findByText('Maria Meier')).toBeInTheDocument();
    expect(lastParams()).toEqual({ skip: 0, limit: 25, search: 'Meier' });
    expect(customerCalls().filter(([, cfg]) => cfg.params.search)).toHaveLength(1);
  });

  it('sends type and status filters as params', async () => {
    mockGet.mockResolvedValue({ data: [customer(1)] });
    renderWithQuery(<CustomersPage />, { route: '/customers' });
    await screen.findByText('Maria Muster1');

    await userEvent.selectOptions(screen.getByLabelText('Kundentyp'), 'business');
    await userEvent.selectOptions(screen.getByLabelText('Kundenstatus'), 'false');
    await waitFor(() =>
      expect(lastParams()).toEqual({
        skip: 0,
        limit: 25,
        customer_type: 'business',
        is_active: false,
      }),
    );
  });

  it('shows an empty state with an action when nothing matches', async () => {
    mockGet.mockResolvedValue({ data: [] });
    renderWithQuery(<CustomersPage />, { route: '/customers' });
    expect(await screen.findByRole('heading', { name: 'Noch keine Kunden' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Kunden anlegen' })).toBeInTheDocument();
  });

  it('deletes through a mutation and refetches the list', async () => {
    mockGet.mockResolvedValue({ data: [customer(1)] });
    mockShowConfirm.mockResolvedValue(true);
    mockDelete.mockResolvedValue({ data: {} });
    renderWithQuery(<CustomersPage />, { route: '/customers' });
    await screen.findByText('Maria Muster1');

    await userEvent.click(screen.getByRole('button', { name: 'Kunden löschen' }));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/customers/1'));
    await waitFor(() => expect(customerCalls()).toHaveLength(2));
  });
});
