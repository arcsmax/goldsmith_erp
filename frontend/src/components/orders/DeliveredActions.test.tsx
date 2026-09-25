// DeliveredActions (W2-11, DOM-34/35): Abholprotokoll + Wertgutachten.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockDownloadHandover = vi.fn();
const mockSaveBlob = vi.fn();
vi.mock('../../api/handover', () => ({
  downloadHandoverPdf: (...a: unknown[]) => mockDownloadHandover(...a),
  saveBlob: (...a: unknown[]) => mockSaveBlob(...a),
}));

const mockList = vi.fn();
const mockCreateFromOrder = vi.fn();
const mockDownloadAndSave = vi.fn();
vi.mock('../../api/valuations', () => ({
  valuationsApi: {
    list: (...a: unknown[]) => mockList(...a),
    createFromOrder: (...a: unknown[]) => mockCreateFromOrder(...a),
    downloadAndSavePdf: (...a: unknown[]) => mockDownloadAndSave(...a),
  },
}));

const mockShowToast = vi.fn();
vi.mock('../../contexts', () => ({ useToast: () => ({ showToast: mockShowToast }) }));

import { DeliveredActions } from './DeliveredActions';

const cert = { id: 9, certificate_number: 'WG-2026-0001' };

beforeEach(() => {
  vi.clearAllMocks();
  mockList.mockResolvedValue([]);
  mockDownloadHandover.mockResolvedValue(new Blob(['%PDF']));
  mockCreateFromOrder.mockResolvedValue(cert);
  mockDownloadAndSave.mockResolvedValue(undefined);
});

describe('DeliveredActions', () => {
  it('downloads the Abholprotokoll', async () => {
    render(<DeliveredActions orderId={42} price={1200} role="GOLDSMITH" userName="Anne Gold" />);
    await userEvent.click(screen.getByRole('button', { name: 'Abholprotokoll herunterladen' }));
    expect(mockDownloadHandover).toHaveBeenCalledWith(42);
    expect(mockSaveBlob).toHaveBeenCalledWith(expect.any(Blob), 'Abholprotokoll_42.pdf');
  });

  it('creates a Wertgutachten from the order with a prefilled value and downloads it as ADMIN', async () => {
    render(<DeliveredActions orderId={42} price={1200} role="ADMIN" userName="Anne Gold" />);
    await userEvent.click(screen.getByRole('button', { name: 'Wertgutachten erstellen' }));

    expect((screen.getByLabelText('Gutachtenwert (€)') as HTMLInputElement).value).toBe('1200');
    expect((screen.getByLabelText('Gutachter') as HTMLInputElement).value).toBe('Anne Gold');
    await userEvent.click(screen.getByRole('button', { name: 'Wertgutachten speichern' }));

    expect(mockCreateFromOrder).toHaveBeenCalledWith(42, {
      appraised_value: 1200,
      goldsmith_name: 'Anne Gold',
    });
    expect(mockDownloadAndSave).toHaveBeenCalledWith(9, 'WG-2026-0001');
    expect(mockShowToast).toHaveBeenCalledWith('Wertgutachten WG-2026-0001 erstellt', 'success');
  });

  it('does not export the PDF for a goldsmith (ADMIN only) but still creates it', async () => {
    render(<DeliveredActions orderId={42} price={1200} role="GOLDSMITH" userName="Anne Gold" />);
    await userEvent.click(screen.getByRole('button', { name: 'Wertgutachten erstellen' }));
    await userEvent.click(screen.getByRole('button', { name: 'Wertgutachten speichern' }));

    expect(mockCreateFromOrder).toHaveBeenCalled();
    expect(mockDownloadAndSave).not.toHaveBeenCalled();
  });

  it('offers the existing certificate instead of creating a second one', async () => {
    mockList.mockResolvedValue([cert]);
    render(<DeliveredActions orderId={42} price={1200} role="ADMIN" userName="Anne Gold" />);
    await userEvent.click(await screen.findByRole('button', { name: 'Wertgutachten WG-2026-0001 herunterladen' }));
    expect(mockDownloadAndSave).toHaveBeenCalledWith(9, 'WG-2026-0001');
    expect(mockCreateFromOrder).not.toHaveBeenCalled();
  });
});
