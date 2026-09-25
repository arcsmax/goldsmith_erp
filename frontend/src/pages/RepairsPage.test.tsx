// RepairsPage — counter intake wiring (W2-12, FE-17).
//
// Pins: "Neue Reparatur" opens the intake screen; `?neu=1&customer_id=`
// (the customer page's link) opens it with that customer; finishing the
// intake navigates to the new repair; the KVA column is gated by role.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockGetAll = vi.fn();
vi.mock('../api/repairs', () => ({
  repairsApi: { getAll: (...a: unknown[]) => mockGetAll(...a) },
}));

const mockRole = vi.fn(() => 'GOLDSMITH');
vi.mock('../contexts', () => ({
  useAuth: () => ({ user: { role: mockRole() } }),
}));

vi.mock('../components/repairs/RepairIntakeScreen', () => ({
  RepairIntakeScreen: ({
    onDone,
    initialCustomerId,
  }: {
    onDone: (id: number) => void;
    initialCustomerId?: number;
  }) => (
    <div role="dialog" aria-label="Neue Reparatur">
      <span>Kunde vorgewählt: {initialCustomerId ?? 'keiner'}</span>
      <button type="button" onClick={() => onDone(42)}>
        Zur Reparatur
      </button>
    </div>
  ),
}));

import { RepairsPage } from './RepairsPage';

const ROW = {
  id: 3,
  repair_number: 'REP-2026-0003',
  bag_number: 'TU-2026-0003',
  item_description: 'Ring',
  item_type: 'ring',
  status: 'received',
  estimated_cost: 45,
  created_at: '2026-09-25T10:00:00Z',
  updated_at: '2026-09-25T10:00:00Z',
};

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/repairs" element={<RepairsPage />} />
        <Route path="/repairs/:id" element={<p>Detail der Reparatur</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe('RepairsPage intake', () => {
  it('opens the intake from "Neue Reparatur" and goes to the new repair when done', async () => {
    const user = userEvent.setup();
    mockGetAll.mockResolvedValue([]);
    renderAt('/repairs');

    await user.click(screen.getByRole('button', { name: 'Neue Reparatur' }));
    expect(screen.getByRole('dialog', { name: 'Neue Reparatur' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Zur Reparatur' }));
    expect(await screen.findByText('Detail der Reparatur')).toBeInTheDocument();
  });

  it('opens the intake with the customer from the link', async () => {
    mockGetAll.mockResolvedValue([]);
    renderAt('/repairs?neu=1&customer_id=11');

    expect(screen.getByText('Kunde vorgewählt: 11')).toBeInTheDocument();
  });

  it('links rows to the repair and shows the KVA for goldsmiths', async () => {
    mockGetAll.mockResolvedValue([ROW]);
    renderAt('/repairs');

    const link = await screen.findByRole('link', { name: 'REP-2026-0003' });
    expect(link).toHaveAttribute('href', '/repairs/3');
    expect(screen.getByRole('columnheader', { name: 'KVA' })).toBeInTheDocument();
    expect(screen.getByText('45,00 €')).toBeInTheDocument();
  });

  it('hides the KVA column for viewers', async () => {
    mockRole.mockReturnValue('VIEWER');
    mockGetAll.mockResolvedValue([ROW]);
    renderAt('/repairs');

    await screen.findByRole('link', { name: 'REP-2026-0003' });
    expect(screen.queryByRole('columnheader', { name: 'KVA' })).not.toBeInTheDocument();
  });
});
