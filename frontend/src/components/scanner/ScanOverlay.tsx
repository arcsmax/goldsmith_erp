// ScanOverlay — Slice 10 of V1.1 QR/Barcode workflow.
//
// Full-screen camera overlay raised by ScanFab. Hosts the QrCameraScanner
// (camera + manual-input fallback) and, after a scan resolves, renders a
// placeholder result block. Slice 11 will replace that placeholder with the
// real QuickActionModalV2.
//
// Responsibilities covered in this slice:
//
//   * Camera lifecycle (pause after scan, resume on "Weiterscannen" button).
//   * Error surface with retry CTA.
//   * Close button (top-right) calling `closeScanner()` on the context.
//   * A10.3 auto-dismiss: when a NEW scan arrives on the ScannerContext
//     (e.g. a bench-scanner burst) while a previous result is rendered,
//     the old result is dropped and the new one takes over — no tap
//     required (workshop ergonomics: dirty hands can't cancel).
//   * Focus trap while the overlay is open (WCAG 2.1 SC 2.4.3 focus order,
//     SC 2.1.2 no keyboard trap is the INVERSE intent — we DO trap inside
//     the dialog but release on close/Esc). Esc triggers close.
//   * `prefers-reduced-motion` respected: animations drop to ≤120ms fade.
//
// Scan tracking (2026-09 audit, SC-01): every decode is logged right away
// (scanTracking.recordScan, action "scan_only" / "unrecognised" /
// "resolve_failed"), and every action picked in the sheet writes a second
// row with its result (recordAction). While a result is shown, the sheet
// (Sheet primitive) owns focus and Escape; the camera panel is not rendered.
//
// Slice 11 hook: `lastResolveResponse` is exposed for tests via
// data-testid. The placeholder JSON block will be replaced by the real
// QuickActionModalV2 in the next PR.
//
// References:
//   docs/superpowers/plans/qr-barcode-workflow/V1.1-IMPLEMENTATION-PLAN.md §10
//   docs/superpowers/plans/qr-barcode-workflow/V1.1-AMENDMENTS.md A10.1–A10.3
//   docs/superpowers/plans/qr-barcode-workflow/V1.1-UI-DESIGN-SPEC.md

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { QrCameraScanner } from './QrCameraScanner';
import type { ScanSource } from './QrCameraScanner';
import { ScannerRouter } from '../../lib/scan-router';
import { NetworkAliasResolver } from '../../lib/network-alias-resolver';
import { NetworkTransport } from '../../lib/network-transport';
import { useScannerContext } from '../../contexts/ScannerContext';
import { useTimeTracking } from '../../contexts/TimeTrackingContext';
import { useOptionalAuth } from '../../contexts/AuthContext';
import type { ResolveResponse, Transport } from '../../types/scanner';
import { QuickActionModalV2 } from './QuickActionModalV2';
import {
  MAX_PIECE_LOCATION,
  dispatchAction,
  isSupportedAction,
  type ActionHooks,
} from './ActionHandlers';
import {
  buildScanContext,
  recordAction,
  recordScan,
  takeHandedOffScan,
  type TrackedScan,
} from './scanTracking';
import { ModalStackHost } from '../../lib/modal-stack';
import { useToast } from '../../contexts/ToastContext';
import { usePromptDialog } from '../../ui';
import { useNavigate } from 'react-router-dom';
import '../../styles/components/ScanOverlay.css';

// ---------------------------------------------------------------------------
// Props (injection for tests + Slice 11)
// ---------------------------------------------------------------------------

export interface ScanOverlayProps {
  /**
   * Optional transport injection for tests. Normal callers should omit —
   * the component constructs a NetworkTransport backed by the shared axios
   * client which is already baseURL'd to `/api/v1`.
   */
  transport?: Transport;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type ShowToast = ReturnType<typeof useToast>['showToast'];

/**
 * The overlay also renders in isolated tests without a ToastProvider; the
 * context read happens on every render either way (hook order is stable).
 */
function useOptionalToast(): ShowToast | null {
  try {
    return useToast().showToast;
  } catch {
    return null;
  }
}

/** Only actions the sheet can execute (the rest had no handler, FE audit). */
function withSupportedActions(response: ResolveResponse): ResolveResponse {
  return { ...response, actions: response.actions.filter((a) => isSupportedAction(a.id)) };
}

/**
 * Compare two ResolveResponses for "newness". Used by A10.3 auto-dismiss so
 * we only replace the current result when a genuinely different scan
 * arrives (and not when React re-renders with the same object).
 */
function isDifferentResponse(
  a: ResolveResponse | null,
  b: ResolveResponse | null,
): boolean {
  if (a === null || b === null) return a !== b;
  if (a.entity_type !== b.entity_type) return true;
  if (a.entity_id !== b.entity_id) return true;
  if (a.resolution_path !== b.resolution_path) return true;
  return false;
}

// ---------------------------------------------------------------------------
// Focus trap helpers
// ---------------------------------------------------------------------------

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function getFocusable(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const ScanOverlay: React.FC<ScanOverlayProps> = ({ transport }) => {
  const {
    scanOverlayOpen,
    closeScanner,
    setLastScan,
    setInputSource,
    lastScan,
    currentLocation,
  } = useScannerContext();
  const { runningEntry, refreshRunningEntry } = useTimeTracking();
  const auth = useOptionalAuth();
  const userId = auth?.user?.id ?? null;
  const navigate = useNavigate();

  const [isActive, setIsActive] = useState<boolean>(true);
  const [lastResolveResponse, setLastResolveResponse] =
    useState<ResolveResponse | null>(null);
  const [resolving, setResolving] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [scannedPayload, setScannedPayload] = useState<string>('');
  // The logged scan the sheet's actions follow up (parent_scan_id).
  const trackedRef = useRef<TrackedScan | null>(null);
  const { prompt, dialog: promptDialog } = usePromptDialog();
  const showToast = useOptionalToast();

  const overlayRef = useRef<HTMLDivElement | null>(null);
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);
  const prevActiveElement = useRef<Element | null>(null);

  // Construct the router once per component lifetime. The transport is
  // injectable for tests; prod uses NetworkTransport which consumes the
  // shared apiClient (baseURL `/api/v1`).
  const activeTransport = useMemo<Transport>(
    () => transport ?? new NetworkTransport(),
    [transport],
  );
  const router = useMemo<ScannerRouter>(() => {
    return new ScannerRouter(new NetworkAliasResolver(), activeTransport);
  }, [activeTransport]);

  // -------------------------------------------------------------------------
  // Scan handling
  // -------------------------------------------------------------------------

  // Hooks bundle consumed by ActionHandlers. Closures over context values
  // are stable across renders because each value the closure reads is
  // supplied at call time — the hooks object itself is rebuilt per render
  // but the bundle is cheap and one level deep.
  const hooks: ActionHooks = useMemo(
    () => ({
      navigate: (path: string) => navigate(path),
      toast: (message: string, severity?: 'success' | 'info' | 'warning' | 'error') => {
        // Errors surface on the sheet's banner; confirmations as a toast.
        showToast?.(message, severity ?? 'info');
      },
      promptLocation: (current: string | null) =>
        prompt({
          title: 'Standort setzen',
          label: 'Standort',
          help: 'z. B. Werkbank 2, Tresor, Poliererei',
          defaultValue: current ?? '',
          confirmLabel: 'Standort setzen',
          required: true,
          maxLength: MAX_PIECE_LOCATION,
        }),
      closeOverlay: () => {
        setLastResolveResponse(null);
        setErrorMessage(null);
        setIsActive(false);
        closeScanner();
      },
      refreshTimer: async () => {
        await refreshRunningEntry();
      },
    }),
    [navigate, closeScanner, refreshRunningEntry, showToast, prompt],
  );

  const scanContextFor = useCallback(
    (source: ScanSource) =>
      buildScanContext(source === 'camera' ? 'camera' : 'manual', {
        stationLocation: currentLocation,
        runningEntry,
      }),
    [currentLocation, runningEntry],
  );

  const handleScan = useCallback(
    async (payload: string, source: ScanSource): Promise<void> => {
      setErrorMessage(null);
      setResolving(true);
      setIsActive(false); // pause camera; we'll resume on "Weiterscannen"
      setInputSource(source === 'camera' ? 'camera' : 'manual');
      setScannedPayload(payload);
      const context = scanContextFor(source);
      try {
        const response = await router.resolve(payload, context);
        // Logged BEFORE the sheet shows: a scan without an action counts.
        trackedRef.current = await recordScan(payload, response, context);
        setLastResolveResponse(withSupportedActions(response));
        setLastScan(response);
      } catch (err) {
        // The scan happened even though it could not be resolved.
        trackedRef.current = await recordScan(payload, null, context);
        const msg =
          err instanceof Error && err.message.length > 0
            ? err.message
            : 'Scan konnte nicht verarbeitet werden.';
        setErrorMessage(msg);
        // Re-arm camera so the user can retry without tapping extra buttons.
        setIsActive(true);
      } finally {
        setResolving(false);
      }
    },
    [router, setLastScan, setInputSource, scanContextFor],
  );

  const handleAction = useCallback(
    async (actionId: string): Promise<void> => {
      const response = lastResolveResponse;
      if (response === null) return;
      const tracked = trackedRef.current;
      const scanContext = tracked?.event.context
        ? { ...scanContextFor('manual'), ...tracked.event.context }
        : scanContextFor('manual');
      try {
        const outcome = await dispatchAction(actionId, {
          response,
          scanContext,
          transport: activeTransport,
          hooks,
          // FE-02: when switching, keep the running timer's activity;
          // otherwise the handler uses this user's last-used activity or
          // asks via ActivityPickerModal.
          activityId: runningEntry?.activity_id ?? null,
          runningEntryId: runningEntry?.id ?? null,
          userId,
        });
        // "Nur erfassen": the scan_only row already says it all.
        if (tracked !== null && actionId !== 'log_only') {
          void recordAction(tracked, actionId, outcome.result ?? 'ok', outcome.location);
        }
      } catch (err) {
        if (tracked !== null) void recordAction(tracked, actionId, 'failed');
        throw err;
      }
    },
    [lastResolveResponse, scanContextFor, activeTransport, hooks, runningEntry, userId],
  );

  const handleContinue = useCallback((): void => {
    setLastResolveResponse(null);
    setErrorMessage(null);
    setIsActive(true);
  }, []);

  const handleClose = useCallback((): void => {
    setLastResolveResponse(null);
    setErrorMessage(null);
    setIsActive(false);
    closeScanner();
  }, [closeScanner]);

  // -------------------------------------------------------------------------
  // A10.3 — auto-dismiss on new scan
  //
  // When a different ResolveResponse lands on the ScannerContext (e.g. a
  // bench-scanner burst fired through a different path while the overlay
  // is open), replace the currently-displayed result so the latest scan
  // wins. Dirty-hands ergonomics: no cancel tap required.
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (lastScan === null) return;
    if (lastResolveResponse === null) return;
    if (!isDifferentResponse(lastScan, lastResolveResponse)) return;
    setLastResolveResponse(withSupportedActions(lastScan));
  }, [lastScan, lastResolveResponse]);

  // -------------------------------------------------------------------------
  // Open/close lifecycle: reset internal state on every open; re-arm camera.
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (scanOverlayOpen) {
      // A scan resolved + logged on the ScannerPage opens straight on the
      // sheet; a FAB open starts with the camera.
      const handed = takeHandedOffScan();
      trackedRef.current = handed?.tracked ?? null;
      setScannedPayload(handed?.payload ?? '');
      setIsActive(handed === null);
      setLastResolveResponse(handed ? withSupportedActions(handed.response) : null);
      setErrorMessage(null);
      setResolving(false);
      // Preserve the element that held focus before the overlay opened so we
      // can return focus there on close (WCAG 2.4.3).
      prevActiveElement.current =
        typeof document !== 'undefined' ? document.activeElement : null;
    } else {
      // Return focus to the trigger element (ScanFab) on close, if still in
      // the DOM and focusable.
      const prev = prevActiveElement.current;
      if (
        prev instanceof HTMLElement &&
        typeof prev.focus === 'function' &&
        document.body.contains(prev)
      ) {
        // Defer one frame so DOM settles before focus call.
        window.requestAnimationFrame(() => prev.focus());
      }
    }
  }, [scanOverlayOpen]);

  // -------------------------------------------------------------------------
  // Focus trap + Esc-to-close while overlay is open.
  // -------------------------------------------------------------------------

  const isSheetShown = lastResolveResponse !== null;

  useEffect(() => {
    // While the sheet is shown the Sheet primitive owns focus + Escape.
    if (!scanOverlayOpen || isSheetShown) return;

    // Defer initial focus until the element is in the DOM.
    const rafId = window.requestAnimationFrame(() => {
      closeBtnRef.current?.focus();
    });

    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        handleClose();
        return;
      }
      if (e.key !== 'Tab') return;
      const root = overlayRef.current;
      if (root === null) return;
      const focusable = getFocusable(root);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement as HTMLElement | null;

      if (e.shiftKey) {
        if (active === first || active === null || !root.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      window.cancelAnimationFrame(rafId);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [scanOverlayOpen, isSheetShown, handleClose]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (!scanOverlayOpen) return null;

  if (lastResolveResponse !== null) {
    return (
      <div data-testid="scan-overlay-result">
        <QuickActionModalV2
          resolveResponse={lastResolveResponse}
          rawPayload={scannedPayload}
          onAction={handleAction}
          onClose={handleClose}
          onContinueScanning={handleContinue}
          onStatusHintClick={() => {
            const entityType = lastResolveResponse.entity?.entity_type ?? '';
            const entityIdVal = lastResolveResponse.entity?.entity_id;
            if (entityIdVal === undefined) return;
            const map: Record<string, string> = {
              order: `/orders/${entityIdVal}`,
              repair: `/repairs/${entityIdVal}`,
              metal_purchase: `/metal-inventory/purchases/${entityIdVal}`,
              material: `/materials/${entityIdVal}`,
            };
            const target = map[entityType];
            if (target) {
              navigate(target);
              handleClose();
            }
          }}
        />
        {promptDialog}
        {/* Stacked modals (AlloyMismatchModal, PunzierungsCheckModal). */}
        <ModalStackHost />
      </div>
    );
  }

  return (
    <div
      className="scan-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="QR-Code scannen"
      data-testid="scan-overlay"
      ref={overlayRef}
    >
      <div className="scan-overlay__backdrop" aria-hidden="true" />

      <div className="scan-overlay__panel">
        <header className="scan-overlay__header">
          <h2 className="scan-overlay__title">Scanner</h2>
          <button
            type="button"
            className="scan-overlay__close"
            onClick={handleClose}
            aria-label="Schliessen"
            ref={closeBtnRef}
            data-testid="scan-overlay-close"
          >
            <svg
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
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </header>

        <div className="scan-overlay__body">
          {resolving ? (
            <div
              className="scan-overlay__spinner"
              role="status"
              aria-live="polite"
              data-testid="scan-overlay-spinner"
            >
              Laedt…
            </div>
          ) : null}

          {errorMessage !== null ? (
            <div
              className="scan-overlay__error"
              role="alert"
              data-testid="scan-overlay-error"
            >
              {errorMessage}
            </div>
          ) : null}

          {lastResolveResponse === null && !resolving ? (
            <div className="scan-overlay__scanner-host">
              <QrCameraScanner active={isActive} onScan={handleScan} />
            </div>
          ) : null}

        </div>
      </div>
      {/* Stacked modals (AlloyMismatchModal, PunzierungsCheckModal) render
          above the overlay via the promise-based modal-stack helper. */}
      <ModalStackHost />
    </div>
  );
};

export default ScanOverlay;
