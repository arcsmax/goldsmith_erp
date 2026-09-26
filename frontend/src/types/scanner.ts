// Scanner-specific TypeScript interfaces (Slice 7 of V1.1 QR/Barcode workflow).
//
// Authoritative source: docs/superpowers/plans/qr-barcode-workflow/V1.1-IMPLEMENTATION-PLAN.md §2
// and docs/superpowers/specs/2026-04-16-qr-barcode-workflow-design-v2.md §10.a.
//
// Design principle: async-first, injectable dependencies from Phase 1. In V1.1 the
// AliasResolver is a no-op stub; V1.1.5+ swaps in an IndexedDB-backed implementation
// without touching the ScannerRouter.

export interface ScanContext {
  running_timer_id: string | null;
  current_order_id: number | null;
  current_location: string | null;
  /** W8 workshop location id; the server names it in current_location. */
  location_id?: number;
  device_type: 'mobile' | 'desktop' | 'tablet';
  input_source: 'camera' | 'usb_hid' | 'manual';
  client_version?: string;
  /** Scan tracking (2026-09): the bench tablet (lib/deviceId.ts). */
  device_id?: string;
  /** On an action row: the scan row this action follows up. */
  parent_scan_id?: string;
  /** On an action row: how the action ended. */
  action_result?: 'ok' | 'failed' | 'cancelled';
}

/**
 * Shape returned by the (currently stubbed) alias lookup — distinct from
 * `ResolveResponse.entity`. See `AliasResolver` below.
 */
export interface AliasedEntity {
  entity_type: string;
  entity_id: number;
  data: Record<string, unknown>;
}

export interface ActionItem {
  id: string;
  label: string;
  icon: string;
  primary: boolean;
}

/**
 * Server response for `POST /scan/resolve` (backend `ResolveResponse` in
 * `src/goldsmith_erp/models/scanner.py`, generated type
 * `components["schemas"]["ResolveResponse"]` in `api/generated/schema.d.ts`).
 *
 * `entity_type` / `entity_id` live at the TOP level, alongside `entity`.
 * `entity` is the role-filtered projection of the underlying row itself
 * (e.g. `{ id, title, status, ... }`) — NOT a wrapper carrying its own
 * `entity_type` / `entity_id` / `data` fields.
 */
export interface ResolveResponse {
  resolved: boolean;
  resolution_path: 'prefix' | 'alias' | 'numeric_fallback' | 'unknown';
  entity_type: string | null;
  entity_id: number | null;
  entity: Record<string, unknown> | null;
  actions: ActionItem[];
  status_hint: string | null;
}

export interface ScanEvent {
  raw_payload: string;
  resolved_type?: string;
  resolved_id?: string;
  resolution_path?: string;
  action_taken?: string;
  context?: Partial<ScanContext>;
  offline_queued?: boolean;
  idempotency_key?: string;
  client_tap_at?: string; // ISO 8601
  fallback_reason?: 'camera_denied' | 'camera_unavailable' | 'user_choice';
}

export interface ActionExecution {
  action_id: string;
  entity_type: string;
  entity_id: number;
  payload: Record<string, unknown>;
  idempotency_key: string;
}

export interface ActionResult {
  success: boolean;
  error?: string;
  data?: Record<string, unknown>;
}

export interface AliasResolver {
  lookup(externalCode: string): Promise<AliasedEntity | null>;
}

export interface Transport {
  resolve(rawPayload: string, context: ScanContext): Promise<ResolveResponse>;
  logScan(event: ScanEvent): Promise<void>;
  executeAction(action: ActionExecution): Promise<ActionResult>;
}

/**
 * Batch-log response shape (mirrors backend `BatchLogResponse` schema).
 * Returned by `POST /scan/log/batch` — per-row idempotency accounting.
 */
export interface BatchLogResponse {
  accepted?: number;
  duplicates?: number;
  rejected?: number;
  // Backend currently serialises as `ingested/deduplicated/rejected/reasons`;
  // the V1.1 frontend accepts either shape for resilience to field renames.
  ingested?: number;
  deduplicated?: number;
  reasons?: string[];
  errors?: Array<{ index: number; reason: string }>;
}

/**
 * Shape of a ``scan_logs`` row returned by ``GET /api/v1/scan/log`` (Slice 12).
 * Backs the "Letzte Scans" list on the ScannerPage.
 */
export interface ScanLogRead {
  id: string;
  scanned_at: string; // ISO 8601
  user_id: number;
  raw_payload: string;
  resolved_type: string | null;
  resolved_id: string | null;
  resolution_path: string | null;
  action_taken: string | null;
  offline_queued: boolean;
  synced_at: string | null;
}
