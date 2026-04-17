// ScannerContext — Slice 9 global scanner state + bench-mode wiring.
//
// Responsibilities (plan §Slice 9 "ScannerContext state" + V1.1-AMENDMENTS
// A9.6 / A12.2):
//   * Owns the `lastScan`, `scanOverlayOpen`, `inputSource`, `currentLocation`,
//     and `benchModeEnabled` state surface consumed by ScanFab (Slice 10),
//     ScanOverlay (Slice 10), and QuickActionModalV2 (Slice 11).
//   * Conditionally mounts a BenchScannerListener when the user has bench
//     mode enabled; unmounts cleanly when toggled off.
//   * Persists `benchModeEnabled` per device (A12.2) and `currentLocation`
//     with a 12h TTL (A9.6 reservation — STATION scans land in V1.1.5).
//
// The Provider does NOT render any UI itself — ScanFab / ScanOverlay are
// mounted by MainLayout in Slice 10. This context is purely state + the
// BenchScannerListener lifecycle.

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { createBenchScannerListener } from '../lib/bench-scanner-listener';
import type { ResolveResponse } from '../types/scanner';

export type ScanInputSource = 'camera' | 'usb_hid' | 'manual';

export interface ScannerContextValue {
  /** Most recent resolve response — null before the first scan. */
  lastScan: ResolveResponse | null;
  /** True while the fullscreen ScanOverlay (Slice 10) is open. */
  scanOverlayOpen: boolean;
  openScanner: () => void;
  closeScanner: () => void;
  setLastScan: (response: ResolveResponse | null) => void;

  /**
   * Declared source for the NEXT scan. Transient — resets on reload. Updated
   * by the input surface that triggered the scan (camera, bench listener,
   * manual input).
   */
  inputSource: ScanInputSource;
  setInputSource: (source: ScanInputSource) => void;

  /**
   * Current STATION location. A9.6 — STATION scans land in V1.1.5; the field
   * is reserved on the context in V1.1 so downstream consumers can ship
   * against the final shape. Persisted with 12h TTL in localStorage.
   */
  currentLocation: string | null;
  setCurrentLocation: (loc: string | null) => void;

  /**
   * Werkbank-Modus toggle. A12.2 — device-persistent (localStorage), NOT
   * session-persistent. The Provider mounts a BenchScannerListener whenever
   * this is true and unmounts on toggle-off.
   */
  benchModeEnabled: boolean;
  toggleBenchMode: () => void;
}

// ---------------------------------------------------------------------------
// Storage helpers
// ---------------------------------------------------------------------------

const LS_LOCATION_KEY = 'scan_location';
const LS_BENCH_MODE_KEY = 'scan_bench_mode';
const LOCATION_TTL_MS = 12 * 3600 * 1000;

interface StoredLocation {
  value: string;
  timestamp: number;
}

/**
 * Safely read a JSON value from localStorage. Returns null on any parse /
 * access failure so the provider never blocks boot on a poisoned LS entry.
 */
function safeReadLocation(): string | null {
  try {
    const raw = localStorage.getItem(LS_LOCATION_KEY);
    if (raw === null) return null;
    const parsed = JSON.parse(raw) as Partial<StoredLocation> | null;
    if (parsed === null || typeof parsed !== 'object') return null;
    if (typeof parsed.value !== 'string' || typeof parsed.timestamp !== 'number') {
      return null;
    }
    if (Date.now() - parsed.timestamp > LOCATION_TTL_MS) {
      localStorage.removeItem(LS_LOCATION_KEY);
      return null;
    }
    return parsed.value;
  } catch {
    return null;
  }
}

function safeWriteLocation(value: string | null): void {
  try {
    if (value === null) {
      localStorage.removeItem(LS_LOCATION_KEY);
      return;
    }
    const entry: StoredLocation = { value, timestamp: Date.now() };
    localStorage.setItem(LS_LOCATION_KEY, JSON.stringify(entry));
  } catch {
    // Private-browsing / quota errors must not crash the provider.
  }
}

function safeReadBenchMode(): boolean {
  try {
    return localStorage.getItem(LS_BENCH_MODE_KEY) === 'true';
  } catch {
    return false;
  }
}

function safeWriteBenchMode(enabled: boolean): void {
  try {
    localStorage.setItem(LS_BENCH_MODE_KEY, enabled ? 'true' : 'false');
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const ScannerContext = createContext<ScannerContextValue | undefined>(undefined);

export interface ScannerProviderProps {
  children: React.ReactNode;
  /**
   * Optional override for the bench-scanner emit handler. Normal callers
   * should omit this; Slice 10 wiring will read `lastScan` via the context
   * hook and the default handler writes the raw payload into a transient
   * `lastBenchPayload` (exposed via the provider's ref for Slice 10 to
   * consume through its own `useEffect`).
   *
   * Exposed primarily for tests so the Slice 9 test matrix can assert emit
   * behaviour without needing the full ScannerRouter plumbing.
   */
  onBenchScan?: (payload: string) => void;
}

export const ScannerProvider: React.FC<ScannerProviderProps> = ({
  children,
  onBenchScan,
}) => {
  const [lastScan, setLastScan] = useState<ResolveResponse | null>(null);
  const [scanOverlayOpen, setScanOverlayOpen] = useState<boolean>(false);
  const [inputSource, setInputSourceState] = useState<ScanInputSource>('manual');
  const [currentLocation, setCurrentLocationState] = useState<string | null>(() =>
    safeReadLocation(),
  );
  const [benchModeEnabled, setBenchModeEnabled] = useState<boolean>(() =>
    safeReadBenchMode(),
  );

  const openScanner = useCallback(() => setScanOverlayOpen(true), []);
  const closeScanner = useCallback(() => setScanOverlayOpen(false), []);

  const setInputSource = useCallback((source: ScanInputSource) => {
    setInputSourceState(source);
  }, []);

  const setCurrentLocation = useCallback((loc: string | null) => {
    setCurrentLocationState(loc);
    safeWriteLocation(loc);
  }, []);

  const toggleBenchMode = useCallback(() => {
    setBenchModeEnabled((prev) => {
      const next = !prev;
      safeWriteBenchMode(next);
      return next;
    });
  }, []);

  // Keep the latest onBenchScan callback in a ref so we can mount the
  // listener once per benchModeEnabled transition without re-mounting on
  // every render that changes the callback identity. This matters: the real
  // Slice 10 wiring will pass an inline closure over `scannerRouter.resolve`.
  const onBenchScanRef = useRef<((payload: string) => void) | undefined>(onBenchScan);
  useEffect(() => {
    onBenchScanRef.current = onBenchScan;
  }, [onBenchScan]);

  // Mount/unmount the BenchScannerListener based on benchModeEnabled.
  // The cleanup function returned by createBenchScannerListener is idempotent.
  useEffect(() => {
    if (!benchModeEnabled) return;

    const dispose = createBenchScannerListener({
      onScan: (payload: string) => {
        // When bench mode fires, flip inputSource so the next resolve logs
        // `input_source='usb_hid'` per plan metric (e). Consumers that want
        // to intercept the payload supply `onBenchScan` at provider mount.
        setInputSourceState('usb_hid');
        const handler = onBenchScanRef.current;
        if (handler !== undefined) {
          handler(payload);
        }
      },
    });

    return dispose;
  }, [benchModeEnabled]);

  const value = useMemo<ScannerContextValue>(
    () => ({
      lastScan,
      scanOverlayOpen,
      openScanner,
      closeScanner,
      setLastScan,
      inputSource,
      setInputSource,
      currentLocation,
      setCurrentLocation,
      benchModeEnabled,
      toggleBenchMode,
    }),
    [
      lastScan,
      scanOverlayOpen,
      openScanner,
      closeScanner,
      inputSource,
      setInputSource,
      currentLocation,
      setCurrentLocation,
      benchModeEnabled,
      toggleBenchMode,
    ],
  );

  return (
    <ScannerContext.Provider value={value}>{children}</ScannerContext.Provider>
  );
};

export function useScannerContext(): ScannerContextValue {
  const ctx = useContext(ScannerContext);
  if (ctx === undefined) {
    throw new Error('useScannerContext must be used within a ScannerProvider');
  }
  return ctx;
}
