// RepairDetailPage — "Rechnung erstellen" (ARCH-02: repairs are invoiced
// through POST /repairs/{id}/invoice). GOLDSMITH / ADMIN only, for READY or
// PICKED_UP repairs with a customer; success opens the invoice, 409 / 422
// show the backend's German message.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import type { RepairJob } from '../types';
import { renderWithQuery } from '../test/queryWrapper';

const mockGetById = vi.fn();
vi.mock('../api/repairs', () => ({
  repairsApi: { getById: (...args: unknown[]) => mockGetById(...args) },
  repairPhotoPath: (id: number) => `/repairs/photos/${id}`,
  repairPhotoThumbPath: (id: number) => `/repairs/photos/${id}/thumbnail`,
}));

const mockInvoiceRepair = vi.fn();
vi.mock('../api/jobs', () => ({
  jobsApi: { invoiceRepair: (...args: unknown[]) => mockInvoiceRepair(...args) },
}));

// The Kundeninfo panel loads its own drafts for READY repairs; not under test.
vi.mock('../components/repairs/RepairCustomerUpdatePanel', () => ({
  RepairCustomerUpdatePanel: () => null,
}));

const mockUseAuth = vi.fn();
const mockShowToast = vi.fn();
vi.mock('../contexts', () => ({
  useAuth: () => mockUseAuth(),
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: vi.fn() }),
}));

import { RepairDetailPage } from './RepairDetailPage';

function makeRepair(overrides: Partial<RepairJob> = {}): RepairJob {
  return {
    id: 7,
    repair_number: 'REP-2026-0007',
    bag_number: 'TU-7',
    item_description: 'Kette löten',
    item_type: 'chain',
    status: 'ready',
    customer_id: 3,
    customer: { id: 3, first_name: 'Erika', last_name: 'Muster' },
    is_deleted: false,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    photos: [],
    estimated_cost: 80,
    actual_cost: 90,
    ...overrides,
  } as RepairJob;
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
}

function renderPage() {
  return renderWithQuery(
    <MemoryRouter initialEntries={['/repairs/7']}>
      <Routes>
        <Route path="/repairs/:id" element={<RepairDetailPage />} />
        <Route path="/invoices" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
    { route: null },
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('RepairDetailPage — Rechnung erstellen', () => {
  it('creates the invoice and opens it', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH' } });
    mockGetById.mockResolvedValue(makeRepair());
    mockInvoiceRepair.mockResolvedValue({ id: 42 });

    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Rechnung erstellen' }));

    expect(mockInvoiceRepair).toHaveBeenCalledWith(
      7,
      expect.objectContaining({ due_date: expect.any(String) }),
    );
    expect(await screen.findByTestId('location')).toHaveTextContent('/invoices?invoice_id=42');
    expect(mockShowToast).toHaveBeenCalledWith('Rechnung erstellt', 'success');
  });

  it('shows the backend message on 409 and stays on the page', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'ADMIN' } });
    mockGetById.mockResolvedValue(makeRepair({ status: 'picked_up' }));
    mockInvoiceRepair.mockRejectedValue({
      isAxiosError: true,
      response: { status: 409, data: { detail: 'Für diese Reparatur gibt es bereits eine Rechnung.' } },
    });

    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Rechnung erstellen' }));

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(
        'Für diese Reparatur gibt es bereits eine Rechnung.',
        'error',
      ),
    );
    expect(screen.queryByTestId('location')).not.toBeInTheDocument();
  });

  it.each([
    ['VIEWER', 'ready', 3],
    ['GOLDSMITH', 'in_repair', 3],
    ['GOLDSMITH', 'ready', null],
  ])('hides the action for %s / %s / customer %s', async (role, status, customerId) => {
    mockUseAuth.mockReturnValue({ user: { role } });
    mockGetById.mockResolvedValue(
      makeRepair({ status: status as RepairJob['status'], customer_id: customerId }),
    );

    renderPage();
    await screen.findByRole('heading', { name: 'REP-2026-0007' });
    expect(screen.queryByRole('button', { name: 'Rechnung erstellen' })).not.toBeInTheDocument();
  });
});
