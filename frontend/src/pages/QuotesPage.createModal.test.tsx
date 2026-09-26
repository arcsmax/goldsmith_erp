// LV2-07: "Neues Angebot" carries role="dialog" aria-modal="true" but
// Escape did not close it — only clicking the backdrop or the X did.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithQuery } from '../test/queryWrapper';

const customers = vi.hoisted(() => ({
  getAll: vi.fn(),
  search: vi.fn(),
}));

const api = vi.hoisted(() => ({
  getQuotesPage: vi.fn(),
  getQuote: vi.fn(),
  createQuote: vi.fn(),
}));

vi.mock('../api/quotes', () => ({ quotesApi: api }));
vi.mock('../api/customers', () => ({ customersApi: customers }));
vi.mock('../api/orders', () => ({ ordersApi: { getById: vi.fn() } }));

vi.mock('../contexts', () => ({
  useToast: () => ({ showToast: vi.fn() }),
  useConfirm: () => ({ showConfirm: vi.fn().mockResolvedValue(true) }),
}));
vi.mock('../components/estimator/EstimatorPanel', () => ({ EstimatorPanel: () => null }));
vi.mock('../components/SignatureCanvas', () => ({ SignatureCanvas: () => null }));
vi.mock('../lib/logError', () => ({ logError: vi.fn() }));

import { QuotesPage } from './QuotesPage';

function renderAt(url: string) {
  return renderWithQuery(<QuotesPage />, { route: url });
}

describe('QuotesPage — "Neues Angebot" modal Escape handling (LV2-07)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getQuotesPage.mockResolvedValue({ items: [], total: 0, offset: 0, limit: 25, next_offset: null });
  });

  it('closes the create-quote dialog on Escape', async () => {
    const user = userEvent.setup();
    renderAt('/quotes');

    await user.click(await screen.findByRole('button', { name: 'Neues Angebot' }));
    const dialog = await screen.findByRole('dialog', { name: 'Neues Angebot erstellen' });
    expect(dialog).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog', { name: 'Neues Angebot erstellen' })).not.toBeInTheDocument();
  });
});
