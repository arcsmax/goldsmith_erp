// W2-13 — a `notifications` hint refreshes the unread badge immediately.
// W4-03: the bell reads through TanStack Query; the hint reaches it via the
// app-wide RealtimeInvalidation bridge (['notifications'] root).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, waitFor } from '@testing-library/react';
import { FakeWebSocket, installFakeWebSocket } from '../test/fakeWebSocket';

const mocks = vi.hoisted(() => ({
  getUnreadCount: vi.fn(),
  getNotifications: vi.fn(async () => []),
}));

vi.mock('../contexts/AuthContext', () => {
  const value = { user: { id: 5 } };
  return { useAuth: () => value, useOptionalAuth: () => value };
});
vi.mock('../api/notifications', () => ({
  notificationsApi: {
    getUnreadCount: mocks.getUnreadCount,
    getNotifications: mocks.getNotifications,
    markAsRead: vi.fn(),
    markAllAsRead: vi.fn(),
  },
}));

import { WebSocketProvider } from '../contexts/WebSocketProvider';
import { RealtimeInvalidation } from '../lib/realtimeInvalidation';
import { createTestQueryClient, QueryWrapper } from '../test/queryWrapper';
import { NotificationBell } from './NotificationBell';

describe('NotificationBell live refresh', () => {
  beforeEach(() => {
    installFakeWebSocket();
    mocks.getUnreadCount.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('refetches the unread count on a notifications hint', async () => {
    mocks.getUnreadCount.mockResolvedValueOnce({ unread_count: 0 });
    const view = render(
      <QueryWrapper client={createTestQueryClient()}>
        <WebSocketProvider>
          <RealtimeInvalidation />
          <NotificationBell />
        </WebSocketProvider>
      </QueryWrapper>,
    );
    await waitFor(() => expect(mocks.getUnreadCount).toHaveBeenCalledTimes(1));

    mocks.getUnreadCount.mockResolvedValueOnce({ unread_count: 1 });
    const ws = FakeWebSocket.latest();
    act(() => ws.open());
    act(() => ws.serverSend({ channel: 'notifications', data: { id: 9, severity: 'info' } }));

    await waitFor(() => expect(mocks.getUnreadCount).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(view.container.textContent ?? '').toContain('1'),
    );
  });
});
