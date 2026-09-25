// WorkshopSettingsSection — Werkstatt-Stammdaten form (W2-04, DOM-24).
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
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockGet = vi.fn();
const mockUpdate = vi.fn();
vi.mock('../../api/admin', () => ({
  getWorkshopSettings: (...args: unknown[]) => mockGet(...args),
  updateWorkshopSettings: (...args: unknown[]) => mockUpdate(...args),
}));

import { WorkshopSettingsSection } from './WorkshopSettingsSection';

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

describe('WorkshopSettingsSection', () => {
  it('shows which §14 UStG fields are still missing', async () => {
    mockGet.mockResolvedValue(EMPTY);
    render(<WorkshopSettingsSection />);

    expect(
      await screen.findByText(/fehlen noch: .*Steuernummer oder USt-IdNr\./)
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Name der Werkstatt')).toHaveValue('Goldschmiede');
  });

  it('saves the form and confirms', async () => {
    mockGet.mockResolvedValue(EMPTY);
    mockUpdate.mockResolvedValue({ ...EMPTY, missing_fields: [], is_complete: true });
    render(<WorkshopSettingsSection />);
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
    render(<WorkshopSettingsSection />);
    await screen.findByLabelText('IBAN');

    await userEvent.type(screen.getByLabelText('IBAN'), 'falsch');
    await userEvent.click(screen.getByRole('button', { name: 'Stammdaten speichern' }));

    expect(await screen.findByText(/Ungültige IBAN/)).toBeInTheDocument();
  });
});
