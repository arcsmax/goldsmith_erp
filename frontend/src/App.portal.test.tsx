// FE-01 regression — the public customer portal must render outside the
// authenticated shell.
//
// Before the fix `/portal` sat inside <AuthProvider><ScannerProvider>
// <TimeTrackingProvider>. Their mount effects call /users/me,
// /time-tracking/running and /activities; for a visitor without a cookie
// these 401, the refresh 401s and the axios interceptor hard-redirects to
// /login. We assert the public route mounts NONE of the authenticated
// providers (no authenticated API call at all), while staff routes stay
// protected.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const { getCurrentUser, clientGet } = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  clientGet: vi.fn(),
}));

vi.mock('./api/client', () => ({
  default: {
    get: clientGet,
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

vi.mock('./api', async (orig) => {
  const actual = await orig<typeof import('./api')>();
  return {
    ...actual,
    authApi: { ...actual.authApi, getCurrentUser, logout: vi.fn() },
  };
});

import { AppRoutes } from './App';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe('App routing — public customer portal (FE-01)', () => {
  beforeEach(() => {
    getCurrentUser.mockReset();
    clientGet.mockReset();
    const unauthorized = Object.assign(new Error('401'), {
      response: { status: 401, data: { detail: 'Not authenticated' } },
    });
    getCurrentUser.mockRejectedValue(unauthorized);
    clientGet.mockRejectedValue(unauthorized);
    localStorage.clear();
  });

  it('renders /portal for an unauthenticated visitor without touching auth APIs', async () => {
    renderAt('/portal');

    expect(await screen.findByRole('heading', { name: 'Status prüfen' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Anmelden' })).not.toBeInTheDocument();
    // No authenticated provider mounted → no /users/me, no /time-tracking/running.
    expect(getCurrentUser).not.toHaveBeenCalled();
    expect(clientGet).not.toHaveBeenCalled();
  });

  it('still protects staff routes: /dashboard unauthenticated lands on the login page', async () => {
    renderAt('/dashboard');

    expect(await screen.findByRole('heading', { name: 'Anmelden' })).toBeInTheDocument();
    expect(getCurrentUser).toHaveBeenCalled();
  });
});
