// OrderFormModal tests — Task 9 (V1.1 consultation frontend) integration
// slice only. No test file existed for this component before; scope here
// is deliberately narrow: prove the NoGoWarning embed is purely additive
// and derives its candidates correctly, not a full form-behavior suite.
//
// Pins:
//   (a) NoGoWarning receives customerId=null and candidates=[] before any
//       customer/material field is filled in (never calls the No-Go API
//       on an empty form).
//   (b) selecting a customer + metal type + alloy + surface finish +
//       typing a description feeds NoGoWarning the resolved human-readable
//       labels (not raw enum codes) plus the free-text description.
//   (c) the modal still opens/renders its existing tabs/fields unchanged.
//
// W3-06 (react-hook-form + zod, Field/Tabs/Modal primitives) adapted only the
// DOM: labels carry the visible "Pflichtfeld" marker instead of "*", tabs are
// role="tab", the submit button says "Auftrag anlegen" (verb + noun), and the
// form reads customers and stones through TanStack Query (renderWithQuery).
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import { renderWithQuery } from '../../test/queryWrapper';
import userEvent from '@testing-library/user-event';

const mockGetAllCustomers = vi.fn();
vi.mock('../../api', () => ({
  customersApi: {
    getAll: (...a: unknown[]) => mockGetAllCustomers(...a),
  },
}));

vi.mock('../../hooks/useMetalTypes', () => ({
  useMetalTypes: () => ({ metalTypes: [], isLoading: false }),
}));

const mockNoGoWarning = vi.fn();
vi.mock('../consultation/NoGoWarning', () => ({
  NoGoWarning: (props: { customerId: number | null; candidates: string[] }) => {
    mockNoGoWarning(props);
    return null;
  },
}));

const mockList = vi.fn();
const mockCreate = vi.fn();
const mockUpdate = vi.fn();
const mockRemove = vi.fn();
vi.mock('../../api/gemstones', () => ({
  gemstonesApi: {
    list: (...a: unknown[]) => mockList(...a),
    create: (...a: unknown[]) => mockCreate(...a),
    update: (...a: unknown[]) => mockUpdate(...a),
    remove: (...a: unknown[]) => mockRemove(...a),
  },
}));
vi.mock('../../lib/logError', () => ({ logError: vi.fn() }));

import React from 'react';
import { OrderFormModal } from './OrderFormModal';

const customers = [
  { id: 7, first_name: 'Anna', last_name: 'Muster', company_name: null } as any,
];

beforeEach(() => {
  vi.clearAllMocks();
  mockGetAllCustomers.mockResolvedValue(customers);
  mockList.mockResolvedValue([]);
});

const render = (ui: React.ReactElement) => renderWithQuery(ui, { route: null });

describe('OrderFormModal — NoGoWarning integration', () => {
  it('passes customerId=null and empty candidates on an empty new-order form', async () => {
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} />);
    await screen.findByLabelText(/^Bezeichnung/);

    const calls = mockNoGoWarning.mock.calls;
    const lastCall = calls[calls.length - 1]?.[0];
    expect(lastCall).toEqual({ customerId: null, candidates: [] });
  });

  it('still renders the existing Basisinformationen tab fields unchanged', async () => {
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} />);
    await screen.findByLabelText(/^Bezeichnung/);

    expect(screen.getByLabelText(/^Beschreibung/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Kunde/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Abgabetermin/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Auftrag anlegen' })).toBeInTheDocument();
  });

  it('derives candidates from alloy label, surface finish label, and description; customerId from the selected customer', async () => {
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} />);
    await screen.findByLabelText(/^Bezeichnung/);
    // The modal autofocuses the title field 30ms after mount (see
    // firstInputRef effect). Let that fire before typing elsewhere so it
    // can't steal focus mid-keystroke and truncate the description.
    await new Promise((resolve) => setTimeout(resolve, 50));

    await userEvent.type(screen.getByLabelText(/^Beschreibung/), 'mit Opal-Stein');
    await screen.findByRole('option', { name: /Anna Muster/ });
    await userEvent.selectOptions(screen.getByLabelText(/^Kunde/), '7');

    await userEvent.click(screen.getByRole('tab', { name: /^Auftrag/ }));
    await userEvent.selectOptions(screen.getByLabelText(/^Legierung & Farbe/), 'ag925');

    const calls = mockNoGoWarning.mock.calls;
    const lastCall = calls[calls.length - 1]?.[0];
    expect(lastCall.customerId).toBe(7);
    expect(lastCall.candidates).toContain('Silber 925 (Sterling)');
    expect(lastCall.candidates).toContain('mit Opal-Stein');
  });
});

// ---------------------------------------------------------------------------
// W2-06 (DOM-05, DOM-06, DOM-09, DOM-04): order type, one alloy picker, stones
// ---------------------------------------------------------------------------

async function openAuftragTab() {
  await userEvent.click(screen.getByRole('tab', { name: /^Auftrag/ }));
}

async function fillBasics(title: string, orderType: string) {
  await screen.findByLabelText(/^Bezeichnung/);
  await new Promise((resolve) => setTimeout(resolve, 50));
  await userEvent.type(screen.getByLabelText(/^Bezeichnung/), title);
  await userEvent.type(screen.getByLabelText(/^Beschreibung/), 'Beschreibung');
  await screen.findByRole('option', { name: /Anna Muster/ });
  await userEvent.selectOptions(screen.getByLabelText(/^Kunde/), '7');
  await userEvent.type(screen.getByLabelText(/^Abgabetermin/), '2030-01-15');
  await userEvent.selectOptions(screen.getByLabelText('Schmuckart'), orderType);
}

describe('OrderFormModal — W2-06 intake', () => {
  it('does not demand a ring size for "Ohrring" (earrings), but does for order type ring', async () => {
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} />);
    await fillBasics('Ohrring mit Perle', 'earrings');
    await openAuftragTab();
    expect(screen.queryByLabelText(/Ringmaß/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', { name: 'Basisinformationen' }));
    await userEvent.selectOptions(screen.getByLabelText('Schmuckart'), 'ring');
    await openAuftragTab();
    expect(screen.getByLabelText(/Ringmaß/)).toBeInTheDocument();
  });

  it('one "Legierung & Farbe" picker sets metal_type and alloy; order_type is saved', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={onSubmit} />);
    await fillBasics('Anhänger', 'pendant');
    await openAuftragTab();

    expect(screen.queryByLabelText('Legierung *')).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText(/^Legierung & Farbe/), '750-weiss');

    await userEvent.click(screen.getByRole('tab', { name: 'Metall' }));
    expect(screen.queryByLabelText('Metallart *')).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Geschätztes Gewicht/), '4.5');

    await userEvent.click(screen.getByRole('tab', { name: 'Basisinformationen' }));
    await userEvent.click(screen.getByRole('button', { name: 'Auftrag anlegen' }));

    await vi.waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.metal_type).toBe('white_gold_18k');
    expect(payload.alloy).toBe('750');
    expect(payload.order_type).toBe('pendant');
  });

  it('shows the gemstone repeater when editing an existing order and a hint on a new one', async () => {
    const { unmount } = render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} />);
    await screen.findByLabelText(/^Bezeichnung/);
    await openAuftragTab();
    expect(screen.queryByRole('region', { name: 'Steine' })).not.toBeInTheDocument();
    expect(screen.getByText(/Steine lassen sich nach dem Anlegen/)).toBeInTheDocument();
    unmount();

    const order = {
      id: 42,
      title: 'Ring',
      description: 'Solitär',
      customer_id: 7,
      deadline: '2030-01-15T00:00:00',
      status: 'confirmed',
      metal_type: 'gold_14k',
      alloy: '585',
      order_type: 'ring',
      created_at: '2026-09-01T00:00:00',
      updated_at: '2026-09-01T00:00:00',
    } as any;
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} order={order} />);
    await screen.findByLabelText(/^Bezeichnung/);
    expect((screen.getByLabelText('Schmuckart') as HTMLSelectElement).value).toBe('ring');
    await openAuftragTab();
    const stones = await screen.findByRole('region', { name: 'Steine' });
    expect(await within(stones).findByRole('button', { name: 'Stein hinzufügen' })).toBeInTheDocument();
    expect(mockList).toHaveBeenCalledWith(42);
    expect((screen.getByLabelText(/^Legierung & Farbe/) as HTMLSelectElement).value).toBe('585-gelb');
  });
});

// ---------------------------------------------------------------------------
// W3-06: zod validation and the gemstone field array
// ---------------------------------------------------------------------------

const savedOrder = {
  id: 42,
  title: 'Ring',
  description: 'Solitär',
  customer_id: 7,
  deadline: '2030-01-15T00:00:00',
  status: 'confirmed',
  metal_type: 'gold_14k',
  alloy: '585',
  estimated_weight_g: 3,
  order_type: 'ring',
  ring_size_mm: 54,
  created_at: '2026-09-01T00:00:00',
  updated_at: '2026-09-01T00:00:00',
} as any;

const diamond = {
  id: 11,
  order_id: 42,
  type: 'Diamant',
  quantity: 3,
  carat: 0.1,
  color: 'G',
  quality: 'VS1',
  shape: 'rund',
  setting_type: 'prong',
  is_customer_stone: false,
  cost: 120,
};

describe('OrderFormModal — validation (W3-06)', () => {
  it('shows German errors on the fields and does not submit an empty form', async () => {
    const onSubmit = vi.fn();
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={onSubmit} />);
    await screen.findByLabelText(/^Bezeichnung/);

    await userEvent.click(screen.getByRole('button', { name: 'Auftrag anlegen' }));

    expect(await screen.findByText('Mindestens 2 Zeichen erforderlich')).toBeInTheDocument();
    expect(screen.getByLabelText(/^Bezeichnung/)).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText(/^Kunde/)).toHaveAttribute('aria-invalid', 'true');
    expect(onSubmit).not.toHaveBeenCalled();
    await vi.waitFor(() => expect(screen.getByLabelText(/^Bezeichnung/)).toHaveFocus());
  });

  it('opens the Metall tab when the weight is missing for a chosen alloy', async () => {
    const onSubmit = vi.fn();
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={onSubmit} />);
    await fillBasics('Anhänger', 'pendant');
    await openAuftragTab();
    await userEvent.selectOptions(screen.getByLabelText(/^Legierung & Farbe/), '750-weiss');

    await userEvent.click(screen.getByRole('button', { name: 'Auftrag anlegen' }));

    expect(await screen.findByText('Gewicht ist erforderlich wenn eine Metallart ausgewählt ist')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Metall' })).toHaveAttribute('aria-selected', 'true');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('marks the form dirty so closing asks before discarding', async () => {
    const onClose = vi.fn();
    render(<OrderFormModal isOpen onClose={onClose} onSubmit={vi.fn()} />);
    await screen.findByLabelText(/^Bezeichnung/);
    await new Promise((resolve) => setTimeout(resolve, 50));
    await userEvent.type(screen.getByLabelText(/^Bezeichnung/), 'Ring');

    await userEvent.click(screen.getByRole('button', { name: 'Schließen' }));

    expect(await screen.findByText('Änderungen verwerfen?')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('OrderFormModal — gemstone field array (W3-06)', () => {
  it('loads the saved stones as rows and saves new, changed and removed stones with the order', async () => {
    mockList.mockResolvedValue([diamond, { ...diamond, id: 12, type: 'Saphir' }]);
    mockCreate.mockResolvedValue({ ...diamond, id: 13 });
    mockUpdate.mockResolvedValue(diamond);
    mockRemove.mockResolvedValue(undefined);
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={onSubmit} order={savedOrder} />);
    await screen.findByLabelText(/^Bezeichnung/);
    await openAuftragTab();

    expect(await screen.findByLabelText('Steinart (Stein 1)')).toHaveValue('Diamant');
    expect(screen.getByLabelText('Karat je Stein (Stein 1)')).toHaveValue('0,1');

    await userEvent.clear(screen.getByLabelText('Anzahl (Stein 1)'));
    await userEvent.type(screen.getByLabelText('Anzahl (Stein 1)'), '4');
    const second = screen.getByRole('group', { name: 'Stein 2' });
    await userEvent.click(within(second).getByRole('button', { name: 'Stein entfernen' }));
    await userEvent.click(screen.getByRole('button', { name: 'Stein hinzufügen' }));
    await userEvent.type(screen.getByLabelText('Steinart (Stein 2)'), 'Rubin');
    await userEvent.click(screen.getByLabelText('Kundenstein (Stein 2)'));
    expect(screen.queryByLabelText('Einkaufspreis je Stein (Stein 2)')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Auftrag speichern' }));

    await vi.waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(mockUpdate).toHaveBeenCalledWith(11, expect.objectContaining({ quantity: 4, type: 'Diamant' }));
    expect(mockRemove).toHaveBeenCalledWith(12);
    expect(mockCreate).toHaveBeenCalledWith(42, expect.objectContaining({ type: 'Rubin', is_customer_stone: true }));
    expect(mockCreate.mock.calls[0][1]).not.toHaveProperty('cost');
  });

  it('blocks the save when a stone has no Steinart or a bad Karat value', async () => {
    const onSubmit = vi.fn();
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={onSubmit} order={savedOrder} />);
    await screen.findByLabelText(/^Bezeichnung/);
    await openAuftragTab();
    await userEvent.click(await screen.findByRole('button', { name: 'Stein hinzufügen' }));
    await userEvent.type(screen.getByLabelText('Karat je Stein (Stein 1)'), 'viel');

    await userEvent.click(screen.getByRole('button', { name: 'Auftrag speichern' }));

    expect(await screen.findByText('Steinart fehlt. Bitte die Steinart eingeben.')).toBeInTheDocument();
    expect(screen.getByText('Karat bitte als Zahl eingeben, z. B. 0,25.')).toBeInTheDocument();
    expect(screen.getByLabelText('Steinart (Stein 1)')).toHaveAttribute('aria-invalid', 'true');
    expect(mockCreate).not.toHaveBeenCalled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('keeps the dialog open and says so when saving a stone fails', async () => {
    mockCreate.mockRejectedValue(new Error('offline'));
    const onSubmit = vi.fn();
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={onSubmit} order={savedOrder} />);
    await screen.findByLabelText(/^Bezeichnung/);
    await openAuftragTab();
    await userEvent.click(await screen.findByRole('button', { name: 'Stein hinzufügen' }));
    await userEvent.type(screen.getByLabelText('Steinart (Stein 1)'), 'Perle');

    await userEvent.click(screen.getByRole('button', { name: 'Auftrag speichern' }));

    expect(await screen.findByText(/Steine konnten nicht gespeichert werden/)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
