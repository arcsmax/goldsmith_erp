// W2-13 / FE-08 — a time_tracking_updates hint (timer started, stopped or
// switched on another device of the same user) refreshes the running timer.
// W4-03: the timer is a query now; the hint reaches it through the one
// realtime bridge (RealtimeInvalidation → ['timer']), as in App.tsx.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { FakeWebSocket, installFakeWebSocket } from '../test/fakeWebSocket';

const mocks = vi.hoisted(() => ({
  getRunning: vi.fn(),
  getAllActivities: vi.fn(async () => []),
}));

vi.mock('./AuthContext', () => {
  const value = { user: { id: 5, role: 'goldsmith' } };
  return { useAuth: () => value, useOptionalAuth: () => value };
});
vi.mock('../api/time-tracking', () => ({
  timeTrackingApi: { getRunning: mocks.getRunning },
}));
vi.mock('../api/activities', () => ({
  activitiesApi: { getAll: mocks.getAllActivities },
}));
vi.mock('../api/client', () => ({ default: { post: vi.fn(), get: vi.fn() } }));

import { WebSocketProvider } from './WebSocketProvider';
import { TimeTrackingProvider, useTimeTracking } from './TimeTrackingContext';
import { RealtimeInvalidation } from '../lib/realtimeInvalidation';
import { QueryWrapper, createTestQueryClient } from '../test/queryWrapper';

const renderTree = (probe: React.ReactElement) =>
  render(
    <QueryWrapper client={createTestQueryClient()}>
      <WebSocketProvider>
        <RealtimeInvalidation />
        <TimeTrackingProvider>{probe}</TimeTrackingProvider>
      </WebSocketProvider>
    </QueryWrapper>,
  );

const Probe: React.FC = () => {
  const { runningEntry } = useTimeTracking();
  return <div data-testid="running">{runningEntry ? runningEntry.id : 'none'}</div>;
};

describe('TimeTrackingContext live refresh', () => {
  beforeEach(() => {
    installFakeWebSocket();
    mocks.getRunning.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('refetches the running entry when a time_tracking_updates hint arrives', async () => {
    mocks.getRunning.mockResolvedValueOnce(null);
    renderTree(<Probe />);
    await waitFor(() => expect(mocks.getRunning).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId('running').textContent).toBe('none');

    // Timer started on the bench iPad → hint reaches the laptop.
    mocks.getRunning.mockResolvedValueOnce({ id: 'e-42', order_id: 3, activity_id: 2, user_id: 5 });
    const ws = FakeWebSocket.latest();
    act(() => ws.open());
    act(() =>
      ws.serverSend({ channel: 'time_tracking_updates', data: { action: 'start', user_id: 5 } }),
    );

    await waitFor(() => expect(screen.getByTestId('running').textContent).toBe('e-42'));
    expect(mocks.getRunning).toHaveBeenCalledTimes(2);
  });

  it('does not refetch on unrelated channels', async () => {
    mocks.getRunning.mockResolvedValue(null);
    renderTree(<Probe />);
    await waitFor(() => expect(mocks.getRunning).toHaveBeenCalledTimes(1));
    const ws = FakeWebSocket.latest();
    act(() => ws.open());
    act(() => ws.serverSend({ channel: 'order_updates', data: { order_id: 3 } }));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mocks.getRunning).toHaveBeenCalledTimes(1);
  });
});
