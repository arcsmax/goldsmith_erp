// FE-07 / FE-11 / FE-19 — per-user lifecycle.
//
// FE-07: TimeTrackingProvider initialised once on mount (before login) and
//        never again; logout left per-user state behind.
// FE-11: logout never cleared the service-worker API caches (orders,
//        materials, activities → PII + financial data on shared tablets).
// FE-19: polling kept hitting /time-tracking/running after logout.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  login: vi.fn(async () => ({})),
  logout: vi.fn(),
  getRunning: vi.fn(),
  getAllActivities: vi.fn(async () => []),
}));

vi.mock('../api', () => ({
  authApi: {
    getCurrentUser: mocks.getCurrentUser,
    login: mocks.login,
    logout: mocks.logout,
    register: vi.fn(),
  },
}));
vi.mock('../api/time-tracking', () => ({
  timeTrackingApi: { getRunning: mocks.getRunning },
}));
vi.mock('../api/activities', () => ({
  activitiesApi: { getAll: mocks.getAllActivities },
}));
vi.mock('../api/client', () => ({ default: { post: vi.fn(), get: vi.fn() } }));
vi.mock('../hooks/useWebSocket', () => ({ useWebSocket: () => undefined }));

import { AuthProvider, useAuth } from './AuthContext';
import { TimeTrackingProvider, useTimeTracking } from './TimeTrackingContext';

const USER = { id: 5, email: 'g@example.test', role: 'goldsmith' };
const ENTRY = { id: 'e-1', order_id: 3, activity_id: 2, user_id: 5 };

let authRef: ReturnType<typeof useAuth> | null = null;
const Probe: React.FC = () => {
  authRef = useAuth();
  const { runningEntry } = useTimeTracking();
  return <div data-testid="running">{runningEntry ? runningEntry.id : 'none'}</div>;
};

function renderTree() {
  return render(
    <AuthProvider>
      <TimeTrackingProvider>
        <Probe />
      </TimeTrackingProvider>
    </AuthProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  authRef = null;
});

afterEach(() => {
  vi.useRealTimers();
});

describe('per-user lifecycle', () => {
  it('loads the running timer after login, not only on first mount (FE-07)', async () => {
    mocks.getCurrentUser.mockRejectedValueOnce(new Error('401'));
    mocks.getRunning.mockResolvedValue(ENTRY);
    renderTree();

    await waitFor(() => expect(authRef?.isLoading).toBe(false));
    expect(mocks.getRunning).not.toHaveBeenCalled();

    mocks.getCurrentUser.mockResolvedValueOnce(USER);
    await act(async () => {
      await authRef?.login({ email: USER.email, password: 'x' });
    });

    expect(await screen.findByText('e-1')).toBeInTheDocument();
  });

  it('clears per-user state, storage and SW API caches on logout (FE-07, FE-11)', async () => {
    const deleted: string[] = [];
    const cachesStub = {
      keys: vi.fn(async () => ['api-orders', 'api-materials', 'api-activities', 'static-assets']),
      delete: vi.fn(async (k: string) => {
        deleted.push(k);
        return true;
      }),
    };
    vi.stubGlobal('caches', cachesStub);
    mocks.getCurrentUser.mockResolvedValue(USER);
    mocks.getRunning.mockResolvedValue(ENTRY);
    localStorage.setItem('scanner_last_activity_id', '9');
    renderTree();
    expect(await screen.findByText('e-1')).toBeInTheDocument();

    act(() => authRef?.logout());

    expect(await screen.findByText('none')).toBeInTheDocument();
    expect(localStorage.getItem('running_time_entry')).toBeNull();
    expect(localStorage.getItem('scanner_last_activity_id')).toBeNull();
    await waitFor(() =>
      expect(deleted.sort()).toEqual(['api-activities', 'api-materials', 'api-orders']),
    );
    vi.unstubAllGlobals();
  });

  it('stops polling /time-tracking/running after logout (FE-19)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mocks.getCurrentUser.mockResolvedValue(USER);
    mocks.getRunning.mockResolvedValue(ENTRY);
    renderTree();
    expect(await screen.findByText('e-1')).toBeInTheDocument();

    act(() => authRef?.logout());
    await screen.findByText('none');
    const callsAtLogout = mocks.getRunning.mock.calls.length;

    await act(async () => {
      vi.advanceTimersByTime(20_000);
    });
    expect(mocks.getRunning.mock.calls.length).toBe(callsAtLogout);
  });

  it('stops polling once the server reports no running timer (FE-19)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mocks.getCurrentUser.mockResolvedValue(USER);
    mocks.getRunning.mockResolvedValueOnce(ENTRY).mockResolvedValue(null);
    renderTree();
    expect(await screen.findByText('e-1')).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(5_000);
    });
    await screen.findByText('none');
    const calls = mocks.getRunning.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(20_000);
    });
    expect(mocks.getRunning.mock.calls.length).toBe(calls);
  });
});
