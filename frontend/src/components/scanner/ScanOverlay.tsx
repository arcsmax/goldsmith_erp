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
import type {
  ResolveResponse,
  ScanContext,
  Transport,
} from '../../types/scanner';
import { QuickActionModalV2 } from './QuickActionModalV2';
import { dispatchAction, type ActionHooks } from './ActionHandlers';
import { ModalStackHost } from '../../lib/modal-stack';
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

/**
 * Build a minimal ScanContext payload. V1.1 only needs input_source +
 * current_location (STATION mode is reserved for V1.1.5 per A9.6). Timer /
 * order ambient context will be wired in Slice 11 when TimeTrackingContext
 * exposes the running-timer shape.
 */
function makeScanContext(
  source: ScanSource,
  currentLocation: string | null,
): ScanContext {
  return {
    running_timer_id: null,
    current_order_id: null,
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
  const navigate = useNavigate();

  const [isActive, setIsActive] = useState<boolean>(true);
  const [lastResolveResponse, setLastResolveResponse] =
    useState<ResolveResponse | null>(null);
  const [resolving, setResolving] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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
      toast: (_message: string, _severity?: 'success' | 'info' | 'warning' | 'error') => {
        // Toast wiring is deliberately minimal inside the overlay; the
        // consumer app hoists ToastProvider one level up. ActionHandler
        // error strings surface on the QuickActionModalV2 error banner
        // already.
        void _message;
        void _severity;
      },
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
    [navigate, closeScanner, refreshRunningEntry],
  );

  const handleScan = useCallback(
    async (payload: string, source: ScanSource): Promise<void> => {
      setErrorMessage(null);
      setResolving(true);
      setIsActive(false); // pause camera; we'll resume on "Weiterscannen"
      setInputSource(source === 'camera' ? 'camera' : 'manual');
      try {
        const response = await router.resolve(
          payload,
          makeScanContext(source, currentLocation),
        );
        setLastResolveResponse(response);
        setLastScan(response);
      } catch (err) {
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
    [router, setLastScan, setInputSource, currentLocation],
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
    setLastResolveResponse(lastScan);
  }, [lastScan, lastResolveResponse]);

  // -------------------------------------------------------------------------
  // Open/close lifecycle: reset internal state on every open; re-arm camera.
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (scanOverlayOpen) {
      setIsActive(true);
      setLastResolveResponse(null);
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

  useEffect(() => {
    if (!scanOverlayOpen) return;

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
  }, [scanOverlayOpen, handleClose]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (!scanOverlayOpen) return null;

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

          {lastResolveResponse !== null ? (
            <div
              className="scan-overlay__result"
              data-testid="scan-overlay-result"
            >
              <QuickActionModalV2
                resolveResponse={lastResolveResponse}
                onAction={async (actionId: string): Promise<void> => {
                  await dispatchAction(actionId, {
                    response: lastResolveResponse,
                    scanContext: makeScanContext('manual', currentLocation),
                    transport: activeTransport,
                    hooks,
                    activityId: null,
                    runningEntryId: runningEntry?.id ?? null,
                  });
                }}
                onClose={handleClose}
                onContinueScanning={handleContinue}
                onStatusHintClick={() => {
                  const entityType =
                    lastResolveResponse.entity?.entity_type ?? '';
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
