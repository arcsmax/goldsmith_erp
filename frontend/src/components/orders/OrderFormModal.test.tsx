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
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
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

vi.mock('./GemstoneRepeater', () => ({
  GemstoneRepeater: (props: { orderId: number }) => (
    <div data-testid="gemstone-repeater">Steine für Auftrag {props.orderId}</div>
  ),
}));

import { OrderFormModal } from './OrderFormModal';

const customers = [
  { id: 7, first_name: 'Anna', last_name: 'Muster', company_name: null } as any,
];

beforeEach(() => {
  vi.clearAllMocks();
  mockGetAllCustomers.mockResolvedValue(customers);
});

describe('OrderFormModal — NoGoWarning integration', () => {
  it('passes customerId=null and empty candidates on an empty new-order form', async () => {
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} />);
    await screen.findByLabelText('Bezeichnung *');

    const calls = mockNoGoWarning.mock.calls;
    const lastCall = calls[calls.length - 1]?.[0];
    expect(lastCall).toEqual({ customerId: null, candidates: [] });
  });

  it('still renders the existing Basisinformationen tab fields unchanged', async () => {
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} />);
    await screen.findByLabelText('Bezeichnung *');

    expect(screen.getByLabelText('Beschreibung *')).toBeInTheDocument();
    expect(screen.getByLabelText('Kunde *')).toBeInTheDocument();
    expect(screen.getByLabelText('Abgabetermin *')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Erstellen' })).toBeInTheDocument();
  });

  it('derives candidates from alloy label, surface finish label, and description; customerId from the selected customer', async () => {
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} />);
    await screen.findByLabelText('Bezeichnung *');
    // The modal autofocuses the title field 30ms after mount (see
    // firstInputRef effect). Let that fire before typing elsewhere so it
    // can't steal focus mid-keystroke and truncate the description.
    await new Promise((resolve) => setTimeout(resolve, 50));

    await userEvent.type(screen.getByLabelText('Beschreibung *'), 'mit Opal-Stein');
    await screen.findByRole('option', { name: /Anna Muster/ });
    await userEvent.selectOptions(screen.getByLabelText('Kunde *'), '7');

    await userEvent.click(screen.getByRole('button', { name: /^Auftrag/ }));
    await userEvent.selectOptions(screen.getByLabelText('Legierung & Farbe *'), 'ag925');

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
  await userEvent.click(screen.getByRole('button', { name: /^Auftrag/ }));
}

async function fillBasics(title: string, orderType: string) {
  await screen.findByLabelText('Bezeichnung *');
  await new Promise((resolve) => setTimeout(resolve, 50));
  await userEvent.type(screen.getByLabelText('Bezeichnung *'), title);
  await userEvent.type(screen.getByLabelText('Beschreibung *'), 'Beschreibung');
  await screen.findByRole('option', { name: /Anna Muster/ });
  await userEvent.selectOptions(screen.getByLabelText('Kunde *'), '7');
  await userEvent.type(screen.getByLabelText('Abgabetermin *'), '2030-01-15');
  await userEvent.selectOptions(screen.getByLabelText('Schmuckart'), orderType);
}

describe('OrderFormModal — W2-06 intake', () => {
  it('does not demand a ring size for "Ohrring" (earrings), but does for order type ring', async () => {
    render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} />);
    await fillBasics('Ohrring mit Perle', 'earrings');
    await openAuftragTab();
    expect(screen.queryByLabelText(/Ringmaß/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Basisinformationen' }));
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
    await userEvent.selectOptions(screen.getByLabelText('Legierung & Farbe *'), '750-weiss');

    await userEvent.click(screen.getByRole('button', { name: 'Metall' }));
    expect(screen.queryByLabelText('Metallart *')).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Geschätztes Gewicht/), '4.5');

    // jsdom flags the Metall tab number inputs as step mismatches (float
    // rounding), which blocks a native submit; submit from the first tab.
    await userEvent.click(screen.getByRole('button', { name: 'Basisinformationen' }));
    await userEvent.click(screen.getByRole('button', { name: 'Erstellen' }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.metal_type).toBe('white_gold_18k');
    expect(payload.alloy).toBe('750');
    expect(payload.order_type).toBe('pendant');
  });

  it('shows the gemstone repeater when editing an existing order and a hint on a new one', async () => {
    const { unmount } = render(<OrderFormModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} />);
    await screen.findByLabelText('Bezeichnung *');
    await openAuftragTab();
    expect(screen.queryByTestId('gemstone-repeater')).not.toBeInTheDocument();
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
    await screen.findByLabelText('Bezeichnung *');
    expect((screen.getByLabelText('Schmuckart') as HTMLSelectElement).value).toBe('ring');
    await openAuftragTab();
    expect(screen.getByTestId('gemstone-repeater')).toHaveTextContent('Steine für Auftrag 42');
    expect((screen.getByLabelText('Legierung & Farbe *') as HTMLSelectElement).value).toBe('585-gelb');
  });
});
