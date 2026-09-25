// RepairsPage — counter intake wiring (W2-12, FE-17).
//
// Pins: "Neue Reparatur" opens the intake screen; `?neu=1&customer_id=`
// (the customer page's link) opens it with that customer; finishing the
// intake navigates to the new repair; the KVA column is gated by role.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { renderWithQuery } from '../test/queryWrapper';

const mockGetPage = vi.fn();
vi.mock('../api/repairs', () => ({
  repairsApi: { getPage: (...a: unknown[]) => mockGetPage(...a) },
}));

/** The Page envelope GET /repairs/?offset=… answers with. */
function page(items: unknown[]) {
  return { items, total: items.length, limit: 25, offset: 0, next_offset: null };
}

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
  return renderWithQuery(
    <Routes>
      <Route path="/repairs" element={<RepairsPage />} />
      <Route path="/repairs/:id" element={<p>Detail der Reparatur</p>} />
    </Routes>,
    { route: path },
  );
}

afterEach(() => vi.clearAllMocks());

describe('RepairsPage intake', () => {
  it('opens the intake from "Neue Reparatur" and goes to the new repair when done', async () => {
    const user = userEvent.setup();
    mockGetPage.mockResolvedValue(page([]));
    renderAt('/repairs');

    await user.click(screen.getByRole('button', { name: 'Neue Reparatur' }));
    expect(screen.getByRole('dialog', { name: 'Neue Reparatur' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Zur Reparatur' }));
    expect(await screen.findByText('Detail der Reparatur')).toBeInTheDocument();
  });

  it('opens the intake with the customer from the link', async () => {
    mockGetPage.mockResolvedValue(page([]));
    renderAt('/repairs?neu=1&customer_id=11');

    expect(screen.getByText('Kunde vorgewählt: 11')).toBeInTheDocument();
  });

  it('links rows to the repair and shows the KVA for goldsmiths', async () => {
    mockGetPage.mockResolvedValue(page([ROW]));
    renderAt('/repairs');

    const table = await screen.findByRole('table', { name: 'Reparaturen' });
    const link = within(table).getByRole('link', { name: 'REP-2026-0003' });
    expect(link).toHaveAttribute('href', '/repairs/3');
    expect(within(table).getByRole('columnheader', { name: 'KVA' })).toBeInTheDocument();
    expect(within(table).getByText('45,00 €')).toBeInTheDocument();
  });

  it('hides the KVA column for viewers', async () => {
    mockRole.mockReturnValue('VIEWER');
    mockGetPage.mockResolvedValue(page([ROW]));
    renderAt('/repairs');

    await screen.findByRole('table', { name: 'Reparaturen' });
    expect(screen.queryByRole('columnheader', { name: 'KVA' })).not.toBeInTheDocument();
    expect(screen.queryByText('45,00 €')).not.toBeInTheDocument();
  });

  it('hides "Neue Reparatur" for viewers (REPAIR_CREATE is ADMIN + GOLDSMITH only)', async () => {
    mockRole.mockReturnValue('VIEWER');
    mockGetPage.mockResolvedValue(page([]));
    renderAt('/repairs');

    await screen.findByText('Keine Reparaturen gefunden');
    expect(screen.queryByRole('button', { name: 'Neue Reparatur' })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Neue Reparatur annehmen' }),
    ).not.toBeInTheDocument();
  });

  it('shows "Neue Reparatur" for goldsmiths and admins', async () => {
    mockRole.mockReturnValue('GOLDSMITH');
    mockGetPage.mockResolvedValue(page([]));
    renderAt('/repairs');
    expect(await screen.findByRole('button', { name: 'Neue Reparatur' })).toBeInTheDocument();

    mockRole.mockReturnValue('ADMIN');
    renderAt('/repairs');
    expect(await screen.findAllByRole('button', { name: 'Neue Reparatur' })).not.toHaveLength(0);
  });

  it('asks the server for one page with the status filter from the URL', async () => {
    mockGetPage.mockResolvedValue(page([]));
    renderAt('/repairs?status=ready');

    await screen.findByText('Keine Reparaturen gefunden');
    expect(mockGetPage).toHaveBeenCalledWith(
      { limit: 25, offset: 0, status: 'ready' },
      expect.anything(),
    );
    expect(screen.getByRole('button', { name: 'Filter zurücksetzen' })).toBeInTheDocument();
  });

  it('shows the error with a retry when the list fails', async () => {
    const user = userEvent.setup();
    mockGetPage.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(page([ROW]));
    renderAt('/repairs');

    await user.click(await screen.findByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByRole('table', { name: 'Reparaturen' })).toBeInTheDocument();
  });
});
