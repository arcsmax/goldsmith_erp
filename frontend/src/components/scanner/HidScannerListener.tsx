// HidScannerListener — wires the USB/keyboard-wedge scanner into the
// authenticated shell (2026-09 audit, scanner-tracking fix item 1).
//
// The bench-scanner burst DETECTION already existed (lib/bench-scanner-
// listener.ts, armed by ScannerContext whenever `benchModeEnabled` —
// "Werkbank-Station-Modus" — is on) but nothing ever DID anything with a
// detected burst: `ScannerProvider`'s `onBenchScan` injection point was
// never supplied in App.tsx, so a USB scan fired outside a focused text
// input was silently dropped (not logged, no sheet).
//
// This component is the "what do we do with a burst" half. It is mounted
// once, inside the same provider tree as ScannerContext/TimeTrackingContext
// (see App.tsx), and registers its resolve handler into the ref that
// App.tsx's `onBenchScan` bridge calls. It intentionally does NOT mount its
// own document listener — ScannerContext already owns arming/disarming the
// keyboard-wedge listener per device setting; duplicating that here would
// double-process every keystroke.
//
// The handler reuses the exact same pipeline as the camera and manual-entry
// paths (ScannerPage.handleScan / ScanOverlay.handleScan):
//   resolve → recordScan (BEFORE the sheet, a scan without an action still
//   counts) → handOffScan → setLastScan → openScanner.
//
// `ScanOverlay` is mounted once in `MainLayout`, outside the routed
// `<Outlet>`, so `openScanner()` raises the action sheet on whatever staff
// page is currently showing — no navigation to /scanner is needed.
import React, { useCallback, useEffect, useMemo } from 'react';

import { useScannerContext } from '../../contexts/ScannerContext';
import { useTimeTracking } from '../../contexts/TimeTrackingContext';
import { NetworkAliasResolver } from '../../lib/network-alias-resolver';
import { NetworkTransport } from '../../lib/network-transport';
import { ScannerRouter } from '../../lib/scan-router';
import type { ResolveResponse, Transport } from '../../types/scanner';
import { useOptionalToast } from './useOptionalToast';
import { buildScanContext, handOffScan, recordScan } from './scanTracking';

export type HidBurstHandler = (payload: string) => void;

export interface HidScannerListenerProps {
  /**
   * Filled with the latest burst handler on every render (App.tsx's
   * `onBenchScan` bridge calls `handlerRef.current?.(payload)`). A ref, not
   * a callback prop, because `ScannerProvider`'s `onBenchScan` is supplied
   * from ABOVE the provider (App.tsx) while this component's hooks
   * (`useScannerContext`, `useTimeTracking`) only work BELOW it — the ref is
   * the bridge between the two without mounting a second listener.
   */
  handlerRef: React.MutableRefObject<HidBurstHandler | null>;
  /** Test-only transport injection, mirrors ScanOverlay's pattern. */
  transport?: Transport;
}

export const HidScannerListener: React.FC<HidScannerListenerProps> = ({
  handlerRef,
  transport,
}) => {
  const { setInputSource, setLastScan, openScanner, currentLocation } = useScannerContext();
  const { runningEntry } = useTimeTracking();
  const showToast = useOptionalToast();

  const activeTransport = useMemo<Transport>(
    () => transport ?? new NetworkTransport(),
    [transport],
  );
  const router = useMemo<ScannerRouter>(
    () => new ScannerRouter(new NetworkAliasResolver(), activeTransport),
    [activeTransport],
  );

  const handleBurst = useCallback(
    async (rawPayload: string): Promise<void> => {
      const payload = rawPayload.trim();
      if (payload.length === 0) return;

      setInputSource('usb_hid');
      // Immediate feedback: the physical scan was captured, even before the
      // network round-trip resolves it — a goldsmith with dirty hands
      // shouldn't have to wonder whether the scanner "took".
      showToast?.('Scan erkannt', 'success', 2000);

      const context = buildScanContext('usb_hid', {
        stationLocation: currentLocation,
        runningEntry,
      });
      try {
        const response: ResolveResponse = await router.resolve(payload, context);
        // Logged BEFORE the sheet opens: a scan without an action counts.
        const tracked = await recordScan(payload, response, context);
        handOffScan({ response, tracked, payload });
        setLastScan(response);
        openScanner();
      } catch (err) {
        // The scan still happened even though it could not be resolved.
        await recordScan(payload, null, context);
        console.error('[HidScannerListener] Scan konnte nicht verarbeitet werden', err);
      }
    },
    [setInputSource, showToast, currentLocation, runningEntry, router, setLastScan, openScanner],
  );

  useEffect(() => {
    handlerRef.current = handleBurst;
    return () => {
      if (handlerRef.current === handleBurst) {
        handlerRef.current = null;
      }
    };
  }, [handleBurst, handlerRef]);

  // Headless — no UI of its own (mirrors RealtimeInvalidation / ScannerProvider).
  return null;
};

export default HidScannerListener;
