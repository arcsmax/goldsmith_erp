// WorkshopSettingsPanel — Werkstatt-Stammdaten form (W2-04, DOM-24; W4-03 react-hook-form + zod).
//
// Backend contract (tests/integration/test_invoice_ustg14.py):
// GET/PUT /admin/workshop-settings (ADMIN only); the response lists the
// §14 Abs. 4 UStG seller fields that are still missing.
//
// Pins:
//   (a) loads the settings and shows the missing §14 fields as a hint.
//   (b) saving sends every field (blank optional fields as null) and
//       confirms with "Stammdaten gespeichert".
//   (c) a failed save shows the backend's German message.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockGet = vi.fn();
const mockUpdate = vi.fn();
vi.mock('../../lib/logError', () => ({ logError: vi.fn() }));
vi.mock('../../api/admin', () => ({
  getWorkshopSettings: (...args: unknown[]) => mockGet(...args),
  updateWorkshopSettings: (...args: unknown[]) => mockUpdate(...args),
}));

import { renderWithQuery } from '../../test/queryWrapper';
import { WorkshopSettingsPanel } from './WorkshopSettingsPanel';

const EMPTY = {
  name: 'Goldschmiede',
  owner_name: null,
  street: null,
  postal_code: null,
  city: null,
  country: 'Deutschland',
  phone: null,
  email: null,
  tax_number: null,
  vat_id: null,
  iban: null,
  bic: null,
  bank_name: null,
  is_kleinunternehmer: false,
  default_vat_rate: 19,
  invoice_footer: null,
  updated_at: null,
  missing_fields: ['Straße und Hausnummer', 'PLZ', 'Ort', 'Steuernummer oder USt-IdNr.'],
  is_complete: false,
};

afterEach(() => {
  vi.clearAllMocks();
});

describe('WorkshopSettingsPanel', () => {
  it('shows which §14 UStG fields are still missing', async () => {
    mockGet.mockResolvedValue(EMPTY);
    renderWithQuery(<WorkshopSettingsPanel />);

    expect(
      await screen.findByText(/fehlen noch: .*Steuernummer oder USt-IdNr\./)
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Name der Werkstatt/)).toHaveValue('Goldschmiede');
  });

  it('saves the form and confirms', async () => {
    mockGet.mockResolvedValue(EMPTY);
    mockUpdate.mockResolvedValue({ ...EMPTY, missing_fields: [], is_complete: true });
    renderWithQuery(<WorkshopSettingsPanel />);
    await screen.findByLabelText('Straße und Hausnummer');

    await userEvent.type(screen.getByLabelText('Straße und Hausnummer'), 'Werkstattweg 5');
    await userEvent.type(screen.getByLabelText('PLZ'), '80331');
    await userEvent.type(screen.getByLabelText('Ort'), 'München');
    await userEvent.type(screen.getByLabelText('Steuernummer'), '143/123/45678');
    await userEvent.click(screen.getByLabelText(/Kleinunternehmer/));
    await userEvent.click(screen.getByRole('button', { name: 'Stammdaten speichern' }));

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
    const payload = mockUpdate.mock.calls[0][0];
    expect(payload).toMatchObject({
      name: 'Goldschmiede',
      street: 'Werkstattweg 5',
      postal_code: '80331',
      city: 'München',
      tax_number: '143/123/45678',
      vat_id: null,
      is_kleinunternehmer: true,
      default_vat_rate: 19,
    });
    expect(await screen.findByText('Stammdaten gespeichert')).toBeInTheDocument();
  });

  it('shows the backend error when saving fails', async () => {
    mockGet.mockResolvedValue(EMPTY);
    mockUpdate.mockRejectedValue({
      response: { data: { detail: [{ msg: 'Value error, Ungültige IBAN' }] } },
    });
    renderWithQuery(<WorkshopSettingsPanel />);
    await screen.findByLabelText('IBAN');

    await userEvent.type(screen.getByLabelText('IBAN'), 'falsch');
    await userEvent.click(screen.getByRole('button', { name: 'Stammdaten speichern' }));

    expect(await screen.findByText(/Ungültige IBAN/)).toBeInTheDocument();
  });

  it('blocks the save and names the problem when the zod rules fail', async () => {
    mockGet.mockResolvedValue(EMPTY);
    renderWithQuery(<WorkshopSettingsPanel />);
    const name = await screen.findByLabelText(/Name der Werkstatt/);

    await userEvent.clear(name);
    await userEvent.type(screen.getByLabelText('E-Mail'), 'keine-adresse');
    await userEvent.type(screen.getByLabelText('PLZ'), '80a31');
    await userEvent.clear(screen.getByLabelText('Umsatzsteuersatz (%)'));
    await userEvent.type(screen.getByLabelText('Umsatzsteuersatz (%)'), '120');
    await userEvent.click(screen.getByRole('button', { name: 'Stammdaten speichern' }));

    expect(await screen.findByText(/Name der Werkstatt fehlt/)).toBeInTheDocument();
    expect(screen.getByText(/E-Mail-Adresse ist ungültig/)).toBeInTheDocument();
    expect(screen.getByText(/PLZ bitte nur mit Ziffern/)).toBeInTheDocument();
    expect(screen.getByText(/zwischen 0 und 100/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Name der Werkstatt/)).toHaveAttribute('aria-invalid', 'true');
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it('accepts a comma as decimal separator for the VAT rate', async () => {
    mockGet.mockResolvedValue(EMPTY);
    mockUpdate.mockResolvedValue(EMPTY);
    renderWithQuery(<WorkshopSettingsPanel />);
    const rate = await screen.findByLabelText('Umsatzsteuersatz (%)');

    await userEvent.clear(rate);
    await userEvent.type(rate, '7,5');
    await userEvent.click(screen.getByRole('button', { name: 'Stammdaten speichern' }));

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
    expect(mockUpdate.mock.calls[0][0]).toMatchObject({ default_vat_rate: 7.5 });
  });
});
