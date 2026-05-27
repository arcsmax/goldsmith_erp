// ScannerPage — Slice 12 upgrade.
//
// Replaces the legacy inline-ORDER-parser implementation with the V1.1
// scanner infrastructure:
//
//   * QrCameraScanner component (Slice 8) for camera-based capture.
//   * Manual text input routed through ScannerRouter.resolve() (Slice 7),
//     preserving USB-HID keyboard-wedge scanners that type+Enter into
//     focused inputs.
//   * "Letzte Scans" list fed by ``GET /api/v1/scan/log`` (Slice 12 backend
//     endpoint) — no more localStorage history.
//   * Resolved scans flow through ScannerContext.setLastScan → the globally
//     mounted ScanOverlay (already rendered by MainLayout) opens and drives
//     the QuickActionModalV2 / ActionHandlers flow.
//
// One-shot legacy migration: on first mount, read the old
// ``last_scanned_orders`` localStorage key and POST the entries as
// ``resolution_path='import'`` rows via ``/scan/log/batch``. On success we
// clear the key; on failure we leave it for a retry on the next mount.
//
// Strings: 100% German.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useScannerContext } from '../contexts/ScannerContext';
import { useTimeTracking } from '../contexts/TimeTrackingContext';
import { NetworkAliasResolver } from '../lib/network-alias-resolver';
import { NetworkTransport } from '../lib/network-transport';
import { ScannerRouter } from '../lib/scan-router';
import { QrCameraScanner } from '../components/scanner/QrCameraScanner';
import type { ScanSource } from '../components/scanner/QrCameraScanner';
import { getScanLogHistory, logScanBatch } from '../api/scanner';
import type {
  ResolveResponse,
  ScanContext,
  ScanEvent,
  ScanLogRead,
} from '../types/scanner';
import '../styles/scanner.css';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const LEGACY_STORAGE_KEY = 'last_scanned_orders';
const HISTORY_LIMIT = 20;

interface LegacyScanEntry {
  id: number;
  time: string;
}

/**
 * Build a minimal ScanContext payload. ScannerPage runs outside the
 * QuickActionModalV2 so the running-timer context is read from the global
 * TimeTrackingContext at call time.
 */
function makeScanContext(
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
function formatScanTime(iso: string): string {
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
function describeScanLog(row: ScanLogRead): string {
  if (row.resolved_type && row.resolved_id) {
    const type = row.resolved_type.toUpperCase();
    return `${type}:${row.resolved_id}`;
  }
  return row.raw_payload;
}

/**
 * Describe the action taken on a scan for the history row subtitle.
 * `null` means we render no subtitle (e.g. an unknown scan).
 */
function describeAction(row: ScanLogRead): string | null {
  if (row.action_taken !== null && row.action_taken.length > 0) {
    return row.action_taken;
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
async function migrateLegacyScanHistory(): Promise<boolean> {
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
      resolution_path: 'import',
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

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const ScannerPage: React.FC = () => {
  const navigate = useNavigate();
  const {
    setLastScan,
    setInputSource,
    openScanner,
    currentLocation,
  } = useScannerContext();
  const { runningEntry } = useTimeTracking();

  const [scanInput, setScanInput] = useState<string>('');
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [cameraActive, setCameraActive] = useState<boolean>(false);

  const [history, setHistory] = useState<ScanLogRead[]>([]);
  const [historyLoading, setHistoryLoading] = useState<boolean>(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const manualInputRef = useRef<HTMLInputElement | null>(null);
  const migrationRan = useRef<boolean>(false);

  // -------------------------------------------------------------------------
  // Router — one instance per component lifetime. NetworkTransport wraps
  // the shared apiClient which already authenticates via HttpOnly cookies.
  // -------------------------------------------------------------------------
  const router = useMemo<ScannerRouter>(
    () => new ScannerRouter(new NetworkAliasResolver(), new NetworkTransport()),
    [],
  );

  // -------------------------------------------------------------------------
  // Load history + run legacy migration exactly once on mount
  // -------------------------------------------------------------------------

  const loadHistory = useCallback(async (): Promise<void> => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const rows = await getScanLogHistory(HISTORY_LIMIT);
      setHistory(rows);
    } catch {
      setHistoryError(
        'Scan-Verlauf konnte nicht geladen werden. Bitte spaeter erneut versuchen.',
      );
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    if (migrationRan.current) return;
    migrationRan.current = true;

    // Kick off migration then history fetch. Migration is fire-and-forget
    // — if it succeeds the backend history will now include the imported
    // rows; if it fails silently we still show whatever the backend has.
    void migrateLegacyScanHistory().finally(() => {
      void loadHistory();
    });

    // Auto-focus the manual input on mount so USB HID scanners (which type
    // and press Enter) land in the input without a tap.
    manualInputRef.current?.focus();
  }, [loadHistory]);

  // -------------------------------------------------------------------------
  // Scan handling — both camera and manual paths converge here
  // -------------------------------------------------------------------------

  const handleScan = useCallback(
    async (payload: string, source: ScanSource): Promise<void> => {
      const trimmed = payload.trim();
      if (trimmed.length === 0 || isScanning) return;

      setError(null);
      setIsScanning(true);
      setInputSource(source === 'camera' ? 'camera' : 'manual');
      // Pause the camera if it was running — resume on the next scan click.
      setCameraActive(false);

      try {
        const ctx = makeScanContext(
          source,
          currentLocation,
          runningEntry?.id ?? null,
          runningEntry?.order_id ?? null,
        );
        const response: ResolveResponse = await router.resolve(trimmed, ctx);
        // Publish through the global context so the always-mounted
        // ScanOverlay renders QuickActionModalV2 on top. Opening the
        // overlay last ensures the modal sees `lastScan` already set.
        setLastScan(response);
        openScanner();

        // Clear the manual input so the next scan starts fresh.
        setScanInput('');

        // Optimistic refresh — the scan was just logged server-side by
        // the resolve/action flow inside the overlay, so refreshing
        // history gives the user immediate feedback.
        void loadHistory();
      } catch (err) {
        const message =
          err instanceof Error && err.message.length > 0
            ? err.message
            : 'Scan konnte nicht verarbeitet werden.';
        setError(message);
      } finally {
        setIsScanning(false);
      }
    },
    [
      isScanning,
      setInputSource,
      currentLocation,
      runningEntry,
      router,
      setLastScan,
      openScanner,
      loadHistory,
    ],
  );

  const handleManualSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>): void => {
      event.preventDefault();
      if (scanInput.trim().length === 0) return;
      void handleScan(scanInput, 'manual');
    },
    [scanInput, handleScan],
  );

  const handleCameraToggle = useCallback((): void => {
    setCameraActive((prev) => !prev);
    setError(null);
  }, []);

  const handleHistoryItemClick = useCallback(
    (row: ScanLogRead): void => {
      // Re-resolve the raw payload so the user can re-open the QuickAction
      // flow on a recent entity without needing to scan again. This uses
      // the same resolve pipeline rather than a direct navigate so role
      // filtering and quick-action computation always run server-side.
      void handleScan(row.raw_payload, 'manual');
    },
    [handleScan],
  );

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="scanner-container" data-testid="scanner-page">
      <div className="scanner-box">
        <div className="scanner-icon" aria-hidden="true">
          QR
        </div>
        <h1>QR / Barcode Scanner</h1>
        <p className="scanner-subtitle">
          Scannen Sie einen QR-Code mit der Kamera, oder geben Sie die
          Kennung manuell ein.
        </p>

        {/* Camera section */}
        <section
          className="scanner-camera-section"
          aria-labelledby="scanner-camera-heading"
          data-testid="scanner-camera-section"
        >
          <h2 id="scanner-camera-heading" className="scanner-section-heading">
            Kamera
          </h2>
          {cameraActive ? (
            <QrCameraScanner active={cameraActive} onScan={handleScan} />
          ) : (
            <button
              type="button"
              className="btn-scan"
              onClick={handleCameraToggle}
              data-testid="scanner-camera-start"
            >
              Kamera starten
            </button>
          )}
          {cameraActive ? (
            <button
              type="button"
              className="btn-scan-secondary"
              onClick={handleCameraToggle}
              data-testid="scanner-camera-stop"
            >
              Kamera stoppen
            </button>
          ) : null}
        </section>

        {/* Manual input section */}
        <section
          className="scanner-manual-section"
          aria-labelledby="scanner-manual-heading"
        >
          <h2 id="scanner-manual-heading" className="scanner-section-heading">
            Manuelle Eingabe
          </h2>
          <form
            className="scan-input-group"
            onSubmit={handleManualSubmit}
            data-testid="scanner-manual-form"
          >
            <label htmlFor="scan-input" className="sr-only">
              Scan-Kennung eingeben
            </label>
            <input
              id="scan-input"
              ref={manualInputRef}
              type="text"
              inputMode="text"
              value={scanInput}
              onChange={(e) => setScanInput(e.target.value)}
              placeholder="z.B. ORDER:42 oder Auftragsnummer"
              className="scan-input"
              autoFocus
              disabled={isScanning}
              data-testid="scanner-manual-input"
            />
            <button
              type="submit"
              disabled={scanInput.trim().length === 0 || isScanning}
              className="btn-scan"
              data-testid="scanner-manual-submit"
            >
              {isScanning ? 'Laedt…' : 'Oeffnen'}
            </button>
          </form>
          {error !== null ? (
            <div className="scan-error" role="alert" data-testid="scanner-error">
              {error}
            </div>
          ) : null}
        </section>

        {/* Last scans — backed by GET /api/v1/scan/log */}
        <section
          className="last-scanned"
          aria-labelledby="scanner-history-heading"
          data-testid="scanner-history-section"
        >
          <h3
            id="scanner-history-heading"
            className="scanner-section-heading"
          >
            Letzte Scans
          </h3>
          {historyLoading ? (
            <p
              className="scanner-history-empty"
              data-testid="scanner-history-loading"
            >
              Verlauf wird geladen…
            </p>
          ) : historyError !== null ? (
            <p
              className="scanner-history-error"
              role="alert"
              data-testid="scanner-history-error"
            >
              {historyError}
            </p>
          ) : history.length === 0 ? (
            <p
              className="scanner-history-empty"
              data-testid="scanner-history-empty"
            >
              Noch keine Scans vorhanden.
            </p>
          ) : (
            <ul className="scanned-list" data-testid="scanner-history-list">
              {history.map((row) => {
                const subtitle = describeAction(row);
                return (
                  <li key={row.id} className="scanned-item-row">
                    <button
                      type="button"
                      className="scanned-item"
                      onClick={() => handleHistoryItemClick(row)}
                      data-testid={`scanner-history-item-${row.id}`}
                    >
                      <span className="scanned-id">{describeScanLog(row)}</span>
                      <span className="scanned-time">
                        {formatScanTime(row.scanned_at)}
                      </span>
                      {subtitle !== null ? (
                        <span className="scanned-action">{subtitle}</span>
                      ) : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* Info Box */}
        <div className="scan-info">
          <h3>So funktioniert&apos;s:</h3>
          <ol>
            <li>QR-Code mit der Kamera scannen oder Kennung eingeben.</li>
            <li>
              USB-Handscanner tippen die Kennung automatisch in das
              Eingabefeld.
            </li>
            <li>Schnellaktionen oeffnen sich automatisch nach dem Scan.</li>
          </ol>
        </div>
      </div>
    </div>
  );
};

// Named-export kept for compatibility with existing App.tsx lazy import.
export default ScannerPage;

// Exposed for unit tests — not part of the public component API.
export { migrateLegacyScanHistory as __migrateLegacyScanHistoryForTests };
