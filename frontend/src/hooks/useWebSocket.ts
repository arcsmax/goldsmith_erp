/**
 * useWebSocket — persistent WebSocket connection with exponential back-off
 * reconnect.
 *
 * Connects to `ws[s]://<host>/ws/notifications/{userId}` and calls
 * `onMessage` for every valid JSON message it receives.
 *
 * Reconnect schedule (capped at maxDelay):
 *   attempt 1 → 1 s, attempt 2 → 2 s, attempt 3 → 4 s, … → 30 s max
 *
 * The hook cleans up the socket and any pending reconnect timer on unmount
 * so there are no dangling references.
 */
import { useEffect, useRef, useCallback } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface WebSocketMessage {
  type?: string;
  [key: string]: unknown;
}

export interface UseWebSocketOptions {
  /** User ID used to subscribe to the per-user notification channel. */
  userId: number | null;
  /** Called for every parsed JSON message received from the server. */
  onMessage: (message: WebSocketMessage) => void;
  /** Base reconnect delay in milliseconds (default: 1 000). */
  baseDelay?: number;
  /** Maximum reconnect delay in milliseconds (default: 30 000). */
  maxDelay?: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build the WebSocket URL.
 *
 * - In development (Vite proxy or direct): ws://localhost:8080/ws/…
 * - In production (same-origin): relative ws:// using window.location
 *
 * We always use the relative approach so the hook works behind any reverse
 * proxy that terminates TLS.
 */
function buildWsUrl(userId: number): string {
  const { protocol, host } = window.location;
  const wsProtocol = protocol === 'https:' ? 'wss:' : 'ws:';
  return `${wsProtocol}//${host}/ws/notifications/${userId}`;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useWebSocket({
  userId,
  onMessage,
  baseDelay = 1_000,
  maxDelay = 30_000,
}: UseWebSocketOptions): void {
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef<number>(0);
  const isMountedRef = useRef<boolean>(true);

  // Keep a stable reference to onMessage so the effect does not re-run on
  // every render when the caller passes an inline function.
  const onMessageRef = useRef(onMessage);
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const closeSocket = useCallback(() => {
    if (socketRef.current) {
      // Prevent the onclose handler from scheduling a reconnect when we are
      // intentionally closing the connection (e.g. userId changed, unmount).
      socketRef.current.onclose = null;
      socketRef.current.onerror = null;
      socketRef.current.onmessage = null;
      socketRef.current.close();
      socketRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (!isMountedRef.current || userId === null) return;

    const url = buildWsUrl(userId);
    const ws = new WebSocket(url);
    socketRef.current = ws;

    ws.onopen = () => {
      if (!isMountedRef.current) {
        ws.close();
        return;
      }
      // Reset back-off on a successful connection.
      attemptRef.current = 0;
    };

    ws.onmessage = (event: MessageEvent) => {
      if (!isMountedRef.current) return;
      try {
        const data = JSON.parse(event.data as string) as WebSocketMessage;
        onMessageRef.current(data);
      } catch {
        // Non-JSON frames (e.g. ping strings) are silently ignored.
      }
    };

    ws.onerror = () => {
      // onerror is always followed by onclose — let onclose handle reconnect.
    };

    ws.onclose = () => {
      if (!isMountedRef.current) return;

      // Exponential back-off: 1 s, 2 s, 4 s, 8 s, … capped at maxDelay.
      const delay = Math.min(baseDelay * 2 ** attemptRef.current, maxDelay);
      attemptRef.current += 1;

      reconnectTimerRef.current = setTimeout(() => {
        if (isMountedRef.current) {
          connect();
        }
      }, delay);
    };
  }, [userId, baseDelay, maxDelay]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    isMountedRef.current = true;

    if (userId !== null) {
      connect();
    }

    return () => {
      isMountedRef.current = false;
      clearReconnectTimer();
      closeSocket();
    };
  }, [userId, connect, clearReconnectTimer, closeSocket]);
}
