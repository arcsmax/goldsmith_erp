// W2-05 (DOM-11, DOM-11d, FE-18): QuotesPage "Versenden", approval method
// and the ?order_id / ?quote_id hand-offs.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithQuery } from '../test/queryWrapper';
import type { Quote } from '../types';

const customers = vi.hoisted(() => ({
  getAll: vi.fn(),
  search: vi.fn(),
}));

const api = vi.hoisted(() => ({
  getQuotesPage: vi.fn(),
  getQuote: vi.fn(),
  sendQuote: vi.fn(),
  approveQuote: vi.fn(),
  downloadPdf: vi.fn(),
  createQuote: vi.fn(),
}));

vi.mock('../api/quotes', () => ({ quotesApi: api }));
vi.mock('../api/customers', () => ({ customersApi: customers }));
vi.mock('../api/orders', () => ({
  ordersApi: { getById: vi.fn().mockResolvedValue({ id: 42, order_type: 'ring' }) },
}));

const mockShowToast = vi.fn();
vi.mock('../contexts', () => ({
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: vi.fn().mockResolvedValue(true) }),
}));
vi.mock('../components/estimator/EstimatorPanel', () => ({
  EstimatorPanel: () => null,
}));
vi.mock('../components/SignatureCanvas', () => ({
  SignatureCanvas: () => null,
}));
vi.mock('../lib/logError', () => ({ logError: vi.fn() }));

import { QuotesPage, sendOutcomeMessage } from './QuotesPage';

function makeQuote(overrides: Partial<Quote> = {}): Quote {
  return {
    id: 5,
    quote_number: 'KV-2026-0005',
    order_id: null,
    customer_id: 7,
    created_by: 1,
    status: 'draft',
    valid_until: '2026-10-09T00:00:00',
    subtotal: 150,
    tax_rate: 19,
    tax_amount: 28.5,
    total: 178.5,
    notes: null,
    created_at: '2026-09-25T10:00:00',
    updated_at: '2026-09-25T10:00:00',
    line_items: [],
    ...overrides,
  };
}

function renderAt(url: string) {
  return renderWithQuery(<QuotesPage />, { route: url });
}

describe('QuotesPage Versenden (DOM-11)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getQuotesPage.mockResolvedValue({ items: [], total: 0, offset: 0, limit: 25, next_offset: null });
    api.getQuote.mockResolvedValue(makeQuote());
    api.downloadPdf.mockResolvedValue(undefined);
  });

  it('emails the quote: calls the send endpoint and shows the German outcome', async () => {
    api.sendQuote.mockResolvedValue(
      makeQuote({ status: 'sent', delivery_method: 'email', sent_at: '2026-09-25T10:05:00' } as Partial<Quote>)
    );
    const user = userEvent.setup();
    renderAt('/quotes?quote_id=5');

    await user.click(await screen.findByRole('button', { name: 'Versenden' }));

    await waitFor(() => expect(api.sendQuote).toHaveBeenCalledWith(5));
    expect(api.downloadPdf).not.toHaveBeenCalled();
    expect(mockShowToast).toHaveBeenCalledWith('Kostenvoranschlag per E-Mail versendet.', 'success');
  });

  it('without SMTP it downloads the PDF and says so', async () => {
    api.sendQuote.mockResolvedValue(
      makeQuote({ status: 'sent', delivery_method: 'pdf_manual' } as Partial<Quote>)
    );
    const user = userEvent.setup();
    renderAt('/quotes?quote_id=5');

    await user.click(await screen.findByRole('button', { name: 'Versenden' }));

    await waitFor(() => expect(api.downloadPdf).toHaveBeenCalledWith(5, 'KV-2026-0005'));
    expect(mockShowToast).toHaveBeenCalledWith(
      sendOutcomeMessage({ ...makeQuote(), delivery_method: 'pdf_manual' }),
      'success'
    );
  });

  it('a failed email shows the backend German error and keeps the draft', async () => {
    api.sendQuote.mockRejectedValue({
      isAxiosError: true,
      response: { status: 502, data: { detail: 'E-Mail-Versand fehlgeschlagen. Der Kostenvoranschlag bleibt ein Entwurf.' } },
    });
    const user = userEvent.setup();
    renderAt('/quotes?quote_id=5');

    await user.click(await screen.findByRole('button', { name: 'Versenden' }));

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(
        'E-Mail-Versand fehlgeschlagen. Der Kostenvoranschlag bleibt ein Entwurf.',
        'error'
      )
    );
    expect(api.downloadPdf).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Versenden' })).toBeInTheDocument();
  });
});

describe('QuotesPage approval method (DOM-11d)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getQuotesPage.mockResolvedValue({ items: [], total: 0, offset: 0, limit: 25, next_offset: null });
    api.getQuote.mockResolvedValue(makeQuote({ status: 'sent' }));
    api.approveQuote.mockResolvedValue(makeQuote({ status: 'approved' }));
  });

  it('requires choosing how the customer agreed and sends it', async () => {
    const user = userEvent.setup();
    renderAt('/quotes?quote_id=5');

    await user.click(await screen.findByRole('button', { name: 'Genehmigen' }));
    const approve = screen.getByRole('button', { name: 'Angebot genehmigen' });
    expect(approve).toBeDisabled();

    await user.click(screen.getByLabelText('Telefonisch'));
    await user.click(approve);

    await waitFor(() =>
      expect(api.approveQuote).toHaveBeenCalledWith(5, {
        response_method: 'phone',
        signature_data: undefined,
      })
    );
  });
});

describe('QuotesPage hand-off from the order page (FE-18)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getQuotesPage.mockResolvedValue({ items: [], total: 0, offset: 0, limit: 25, next_offset: null });
  });

  it('opens the create modal pre-filled from ?order_id&customer_id', async () => {
    renderAt('/quotes?order_id=42&customer_id=7');

    expect(await screen.findByRole('dialog', { name: 'Neues Angebot erstellen' })).toBeInTheDocument();
    expect(await screen.findByText('Kunde #7')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Kunde ändern' })).toBeInTheDocument();
    expect((screen.getByLabelText('Auftragsnummer (optional)') as HTMLInputElement).value).toBe('42');
  });
});

describe('QuotesPage customer selection (LV-02)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getQuotesPage.mockResolvedValue({ items: [], total: 0, offset: 0, limit: 25, next_offset: null });
  });

  it('never loads the whole customer list (the API caps limit at 100)', async () => {
    renderAt('/quotes');
    await screen.findByRole('button', { name: 'Neues Angebot' });
    expect(customers.getAll).not.toHaveBeenCalled();
  });

  it('finds the customer through the search and enables "Angebot erstellen"', async () => {
    customers.search.mockResolvedValue([
      { id: 7, first_name: 'Erika', last_name: 'Muster', company_name: null },
    ]);
    const user = userEvent.setup();
    renderAt('/quotes');
    await user.click(await screen.findByRole('button', { name: 'Neues Angebot' }));

    const submit = screen.getByRole('button', { name: 'Angebot erstellen' });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText(/^Kunde/), 'Mus');
    await user.click(await screen.findByRole('button', { name: 'Erika Muster' }));

    expect(screen.getByText('Erika Muster')).toBeInTheDocument();
    expect(submit).toBeEnabled();
    expect(customers.search).toHaveBeenCalledWith('Mus', expect.any(Number));
  });

  it('shows a toast when the customer search fails instead of failing silently', async () => {
    customers.search.mockRejectedValue(new Error('network'));
    const user = userEvent.setup();
    renderAt('/quotes');
    await user.click(await screen.findByRole('button', { name: 'Neues Angebot' }));
    await user.type(screen.getByLabelText(/^Kunde/), 'Mus');

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(
        'Kundensuche fehlgeschlagen. Bitte erneut versuchen.',
        'error',
      ),
    );
  });
});
