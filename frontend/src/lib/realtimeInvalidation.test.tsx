// W3-03: realtime hints invalidate TanStack Query roots in one place, and the
// refetch bus keeps firing for pages that are not migrated yet.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { act, render } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { FakeWebSocket, installFakeWebSocket } from '../test/fakeWebSocket';
import { createTestQueryClient } from '../test/queryWrapper';

const auth = vi.hoisted(() => ({ user: { id: 5 } as { id: number } | null }));
vi.mock('../contexts/AuthContext', () => ({
  useOptionalAuth: () => ({ user: auth.user }),
}));

import { WebSocketProvider } from '../contexts/WebSocketProvider';
import { RealtimeInvalidation, REALTIME_INVALIDATIONS } from './realtimeInvalidation';
import { registerRefetch } from './refetchBus';

function renderBridge() {
  const client = createTestQueryClient();
  const spy = vi.spyOn(client, 'invalidateQueries');
  render(
    <QueryClientProvider client={client}>
      <WebSocketProvider baseDelay={1000} maxDelay={8000} watchdogMs={60_000}>
        <RealtimeInvalidation />
      </WebSocketProvider>
    </QueryClientProvider>,
  );
  const invalidatedRoots = () => spy.mock.calls.map(([filters]) => filters?.queryKey);
  return { client, spy, invalidatedRoots };
}

describe('realtimeInvalidation', () => {
  beforeEach(() => {
    installFakeWebSocket();
    auth.user = { id: 5 };
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('maps order, timer and notification hints to their query roots', () => {
    expect(REALTIME_INVALIDATIONS.order_updates).toContainEqual(['orders']);
    expect(REALTIME_INVALIDATIONS.time_tracking_updates).toContainEqual(['timer']);
    expect(REALTIME_INVALIDATIONS.notifications).toContainEqual(['notifications']);
  });

  it('maps repair and job hints to ["repairs"] / ["jobs"]', () => {
    expect(REALTIME_INVALIDATIONS.repair_updates).toContainEqual(['repairs']);
    expect(REALTIME_INVALIDATIONS.repair_updates).toContainEqual(['jobs']);
    expect(REALTIME_INVALIDATIONS.job_updates).toContainEqual(['jobs']);
  });

  it('invalidates ["repairs"] and ["jobs"] on a repair_updates hint', () => {
    const { invalidatedRoots } = renderBridge();
    act(() => FakeWebSocket.latest().open());
    act(() =>
      FakeWebSocket.latest().serverSend({ channel: 'repair_updates', data: { repair_id: 1 } }),
    );
    expect(invalidatedRoots()).toEqual([['repairs'], ['jobs']]);
  });

  it('invalidates ["jobs"] on a job_updates hint', () => {
    const { invalidatedRoots } = renderBridge();
    act(() => FakeWebSocket.latest().serverSend({ channel: 'job_updates', data: { job_id: 1 } }));
    expect(invalidatedRoots()).toEqual([['jobs']]);
  });

  it('invalidates ["orders"] (and the dashboard and handoffs) on an order_updates hint', () => {
    const { invalidatedRoots } = renderBridge();
    act(() => FakeWebSocket.latest().open());
    act(() =>
      FakeWebSocket.latest().serverSend({ channel: 'order_updates', data: { order_id: 1 } }),
    );
    expect(invalidatedRoots()).toEqual([
      ['orders'],
      ['dashboard'],
      ['handoffs'],
      ['calendar'],
      ['jobs'],
    ]);
  });

  it('invalidates ["timer"] on a time_tracking_updates hint', () => {
    const { invalidatedRoots } = renderBridge();
    act(() => FakeWebSocket.latest().serverSend({ channel: 'time_tracking_updates', data: {} }));
    expect(invalidatedRoots()).toContainEqual(['timer']);
    expect(invalidatedRoots()).not.toContainEqual(['orders']);
  });

  it('invalidates ["notifications"] on a notifications hint', () => {
    const { invalidatedRoots } = renderBridge();
    act(() => FakeWebSocket.latest().serverSend({ channel: 'notifications', data: {} }));
    expect(invalidatedRoots()).toContainEqual(['notifications']);
  });

  it('still triggers the refetch bus for pages not yet migrated', () => {
    const legacy = vi.fn();
    const unregister = registerRefetch('orders', legacy);
    renderBridge();
    act(() => FakeWebSocket.latest().serverSend({ channel: 'order_updates', data: {} }));
    expect(legacy).toHaveBeenCalledTimes(1);
    unregister();
  });

  it('invalidates every root after a reconnect (resync)', () => {
    vi.useFakeTimers();
    try {
      const { invalidatedRoots } = renderBridge();
      act(() => FakeWebSocket.latest().open());
      act(() => FakeWebSocket.latest().serverClose());
      act(() => vi.advanceTimersByTime(1000));
      act(() => FakeWebSocket.latest().open());
      expect(invalidatedRoots()).toEqual(
        expect.arrayContaining([['orders'], ['timer'], ['notifications']]),
      );
    } finally {
      vi.useRealTimers();
    }
  });
});
