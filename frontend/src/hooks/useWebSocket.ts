/**
 * useWebSocket — one persistent WebSocket with exponential back-off
 * reconnect, heartbeat reply and a silence watchdog.
 *
 * Used only by WebSocketProvider (W2-13); components subscribe through
 * `useRealtime(channel, handler)` instead of opening their own sockets.
 *
 * - Auth rides on the HttpOnly `access_token` cookie (same origin).
 * - `userId` keys the session: null closes the socket and stops
 *   reconnecting (logout); a different id closes and reopens (next user).
 * - Reconnect schedule: 1 s, 2 s, 4 s, … capped at `maxDelay`; reset on
 *   a successful open.
 * - The server sends `{"type":"ping"}` every 30 s; the hook answers
 *   "pong". If nothing arrives for `watchdogMs`, the socket is presumed
 *   dead and reopened.
 */
import { useEffect, useRef } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface WebSocketMessage {
  type?: string;
  channel?: string;
  data?: unknown;
  [key: string]: unknown;
}

export interface WebSocketOpenInfo {
  /** True when this open follows a drop in the same session. */
  isReconnect: boolean;
}

export interface UseWebSocketOptions {
  /** Signed-in user; null keeps the socket closed. */
  userId: number | null;
  /** Called for every parsed JSON message except heartbeats. */
  onMessage: (message: WebSocketMessage) => void;
  /** Called after each successful open. */
  onOpen?: (info: WebSocketOpenInfo) => void;
  /** Server path (default: /ws/events). */
  path?: string;
  /** Base reconnect delay in milliseconds (default: 1 000). */
  baseDelay?: number;
  /** Maximum reconnect delay in milliseconds (default: 30 000). */
  maxDelay?: number;
  /** Reopen when no frame arrives for this long (default: 75 000). */
  watchdogMs?: number;
}

export const DEFAULT_WS_PATH = '/ws/events';
const DEFAULT_BASE_DELAY_MS = 1_000;
const DEFAULT_MAX_DELAY_MS = 30_000;
/** 2.5 server heartbeats (30 s) without any frame. */
const DEFAULT_WATCHDOG_MS = 75_000;
const PONG = 'pong';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Same-origin URL so the hook works behind any TLS-terminating proxy. */
export function buildWsUrl(path: string = DEFAULT_WS_PATH): string {
  const { protocol, host } = window.location;
  const wsProtocol = protocol === 'https:' ? 'wss:' : 'ws:';
  return `${wsProtocol}//${host}${path}`;
}

export function reconnectDelay(attempt: number, baseDelay: number, maxDelay: number): number {
  return Math.min(baseDelay * 2 ** attempt, maxDelay);
}

function parseFrame(raw: unknown): WebSocketMessage | null {
  if (typeof raw !== 'string') return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return parsed !== null && typeof parsed === 'object' ? (parsed as WebSocketMessage) : null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useWebSocket({
  userId,
  onMessage,
  onOpen,
  path = DEFAULT_WS_PATH,
  baseDelay = DEFAULT_BASE_DELAY_MS,
  maxDelay = DEFAULT_MAX_DELAY_MS,
  watchdogMs = DEFAULT_WATCHDOG_MS,
}: UseWebSocketOptions): void {
  // Latest callbacks without re-running the connection effect.
  const onMessageRef = useRef(onMessage);
  const onOpenRef = useRef(onOpen);
  useEffect(() => {
    onMessageRef.current = onMessage;
    onOpenRef.current = onOpen;
  }, [onMessage, onOpen]);

  useEffect(() => {
    if (userId === null) return undefined;

    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let watchdogTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let hasOpened = false;
    let isActive = true;

    const clearWatchdog = () => {
      if (watchdogTimer !== null) clearTimeout(watchdogTimer);
      watchdogTimer = null;
    };

    const armWatchdog = (ws: WebSocket) => {
      clearWatchdog();
      watchdogTimer = setTimeout(() => {
        console.warn('Live-update socket silent; reconnecting');
        ws.close();
      }, watchdogMs);
    };

    const scheduleReconnect = () => {
      const delay = reconnectDelay(attempt, baseDelay, maxDelay);
      attempt += 1;
      reconnectTimer = setTimeout(connect, delay);
    };

    function connect(): void {
      if (!isActive) return;
      const ws = new WebSocket(buildWsUrl(path));
      socket = ws;

      ws.onopen = () => {
        attempt = 0;
        const isReconnect = hasOpened;
        hasOpened = true;
        armWatchdog(ws);
        onOpenRef.current?.({ isReconnect });
      };

      ws.onmessage = (event: MessageEvent) => {
        armWatchdog(ws);
        const message = parseFrame(event.data);
        if (message === null) return;
        if (message.type === 'ping') {
          ws.send(PONG);
          return;
        }
        onMessageRef.current(message);
      };

      // onerror is always followed by onclose — onclose reconnects.
      ws.onerror = () => undefined;

      ws.onclose = () => {
        clearWatchdog();
        if (!isActive || socket !== ws) return;
        socket = null;
        scheduleReconnect();
      };
    }

    connect();

    return () => {
      isActive = false;
      clearWatchdog();
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      if (socket) {
        const closing = socket;
        socket = null;
        closing.onclose = null;
        closing.onmessage = null;
        closing.onerror = null;
        closing.onopen = null;
        closing.close();
      }
    };
  }, [userId, path, baseDelay, maxDelay, watchdogMs]);
}
