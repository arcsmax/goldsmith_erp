// ScanFab — Slice 10 of V1.1 QR/Barcode workflow.
//
// Global floating-action-button that opens the ScanOverlay. Reachable from
// every authenticated page.
//
// Key behaviours (plan §Slice 10 + AMENDMENTS A10.1 / A10.2 / A10.3):
//
//   * Hidden on /login and /register routes. (MainLayout never mounts on
//     those routes in practice, but the guard is kept for defensive safety
//     against future routing changes.) The FAB also hides while its own
//     overlay is open — the overlay owns its own close affordance.
//   * Records `client_tap_at = Date.now()` into ScannerContext on every tap
//     so NetworkTransport can include it when logging the scan event
//     (A10.2 → A7.1 → spec §14.a row b FAB-tap-to-timer median).
//   * Stacks above the TimerWidget FAB (z-index 1050) when a timer is
//     running. The stacked offset is `--fab-bottom + 72px` so the two FABs
//     don't collide on iPad 9. Gen portrait (A10.1 pre-ship check).
//   * Touch target >= 48px (--touch-comfort token) — tested under gloves +
//     talc at the bench.
//   * Amber hover/focus accent per Jason's design spec (V1.1-UI-DESIGN-SPEC).
//   * Respects `prefers-reduced-motion` — no pulse / scale on hover.
//
// This component is intentionally tiny — the real work lives in the overlay
// that `openScanner()` raises. Tests live in `src/test/ScanFab.test.tsx`.

import React, { useCallback } from 'react';
import { useLocation } from 'react-router-dom';

import { useScannerContext } from '../../contexts/ScannerContext';
import { useTimeTracking } from '../../contexts';
import '../../styles/components/ScanFab.css';

// Paths on which the FAB must be invisible. Keep in sync with the
// authentication-free route list in `App.tsx`. If a future route wants to
// opt-out, add it here.
const HIDDEN_PATHS: ReadonlySet<string> = new Set(['/login', '/register']);

export const ScanFab: React.FC = () => {
  const { openScanner, scanOverlayOpen, recordFabTap } = useScannerContext();
  const { runningEntry } = useTimeTracking();
  const location = useLocation();

  const handleTap = useCallback((): void => {
    // Record the tap first (A10.2) — a synchronous Date.now() write — before
    // raising the overlay, so the scan event emitted downstream carries an
    // accurate FAB-tap timestamp.
    recordFabTap();
    openScanner();
  }, [openScanner, recordFabTap]);

  // Route-based visibility. The FAB must not appear on auth screens even if
  // someone mounts MainLayout there by accident.
  if (HIDDEN_PATHS.has(location.pathname)) {
    return null;
  }

  // Avoid double-rendering over our own overlay — the overlay has its own
  // close affordance; a FAB floating on top of it is noise.
  if (scanOverlayOpen) {
    return null;
  }

  const stacked = runningEntry !== null;
  const className = stacked ? 'scan-fab scan-fab--stacked' : 'scan-fab';

  return (
    <button
      type="button"
      className={className}
      onClick={handleTap}
      aria-label="QR-Code scannen"
      data-testid="scan-fab"
    >
      {/* Inline SVG — no icon library in this bundle. Uses currentColor so
          hover/focus states can theme it via CSS. */}
      <svg
        className="scan-fab__icon"
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {/* Four corner brackets suggest a QR finder pattern without pretending
            to be a literal QR code. */}
        <path d="M3 7V5a2 2 0 0 1 2-2h2" />
        <path d="M17 3h2a2 2 0 0 1 2 2v2" />
        <path d="M21 17v2a2 2 0 0 1-2 2h-2" />
        <path d="M7 21H5a2 2 0 0 1-2-2v-2" />
        {/* Inner QR eyes — three squares, like a classic QR code. */}
        <rect x="7" y="7" width="3" height="3" />
        <rect x="14" y="7" width="3" height="3" />
        <rect x="7" y="14" width="3" height="3" />
        {/* Data bits on the fourth quadrant. */}
        <path d="M14 14h1" />
        <path d="M17 14h0" />
        <path d="M14 17h0" />
        <path d="M17 17h0" />
      </svg>
    </button>
  );
};

export default ScanFab;
