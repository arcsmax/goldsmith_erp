// NetworkTransport — V1.1 axios-backed Transport.
//
// Every mutating call auto-generates an Idempotency-Key header (v4 UUID via
// `crypto.randomUUID()`) when the caller doesn't supply one. This is the
// non-negotiable M1 contract — scan-originated mutations MUST be idempotent
// from day one so the V1.1.5 offline-queue swap is drop-in.
//
// X-Client-Created-At is attached to every action execution for clock-skew
// debugging (backend rejects entries older than 30 days per Slice 2 gate).
//
// The apiClient is already baseURL'd to `/api/v1`, so all paths are relative
// to that — `/scan/resolve`, `/scan/log`, `/scan/action/:id`.

import apiClient from '../api/client';
import type {
  ActionExecution,
  ActionResult,
  ResolveResponse,
  ScanContext,
  ScanEvent,
  Transport,
} from '../types/scanner';

/**
 * Generate a v4 UUID using the Web Crypto API.
 *
 * `crypto.randomUUID()` is available in every browser we target (Chrome 92+,
 * Safari 15.4+, Firefox 95+) and is cryptographically secure. If a future
 * target lacks support we will inject a polyfill — we deliberately do NOT
 * add the `uuid` npm dep just for this, keeping the scanner bundle lean (M7).
 */
function makeIdempotencyKey(): string {
  return crypto.randomUUID();
}

export class NetworkTransport implements Transport {
  async resolve(
    rawPayload: string,
    context: ScanContext,
  ): Promise<ResolveResponse> {
    const { data } = await apiClient.post<ResolveResponse>('/scan/resolve', {
      raw_payload: rawPayload,
      context,
    });
    return data;
  }

  async logScan(event: ScanEvent): Promise<void> {
    await apiClient.post('/scan/log', event);
  }

  async executeAction(action: ActionExecution): Promise<ActionResult> {
    // Every mutating action gets an idempotency key. If the caller already
    // generated one (e.g. offline queue replaying a buffered action) we use
    // it as-is so retries stay idempotent across client restarts.
    const idempotencyKey = action.idempotency_key || makeIdempotencyKey();

    const { data } = await apiClient.post<ActionResult>(
      `/scan/action/${action.action_id}`,
      {
        entity_type: action.entity_type,
        entity_id: action.entity_id,
        payload: action.payload,
      },
      {
        headers: {
          'Idempotency-Key': idempotencyKey,
          'X-Client-Created-At': new Date().toISOString(),
        },
      },
    );
    return data;
  }
}
