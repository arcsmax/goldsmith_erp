// CustomerDetailPage — customer 360 "Verlauf" tab (W2-12, DOM-38) and the
// Rechnungen tab's server-side customer filter.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockGetById = vi.fn();
vi.mock('../api', () => ({
  customersApi: { getById: (...a: unknown[]) => mockGetById(...a) },
  ordersApi: { getAll: vi.fn().mockResolvedValue([]) },
}));

const mockGetActivity = vi.fn();
vi.mock('../api/customers', () => ({
  customersApi: { getActivity: (...a: unknown[]) => mockGetActivity(...a) },
}));

const mockGetInvoices = vi.fn();
vi.mock('../api/invoices', () => ({
  invoicesApi: { getInvoices: (...a: unknown[]) => mockGetInvoices(...a) },
}));

vi.mock('../contexts', () => ({
  useAuth: () => ({ user: { role: 'GOLDSMITH' }, hasRole: () => true }),
  useToast: () => ({ showToast: vi.fn() }),
  useConfirm: () => ({ showConfirm: vi.fn().mockResolvedValue(false) }),
}));

vi.mock('../api/consents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/consents')>()),
  consentsApi: { list: vi.fn().mockResolvedValue([]), grant: vi.fn(), revoke: vi.fn() },
}));

import { CustomerDetailPage } from './CustomerDetailPage';

const CUSTOMER = {
  id: 11,
  first_name: 'Anna',
  last_name: 'Beispiel',
  email: 'anna@example.com',
  country: 'DE',
  customer_type: 'private',
  tags: [],
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/customers/11']}>
      <Routes>
        <Route path="/customers/:id" element={<CustomerDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe('CustomerDetailPage — Verlauf', () => {
  it('shows the merged history with badges and links', async () => {
    const user = userEvent.setup();
    mockGetById.mockResolvedValue(CUSTOMER);
    mockGetActivity.mockResolvedValue({
      items: [
        {
          kind: 'repair',
          id: 2,
          occurred_at: '2026-09-03T10:00:00',
          status: 'ready',
          title: 'Kette gerissen',
          reference: 'REP-2026-0901',
          amount: 40,
          repair_job_id: 2,
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
      next_offset: null,
    });
    renderPage();
    await screen.findByText('anna@example.com');

    await user.click(screen.getByRole('tab', { name: 'Verlauf' }));

    const row = await screen.findByRole('link', { name: /Kette gerissen/ });
    expect(row).toHaveAttribute('href', '/repairs/2');
    expect(screen.getByText('Abholbereit')).toBeInTheDocument();
    expect(screen.getByText('40,00 €')).toBeInTheDocument();
    expect(mockGetActivity).toHaveBeenCalledWith(11, { offset: 0, limit: 50 });
  });

  it('asks the server for this customer’s invoices only', async () => {
    const user = userEvent.setup();
    mockGetById.mockResolvedValue(CUSTOMER);
    mockGetInvoices.mockResolvedValue({
      items: [
        {
          id: 4,
          invoice_number: 'RE-2026-0901',
          status: 'paid',
          total: 1200,
          issue_date: '2026-09-05T10:00:00',
          customer_id: 11,
        },
      ],
      total: 1,
    });
    renderPage();
    await screen.findByText('anna@example.com');

    await user.click(screen.getByRole('tab', { name: 'Rechnungen' }));

    expect(await screen.findByText('RE-2026-0901')).toBeInTheDocument();
    expect(mockGetInvoices).toHaveBeenCalledWith({ customer_id: 11, limit: 200 });
    expect(screen.getByText('Bezahlt')).toBeInTheDocument();
    expect(screen.getByText('1.200,00 €')).toBeInTheDocument();
  });
});
