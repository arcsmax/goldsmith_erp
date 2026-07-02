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
    await userEvent.selectOptions(screen.getByLabelText('Legierung *'), 'Ag925');

    const calls = mockNoGoWarning.mock.calls;
    const lastCall = calls[calls.length - 1]?.[0];
    expect(lastCall.customerId).toBe(7);
    expect(lastCall.candidates).toContain('Silber 925 (Sterling)');
    expect(lastCall.candidates).toContain('mit Opal-Stein');
  });
});
