/**
 * WebSocketProvider — the ONE live-update socket of the staff app
 * (W2-13 / FE-08, BE-20, D.1).
 *
 * Mounted inside the authenticated shell (StaffApp in App.tsx), never on
 * /portal. It connects while a user is signed in, closes on logout and
 * reopens for the next user.
 *
 * Server frames are invalidation hints `{ channel, data }` carrying ids,
 * status and timestamps only (no prices, no PII). Consumers refetch through
 * REST, which applies the role projection:
 *
 *   useRealtime('time_tracking_updates', () => refreshRunningEntry());
 *   useRefetchOn('orders', loadOrders);          // lib/refetchBus
 *
 * After a reconnect every subscriber gets a `resync` event and every
 * refetch topic fires, because hints sent while offline are lost.
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef } from 'react';
import { useOptionalAuth } from './AuthContext';
import { useWebSocket, type WebSocketMessage, type WebSocketOpenInfo } from '../hooks/useWebSocket';
import { triggerAllRefetch, triggerRefetch, type RefetchTopic } from '../lib/refetchBus';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type RealtimeChannel = 'order_updates' | 'time_tracking_updates' | 'notifications';

export interface RealtimeEvent {
  channel: RealtimeChannel;
  /** Hint payload (ids, action, status); empty on resync. */
  data: Readonly<Record<string, unknown>>;
  /** True when fired after a reconnect instead of by a server event. */
  resync: boolean;
}

export type RealtimeHandler = (event: RealtimeEvent) => void;

interface WebSocketContextValue {
  subscribe: (channel: RealtimeChannel, handler: RealtimeHandler) => () => void;
}

export interface WebSocketProviderProps {
  children: React.ReactNode;
  /** Test hooks; production uses the useWebSocket defaults. */
  baseDelay?: number;
  maxDelay?: number;
  watchdogMs?: number;
}

const CHANNEL_TOPICS: Readonly<Record<RealtimeChannel, RefetchTopic>> = {
  order_updates: 'orders',
  time_tracking_updates: 'time_tracking',
  notifications: 'notifications',
};

const CHANNELS = Object.keys(CHANNEL_TOPICS) as RealtimeChannel[];

function isRealtimeChannel(value: unknown): value is RealtimeChannel {
  return typeof value === 'string' && value in CHANNEL_TOPICS;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

export const WebSocketProvider: React.FC<WebSocketProviderProps> = ({
  children,
  baseDelay,
  maxDelay,
  watchdogMs,
}) => {
  const auth = useOptionalAuth();
  const userId = auth?.user?.id ?? null;

  const handlersRef = useRef<ReadonlyMap<RealtimeChannel, ReadonlySet<RealtimeHandler>>>(new Map());

  const subscribe = useCallback((channel: RealtimeChannel, handler: RealtimeHandler) => {
    const current = handlersRef.current.get(channel) ?? new Set<RealtimeHandler>();
    handlersRef.current = new Map(handlersRef.current).set(channel, new Set(current).add(handler));
    return () => {
      const remaining = new Set(handlersRef.current.get(channel) ?? []);
      remaining.delete(handler);
      handlersRef.current = new Map(handlersRef.current).set(channel, remaining);
    };
  }, []);

  const dispatch = useCallback((event: RealtimeEvent) => {
    for (const handler of handlersRef.current.get(event.channel) ?? []) {
      try {
        handler(event);
      } catch (err) {
        console.error('Realtime handler failed', { channel: event.channel, err });
      }
    }
  }, []);

  const handleMessage = useCallback(
    (message: WebSocketMessage) => {
      if (!isRealtimeChannel(message.channel)) return;
      const data = isRecord(message.data) ? message.data : {};
      dispatch({ channel: message.channel, data, resync: false });
      triggerRefetch(CHANNEL_TOPICS[message.channel]);
    },
    [dispatch],
  );

  const handleOpen = useCallback(
    ({ isReconnect }: WebSocketOpenInfo) => {
      if (!isReconnect) return;
      CHANNELS.forEach((channel) => dispatch({ channel, data: {}, resync: true }));
      triggerAllRefetch();
    },
    [dispatch],
  );

  useWebSocket({
    userId,
    onMessage: handleMessage,
    onOpen: handleOpen,
    baseDelay,
    maxDelay,
    watchdogMs,
  });

  const value = useMemo<WebSocketContextValue>(() => ({ subscribe }), [subscribe]);

  return <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>;
};

// ---------------------------------------------------------------------------
// Consumer hook
// ---------------------------------------------------------------------------

/**
 * Call `handler` for every hint on `channel` (and on resync after a
 * reconnect). The latest handler is always used. Outside a
 * WebSocketProvider (tests, /portal) this is a no-op.
 */
export function useRealtime(channel: RealtimeChannel, handler: RealtimeHandler): void {
  const context = useContext(WebSocketContext);
  const handlerRef = useRef(handler);
  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    if (!context) return undefined;
    return context.subscribe(channel, (event) => handlerRef.current(event));
  }, [context, channel]);
}
