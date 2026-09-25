// UsersPage on TanStack Query (W4-03): list via useQuery, deactivate via
// useMutation with ['users'] invalidation.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithQuery } from '../test/queryWrapper';

const mockGet = vi.fn();
const mockDelete = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...a: unknown[]) => mockGet(...a),
    delete: (...a: unknown[]) => mockDelete(...a),
  },
}));

const mockShowConfirm = vi.fn();
const mockShowToast = vi.fn();
vi.mock('../contexts', () => ({
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: mockShowConfirm }),
}));

import { UsersPage } from './UsersPage';

function user(id: number, isActive = true) {
  return {
    id,
    email: `nutzer${id}@example.test`,
    first_name: 'Demo',
    last_name: `Nutzer${id}`,
    role: 'GOLDSMITH',
    is_active: isActive,
    created_at: '2026-09-01T10:00:00Z',
  };
}

function userListCalls() {
  return mockGet.mock.calls.filter(([url]) => url === '/users/');
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('UsersPage (query)', () => {
  it('renders the users with the active count in the header', async () => {
    mockGet.mockResolvedValue({ data: [user(1), user(2, false)] });
    renderWithQuery(<UsersPage />);

    expect(await screen.findAllByText('nutzer1@example.test')).not.toHaveLength(0);
    expect(screen.getByText('2 Benutzer · 1 aktiv')).toBeInTheDocument();
    expect(screen.getAllByText('Goldschmied').length).toBeGreaterThan(0);

    // W7 hygiene: the account status is a <StatusBadge kind="user">, not
    // the old bespoke `.users-active-state` span — icon + German label,
    // never colour alone (CLAUDE.md UI rules). DataTable renders a table
    // row and a responsive card per user, so each label appears twice.
    for (const badge of screen.getAllByText('Aktiv')) {
      expect(badge.closest('[data-kind="user"]')).toHaveAttribute('data-status', 'active');
    }
    for (const badge of screen.getAllByText('Inaktiv')) {
      expect(badge.closest('[data-kind="user"]')).toHaveAttribute('data-status', 'inactive');
    }
  });

  it('shows an empty state with an action when there are no users', async () => {
    mockGet.mockResolvedValue({ data: [] });
    renderWithQuery(<UsersPage />);

    expect(await screen.findByText('Noch keine Benutzer')).toBeInTheDocument();
  });

  it('shows the error with a retry button', async () => {
    mockGet.mockRejectedValue(new Error('boom'));
    renderWithQuery(<UsersPage />);

    expect(await screen.findByRole('button', { name: 'Erneut versuchen' })).toBeInTheDocument();
  });

  it('deactivates after confirmation and refetches the list', async () => {
    mockGet.mockResolvedValue({ data: [user(1)] });
    mockDelete.mockResolvedValue({ data: { success: true, message: 'ok' } });
    mockShowConfirm.mockResolvedValue(true);
    renderWithQuery(<UsersPage />);

    const [button] = await screen.findAllByRole('button', { name: 'Deaktivieren' });
    await userEvent.click(button);

    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/users/1'));
    await waitFor(() => expect(userListCalls().length).toBeGreaterThanOrEqual(2));
    expect(mockShowToast).toHaveBeenCalledWith('Benutzer deaktiviert', 'success');
  });
});
