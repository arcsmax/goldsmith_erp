/**
 * Realtime → TanStack Query bridge, in ONE place (W3-03, FE-08).
 *
 * The WebSocketProvider turns server hints into `useRealtime` events (and a
 * `resync` event per channel after a reconnect). This module maps each
 * channel to the query roots it makes stale:
 *
 *   order_updates          → ['orders'], ['dashboard'], ['handoffs'], ['calendar'], ['jobs']
 *   time_tracking_updates  → ['timer'], ['dashboard']
 *   notifications          → ['notifications'], ['handoffs']
 *   repair_updates         → ['repairs'], ['jobs']
 *   job_updates            → ['jobs']
 *   scan_updates           → ['scan-log'] + the scanned piece's detail (last_scan)
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
  order_updates: [
    queryKeys.orders.all,
    queryKeys.dashboard.all,
    queryKeys.handoffs.all,
    // Calendar deadlines are derived from order delivery dates.
    queryKeys.calendar.all,
    // The Werkstatt board (jobs spine) mirrors order status and deadline.
    queryKeys.jobs.all,
  ],
  time_tracking_updates: [queryKeys.timer.all, queryKeys.dashboard.all],
  notifications: [queryKeys.notifications.all, queryKeys.handoffs.all],
  repair_updates: [queryKeys.repairs.all, queryKeys.jobs.all],
  job_updates: [queryKeys.jobs.all],
  // Every Scan-Verlauf list; the scanned piece's detail (its "Zuletzt
  // gescannt" line) is added per hint by scanPieceKeys below, so a busy
  // bench does not refetch every order list on each scan.
  scan_updates: [queryKeys.scanLog.all],
};

/** The detail query of the piece a `scan_updates` hint is about, if any. */
export function scanPieceKeys(data: Readonly<Record<string, unknown>>): QueryKey[] {
  const id = Number(data.entity_id);
  if (!Number.isInteger(id) || id <= 0) return [];
  if (data.entity_type === 'order') return [queryKeys.orders.detail(id)];
  if (data.entity_type === 'repair') return [queryKeys.repairs.detail(id)];
  return [];
}

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
  useRealtime('repair_updates', handle('repair_updates'));
  useRealtime('job_updates', handle('job_updates'));
  useRealtime('scan_updates', (event) => {
    handle('scan_updates')();
    scanPieceKeys(event.data).forEach((queryKey) => {
      client
        .invalidateQueries({ queryKey })
        .catch((err) => logInvalidationError('scan_updates', err));
    });
  });
}

/** Render-nothing mount point for App.tsx (inside WebSocketProvider). */
export function RealtimeInvalidation(): null {
  useRealtimeInvalidation();
  return null;
}
