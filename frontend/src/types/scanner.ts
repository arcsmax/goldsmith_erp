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
  device_type: 'mobile' | 'desktop' | 'tablet';
  input_source: 'camera' | 'usb_hid' | 'manual';
  client_version?: string;
}

export interface ResolvedEntity {
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

export interface ResolveResponse {
  resolved: boolean;
  resolution_path: 'prefix' | 'alias' | 'numeric_fallback' | 'unknown';
  entity_type: string | null;
  entity_id: number | null;
  entity: ResolvedEntity | null;
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
  lookup(externalCode: string): Promise<ResolvedEntity | null>;
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
  accepted: number;
  duplicates: number;
  rejected: number;
  errors?: Array<{ index: number; reason: string }>;
}
