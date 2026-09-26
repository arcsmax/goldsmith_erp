// W4-03 (W2-04 open item): "Stornieren" on an issued invoice creates the
// linked negative Stornorechnung through POST /invoices/{id}/storno.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithQuery } from '../test/queryWrapper';
import type { Invoice } from '../types';

const mockShowToast = vi.fn();
const mockHasRole = vi.fn((roles: string[]) => roles.includes('ADMIN'));

vi.mock('../contexts', () => ({
  useAuth: () => ({ hasRole: mockHasRole, user: { id: 1, role: 'ADMIN' }, isAuthenticated: true }),
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: vi.fn().mockResolvedValue(true) }),
}));

const api = vi.hoisted(() => ({
  getInvoices: vi.fn(),
  getInvoice: vi.fn(),
  createStorno: vi.fn(),
  cancelInvoice: vi.fn(),
  createFromOrder: vi.fn(),
  markAsPaid: vi.fn(),
  updateInvoice: vi.fn(),
}));

vi.mock('../api/invoices', () => ({ invoicesApi: api }));
vi.mock('../api/orders', () => ({ ordersApi: { getAll: vi.fn().mockResolvedValue([]) } }));
vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
vi.mock('../lib/logError', () => ({ logError: vi.fn() }));

import { InvoicesPage } from './InvoicesPage';

function makeInvoice(overrides: Partial<Invoice> = {}): Invoice {
  return {
    id: 7,
    invoice_number: 'RE-2026-0007',
    order_id: 1,
    customer_id: 1,
    created_by: 1,
    status: 'sent',
    issue_date: '2026-09-01T10:00:00Z',
    due_date: '2026-09-15T10:00:00Z',
    paid_date: null,
    subtotal: 100,
    tax_rate: 19,
    tax_amount: 19,
    total: 119,
    scrap_gold_credit: 0,
    notes: null,
    payment_method: null,
    created_at: '2026-09-01T10:00:00Z',
    updated_at: '2026-09-01T10:00:00Z',
    line_items: [],
    ...overrides,
  } as Invoice;
}

const STORNO = makeInvoice({
  id: 8,
  invoice_number: 'RE-2026-0008',
  status: 'sent',
  subtotal: -100,
  tax_amount: -19,
  total: -119,
  cancels_invoice_id: 7,
});

function renderAt(route: string) {
  return renderWithQuery(<InvoicesPage />, { route });
}

function detailPanel(): HTMLElement {
  return screen.getByTestId('invoice-detail-panel');
}

describe('InvoicesPage Storno (W2-04)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHasRole.mockImplementation((roles: string[]) => roles.includes('ADMIN'));
    api.getInvoices.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 25 });
    api.getInvoice.mockImplementation(async (id: number) => (id === 8 ? STORNO : makeInvoice()));
    api.createStorno.mockResolvedValue(STORNO);
  });

  it('asks for a reason, creates the Stornorechnung and opens it', async () => {
    const user = userEvent.setup();
    renderAt('/invoices?invoice_id=7');

    await user.click(await within(await screen.findByTestId('invoice-detail-panel')).findByRole('button', { name: 'Stornieren' }));
    const dialog = await screen.findByRole('dialog', { name: 'Rechnung stornieren' });
    await user.type(within(dialog).getByLabelText(/Grund der Stornierung/), 'Falscher Betrag');
    await user.click(within(dialog).getByRole('button', { name: 'Stornorechnung erstellen' }));

    await waitFor(() => expect(api.createStorno).toHaveBeenCalledWith(7, 'Falscher Betrag'));
    expect(api.cancelInvoice).not.toHaveBeenCalled();
    expect(mockShowToast).toHaveBeenCalledWith('Stornorechnung RE-2026-0008 erstellt.', 'success');

    // The new Storno opens and links back to the original invoice.
    await waitFor(() => expect(within(detailPanel()).getByText('RE-2026-0008')).toBeInTheDocument());
    expect(within(detailPanel()).getByRole('link', { name: 'Rechnung #7' })).toBeInTheDocument();
  });

  it('does nothing when the reason dialog is cancelled', async () => {
    const user = userEvent.setup();
    renderAt('/invoices?invoice_id=7');

    await user.click(await within(await screen.findByTestId('invoice-detail-panel')).findByRole('button', { name: 'Stornieren' }));
    const dialog = await screen.findByRole('dialog', { name: 'Rechnung stornieren' });
    await user.click(within(dialog).getByRole('button', { name: 'Abbrechen' }));

    expect(api.createStorno).not.toHaveBeenCalled();
  });

  it('offers the Storno for a paid invoice too', async () => {
    api.getInvoice.mockResolvedValue(makeInvoice({ status: 'paid', paid_date: '2026-09-10T10:00:00Z' }));
    renderAt('/invoices?invoice_id=7');
    expect(await within(await screen.findByTestId('invoice-detail-panel')).findByRole('button', { name: 'Stornieren' })).toBeInTheDocument();
  });

  it('never offers a Storno of a Storno, nor of a draft', async () => {
    api.getInvoice.mockResolvedValue(STORNO);
    const { unmount } = renderAt('/invoices?invoice_id=8');
    await screen.findByTestId('invoice-detail-panel');
    expect(within(detailPanel()).queryByRole('button', { name: 'Stornieren' })).not.toBeInTheDocument();
    unmount();

    api.getInvoice.mockResolvedValue(makeInvoice({ status: 'draft' }));
    renderAt('/invoices?invoice_id=7');
    await screen.findByTestId('invoice-detail-panel');
    expect(within(detailPanel()).queryByRole('button', { name: 'Stornieren' })).not.toBeInTheDocument();
    expect(within(detailPanel()).getByRole('button', { name: 'Entwurf stornieren' })).toBeInTheDocument();
  });

  it('hides the Storno from a goldsmith (backend: INVOICE_DELETE is ADMIN only)', async () => {
    mockHasRole.mockImplementation((roles: string[]) => roles.includes('GOLDSMITH'));
    renderAt('/invoices?invoice_id=7');
    await screen.findByTestId('invoice-detail-panel');
    expect(within(detailPanel()).queryByRole('button', { name: 'Stornieren' })).not.toBeInTheDocument();
    expect(within(detailPanel()).getByRole('button', { name: 'Als bezahlt markieren' })).toBeInTheDocument();
  });

  it('shows the backend reason when the Storno is refused', async () => {
    api.createStorno.mockRejectedValue({
      isAxiosError: true,
      response: { status: 422, data: { detail: 'Rechnung ist bereits storniert.' } },
    });
    const user = userEvent.setup();
    renderAt('/invoices?invoice_id=7');

    await user.click(await within(await screen.findByTestId('invoice-detail-panel')).findByRole('button', { name: 'Stornieren' }));
    const dialog = await screen.findByRole('dialog', { name: 'Rechnung stornieren' });
    await user.click(within(dialog).getByRole('button', { name: 'Stornorechnung erstellen' }));

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith('Rechnung ist bereits storniert.', 'error'),
    );
  });
});
