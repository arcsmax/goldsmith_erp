// W2-13 — the live-update socket lives in the staff shell only. The public
// customer portal must never open it, even on a device with a staff session.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { FakeWebSocket, installFakeWebSocket } from './test/fakeWebSocket';

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

const STAFF_USER = { id: 5, email: 'g@example.test', role: 'goldsmith', is_active: true };

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe('App routing — live-update socket placement (W2-13)', () => {
  beforeEach(() => {
    installFakeWebSocket();
    localStorage.clear();
    getCurrentUser.mockReset();
    clientGet.mockReset();
    getCurrentUser.mockResolvedValue(STAFF_USER);
    clientGet.mockRejectedValue(Object.assign(new Error('offline'), { response: { status: 503 } }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('never opens a socket on /portal, even with a staff session on the device', async () => {
    localStorage.setItem('user', JSON.stringify(STAFF_USER));
    renderAt('/portal');
    expect(await screen.findByRole('heading', { name: 'Status prüfen' })).toBeInTheDocument();
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it('opens exactly one socket in the staff shell once signed in', async () => {
    renderAt('/login');
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    expect(FakeWebSocket.instances[0].url).toMatch(/\/ws\/events$/);
  });

  it('opens no socket in the staff shell while signed out', async () => {
    getCurrentUser.mockRejectedValue(
      Object.assign(new Error('401'), { response: { status: 401 } }),
    );
    renderAt('/login');
    expect(await screen.findByRole('heading', { name: 'Anmelden' })).toBeInTheDocument();
    expect(FakeWebSocket.instances).toHaveLength(0);
  });
});
