// LV-21: the session probe on mount (GET /users/me, then POST /refresh)
// filled the /login console with errors although "no session" is the
// expected answer there. A 401 is a silent "not logged in"; any other
// failure stays loud (logError). On /login and /register without a cached
// user the probe is skipped, so the logged-out page makes no 401 calls.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, waitFor } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
}));

vi.mock('../api', () => ({
  authApi: {
    getCurrentUser: mocks.getCurrentUser,
    login: vi.fn(),
    logout: vi.fn(),
    register: vi.fn(),
  },
}));
vi.mock('../api/client', () => ({ default: { post: vi.fn(), get: vi.fn() } }));

import { AuthProvider, useAuth } from './AuthContext';

let authRef: ReturnType<typeof useAuth> | null = null;
const Probe: React.FC = () => {
  authRef = useAuth();
  return null;
};

function renderProvider() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
}

function httpError(status: number) {
  return Object.assign(new Error(`HTTP ${status}`), {
    isAxiosError: true,
    response: { status, data: {} },
    config: { url: '/users/me' },
  });
}

let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  authRef = null;
  window.history.pushState({}, '', '/dashboard');
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  consoleError.mockRestore();
  window.history.pushState({}, '', '/');
});

describe('AuthContext session probe (LV-21)', () => {
  it('treats a 401 as a silent "no session"', async () => {
    mocks.getCurrentUser.mockRejectedValue(httpError(401));
    renderProvider();

    await waitFor(() => expect(authRef?.isLoading).toBe(false));
    expect(authRef?.user).toBeNull();
    expect(consoleError).not.toHaveBeenCalled();
  });

  it('logs any other probe failure loudly', async () => {
    mocks.getCurrentUser.mockRejectedValue(httpError(500));
    renderProvider();

    await waitFor(() => expect(authRef?.isLoading).toBe(false));
    expect(authRef?.user).toBeNull();
    expect(consoleError).toHaveBeenCalledWith(
      'AuthContext.sessionProbe',
      expect.objectContaining({ status: 500 }),
    );
  });

  it('skips the probe on /login when no user is cached', async () => {
    window.history.pushState({}, '', '/login');
    renderProvider();

    await waitFor(() => expect(authRef?.isLoading).toBe(false));
    expect(mocks.getCurrentUser).not.toHaveBeenCalled();
    expect(authRef?.user).toBeNull();
  });

  it('still validates a cached user on /login', async () => {
    window.history.pushState({}, '', '/login');
    localStorage.setItem('user', JSON.stringify({ id: 1, email: 'a@example.test', role: 'admin' }));
    mocks.getCurrentUser.mockResolvedValue({ id: 1, email: 'a@example.test', role: 'admin' });
    renderProvider();

    await waitFor(() => expect(mocks.getCurrentUser).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(authRef?.isLoading).toBe(false));
    expect(authRef?.user?.id).toBe(1);
  });
});
