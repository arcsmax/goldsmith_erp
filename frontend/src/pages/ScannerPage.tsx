// ScannerPage — bench mode (W4-03, UI-UX-PLAYBOOK 5.5).
//
// One screen, one job: get to the job bag's order. Camera start, manual
// number entry and every "Letzte Scans" row are single 56px taps. A
// resolved scan goes through ScannerContext.setLastScan → the always-mounted
// ScanOverlay opens with QuickActionModalV2 and its big action buttons.
//
//   * QrCameraScanner (Slice 8) only after a tap on "Kamera starten"; the
//     camera never opens by itself.
//   * Manual entry routes through ScannerRouter.resolve() (Slice 7) and
//     keeps USB/HID keyboard-wedge scanners working (focus on mount).
//   * "Letzte Scans" is the query scanHistoryQuery (GET /scan/log); a scan
//     invalidates it. The one-shot legacy import of `last_scanned_orders`
//     runs first (components/scanner/scanHistory.ts).
//   * The running timer (TimeTrackingContext) shows with its pause state.
//   * The Werkbank-Modus toggle sits in the header (per device).
//   * Scan tracking (2026-09 audit, SC-01): every resolve (camera, hand
//     scanner, typed number, "Letzte Scans" re-open) is logged right away
//     (components/scanner/scanTracking.ts) with this device's id and bench
//     location ("Standort dieses Geräts", chosen once per device), then
//     handed to the overlay's action sheet. ADMIN / GOLDSMITH also get the
//     cross-piece Scan-Verlauf search (pages/admin/ScanHistoryPanel.tsx).
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';

import { queryKeys } from '../api/queryKeys';
import { scanHistoryQuery } from '../api/scanner';
import { BenchModeToggle } from '../components/scanner/BenchModeToggle';
import { QrCameraScanner, type ScanSource } from '../components/scanner/QrCameraScanner';
import { DeviceLocationSetting } from '../components/scanner/DeviceLocationSetting';
import {
  HISTORY_LIMIT,
  describeAction,
  describeScanLog,
  formatScanTime,
  migrateLegacyScanHistory,
} from '../components/scanner/scanHistory';
import {
  buildScanContext,
  flushScanQueue,
  handOffScan,
  recordScan,
} from '../components/scanner/scanTracking';
import { useOptionalAuth } from '../contexts/AuthContext';
import { canCreateOrders } from '../lib/roles';
import { ScanHistoryPanel } from './admin/ScanHistoryPanel';
import { useScannerContext } from '../contexts/ScannerContext';
import { useTimeTracking } from '../contexts/TimeTrackingContext';
import { getErrorMessage } from '../lib/errors';
import { NetworkAliasResolver } from '../lib/network-alias-resolver';
import { NetworkTransport } from '../lib/network-transport';
import { ScannerRouter } from '../lib/scan-router';
import { Button, EmptyState, Field, Icon, PageHeader } from '../ui';
import { StatusBadge } from '../ui/StatusBadge';
import type { ResolveResponse, ScanLogRead } from '../types/scanner';
import '../styles/scanner.css';

/** A router error (plain Error, German text) keeps its message; HTTP errors are mapped. */
function scanErrorMessage(err: unknown): string {
  const isHttp = typeof err === 'object' && err !== null && ('response' in err || 'isAxiosError' in err);
  if (!isHttp && err instanceof Error && err.message.length > 0) return err.message;
  return getErrorMessage(err, 'Scan konnte nicht verarbeitet werden.');
}

/** Run the legacy import once per mount, then let the history query load. */
function useLegacyMigration(): boolean {
  const [isDone, setIsDone] = useState(false);
  const hasRun = useRef(false);
  useEffect(() => {
    if (hasRun.current) return;
    hasRun.current = true;
    void migrateLegacyScanHistory().finally(() => setIsDone(true));
  }, []);
  return isDone;
}

const ScanHistory: React.FC<{
  query: UseQueryResult<ScanLogRead[]>;
  isScanning: boolean;
  onReopen: (row: ScanLogRead) => void;
  onStartCamera: () => void;
}> = ({ query, isScanning, onReopen, onStartCamera }) => {
  if (query.isPending) {
    return (
      <p className="scanner-history-note" role="status" data-testid="scanner-history-loading">
        Verlauf wird geladen…
      </p>
    );
  }
  if (query.isError) {
    return (
      <div className="scanner-history-error" data-testid="scanner-history-error">
        <p role="alert">Scan-Verlauf konnte nicht geladen werden. Bitte später erneut versuchen.</p>
        <Button variant="secondary" icon="refresh" onClick={() => void query.refetch()}>
          Erneut versuchen
        </Button>
      </div>
    );
  }
  if (query.data.length === 0) {
    return (
      <div data-testid="scanner-history-empty">
        <EmptyState
          icon="scan"
          title="Noch keine Scans vorhanden"
          body="Scannen Sie den QR-Code auf der Auftragstüte."
          headingLevel={3}
          action={
            <Button size="lg" icon="camera" onClick={onStartCamera}>
              Kamera starten
            </Button>
          }
        />
      </div>
    );
  }
  return (
    <ul className="scanner-history-list" data-testid="scanner-history-list">
      {query.data.map((row) => {
        const subtitle = describeAction(row);
        return (
          <li key={row.id}>
            <button
              type="button"
              className="scanner-history-item"
              onClick={() => onReopen(row)}
              disabled={isScanning}
              data-testid={`scanner-history-item-${row.id}`}
            >
              <span className="scanner-history-item__id">{describeScanLog(row)}</span>
              <span className="scanner-history-item__meta">
                <time dateTime={row.scanned_at}>{formatScanTime(row.scanned_at)}</time>
                {subtitle !== null && <span> · {subtitle}</span>}
              </span>
              <Icon name="arrow-right" className="scanner-history-item__chevron" />
            </button>
          </li>
        );
      })}
    </ul>
  );
};

export const ScannerPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { setLastScan, setInputSource, openScanner, currentLocation } = useScannerContext();
  const { runningEntry } = useTimeTracking();

  const [scanInput, setScanInput] = useState('');
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const manualInputRef = useRef<HTMLInputElement | null>(null);

  const auth = useOptionalAuth();
  // Mirrors the backend gate on GET /scan/history (ADMIN + GOLDSMITH).
  const canSearchScans = canCreateOrders(auth?.user?.role);

  const isMigrated = useLegacyMigration();

  // Scans that could not be sent earlier (offline) go out now.
  useEffect(() => {
    void flushScanQueue();
  }, []);
  const history = useQuery({ ...scanHistoryQuery(HISTORY_LIMIT), enabled: isMigrated });

  // One router per page lifetime; NetworkTransport uses the shared apiClient.
  const router = useMemo(
    () => new ScannerRouter(new NetworkAliasResolver(), new NetworkTransport()),
    [],
  );

  // USB/HID scanners type and press Enter: land them in the input.
  useEffect(() => {
    manualInputRef.current?.focus();
  }, []);

  const handleScan = useCallback(
    async (payload: string, source: ScanSource): Promise<void> => {
      const trimmed = payload.trim();
      if (trimmed.length === 0 || isScanning) return;
      setError(null);
      setIsScanning(true);
      setInputSource(source === 'camera' ? 'camera' : 'manual');
      setCameraActive(false);
      const ctx = buildScanContext(source === 'camera' ? 'camera' : 'manual', {
        stationLocation: currentLocation,
        runningEntry,
      });
      try {
        const response: ResolveResponse = await router.resolve(trimmed, ctx);
        // Logged before the sheet opens: a scan without an action counts.
        const tracked = await recordScan(trimmed, response, ctx);
        // The overlay opens straight on the action sheet for this scan.
        handOffScan({ response, tracked, payload: trimmed });
        setLastScan(response);
        openScanner();
        setScanInput('');
        void queryClient.invalidateQueries({ queryKey: queryKeys.scanLog.all });
      } catch (err) {
        console.error('Scan konnte nicht verarbeitet werden', { source, err });
        // The scan still happened: record it as resolve_failed.
        await recordScan(trimmed, null, ctx);
        setError(scanErrorMessage(err));
      } finally {
        setIsScanning(false);
      }
    },
    [isScanning, setInputSource, currentLocation, runningEntry, router, setLastScan, openScanner, queryClient],
  );

  const handleManualSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (scanInput.trim().length > 0) void handleScan(scanInput, 'manual');
  };

  const toggleCamera = (): void => {
    setCameraActive((prev) => !prev);
    setError(null);
  };

  return (
    <div className="scanner-page" data-testid="scanner-page">
      <PageHeader
        title="Scanner"
        meta="QR-Code auf der Auftragstüte scannen oder Nummer eintippen"
        secondaryActions={<BenchModeToggle />}
        stickyPrimary={false}
      />

      <DeviceLocationSetting />

      {runningEntry && (
        <p className="scanner-running" role="status">
          <Icon name="clock" />
          <span>
            Timer läuft: <strong>Auftrag #{runningEntry.order_id}</strong>
          </span>
          {runningEntry.is_paused && <StatusBadge kind="timeEntry" status="paused" size="lg" />}
        </p>
      )}

      <section
        className="scanner-section"
        aria-labelledby="scanner-camera-heading"
        data-testid="scanner-camera-section"
      >
        <h2 id="scanner-camera-heading">Kamera</h2>
        {cameraActive && <QrCameraScanner active={cameraActive} onScan={handleScan} />}
        <Button
          size="lg"
          block
          variant={cameraActive ? 'secondary' : 'primary'}
          icon={cameraActive ? 'close' : 'camera'}
          onClick={toggleCamera}
          data-testid={cameraActive ? 'scanner-camera-stop' : 'scanner-camera-start'}
        >
          {cameraActive ? 'Kamera stoppen' : 'Kamera starten'}
        </Button>
      </section>

      <section className="scanner-section" aria-labelledby="scanner-manual-heading">
        <h2 id="scanner-manual-heading">Nummer eintippen</h2>
        <form className="scanner-manual-form" onSubmit={handleManualSubmit} data-testid="scanner-manual-form">
          <Field
            label="Auftragsnummer oder Kennung"
            name="scan-input"
            help="z. B. 42 oder ORDER:42. Handscanner tippen die Kennung automatisch ein."
          >
            <input
              id="scan-input"
              ref={manualInputRef}
              type="text"
              inputMode="text"
              autoComplete="off"
              value={scanInput}
              onChange={(e) => setScanInput(e.target.value)}
              disabled={isScanning}
              data-testid="scanner-manual-input"
            />
          </Field>
          <Button
            type="submit"
            size="lg"
            icon="search"
            loading={isScanning}
            disabled={scanInput.trim().length === 0}
            data-testid="scanner-manual-submit"
          >
            Auftrag öffnen
          </Button>
        </form>
        {error !== null && (
          <p className="scanner-error" role="alert" data-testid="scanner-error">
            {error}
          </p>
        )}
      </section>

      <section
        className="scanner-section"
        aria-labelledby="scanner-history-heading"
        data-testid="scanner-history-section"
      >
        <h2 id="scanner-history-heading">Letzte Scans</h2>
        <ScanHistory
          query={history}
          isScanning={isScanning}
          onReopen={(row) => void handleScan(row.raw_payload, 'manual')}
          onStartCamera={() => setCameraActive(true)}
        />
      </section>

      {canSearchScans && <ScanHistoryPanel />}
    </div>
  );
};

export default ScannerPage;

// Exposed for unit tests — not part of the public component API.
export { migrateLegacyScanHistory as __migrateLegacyScanHistoryForTests };
