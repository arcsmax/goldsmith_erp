// W2-13 / FE-08 — one live-update socket per session, reconnect with
// back-off, channel dispatch via useRealtime, refetch bus, logout/login.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { act, render } from '@testing-library/react';
import { FakeWebSocket, installFakeWebSocket } from '../test/fakeWebSocket';

const auth = vi.hoisted(() => ({ user: null as { id: number } | null }));
vi.mock('./AuthContext', () => ({
  useOptionalAuth: () => ({ user: auth.user }),
}));

import { WebSocketProvider, useRealtime, type RealtimeEvent } from './WebSocketProvider';
import { registerRefetch } from '../lib/refetchBus';

const Subscriber: React.FC<{ onEvent: (event: RealtimeEvent) => void }> = ({ onEvent }) => {
  useRealtime('time_tracking_updates', onEvent);
  return null;
};

function renderProvider(onEvent: (event: RealtimeEvent) => void = () => undefined) {
  return render(
    <WebSocketProvider baseDelay={1000} maxDelay={8000} watchdogMs={60_000}>
      <Subscriber onEvent={onEvent} />
    </WebSocketProvider>,
  );
}

describe('WebSocketProvider', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    installFakeWebSocket();
    auth.user = { id: 5 };
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('opens exactly one socket to /ws/events while signed in', () => {
    renderProvider();
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toMatch(/\/ws\/events$/);
  });

  it('opens no socket without a user', () => {
    auth.user = null;
    renderProvider();
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it('reconnects with exponential back-off and resets after a successful open', () => {
    renderProvider();
    const first = FakeWebSocket.latest();
    act(() => first.serverClose());

    act(() => vi.advanceTimersByTime(999));
    expect(FakeWebSocket.instances).toHaveLength(1);
    act(() => vi.advanceTimersByTime(1));
    expect(FakeWebSocket.instances).toHaveLength(2);

    act(() => FakeWebSocket.latest().serverClose());
    act(() => vi.advanceTimersByTime(1999));
    expect(FakeWebSocket.instances).toHaveLength(2);
    act(() => vi.advanceTimersByTime(1));
    expect(FakeWebSocket.instances).toHaveLength(3);

    act(() => FakeWebSocket.latest().open());
    act(() => FakeWebSocket.latest().serverClose());
    act(() => vi.advanceTimersByTime(1000));
    expect(FakeWebSocket.instances).toHaveLength(4);
  });

  it('caps the back-off at maxDelay', () => {
    renderProvider();
    for (let i = 0; i < 6; i += 1) {
      act(() => FakeWebSocket.latest().serverClose());
      act(() => vi.advanceTimersByTime(8000));
    }
    expect(FakeWebSocket.instances).toHaveLength(7);
  });

  it('dispatches hints to subscribers of that channel only', () => {
    const onEvent = vi.fn();
    renderProvider(onEvent);
    const ws = FakeWebSocket.latest();
    act(() => ws.open());

    act(() => ws.serverSend({ channel: 'order_updates', data: { order_id: 1 } }));
    expect(onEvent).not.toHaveBeenCalled();

    act(() =>
      ws.serverSend({ channel: 'time_tracking_updates', data: { action: 'start', user_id: 5 } }),
    );
    expect(onEvent).toHaveBeenCalledWith({
      channel: 'time_tracking_updates',
      data: { action: 'start', user_id: 5 },
      resync: false,
    });
  });

  it('ignores malformed and unknown frames', () => {
    const onEvent = vi.fn();
    renderProvider(onEvent);
    const ws = FakeWebSocket.latest();
    act(() => ws.open());
    act(() => ws.serverSendRaw('not json'));
    act(() => ws.serverSend({ channel: 'material_updates', data: {} }));
    expect(onEvent).not.toHaveBeenCalled();
  });

  it('answers the server heartbeat with pong', () => {
    renderProvider();
    const ws = FakeWebSocket.latest();
    act(() => ws.open());
    act(() => ws.serverSend({ type: 'ping' }));
    expect(ws.sent).toEqual(['pong']);
  });

  it('reopens a silent socket after the watchdog period', () => {
    renderProvider();
    act(() => FakeWebSocket.latest().open());
    act(() => vi.advanceTimersByTime(60_000));
    act(() => vi.advanceTimersByTime(1000));
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it('triggers the orders refetch bus on order_updates', () => {
    const refetch = vi.fn();
    const unregister = registerRefetch('orders', refetch);
    renderProvider();
    const ws = FakeWebSocket.latest();
    act(() => ws.open());
    act(() => ws.serverSend({ channel: 'order_updates', data: { order_id: 7 } }));
    expect(refetch).toHaveBeenCalledTimes(1);
    unregister();
  });

  it('resyncs subscribers and every refetch topic after a reconnect', () => {
    const onEvent = vi.fn();
    const refetchOrders = vi.fn();
    const unregister = registerRefetch('orders', refetchOrders);
    renderProvider(onEvent);
    act(() => FakeWebSocket.latest().open());
    expect(onEvent).not.toHaveBeenCalled();

    act(() => FakeWebSocket.latest().serverClose());
    act(() => vi.advanceTimersByTime(1000));
    act(() => FakeWebSocket.latest().open());

    expect(onEvent).toHaveBeenCalledWith({ channel: 'time_tracking_updates', data: {}, resync: true });
    expect(refetchOrders).toHaveBeenCalledTimes(1);
    unregister();
  });

  it('closes on logout without reconnecting and reopens for the next user', () => {
    const view = renderProvider();
    const first = FakeWebSocket.latest();
    act(() => first.open());

    auth.user = null;
    view.rerender(
      <WebSocketProvider baseDelay={1000} maxDelay={8000} watchdogMs={60_000}>
        <Subscriber onEvent={() => undefined} />
      </WebSocketProvider>,
    );
    expect(first.closedByClient).toBe(true);
    act(() => vi.advanceTimersByTime(30_000));
    expect(FakeWebSocket.instances).toHaveLength(1);

    auth.user = { id: 9 };
    view.rerender(
      <WebSocketProvider baseDelay={1000} maxDelay={8000} watchdogMs={60_000}>
        <Subscriber onEvent={() => undefined} />
      </WebSocketProvider>,
    );
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(FakeWebSocket.latest().closedByClient).toBe(false);
  });

  it('closes the socket on unmount', () => {
    const view = renderProvider();
    const ws = FakeWebSocket.latest();
    view.unmount();
    expect(ws.closedByClient).toBe(true);
    act(() => vi.advanceTimersByTime(30_000));
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});

describe('useRealtime outside a provider', () => {
  it('is a no-op', () => {
    installFakeWebSocket();
    expect(() => render(<Subscriber onEvent={() => undefined} />)).not.toThrow();
    expect(FakeWebSocket.instances).toHaveLength(0);
    vi.unstubAllGlobals();
  });
});
