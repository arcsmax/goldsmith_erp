// GemstoneRepeater (W2-06, DOM-04): stones on the order form and Übersicht.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

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

const mockShowToast = vi.fn();
const mockShowConfirm = vi.fn();
vi.mock('../../contexts', () => ({
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: mockShowConfirm }),
}));

import { GemstoneRepeater } from './GemstoneRepeater';

const diamond = {
  id: 11,
  order_id: 5,
  type: 'Diamant',
  quantity: 3,
  carat: 0.1,
  color: 'G',
  quality: 'VS1',
  shape: 'rund',
  setting_type: 'prong',
  is_customer_stone: false,
  cost: 120,
  total_cost: 360,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockList.mockResolvedValue([diamond]);
  mockShowConfirm.mockResolvedValue(true);
});

describe('GemstoneRepeater', () => {
  it('loads the stones of the order and shows the Fassungsart dropdown with German labels', async () => {
    render(<GemstoneRepeater orderId={5} canEdit canViewCost />);

    const select = await screen.findByLabelText('Fassungsart (Stein 1)');
    expect(mockList).toHaveBeenCalledWith(5);
    expect((select as HTMLSelectElement).value).toBe('prong');
    const labels = within(select).getAllByRole('option').map((o) => o.textContent);
    expect(labels).toEqual([
      '— keine Angabe —',
      'Zargenfassung',
      'Krappenfassung',
      'Kanalfassung',
      'Pavé',
      'Spannfassung',
      'Unsichtbare Fassung',
    ]);
  });

  it('adds a new stone row and saves it with the chosen Fassungsart and Kundenstein flag', async () => {
    mockList.mockResolvedValue([]);
    mockCreate.mockResolvedValue({ ...diamond, id: 12, type: 'Rubin', setting_type: 'bezel' });
    render(<GemstoneRepeater orderId={5} canEdit canViewCost />);

    await userEvent.click(await screen.findByRole('button', { name: 'Stein hinzufügen' }));
    await userEvent.type(screen.getByLabelText('Steinart (Stein 1)'), 'Rubin');
    await userEvent.selectOptions(screen.getByLabelText('Fassungsart (Stein 1)'), 'bezel');
    await userEvent.click(screen.getByLabelText('Kundenstein (Stein 1)'));
    await userEvent.click(screen.getByRole('button', { name: 'Stein speichern' }));

    expect(mockCreate).toHaveBeenCalledWith(
      5,
      expect.objectContaining({
        type: 'Rubin',
        quantity: 1,
        setting_type: 'bezel',
        is_customer_stone: true,
      })
    );
    // A Kundenstein never sends a purchase price.
    expect(mockCreate.mock.calls[0][1]).not.toHaveProperty('cost');
    expect(mockShowToast).toHaveBeenCalledWith('Stein gespeichert', 'success');
  });

  it('asks before removing a saved stone', async () => {
    mockRemove.mockResolvedValue(undefined);
    render(<GemstoneRepeater orderId={5} canEdit canViewCost />);

    await userEvent.click(await screen.findByRole('button', { name: 'Stein entfernen' }));
    expect(mockShowConfirm).toHaveBeenCalledWith(expect.objectContaining({ variant: 'danger' }));
    expect(mockRemove).toHaveBeenCalledWith(11);
  });

  it('is read-only without edit rights and hides the cost', async () => {
    render(<GemstoneRepeater orderId={5} canEdit={false} canViewCost={false} />);

    expect(await screen.findByText('3 × Diamant 0,10 ct G/VS1, rund, Krappenfassung')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Stein hinzufügen' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Einkaufspreis/)).not.toBeInTheDocument();
  });

  it('shows an empty state with an action when the order has no stones', async () => {
    mockList.mockResolvedValue([]);
    render(<GemstoneRepeater orderId={5} canEdit canViewCost />);

    expect(await screen.findByText('Noch keine Steine erfasst.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stein hinzufügen' })).toBeInTheDocument();
  });
});
