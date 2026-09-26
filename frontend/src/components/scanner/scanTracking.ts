// Scan tracking (2026-09 audit, SC-01): every scan is on record.
//
// The owner's rule: a lost piece's history must show who scanned it last,
// where, and what they did — a scan without an action too. So:
//
//   1. recordScan() runs right after every decode (camera, hand scanner,
//      manual entry), BEFORE the action sheet opens. It writes one
//      scan_logs row: action_taken "scan_only", or "unrecognised" (the
//      server answered resolved=false), or "resolve_failed" (the resolve
//      call itself failed — the scan still happened).
//   2. recordAction() runs when the user picks an action in the sheet. It
//      writes a SECOND row (the table is append-only and partitioned; rows
//      are never updated) with action_taken=<action id> and, in the
//      context, parent_scan_id (the first row) and action_result
//      ok / failed / cancelled.
//   3. Who = the JWT user (server side). When = server time. Where = the
//      device's bench location (lib/deviceId.ts), else the station set on
//      the ScannerContext, else the running timer's location, else null.
//      Which tablet = the per-device id.
//
// A failed POST never blocks the goldsmith: the event goes to a small
// localStorage queue and is sent with the next successful scan (or when the
// scanner page mounts) via POST /scan/log/batch. Idempotency keys make the
// retries safe.
import { logScanBatch, logScanEvent } from '../../api/scanner';
import { getDeviceId, getDeviceLocationEntry, normaliseLocation } from '../../lib/deviceId';
import { logError } from '../../lib/logError';
import type { ResolveResponse, ScanContext, ScanEvent } from '../../types/scanner';

export type TrackedSource = 'camera' | 'usb_hid' | 'manual';
export type ActionResult = 'ok' | 'failed' | 'cancelled';

/** action_taken values of the first row (the scan itself). */
export const SCAN_ONLY = 'scan_only';
export const UNRECOGNISED = 'unrecognised';
export const RESOLVE_FAILED = 'resolve_failed';

const QUEUE_KEY = 'scan_log_queue';
const MAX_QUEUE = 100;

export interface RunningTimerInfo {
  id: string;
  order_id: number;
  location?: string | null;
}

export interface LocationSources {
  /** ScannerContext.currentLocation (a station scan, 12h TTL). */
  stationLocation?: string | null;
  runningEntry?: RunningTimerInfo | null;
}

/** A logged scan: the base event (for the action row) and its row id. */
export interface TrackedScan {
  event: ScanEvent;
  scanId: string | null;
}

export interface ScanLocation {
  name: string | null;
  /** workshop_locations id when the location came from the device setting. */
  id: number | null;
}

/** Where this scan happened: device bench → station → running timer → null. */
export function resolveScanLocation(sources: LocationSources): ScanLocation {
  const device = getDeviceLocationEntry();
  if (device !== null) return { name: device.name, id: device.id };
  const name =
    normaliseLocation(sources.stationLocation) ??
    normaliseLocation(sources.runningEntry?.location) ??
    null;
  return { name, id: null };
}

export function detectDeviceType(): 'mobile' | 'desktop' | 'tablet' {
  if (typeof navigator === 'undefined') return 'desktop';
  const ua = navigator.userAgent;
  if (/iPad/.test(ua) || (ua.includes('Mac') && 'ontouchend' in document)) {
    return 'tablet';
  }
  if (/Mobile|Android|iPhone/.test(ua)) return 'mobile';
  return 'desktop';
}

/** The ScanContext sent with resolve and with every log row. */
export function buildScanContext(source: TrackedSource, sources: LocationSources): ScanContext {
  const location = resolveScanLocation(sources);
  return {
    running_timer_id: sources.runningEntry?.id ?? null,
    current_order_id: sources.runningEntry?.order_id ?? null,
    current_location: location.name,
    ...(location.id !== null ? { location_id: location.id } : {}),
    device_type: detectDeviceType(),
    input_source: source,
    device_id: getDeviceId(),
  };
}

function firstRowAction(response: ResolveResponse | null): string {
  if (response === null) return RESOLVE_FAILED;
  return response.resolved ? SCAN_ONLY : UNRECOGNISED;
}

/** The first-row event for a decode (pure; exported for tests). */
export function buildScanEvent(
  payload: string,
  response: ResolveResponse | null,
  context: ScanContext,
): ScanEvent {
  const isResolved = response !== null && response.resolved;
  return {
    raw_payload: payload,
    resolved_type: isResolved && response.entity_type ? response.entity_type : undefined,
    resolved_id:
      isResolved && response.entity_id !== null ? String(response.entity_id) : undefined,
    resolution_path: response?.resolution_path ?? 'unknown',
    action_taken: firstRowAction(response),
    context: { ...context },
    offline_queued: false,
    idempotency_key: crypto.randomUUID(),
  };
}

// ---------------------------------------------------------------------------
// Offline queue
// ---------------------------------------------------------------------------

function readQueue(): ScanEvent[] {
  try {
    const raw = localStorage.getItem(QUEUE_KEY);
    if (raw === null) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as ScanEvent[]) : [];
  } catch {
    return [];
  }
}

function writeQueue(events: readonly ScanEvent[]): void {
  try {
    if (events.length === 0) localStorage.removeItem(QUEUE_KEY);
    else localStorage.setItem(QUEUE_KEY, JSON.stringify(events.slice(-MAX_QUEUE)));
  } catch {
    // Storage full / private mode: the event is lost, the error is logged.
    logError('scanTracking.queue', new Error('Scan-Warteschlange nicht speicherbar'));
  }
}

function enqueue(event: ScanEvent): void {
  writeQueue([...readQueue(), { ...event, offline_queued: true }]);
}

/** Number of scan events still waiting to be sent (for the UI hint). */
export function pendingScanCount(): number {
  return readQueue().length;
}

let isFlushing = false;

/** Send queued scan events in one batch; keeps them on failure. */
export async function flushScanQueue(): Promise<void> {
  if (isFlushing) return;
  const queued = readQueue();
  if (queued.length === 0) return;
  isFlushing = true;
  try {
    await logScanBatch(queued.slice(0, MAX_QUEUE));
    writeQueue(readQueue().slice(queued.length));
  } catch (err) {
    logError('scanTracking.flush', err);
  } finally {
    isFlushing = false;
  }
}

async function send(event: ScanEvent): Promise<string | null> {
  try {
    const row = await logScanEvent(event);
    void flushScanQueue();
    return row.id;
  } catch (err) {
    logError('scanTracking.send', err);
    enqueue(event);
    return null;
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Log a decode right away (never throws). */
export async function recordScan(
  payload: string,
  response: ResolveResponse | null,
  context: ScanContext,
): Promise<TrackedScan> {
  const event = buildScanEvent(payload, response, context);
  const scanId = await send(event);
  return { event, scanId };
}

/** Log the action picked after a scan as a second row (never throws). */
export async function recordAction(
  tracked: TrackedScan,
  actionId: string,
  result: ActionResult,
  location?: { name: string | null; id: number | null },
): Promise<void> {
  const baseContext = tracked.event.context ?? {};
  const event: ScanEvent = {
    ...tracked.event,
    action_taken: actionId,
    idempotency_key: crypto.randomUUID(),
    offline_queued: false,
    context: {
      ...baseContext,
      ...(tracked.scanId !== null ? { parent_scan_id: tracked.scanId } : {}),
      action_result: result,
      ...(location !== undefined
        ? { current_location: location.name, location_id: location.id ?? undefined }
        : {}),
    },
  };
  await send(event);
}

// ---------------------------------------------------------------------------
// Hand-off from ScannerPage to the ScanOverlay sheet
// ---------------------------------------------------------------------------
//
// ScannerPage resolves and logs the scan itself, then opens the overlay.
// The overlay resets its state on open, so it takes the scan from here
// (once) instead of from ScannerContext.lastScan, which also holds older
// scans. Before this, a ScannerPage scan opened the camera, not the sheet.

export interface HandedOffScan {
  response: ResolveResponse;
  tracked: TrackedScan | null;
  payload: string;
}

let handedOff: HandedOffScan | null = null;

export function handOffScan(scan: HandedOffScan): void {
  handedOff = scan;
}

/** The scan handed off by the page, once; null when there is none. */
export function takeHandedOffScan(): HandedOffScan | null {
  const scan = handedOff;
  handedOff = null;
  return scan;
}
