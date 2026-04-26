// InvoicesPage tests — code-review-fixes-2026-04-23.
//
// Pins two regressions (Bug #2 and Bug #3 from the fix wave):
//
//   1. The CreateInvoiceModal MUST surface the backend's `detail` string
//      inline when invoice creation fails (e.g. order status not eligible),
//      and MUST NOT show the previous generic "Fehler beim Erstellen der
//      Rechnung." message when the backend supplied a more useful detail.
//
//   2. The order picker MUST only show orders whose status is one the
//      backend will actually accept (completed / delivered). Ineligible
//      orders (draft, in_progress, etc.) must not appear in the dropdown.
//
//   3. The InvoiceDetailPanel print body MUST render the Zwischensumme,
//      MwSt and total even when an invoice has zero `line_items` — that
//      block was load-bearing for the print page going non-blank.
//
// The contexts (auth/toast/confirm) are mocked so the test does not need
// to spin up the full provider tree. The API modules are mocked so the
// test never touches the network — the goal is to drive the component
// with controlled responses.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// ---------------------------------------------------------------------------
// Context mocks — keep these BEFORE the component import.
// ---------------------------------------------------------------------------

const mockShowToast = vi.fn();
const mockShowConfirm = vi.fn();
const mockHasRole = vi.fn(() => true);

vi.mock('../contexts', () => ({
  useAuth: () => ({
    hasRole: mockHasRole,
    user: { id: 1, role: 'ADMIN' },
    isAuthenticated: true,
  }),
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: mockShowConfirm }),
}));

// ---------------------------------------------------------------------------
// API mocks
// ---------------------------------------------------------------------------

const mockGetInvoices = vi.fn();
const mockCreateFromOrder = vi.fn();
const mockGetInvoice = vi.fn();
const mockOrdersGetAll = vi.fn();

vi.mock('../api/invoices', () => ({
  invoicesApi: {
    getInvoices: (...args: unknown[]) => mockGetInvoices(...args),
    createFromOrder: (...args: unknown[]) => mockCreateFromOrder(...args),
    getInvoice: (...args: unknown[]) => mockGetInvoice(...args),
    updateInvoice: vi.fn(),
    markAsPaid: vi.fn(),
  },
}));

vi.mock('../api/orders', () => ({
  ordersApi: {
    getAll: (...args: unknown[]) => mockOrdersGetAll(...args),
  },
}));

vi.mock('../api/client', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

// ---------------------------------------------------------------------------
// Component under test
// ---------------------------------------------------------------------------

import { InvoicesPage } from './InvoicesPage';
import type { OrderType, Invoice } from '../types';

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

function makeOrder(overrides: Partial<OrderType> = {}): OrderType {
  return {
    id: 1,
    title: 'Test Order',
    description: 'desc',
    price: 100,
    status: 'completed',
    customer_id: 1,
    created_at: '2026-04-01T00:00:00Z',
    updated_at: '2026-04-01T00:00:00Z',
    ...overrides,
  };
}

function makeInvoice(overrides: Partial<Invoice> = {}): Invoice {
  return {
    id: 99,
    invoice_number: 'RE-2026-0099',
    order_id: 1,
    customer_id: 1,
    created_by: 1,
    status: 'DRAFT',
    issue_date: '2026-04-23T10:00:00Z',
    due_date: '2026-05-07T10:00:00Z',
    paid_date: null,
    subtotal: 100,
    tax_rate: 19,
    tax_amount: 19,
    total: 119,
    notes: null,
    payment_method: null,
    created_at: '2026-04-23T10:00:00Z',
    updated_at: '2026-04-23T10:00:00Z',
    line_items: [],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('InvoicesPage — Bug #3 (generic error & dropdown filter)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHasRole.mockReturnValue(true);
    mockGetInvoices.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 25 });
  });

  it('shows the backend detail inline in the modal when creation fails', async () => {
    // Arrange: the user can pick a completed order (so the dropdown is
    // populated and the submit button enables), but the backend rejects
    // with a 422 because — say — the order already has an active invoice.
    mockOrdersGetAll.mockResolvedValue([
      makeOrder({ id: 3, status: 'completed', title: 'Ohrringe Paar' }),
    ]);
    const backendDetail =
      'Fuer Auftrag 3 existiert bereits eine aktive Rechnung';
    mockCreateFromOrder.mockRejectedValue({
      response: { status: 409, data: { detail: backendDetail } },
    });

    render(<InvoicesPage />);

    // Wait for the initial invoice list fetch to settle
    await waitFor(() => expect(mockGetInvoices).toHaveBeenCalled());

    // Open the create modal
    fireEvent.click(screen.getByRole('button', { name: /Rechnung erstellen/i }));

    // Wait for the orders fetch to populate the dropdown
    await waitFor(() => expect(mockOrdersGetAll).toHaveBeenCalled());

    // Pick the eligible order
    const orderSelect = await screen.findByLabelText(/Auftrag/i);
    fireEvent.change(orderSelect, { target: { value: '3' } });

    // Submit the modal
    const submitBtn = screen.getByRole('button', {
      name: /^Rechnung erstellen$/i,
    });
    fireEvent.click(submitBtn);

    // Assert: the backend detail surfaces inline AND via toast — the
    // generic "Fehler beim Erstellen der Rechnung." string MUST NOT be
    // shown when a more specific detail is available.
    await waitFor(() => {
      expect(screen.getByTestId('invoice-create-error')).toHaveTextContent(
        backendDetail
      );
    });
    expect(mockShowToast).toHaveBeenCalledWith(backendDetail, 'error');
    expect(
      screen.queryByText('Fehler beim Erstellen der Rechnung.')
    ).not.toBeInTheDocument();
  });

  it('filters out non-completable orders from the dropdown', async () => {
    // Arrange: backend returns a mix of statuses — only completed and
    // delivered should be selectable. draft / in_progress are ineligible
    // because the backend's create_invoice_from_order guard rejects them.
    mockOrdersGetAll.mockResolvedValue([
      makeOrder({ id: 1, status: 'in_progress', title: 'Goldring Reparatur' }),
      makeOrder({ id: 2, status: 'draft', title: 'Verlobungsring' }),
      makeOrder({ id: 3, status: 'completed', title: 'Ohrringe Paar' }),
      makeOrder({ id: 4, status: 'delivered', title: 'Trauring Paar' }),
    ]);

    render(<InvoicesPage />);
    await waitFor(() => expect(mockGetInvoices).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('button', { name: /Rechnung erstellen/i }));
    await waitFor(() => expect(mockOrdersGetAll).toHaveBeenCalled());

    const orderSelect = (await screen.findByLabelText(
      /Auftrag/i
    )) as HTMLSelectElement;

    // Visible options: placeholder + the 2 eligible orders
    const optionValues = Array.from(orderSelect.options).map((o) => o.value);
    expect(optionValues).toContain('3'); // completed → eligible
    expect(optionValues).toContain('4'); // delivered → eligible
    expect(optionValues).not.toContain('1'); // in_progress → hidden
    expect(optionValues).not.toContain('2'); // draft → hidden
  });
});

describe('InvoicesPage — Bug #2 (Drucken renders empty)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHasRole.mockReturnValue(true);
  });

  it('renders the invoice body (Zwischensumme + Gesamtbetrag) even when line_items is empty', async () => {
    // Arrange: a real-world invoice with zero line_items. The print page
    // bug previously hid the entire detail panel via display:none on
    // .invoices-table; the regression test for that lives in the CSS
    // diff. The frontend regression we want to pin here is that the
    // totals block renders unconditionally — without it, the printed
    // page would be blank even with the CSS fix.
    const invoice = makeInvoice({
      subtotal: 100,
      tax_rate: 19,
      tax_amount: 19,
      total: 119,
      line_items: [],
    });
    mockGetInvoices.mockResolvedValue({
      items: [
        {
          id: invoice.id,
          invoice_number: invoice.invoice_number,
          order_id: invoice.order_id,
          customer_id: invoice.customer_id,
          status: invoice.status,
          issue_date: invoice.issue_date,
          due_date: invoice.due_date,
          paid_date: null,
          total: invoice.total,
          created_at: invoice.created_at,
        },
      ],
      total: 1,
      skip: 0,
      limit: 25,
    });
    mockGetInvoice.mockResolvedValue(invoice);

    render(<InvoicesPage />);

    // Wait for the row to appear, then click it to expand the detail panel
    const rowCell = await screen.findByText('RE-2026-0099');
    fireEvent.click(rowCell);

    // The expanded detail panel must include the totals block
    await waitFor(() => {
      expect(screen.getByText(/Zwischensumme \(netto\)/)).toBeInTheDocument();
    });
    expect(screen.getByText(/MwSt \(19%\)/)).toBeInTheDocument();
    expect(screen.getByText(/Gesamtbetrag \(brutto\)/)).toBeInTheDocument();
    // The Drucken button must be wired up in the panel header
    expect(
      screen.getByRole('button', { name: /Drucken/i })
    ).toBeInTheDocument();
  });
});
