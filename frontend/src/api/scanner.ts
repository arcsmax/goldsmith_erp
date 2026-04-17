// Scanner API client — thin named-function wrappers around NetworkTransport.
//
// Purpose: give places that want a plain function-call ergonomics an import
// path that matches the rest of the api/ layer. The source of truth remains
// NetworkTransport (lib/network-transport.ts); these wrappers construct a
// singleton instance and delegate.
//
// `searchEntities` and `logScanBatch` aren't part of the core Transport
// interface (they're convenience surface on top of the backend router), so
// they use apiClient directly.

import apiClient from './client';
import { NetworkTransport } from '../lib/network-transport';
import type {
  BatchLogResponse,
  ResolveResponse,
  ScanContext,
  ScanEvent,
  ScanLogRead,
} from '../types/scanner';

// Singleton — Transport is stateless, so one instance is fine.
const transport = new NetworkTransport();

/**
 * Canonicalise + resolve a raw scan payload against the backend.
 * Returns the role-filtered ResolveResponse.
 *
 * Most callers should prefer constructing a ScannerRouter (lib/scan-router.ts)
 * with an AliasResolver + Transport injected. Use this wrapper only when you
 * know you want the raw transport-level call without alias lookup.
 */
export async function resolvePayload(
  rawPayload: string,
  context: ScanContext,
): Promise<ResolveResponse> {
  return transport.resolve(rawPayload, context);
}

/** Log a single scan event (fire-and-forget from the UI side). */
export async function logScan(event: ScanEvent): Promise<void> {
  return transport.logScan(event);
}

/**
 * Log a batch of scan events — used by the offline-queue flush in V1.1.5+,
 * and by the legacy `localStorage('last_scanned_orders')` migration in Slice 12.
 * Honors idempotency per-row on the server side.
 *
 * The batch endpoint requires the Slice-2 Idempotency header pair; we
 * auto-generate them when the caller doesn't care (legacy migration is the
 * primary caller and simply wants one-shot delivery).
 */
export async function logScanBatch(
  events: ScanEvent[],
): Promise<BatchLogResponse> {
  const { data } = await apiClient.post<BatchLogResponse>(
    '/scan/log/batch',
    { events },
    {
      headers: {
        'Idempotency-Key': crypto.randomUUID(),
        'X-Client-Created-At': new Date().toISOString(),
      },
    },
  );
  return data;
}

/**
 * Fetch the caller's recent scan history. Slice 12 — backs the "Letzte Scans"
 * list on ScannerPage.
 *
 * Only the JWT user's own history is accessible in V1.1 — the `user_id`
 * query param is a fixed `"me"` sentinel on the server side.
 */
export async function getScanLogHistory(
  limit: number = 20,
): Promise<ScanLogRead[]> {
  const { data } = await apiClient.get<ScanLogRead[]>('/scan/log', {
    params: { user_id: 'me', limit },
  });
  return data;
}

/**
 * Multi-entity search for UnknownCodeModal (V1.2) and for generic search
 * boxes that want to traverse orders/materials/customers in one call.
 *
 * V1.1 scope: the endpoint exists (Slice 4) but only a few UI consumers
 * land in V1.1. Typed loosely (`unknown[]`) until V1.2 pins the result
 * schema per entity type.
 */
export async function searchEntities(
  query: string,
  types?: string[],
): Promise<unknown[]> {
  const { data } = await apiClient.get<unknown[]>('/scan/search', {
    params: {
      q: query,
      types: types && types.length > 0 ? types.join(',') : undefined,
    },
  });
  return data;
}
