// ScrapGoldTab — W2-16 (DOM-21): Ausweisdaten for the Ankaufsbuch.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockGetForOrder = vi.fn();
const mockSetIdentification = vi.fn();
vi.mock('../../api/scrap-gold', async (orig) => {
  const actual = await orig<typeof import('../../api/scrap-gold')>();
  return {
    ...actual,
    scrapGoldApi: {
      ...actual.scrapGoldApi,
      getForOrder: (...a: unknown[]) => mockGetForOrder(...a),
      setIdentification: (...a: unknown[]) => mockSetIdentification(...a),
    },
  };
});
vi.mock('../../api/client', () => ({ default: { get: vi.fn() } }));

const mockShowToast = vi.fn();
vi.mock('../../contexts', () => ({ useToast: () => ({ showToast: mockShowToast }) }));
vi.mock('../SignatureCanvas', () => ({
  SignatureCanvas: () => <div data-testid="signature-canvas" />,
}));
vi.mock('./AlloyCalculator', () => ({ AlloyCalculator: () => null, ALLOY_OPTIONS: [] }));

import { ScrapGoldTab } from './ScrapGoldTab';

const base = {
  id: 3,
  order_id: 5,
  customer_id: 7,
  created_by: 1,
  status: 'calculated',
  total_fine_gold_g: 40,
  total_value_eur: 2500,
  gold_price_per_g: 62.5,
  price_source: 'fixed_rate',
  signature_data: null,
  signed_at: null,
  receipt_pdf_path: null,
  notes: null,
  items: [
    {
      id: 1,
      scrap_gold_id: 3,
      description: 'Alter Ehering',
      alloy: '585',
      weight_g: 10,
      fine_content_g: 5.85,
      photo_path: null,
      created_at: '2026-09-25T00:00:00',
    },
  ],
  created_at: '2026-09-25T00:00:00',
  updated_at: '2026-09-25T00:00:00',
  id_document_type: null,
  id_document_number_last4: null,
  id_issuing_authority: null,
  id_checked_by: null,
  id_checked_at: null,
  has_identification: false,
  id_required: true,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ScrapGoldTab — Ausweisdaten (W2-16)', () => {
  it('above the threshold asks for ID data and blocks the signature until it is saved', async () => {
    mockGetForOrder.mockResolvedValue(base);
    render(<ScrapGoldTab orderId={5} customerId={7} />);

    expect(await screen.findByText(/Ausweisdaten sind bei diesem Ankaufswert Pflicht/)).toBeInTheDocument();
    expect(screen.queryByTestId('signature-canvas')).not.toBeInTheDocument();
    expect(screen.getByText(/Bitte zuerst die Ausweisdaten erfassen/)).toBeInTheDocument();
  });

  it('saves Ausweisart, Nummer and Behörde and then allows the signature', async () => {
    mockGetForOrder.mockResolvedValue(base);
    mockSetIdentification.mockResolvedValue({
      ...base,
      id_document_type: 'reisepass',
      id_document_number_last4: '4711',
      id_issuing_authority: 'Stadt Augsburg',
      has_identification: true,
    });
    render(<ScrapGoldTab orderId={5} customerId={7} />);

    await userEvent.selectOptions(await screen.findByLabelText('Ausweisart'), 'reisepass');
    await userEvent.type(screen.getByLabelText('Ausweisnummer'), 'C01X04711');
    await userEvent.type(screen.getByLabelText('Ausstellende Behörde'), 'Stadt Augsburg');
    await userEvent.click(screen.getByRole('button', { name: 'Ausweisdaten speichern' }));

    expect(mockSetIdentification).toHaveBeenCalledWith(3, {
      id_document_type: 'reisepass',
      id_document_number: 'C01X04711',
      id_issuing_authority: 'Stadt Augsburg',
    });
    expect(mockShowToast).toHaveBeenCalledWith('Ausweisdaten gespeichert', 'success');
    expect(await screen.findByTestId('signature-canvas')).toBeInTheDocument();
    expect(screen.getByText(/Reisepass · Nr\. endet auf 4711 · Stadt Augsburg/)).toBeInTheDocument();
  });

  it('below the threshold the ID fields are optional and the signature is available', async () => {
    mockGetForOrder.mockResolvedValue({ ...base, total_value_eur: 480, id_required: false });
    render(<ScrapGoldTab orderId={5} customerId={7} />);

    expect(await screen.findByTestId('signature-canvas')).toBeInTheDocument();
    expect(screen.getByText(/Ausweisdaten \(optional\)/)).toBeInTheDocument();
  });

  it('shows the recorded ID read-only once signed', async () => {
    mockGetForOrder.mockResolvedValue({
      ...base,
      status: 'signed',
      signed_at: '2026-09-25T10:00:00',
      id_document_type: 'personalausweis',
      id_document_number_last4: '1234',
      id_issuing_authority: 'Stadt München',
      has_identification: true,
    });
    render(<ScrapGoldTab orderId={5} customerId={7} />);

    expect(await screen.findByText(/Personalausweis · Nr\. endet auf 1234 · Stadt München/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Ausweisnummer')).not.toBeInTheDocument();
  });
});
