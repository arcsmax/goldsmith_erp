// LocationsPanel (W8) — Standorte in the Systemübersicht.
//
// Backend contract (tests/integration/test_locations_api.py):
// GET/POST /admin/locations, PATCH/DELETE /admin/locations/{id}.
//
// Pins:
//   (a) lists every location incl. deactivated ones with a status text.
//   (b) "Standort hinzufügen" posts name + kind.
//   (c) moving a row down swaps the sort orders.
//   (d) deactivating asks first, then calls DELETE.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockGetAll = vi.fn();
const mockCreate = vi.fn();
const mockUpdate = vi.fn();
const mockDeactivate = vi.fn();
const mockShowConfirm = vi.fn();

vi.mock('../../lib/logError', () => ({ logError: vi.fn() }));
vi.mock('../../contexts/ToastContext', () => ({
  useConfirm: () => ({ showConfirm: mockShowConfirm }),
}));
vi.mock('../../api/locations', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/locations')>();
  return {
    ...actual,
    getAllLocations: (...args: unknown[]) => mockGetAll(...args),
    createLocation: (...args: unknown[]) => mockCreate(...args),
    updateLocation: (...args: unknown[]) => mockUpdate(...args),
    deactivateLocation: (...args: unknown[]) => mockDeactivate(...args),
  };
});

import { renderWithQuery } from '../../test/queryWrapper';
import { LocationsPanel, reorderPatches } from './LocationsPanel';

const loc = (id: number, name: string, sort: number, isActive = true) => ({
  id,
  name,
  kind: 'bench' as const,
  is_active: isActive,
  sort_order: sort,
  created_at: '2026-09-25T10:00:00Z',
});

const ROWS = [loc(1, 'Werkbank 1', 10), loc(2, 'Tresor', 20), loc(3, 'Alte Bank', 30, false)];

afterEach(() => {
  vi.clearAllMocks();
});

describe('LocationsPanel', () => {
  it('lists active and deactivated locations', async () => {
    mockGetAll.mockResolvedValue(ROWS);
    renderWithQuery(<LocationsPanel />);

    expect((await screen.findAllByText('Werkbank 1')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Deaktiviert').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: 'Standort aktivieren' }).length).toBeGreaterThan(0);
  });

  it('adds a location with name and kind', async () => {
    mockGetAll.mockResolvedValue([]);
    mockCreate.mockResolvedValue(loc(4, 'Vitrine', 40));
    renderWithQuery(<LocationsPanel />);

    await screen.findByText('Noch keine Standorte');
    await userEvent.type(screen.getByLabelText(/^Name/), 'Vitrine');
    await userEvent.selectOptions(screen.getByLabelText('Art'), 'showroom');
    await userEvent.click(screen.getByRole('button', { name: 'Standort hinzufügen' }));

    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith({ name: 'Vitrine', kind: 'showroom' }),
    );
  });

  it('moves a location down by swapping sort orders', async () => {
    mockGetAll.mockResolvedValue(ROWS);
    mockUpdate.mockResolvedValue(ROWS[0]);
    renderWithQuery(<LocationsPanel />);

    const [down] = await screen.findAllByRole('button', { name: 'Werkbank 1 nach unten' });
    await userEvent.click(down);

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(2));
    expect(mockUpdate).toHaveBeenCalledWith(2, { sort_order: 10 });
    expect(mockUpdate).toHaveBeenCalledWith(1, { sort_order: 20 });
  });

  it('asks before deactivating', async () => {
    mockGetAll.mockResolvedValue(ROWS);
    mockShowConfirm.mockResolvedValue(true);
    mockDeactivate.mockResolvedValue({ ...ROWS[1], is_active: false });
    renderWithQuery(<LocationsPanel />);

    const buttons = await screen.findAllByRole('button', { name: 'Standort deaktivieren' });
    await userEvent.click(buttons[0]);

    await waitFor(() => expect(mockDeactivate).toHaveBeenCalledWith(1));
    expect(mockShowConfirm).toHaveBeenCalledWith(expect.objectContaining({ variant: 'danger' }));
  });
});

describe('reorderPatches', () => {
  it('returns nothing at the edges', () => {
    expect(reorderPatches(ROWS, 0, -1)).toEqual([]);
    expect(reorderPatches(ROWS, 2, 1)).toEqual([]);
  });

  it('normalises equal sort orders', () => {
    const rows = [loc(1, 'A', 0), loc(2, 'B', 0)];
    expect(reorderPatches(rows, 0, 1)).toEqual([
      { id: 2, data: { sort_order: 10 } },
      { id: 1, data: { sort_order: 20 } },
    ]);
  });
});
