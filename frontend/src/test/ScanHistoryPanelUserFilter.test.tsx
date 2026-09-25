// ScanHistoryPanel — Mitarbeiter:in filter dropdown (2026-09 audit, SC-03
// follow-up: "Scan-history search has no user dropdown in the UI (API
// supports user=)").
//
// GET /users/ requires Permission.USER_VIEW, which only ADMIN holds
// (core/permissions.py ROLE_PERMISSIONS) even though GOLDSMITH may also
// open this panel — so the dropdown itself is ADMIN-only; GOLDSMITH keeps
// the existing free-text search with no user filter and never calls
// GET /users/ (no 403 noise).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

const mocks = vi.hoisted(() => ({ apiGet: vi.fn(), mockAuth: null as unknown }));

vi.mock('../api/client', () => ({ default: { get: mocks.apiGet, post: vi.fn() } }));
vi.mock('../contexts/AuthContext', () => ({ useOptionalAuth: () => mocks.mockAuth }));

import { ScanHistoryPanel, toSearchParams } from '../pages/admin/ScanHistoryPanel';
import { QueryWrapper, createTestQueryClient } from './queryWrapper';

const STAFF = [
  { id: 3, email: 'zora@werkstatt.de', first_name: 'Zora', last_name: 'Weiss', is_active: true, role: 'goldsmith' },
  { id: 1, email: 'anne@werkstatt.de', first_name: 'Anne', last_name: 'Goldschmied', is_active: true, role: 'admin' },
];

const EMPTY_HISTORY = { items: [], total: 0, limit: 25, offset: 0, next_offset: null };

function wrap(node: React.ReactNode) {
  return render(
    <QueryWrapper client={createTestQueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryWrapper>,
  );
}

beforeEach(() => {
  mocks.apiGet.mockReset().mockImplementation(async (url: string) => {
    if (url === '/users/') return { data: STAFF };
    if (url === '/scan/history') return { data: EMPTY_HISTORY };
    return { data: {} };
  });
});

afterEach(() => {
  mocks.mockAuth = null;
});

describe('ScanHistoryPanel — Mitarbeiter:in filter', () => {
  it('toSearchParams includes user= only when a user id is selected', () => {
    expect(toSearchParams({ q: '', user: '', from: '', to: '' }, 0)).toEqual({
      limit: 25,
      offset: 0,
    });
    expect(toSearchParams({ q: '', user: '3', from: '', to: '' }, 0)).toEqual({
      user: 3,
      limit: 25,
      offset: 0,
    });
  });

  it('ADMIN sees the dropdown, sorted by name, and can filter by staff user', async () => {
    mocks.mockAuth = { user: { id: 1, role: 'admin', email: 'anne@werkstatt.de' } };
    wrap(<ScanHistoryPanel />);

    const select = await screen.findByTestId('scan-history-user-select');
    await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledWith('/users/', { params: { skip: 0, limit: 100 } }));

    const options = Array.from(select.querySelectorAll('option')).map((o) => o.textContent);
    // "Alle Mitarbeiter:innen" first, then staff sorted by display name (Anne before Zora).
    expect(options).toEqual(['Alle Mitarbeiter:innen', 'Anne Goldschmied', 'Zora Weiss']);

    const user = userEvent.setup();
    await user.selectOptions(select, '1');

    await user.click(screen.getByRole('button', { name: 'Scans suchen' }));

    await waitFor(() =>
      expect(mocks.apiGet).toHaveBeenLastCalledWith('/scan/history', {
        params: { user: 1, limit: 25, offset: 0 },
      }),
    );
  });

  it('GOLDSMITH gets no dropdown and GET /users/ is never called', async () => {
    mocks.mockAuth = { user: { id: 2, role: 'goldsmith', email: 'goldsmith@werkstatt.de' } };
    wrap(<ScanHistoryPanel />);

    await screen.findByTestId('scan-history-form');
    expect(screen.queryByTestId('scan-history-user-select')).toBeNull();

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/Nummer oder Code/), '42');
    await user.click(screen.getByRole('button', { name: 'Scans suchen' }));

    await waitFor(() =>
      expect(mocks.apiGet).toHaveBeenLastCalledWith('/scan/history', {
        params: { q: '42', limit: 25, offset: 0 },
      }),
    );
    expect(mocks.apiGet.mock.calls.some((c) => c[0] === '/users/')).toBe(false);
  });
});
