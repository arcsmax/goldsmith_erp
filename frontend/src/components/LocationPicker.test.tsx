// LocationPicker (W8): Standort dropdown fed by GET /locations?active=true.
//
// Pins:
//   (a) options come from the query, in API order.
//   (b) a stored deactivated / legacy value stays visible and selected.
//   (c) ADMIN sees "Standort hinzufügen"; creating selects the new location.
//   (d) other roles get no quick-add.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockGetActive = vi.fn();
const mockCreate = vi.fn();
const mockAuth = { isAdmin: false };

vi.mock('../lib/logError', () => ({ logError: vi.fn() }));
vi.mock('../contexts/AuthContext', () => ({ useOptionalAuth: () => mockAuth }));
vi.mock('../api/locations', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/locations')>();
  return {
    ...actual,
    getActiveLocations: (...args: unknown[]) => mockGetActive(...args),
    createLocation: (...args: unknown[]) => mockCreate(...args),
  };
});

import { renderWithQuery } from '../test/queryWrapper';
import { LocationPicker } from './LocationPicker';

const loc = (id: number, name: string) => ({
  id,
  name,
  kind: 'bench' as const,
  is_active: true,
  sort_order: id * 10,
  created_at: '2026-09-25T10:00:00Z',
});

afterEach(() => {
  vi.clearAllMocks();
  mockAuth.isAdmin = false;
});

describe('LocationPicker', () => {
  it('renders the active locations from the query', async () => {
    mockGetActive.mockResolvedValue([loc(1, 'Werkbank 1'), loc(2, 'Tresor')]);
    renderWithQuery(<LocationPicker value={2} onChange={vi.fn()} />);

    expect(await screen.findByRole('option', { name: 'Tresor' })).toBeInTheDocument();
    const select = screen.getByLabelText('Standort') as HTMLSelectElement;
    const names = Array.from(select.options).map((o) => o.textContent);
    expect(names).toEqual(['Kein Standort', 'Werkbank 1', 'Tresor']);
    expect(select.value).toBe('2');
  });

  it('keeps a stored deactivated location visible', async () => {
    mockGetActive.mockResolvedValue([loc(1, 'Werkbank 1')]);
    renderWithQuery(<LocationPicker value={9} currentName="Alte Bank" onChange={vi.fn()} />);

    expect(await screen.findByRole('option', { name: 'Alte Bank (deaktiviert)' })).toBeInTheDocument();
    expect((screen.getByLabelText('Standort') as HTMLSelectElement).value).toBe('stored');
  });

  it('reports the chosen location', async () => {
    mockGetActive.mockResolvedValue([loc(1, 'Werkbank 1'), loc(2, 'Tresor')]);
    const onChange = vi.fn();
    renderWithQuery(<LocationPicker value={null} onChange={onChange} />);

    await screen.findByRole('option', { name: 'Tresor' });
    await userEvent.selectOptions(screen.getByLabelText('Standort'), '2');
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ id: 2, name: 'Tresor' }));
  });

  it('lets ADMIN add a location and selects it', async () => {
    mockAuth.isAdmin = true;
    mockGetActive.mockResolvedValue([loc(1, 'Werkbank 1')]);
    mockCreate.mockResolvedValue(loc(3, 'Polierbank'));
    const onChange = vi.fn();
    renderWithQuery(<LocationPicker value={null} onChange={onChange} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Standort hinzufügen' }));
    await userEvent.type(screen.getByLabelText('Neuer Standort'), 'Polierbank');
    await userEvent.click(screen.getByRole('button', { name: 'Standort speichern' }));

    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith({ name: 'Polierbank', kind: 'other' }),
    );
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ id: 3 })),
    );
  });

  it('hides the quick-add for non-admins', async () => {
    mockGetActive.mockResolvedValue([loc(1, 'Werkbank 1')]);
    renderWithQuery(<LocationPicker value={null} onChange={vi.fn()} />);

    await screen.findByRole('option', { name: 'Werkbank 1' });
    expect(screen.queryByRole('button', { name: 'Standort hinzufügen' })).not.toBeInTheDocument();
  });
});
