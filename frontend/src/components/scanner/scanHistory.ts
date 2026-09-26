// Scan history helpers for ScannerPage (W4-03, extracted from the page).
//
//   * makeScanContext / detectDeviceType: the ScanContext sent with a resolve.
//   * formatScanTime / describeScanLog / describeAction: "Letzte Scans" rows.
//   * migrateLegacyScanHistory: one-shot import of the old
//     `last_scanned_orders` localStorage key via /scan/log/batch. On failure
//     the key stays for a retry on the next mount; malformed data is dropped.
import { logScanBatch } from '../../api/scanner';
import type { ScanContext, ScanEvent, ScanLogRead } from '../../types/scanner';
import type { ScanSource } from './QrCameraScanner';

const LEGACY_STORAGE_KEY = 'last_scanned_orders';
export const HISTORY_LIMIT = 20;

interface LegacyScanEntry {
  id: number;
  time: string;
}

/**
 * Build a minimal ScanContext payload. ScannerPage runs outside the
 * QuickActionModalV2 so the running-timer context is read from the global
 * TimeTrackingContext at call time.
 */
export function makeScanContext(
  source: ScanSource,
  currentLocation: string | null,
  runningEntryId: string | null,
  runningEntryOrderId: number | null,
): ScanContext {
  return {
    running_timer_id: runningEntryId,
    current_order_id: runningEntryOrderId,
    current_location: currentLocation,
    device_type: detectDeviceType(),
    input_source: source === 'camera' ? 'camera' : 'manual',
  };
}

function detectDeviceType(): 'mobile' | 'desktop' | 'tablet' {
  if (typeof navigator === 'undefined') return 'desktop';
  const ua = navigator.userAgent;
  if (/iPad/.test(ua) || (ua.includes('Mac') && 'ontouchend' in document)) {
    return 'tablet';
  }
  if (/Mobile|Android|iPhone/.test(ua)) return 'mobile';
  return 'desktop';
}

/**
 * Format a scanned-at ISO timestamp for the "Letzte Scans" list. Uses the
 * browser locale (de-DE preferred) but falls back to a stable ISO-like
 * representation if Intl is unavailable (e.g. very restrictive environments).
 */
export function formatScanTime(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('de-DE', {
      dateStyle: 'short',
      timeStyle: 'short',
    });
  } catch {
    return iso;
  }
}

/**
 * Render a human-readable label for a ScanLogRead row. Falls back to the
 * raw payload when resolution metadata is missing (unknown scans still
 * appear in history).
 */
export function describeScanLog(row: ScanLogRead): string {
  if (row.resolved_type && row.resolved_id) {
    const type = row.resolved_type.toUpperCase();
    return `${type}:${row.resolved_id}`;
  }
  return row.raw_payload;
}

/** German past-tense labels for the action ids the scan log records. */
const ACTION_LABELS: Readonly<Record<string, string>> = {
  scan_only: 'Nur gescannt',
  unrecognised: 'Nicht erkannt',
  resolve_failed: 'Scan fehlgeschlagen',
  log_only: 'Erfasst',
  start_timer: 'Timer gestartet',
  stop_timer: 'Timer gestoppt',
  switch_timer: 'Timer gewechselt',
  change_status: 'Status weiter',
  advance_repair: 'Status weiter',
  handover: 'Übergabe',
  change_location: 'Standort gesetzt',
  switch_activity: 'Aktivität gewechselt',
  log_interruption: 'Unterbrechung erfasst',
  take_photo: 'Foto aufgenommen',
  print_label: 'Etikett gedruckt',
  open_entity: 'Geöffnet',
  consume_material: 'Material entnommen',
  punzierung_check: 'Punzierung geprüft',
  legacy_migration: 'Übernommen',
};

const RESULT_SUFFIX: Readonly<Record<string, string>> = {
  failed: ' – fehlgeschlagen',
  cancelled: ' – abgebrochen',
};

/** German label for a logged action id plus its result (Scan-Verlauf). */
export function describeActionId(
  actionTaken: string | null | undefined,
  actionResult?: string | null,
): string {
  const label =
    actionTaken !== null && actionTaken !== undefined && actionTaken.length > 0
      ? (ACTION_LABELS[actionTaken] ?? actionTaken)
      : 'Nur gescannt';
  return `${label}${actionResult ? (RESULT_SUFFIX[actionResult] ?? '') : ''}`;
}

/**
 * Describe the action taken on a scan for the history row subtitle.
 * `null` means we render no subtitle (e.g. a scan without an action).
 */
export function describeAction(row: ScanLogRead): string | null {
  if (row.action_taken !== null && row.action_taken.length > 0) {
    return ACTION_LABELS[row.action_taken] ?? row.action_taken;
  }
  if (row.resolution_path === 'unknown') {
    return 'Nicht erkannt';
  }
  return null;
}

/**
 * Migrate the legacy ``last_scanned_orders`` localStorage key into the
 * backend ``scan_logs`` table via the batch endpoint.
 *
 * Grace rules (plan §Slice 12):
 *   * If the POST fails (offline, 5xx), localStorage is NOT cleared so the
 *     next page load retries.
 *   * If the POST succeeds OR the storage blob is malformed, the key is
 *     removed (malformed entries are not worth re-attempting).
 *
 * Returns true when a migration attempt was actually made (for tests).
 */
export async function migrateLegacyScanHistory(): Promise<boolean> {
  let raw: string | null;
  try {
    raw = localStorage.getItem(LEGACY_STORAGE_KEY);
  } catch {
    return false;
  }
  if (raw === null) return false;

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    // Malformed — strip it so we don't retry forever.
    try {
      localStorage.removeItem(LEGACY_STORAGE_KEY);
    } catch {
      // ignore
    }
    return false;
  }

  if (!Array.isArray(parsed) || parsed.length === 0) {
    try {
      localStorage.removeItem(LEGACY_STORAGE_KEY);
    } catch {
      // ignore
    }
    return false;
  }

  const events: ScanEvent[] = [];
  for (const entry of parsed as LegacyScanEntry[]) {
    if (
      typeof entry !== 'object' ||
      entry === null ||
      typeof (entry as LegacyScanEntry).id !== 'number'
    ) {
      continue;
    }
    events.push({
      raw_payload: `ORDER:${(entry as LegacyScanEntry).id}`,
      resolved_type: 'order',
      resolved_id: String((entry as LegacyScanEntry).id),
      resolution_path: 'prefix',
      action_taken: 'legacy_migration',
      offline_queued: false,
      idempotency_key: crypto.randomUUID(),
    });
  }

  if (events.length === 0) {
    try {
      localStorage.removeItem(LEGACY_STORAGE_KEY);
    } catch {
      // ignore
    }
    return false;
  }

  try {
    await logScanBatch(events);
    try {
      localStorage.removeItem(LEGACY_STORAGE_KEY);
    } catch {
      // ignore
    }
    return true;
  } catch {
    // Leave the legacy key in place — retry on next mount.
    return false;
  }
}
