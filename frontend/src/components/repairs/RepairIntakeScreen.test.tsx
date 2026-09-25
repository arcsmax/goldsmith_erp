// RepairIntakeScreen — counter intake in one screen (W2-12, FE-17, DOM-08).
//
// Pins:
//   (a) required fields: without a customer and a description nothing is
//       sent and both errors are shown in German;
//   (b) quick-create path: "Neuer Kunde" creates a walk-in customer with
//       name and phone only, and that customer is selected;
//   (c) submit payload: chips and fields become exactly the RepairJobCreate
//       body, photos are uploaded as INTAKE photos, then the Annahmeschein
//       step shows the repair number and "Zur Reparatur" hands back the id.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithQuery } from '../../test/queryWrapper';

const mockSearch = vi.fn();
const mockCreateCustomer = vi.fn();
vi.mock('../../api/customers', () => ({
  customersApi: {
    search: (...a: unknown[]) => mockSearch(...a),
    create: (...a: unknown[]) => mockCreateCustomer(...a),
  },
}));

const mockCreateRepair = vi.fn();
const mockUploadPhoto = vi.fn();
const mockGetPdf = vi.fn();
vi.mock('../../api/repairs', () => ({
  repairsApi: {
    create: (...a: unknown[]) => mockCreateRepair(...a),
    uploadPhoto: (...a: unknown[]) => mockUploadPhoto(...a),
    getAnnahmescheinPdf: (...a: unknown[]) => mockGetPdf(...a),
  },
}));

const mockShowToast = vi.fn();
const mockShowConfirm = vi.fn();
const mockRole = vi.fn(() => 'GOLDSMITH');
vi.mock('../../contexts', () => ({
  useAuth: () => ({ user: { role: mockRole() } }),
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: mockShowConfirm }),
}));

import { RepairIntakeScreen } from './RepairIntakeScreen';

const MARIA = {
  id: 7,
  first_name: 'Maria',
  last_name: 'Mustermann',
  email: null,
  phone: '+49 89 123456',
  customer_type: 'private',
  is_active: true,
  created_at: '2026-09-01T00:00:00Z',
};

const CREATED_REPAIR = {
  id: 42,
  repair_number: 'REP-2026-0042',
  bag_number: 'TU-2026-0042',
  item_description: 'Ehering',
  item_type: 'ring',
  status: 'received',
  is_deleted: false,
  created_at: '2026-09-25T10:00:00Z',
  updated_at: '2026-09-25T10:00:00Z',
  photos: [],
};

function renderScreen(props: { initialCustomerId?: number } = {}) {
  const onClose = vi.fn();
  const onDone = vi.fn();
  renderWithQuery(<RepairIntakeScreen onClose={onClose} onDone={onDone} {...props} />, {
    route: null,
  });
  return { onClose, onDone };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-09-25T09:00:00'));
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
  mockRole.mockReturnValue('GOLDSMITH');
});

describe('RepairIntakeScreen', () => {
  it('blocks submit and names the missing required fields', async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.click(screen.getByRole('button', { name: 'Reparatur annehmen' }));

    expect(mockCreateRepair).not.toHaveBeenCalled();
    expect(
      screen.getByText('Kundin oder Kunde fehlt. Bitte suchen oder neu anlegen.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Beschreibung fehlt. Bitte das Stück kurz beschreiben.'),
    ).toBeInTheDocument();
  });

  it('rejects a price indication that is not a number', async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.type(screen.getByLabelText(/Preisindikation/), 'abc');
    await user.click(screen.getByRole('button', { name: 'Reparatur annehmen' }));

    expect(
      screen.getByText('Preis ungültig. Bitte als Zahl eingeben, z. B. 45,00.'),
    ).toBeInTheDocument();
    expect(mockCreateRepair).not.toHaveBeenCalled();
  });

  it('quick-creates a walk-in customer with name and phone', async () => {
    const user = userEvent.setup();
    mockCreateCustomer.mockResolvedValue({ ...MARIA, id: 9, first_name: 'Paul', last_name: 'Neu' });
    renderScreen();

    await user.click(screen.getByRole('button', { name: 'Neuer Kunde' }));
    await user.type(screen.getByLabelText('Vorname'), 'Paul');
    await user.type(screen.getByLabelText('Nachname'), 'Neu');
    await user.type(screen.getByLabelText('Telefon'), '0171 555');
    await user.click(screen.getByRole('button', { name: 'Kunde anlegen' }));

    expect(mockCreateCustomer).toHaveBeenCalledWith({
      first_name: 'Paul',
      last_name: 'Neu',
      phone: '0171 555',
    });
    expect(await screen.findByText('Paul Neu')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Andere Kundin oder anderen Kunden wählen' }))
      .toBeInTheDocument();
  });

  it('quick-create needs a phone number', async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.click(screen.getByRole('button', { name: 'Neuer Kunde' }));
    await user.type(screen.getByLabelText('Vorname'), 'Paul');
    await user.type(screen.getByLabelText('Nachname'), 'Neu');
    await user.click(screen.getByRole('button', { name: 'Kunde anlegen' }));

    expect(mockCreateCustomer).not.toHaveBeenCalled();
    expect(screen.getByText('Telefon fehlt. Bitte eine Rückrufnummer eingeben.'))
      .toBeInTheDocument();
  });

  it('sends the intake payload, uploads photos and shows the Annahmeschein step', async () => {
    const user = userEvent.setup();
    mockSearch.mockResolvedValue([MARIA]);
    mockCreateRepair.mockResolvedValue(CREATED_REPAIR);
    mockUploadPhoto.mockResolvedValue({ id: 1 });
    const { onDone } = renderScreen();

    await user.type(screen.getByLabelText('Kundin oder Kunde suchen'), 'Mus');
    await user.click(await screen.findByRole('button', { name: /Maria Mustermann/ }));

    const typeGroup = screen.getByRole('group', { name: 'Art des Stücks' });
    await user.click(within(typeGroup).getByRole('button', { name: 'Kette' }));
    await user.click(screen.getByRole('button', { name: '585 Gelbgold' }));
    await user.type(screen.getByLabelText(/Beschreibung des Stücks/), 'Panzerkette 45 cm');

    const photo = new File(['x'], 'kette.jpg', { type: 'image/jpeg' });
    await user.upload(screen.getByLabelText('Foto aufnehmen'), photo);

    const condition = screen.getByRole('group', { name: 'Zustand bei Annahme' });
    await user.click(within(condition).getByRole('button', { name: 'Kratzer' }));
    await user.click(within(condition).getByRole('button', { name: 'Tragespuren' }));

    const problems = screen.getByRole('group', { name: 'Häufige Anliegen' });
    await user.click(within(problems).getByRole('button', { name: 'Kette gerissen' }));

    await user.type(screen.getByLabelText(/Preisindikation/), '45,50');
    await user.click(screen.getByRole('button', { name: 'In 1 Woche' }));

    await user.click(screen.getByRole('button', { name: 'Reparatur annehmen' }));

    await waitFor(() => expect(mockCreateRepair).toHaveBeenCalledTimes(1));
    expect(mockCreateRepair).toHaveBeenCalledWith({
      customer_id: 7,
      item_type: 'chain',
      item_description: 'Panzerkette 45 cm',
      metal_type: '585 Gelbgold',
      condition_notes: ['Kratzer', 'Tragespuren'],
      customer_problem: 'Kette gerissen',
      estimated_cost: 45.5,
      estimated_completion_date: '2026-10-02T00:00:00.000Z',
    });
    await waitFor(() =>
      expect(mockUploadPhoto).toHaveBeenCalledWith(42, photo, 'intake'),
    );

    expect(await screen.findByRole('heading', { name: 'Reparatur angenommen' }))
      .toBeInTheDocument();
    expect(screen.getByText('REP-2026-0042 · Tüte TU-2026-0042')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Annahmeschein drucken' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Zur Reparatur' }));
    expect(onDone).toHaveBeenCalledWith(42);
  });

  it('keeps the created repair when a photo upload fails and says so', async () => {
    const user = userEvent.setup();
    mockSearch.mockResolvedValue([MARIA]);
    mockCreateRepair.mockResolvedValue(CREATED_REPAIR);
    mockUploadPhoto.mockRejectedValue(new Error('network'));
    renderScreen();

    await user.type(screen.getByLabelText('Kundin oder Kunde suchen'), 'Mus');
    await user.click(await screen.findByRole('button', { name: /Maria Mustermann/ }));
    await user.type(screen.getByLabelText(/Beschreibung des Stücks/), 'Ring');
    await user.upload(
      screen.getByLabelText('Foto aufnehmen'),
      new File(['x'], 'a.jpg', { type: 'image/jpeg' }),
    );
    await user.click(screen.getByRole('button', { name: 'Reparatur annehmen' }));

    expect(await screen.findByRole('heading', { name: 'Reparatur angenommen' }))
      .toBeInTheDocument();
    expect(mockShowToast).toHaveBeenCalledWith(
      '1 Foto konnte nicht hochgeladen werden. Bitte in der Reparatur erneut aufnehmen.',
      'error',
    );
  });
});

describe('RepairIntakeScreen — form (react-hook-form + zod)', () => {
  it('moves focus to the first invalid field on submit', async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.click(screen.getByRole('button', { name: 'Reparatur annehmen' }));

    expect(screen.getByLabelText('Kundin oder Kunde suchen')).toHaveFocus();
    expect(screen.getByLabelText(/Beschreibung des Stücks/)).toHaveAttribute('aria-invalid', 'true');
  });

  it('clears an error as soon as the field is fixed after a failed submit', async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.click(screen.getByRole('button', { name: 'Reparatur annehmen' }));
    const message = 'Beschreibung fehlt. Bitte das Stück kurz beschreiben.';
    expect(screen.getByText(message)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Beschreibung des Stücks/), 'Ring');
    await waitFor(() => expect(screen.queryByText(message)).not.toBeInTheDocument());
  });

  it('closes at once while nothing is entered', async () => {
    const user = userEvent.setup();
    const { onClose } = renderScreen();

    await user.keyboard('{Escape}');

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(mockShowConfirm).not.toHaveBeenCalled();
  });

  it('asks "Änderungen verwerfen?" before a dirty form closes on Escape', async () => {
    const user = userEvent.setup();
    const { onClose } = renderScreen();

    await user.type(screen.getByLabelText(/Beschreibung des Stücks/), 'Ring');
    await user.keyboard('{Escape}');

    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText('Änderungen verwerfen?')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Weiter bearbeiten' }));
    expect(screen.getByLabelText(/Beschreibung des Stücks/)).toHaveValue('Ring');

    await user.keyboard('{Escape}');
    await user.click(screen.getByRole('button', { name: 'Verwerfen' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('treats a picked chip as input, and "Abbrechen" asks before discarding it', async () => {
    const user = userEvent.setup();
    mockShowConfirm.mockResolvedValue(false);
    const { onClose } = renderScreen();

    const typeGroup = screen.getByRole('group', { name: 'Art des Stücks' });
    await user.click(within(typeGroup).getByRole('button', { name: 'Kette' }));
    await user.click(screen.getByRole('button', { name: 'Abbrechen' }));

    expect(mockShowConfirm).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Annahme verwerfen?' }),
    );
    expect(onClose).not.toHaveBeenCalled();
  });

  it('never closes on a backdrop click', async () => {
    const user = userEvent.setup();
    const { onClose } = renderScreen();

    await user.click(screen.getByTestId('ui-modal-backdrop'));

    expect(onClose).not.toHaveBeenCalled();
  });

  it('shows no price field to a VIEWER (FINANCIAL_VIEW) and sends no price', async () => {
    mockRole.mockReturnValue('VIEWER');
    renderScreen();

    expect(screen.queryByLabelText(/Preisindikation/)).not.toBeInTheDocument();
  });
});
