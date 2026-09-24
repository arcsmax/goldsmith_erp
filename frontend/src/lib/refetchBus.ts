/**
 * refetchBus — "something changed, refetch" callbacks registered by pages
 * (W2-13 / FE-08).
 *
 * The WebSocketProvider turns each server hint into a topic trigger:
 *   order_updates          → 'orders'
 *   time_tracking_updates  → 'time_tracking'
 *   notifications          → 'notifications'
 * and triggers every topic after a reconnect (events may have been missed).
 *
 * Pages that show orders (dashboard, order list, order detail) register a
 * refetch with `useRefetchOn('orders', load)`. Hints carry ids and status
 * only; the page refetches through REST, which applies the role projection.
 *
 * Wave 3 (W3-03) replaces the callbacks with queryClient.invalidateQueries;
 * the provider side stays the same.
 */
import { useEffect, useRef } from 'react';

export type RefetchTopic = 'orders' | 'time_tracking' | 'notifications';

export const REFETCH_TOPICS: readonly RefetchTopic[] = [
  'orders',
  'time_tracking',
  'notifications',
];

type RefetchCallback = () => void;

let registry: ReadonlyMap<RefetchTopic, ReadonlySet<RefetchCallback>> = new Map();

/** Register a callback for a topic. Returns the unregister function. */
export function registerRefetch(topic: RefetchTopic, callback: RefetchCallback): () => void {
  const current = registry.get(topic) ?? new Set<RefetchCallback>();
  registry = new Map(registry).set(topic, new Set(current).add(callback));
  return () => {
    const remaining = new Set(registry.get(topic) ?? []);
    remaining.delete(callback);
    registry = new Map(registry).set(topic, remaining);
  };
}

/** Run every callback registered for the topic; one failing callback does not stop the rest. */
export function triggerRefetch(topic: RefetchTopic): void {
  for (const callback of registry.get(topic) ?? []) {
    try {
      callback();
    } catch (err) {
      console.error('Refetch callback failed', { topic, err });
    }
  }
}

export function triggerAllRefetch(): void {
  REFETCH_TOPICS.forEach(triggerRefetch);
}

/**
 * Refetch whenever the topic fires. The latest callback is always used, so
 * callers may pass an inline function.
 */
export function useRefetchOn(topic: RefetchTopic, callback: RefetchCallback): void {
  const callbackRef = useRef(callback);
  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => registerRefetch(topic, () => callbackRef.current()), [topic]);
}
