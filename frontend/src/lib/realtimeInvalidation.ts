/**
 * Realtime → TanStack Query bridge, in ONE place (W3-03, FE-08).
 *
 * The WebSocketProvider turns server hints into `useRealtime` events (and a
 * `resync` event per channel after a reconnect). This module maps each
 * channel to the query roots it makes stale:
 *
 *   order_updates          → ['orders'], ['dashboard'], ['handoffs']
 *   time_tracking_updates  → ['timer'], ['dashboard']
 *   notifications          → ['notifications'], ['handoffs']
 *
 * Invalidation refetches only the queries that are mounted; the rest are
 * marked stale and refetch on their next mount. Hints carry ids and status
 * only; the refetch goes through REST, which applies the role projection.
 *
 * Pages not yet on TanStack Query keep using `useRefetchOn` (refetchBus);
 * the provider still triggers the bus, so both paths work side by side.
 * A migrated page must NOT also register `useRefetchOn`, or it refetches
 * twice.
 */
import { useQueryClient, type QueryClient, type QueryKey } from '@tanstack/react-query';
import { queryKeys } from '../api/queryKeys';
import { useRealtime, type RealtimeChannel } from '../contexts/WebSocketProvider';

export const REALTIME_INVALIDATIONS: Readonly<Record<RealtimeChannel, readonly QueryKey[]>> = {
  order_updates: [queryKeys.orders.all, queryKeys.dashboard.all, queryKeys.handoffs.all],
  time_tracking_updates: [queryKeys.timer.all, queryKeys.dashboard.all],
  notifications: [queryKeys.notifications.all, queryKeys.handoffs.all],
};

/** Mark every query of the channel's roots stale and refetch the mounted ones. */
export async function invalidateForChannel(
  client: QueryClient,
  channel: RealtimeChannel,
): Promise<void> {
  await Promise.all(
    REALTIME_INVALIDATIONS[channel].map((queryKey) => client.invalidateQueries({ queryKey })),
  );
}

function logInvalidationError(channel: RealtimeChannel, err: unknown): void {
  console.error('Realtime invalidation failed', { channel, err });
}

/** Subscribe the session's QueryClient to every realtime channel. */
export function useRealtimeInvalidation(): void {
  const client = useQueryClient();
  const handle = (channel: RealtimeChannel) => () => {
    invalidateForChannel(client, channel).catch((err) => logInvalidationError(channel, err));
  };
  useRealtime('order_updates', handle('order_updates'));
  useRealtime('time_tracking_updates', handle('time_tracking_updates'));
  useRealtime('notifications', handle('notifications'));
}

/** Render-nothing mount point for App.tsx (inside WebSocketProvider). */
export function RealtimeInvalidation(): null {
  useRealtimeInvalidation();
  return null;
}
