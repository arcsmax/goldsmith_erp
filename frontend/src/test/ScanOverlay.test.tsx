// ScanOverlay component tests — Slice 10 of V1.1 QR/Barcode workflow.
//
// Scope (plan §Slice 10 verification + AMENDMENTS A10.3 + A11.11):
//   * Hidden when scanOverlayOpen=false.
//   * Renders dialog with aria-modal="true" and aria-label in German.
//   * Close button invokes closeScanner() on the context.
//   * Esc key triggers closeScanner().
//   * Renders the QrCameraScanner while no result is visible.
//   * A successful scan surfaces the result block + "Weiterscannen" CTA.
//   * "Weiterscannen" clears the result and re-arms the scanner.
//   * Error from transport.resolve surfaces in an alert region.
//   * A10.3 auto-dismiss: when lastScan on the context changes (e.g. a
//     bench-scanner burst fired externally) while a previous result is
//     showing, the new response replaces the old one with no user tap.
//   * Focus moves to the close button on open (focus trap initial target).
//   * Tab from the last focusable inside the dialog cycles to the first.
//
// The QrCameraScanner vendor module is NOT mocked here — ScanOverlay uses
// the real component, which has its own test coverage. We DO mock the
// dynamic @yudiel/react-qr-scanner import so the scanner renders a
// data-testid marker without pulling WebRTC into jsdom.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// --- Mock @yudiel/react-qr-scanner so QrCameraScanner renders inert. -----
vi.mock('@yudiel/react-qr-scanner', () => {
  return {
    Scanner: () => <div data-testid="mock-yudiel-scanner" />,
  };
});

// --- HTMLMediaElement shims for jsdom/happy-dom audio kit. --------------
// @ts-expect-error happy-dom stub
HTMLMediaElement.prototype.play = vi.fn(() => Promise.resolve());
// @ts-expect-error happy-dom stub
HTMLMediaElement.prototype.pause = vi.fn();

// navigator.vibrate polyfill for the scanner haptic call.
Object.defineProperty(navigator, 'vibrate', {
  value: vi.fn(() => true),
  writable: true,
  configurable: true,
});

// mediaDevices — minimal stub so QrCameraScanner lands in `denied` state
// quickly rather than hanging on getUserMedia; this is fine for overlay tests
// that don't care about camera plumbing.
Object.defineProperty(navigator, 'mediaDevices', {
  value: {
    getUserMedia: vi.fn(() =>
      Promise.reject(Object.assign(new Error('denied'), { name: 'NotAllowedError' })),
    ),
    enumerateDevices: vi.fn(() => Promise.resolve([])),
  },
  writable: true,
  configurable: true,
});

import { ScanOverlay } from '../components/scanner/ScanOverlay';
import {
  ScannerProvider,
  useScannerContext,
} from '../contexts/ScannerContext';
import type {
  ResolveResponse,
  ScanContext,
  ScanEvent,
  ActionExecution,
  ActionResult,
  Transport,
} from '../types/scanner';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const RESOLVED_ORDER_42: ResolveResponse = {
  resolved: true,
  resolution_path: 'prefix',
  entity_type: 'order',
  entity_id: 42,
  entity: {
    entity_type: 'order',
    entity_id: 42,
    data: { id: 42, status: 'IN_PROGRESS' },
  },
  actions: [],
  status_hint: null,
};

const RESOLVED_ORDER_99: ResolveResponse = {
  resolved: true,
  resolution_path: 'prefix',
  entity_type: 'order',
  entity_id: 99,
  entity: {
    entity_type: 'order',
    entity_id: 99,
    data: { id: 99, status: 'NEW' },
  },
  actions: [],
  status_hint: null,
};

class StubTransport implements Transport {
  public resolveFn: (payload: string, ctx: ScanContext) => Promise<ResolveResponse>;
  public logCalls: ScanEvent[] = [];

  constructor(resolveFn: (payload: string, ctx: ScanContext) => Promise<ResolveResponse>) {
    this.resolveFn = resolveFn;
  }

  resolve(payload: string, context: ScanContext): Promise<ResolveResponse> {
    return this.resolveFn(payload, context);
  }

  async logScan(event: ScanEvent): Promise<void> {
    this.logCalls.push(event);
  }

  async executeAction(_action: ActionExecution): Promise<ActionResult> {
    return { success: true };
  }
}

/** Renders the overlay inside a provider; supplies helpers to manipulate it. */
function renderOverlay(transport?: Transport): {
  openOverlay: () => void;
  closeOverlay: () => void;
  setLastScanExternal: (r: ResolveResponse | null) => void;
  rerender: () => void;
} {
  let openOverlayFn: () => void = () => {};
  let closeOverlayFn: () => void = () => {};
  let setLastScanFn: (r: ResolveResponse | null) => void = () => {};

  const Harness: React.FC = () => {
    const ctx = useScannerContext();
    openOverlayFn = ctx.openScanner;
    closeOverlayFn = ctx.closeScanner;
    setLastScanFn = ctx.setLastScan;
    return <ScanOverlay transport={transport} />;
  };

  render(
    <ScannerProvider>
      <Harness />
    </ScannerProvider>,
  );

  return {
    openOverlay: () => act(() => openOverlayFn()),
    closeOverlay: () => act(() => closeOverlayFn()),
    setLastScanExternal: (r) => act(() => setLastScanFn(r)),
    rerender: () => {},
  };
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Basic rendering + close paths
// ---------------------------------------------------------------------------

describe('ScanOverlay rendering', () => {
  it('renders nothing while scanOverlayOpen=false', () => {
    const transport = new StubTransport(async () => RESOLVED_ORDER_42);
    renderOverlay(transport);
    expect(screen.queryByTestId('scan-overlay')).toBeNull();
  });

  it('renders dialog with role="dialog", aria-modal="true" and German aria-label', () => {
    const transport = new StubTransport(async () => RESOLVED_ORDER_42);
    const { openOverlay } = renderOverlay(transport);
    openOverlay();
    const dialog = screen.getByTestId('scan-overlay');
    expect(dialog.getAttribute('role')).toBe('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.getAttribute('aria-label')).toBe('QR-Code scannen');
  });

  it('renders the QrCameraScanner region before any scan', () => {
    const transport = new StubTransport(async () => RESOLVED_ORDER_42);
    const { openOverlay } = renderOverlay(transport);
    openOverlay();
    // QrCameraScanner internally renders its own root. We assert on the
    // yudiel mock marker OR the qrs-root (happy path before getUserMedia
    // decides). Either is sufficient evidence the scanner host is mounted.
    const sentinel =
      screen.queryByTestId('mock-yudiel-scanner') ??
      document.querySelector('.qrs-root');
    expect(sentinel).not.toBeNull();
  });

  it('close button triggers closeScanner()', async () => {
    const user = userEvent.setup();
    const transport = new StubTransport(async () => RESOLVED_ORDER_42);
    const { openOverlay } = renderOverlay(transport);
    openOverlay();
    expect(screen.getByTestId('scan-overlay')).toBeInTheDocument();

    await user.click(screen.getByTestId('scan-overlay-close'));
    expect(screen.queryByTestId('scan-overlay')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Scan → result flow + Weiterscannen
// ---------------------------------------------------------------------------

describe('ScanOverlay scan flow', () => {
  it('renders the result block + Weiterscannen after a successful scan', async () => {
    const transport = new StubTransport(async () => RESOLVED_ORDER_42);
    const { openOverlay } = renderOverlay(transport);
    openOverlay();

    // Find the manual input and submit — this is the simplest path to
    // drive a scan without spinning up the camera mock state machine.
    const input = await screen.findByLabelText('Code manuell eingeben');
    const user = userEvent.setup();
    await user.type(input, 'ORDER:42{Enter}');

    const result = await screen.findByTestId('scan-overlay-result');
    expect(result.textContent).toContain('42');
    expect(screen.getByTestId('scan-overlay-continue')).toBeInTheDocument();
  });

  it('Weiterscannen clears the result and re-arms the scanner', async () => {
    const transport = new StubTransport(async () => RESOLVED_ORDER_42);
    const { openOverlay } = renderOverlay(transport);
    openOverlay();

    const input = await screen.findByLabelText('Code manuell eingeben');
    const user = userEvent.setup();
    await user.type(input, 'ORDER:42{Enter}');

    await screen.findByTestId('scan-overlay-result');
    await user.click(screen.getByTestId('scan-overlay-continue'));

    await waitFor(() =>
      expect(screen.queryByTestId('scan-overlay-result')).toBeNull(),
    );
  });

  it('surfaces a transport error via the alert region', async () => {
    const transport = new StubTransport(async () => {
      throw new Error('Network down');
    });
    const { openOverlay } = renderOverlay(transport);
    openOverlay();

    const input = await screen.findByLabelText('Code manuell eingeben');
    const user = userEvent.setup();
    await user.type(input, 'ORDER:42{Enter}');

    const err = await screen.findByTestId('scan-overlay-error');
    expect(err.textContent).toMatch(/network down/i);
  });
});

// ---------------------------------------------------------------------------
// A10.3 auto-dismiss on new scan
// ---------------------------------------------------------------------------

describe('ScanOverlay A10.3 auto-dismiss on new scan', () => {
  it('replaces the current result when lastScan on the context changes to a different entity', async () => {
    const transport = new StubTransport(async () => RESOLVED_ORDER_42);
    const { openOverlay, setLastScanExternal } = renderOverlay(transport);
    openOverlay();

    // First scan via manual input.
    const input = await screen.findByLabelText('Code manuell eingeben');
    const user = userEvent.setup();
    await user.type(input, 'ORDER:42{Enter}');
    const firstResult = await screen.findByTestId('scan-overlay-result');
    expect(firstResult.textContent).toContain('42');

    // Second scan arrives externally (bench scanner burst simulated by
    // context.setLastScan(...)).
    setLastScanExternal(RESOLVED_ORDER_99);

    await waitFor(() => {
      const text = screen.getByTestId('scan-overlay-result').textContent ?? '';
      expect(text).toContain('99');
    });
  });

  it('does NOT reopen the result block when lastScan is the same entity', async () => {
    const transport = new StubTransport(async () => RESOLVED_ORDER_42);
    const { openOverlay, setLastScanExternal } = renderOverlay(transport);
    openOverlay();

    // Same scan fires again on the context — no result was rendered yet
    // (user hasn't scanned via overlay), so the overlay should remain in
    // scanner state, not pop a result out of nowhere.
    setLastScanExternal(RESOLVED_ORDER_42);
    // Allow useEffect to flush.
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId('scan-overlay-result')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Focus trap + Esc
// ---------------------------------------------------------------------------

describe('ScanOverlay focus management', () => {
  it('moves focus inside the overlay on open', async () => {
    const transport = new StubTransport(async () => RESOLVED_ORDER_42);
    const { openOverlay } = renderOverlay(transport);
    openOverlay();

    const overlay = await screen.findByTestId('scan-overlay');
    // Focus trap guarantee: active element must be a descendant of the
    // dialog root shortly after mount. Either the close button (our
    // preferred initial target) or the manual-input fallback inside
    // QrCameraScanner's denied state are both acceptable — both live
    // inside the dialog and are reachable via Tab.
    await waitFor(() => {
      const active = document.activeElement;
      expect(active).not.toBeNull();
      expect(overlay.contains(active as Node)).toBe(true);
    });
  });

  it('closes on Escape keydown', async () => {
    const transport = new StubTransport(async () => RESOLVED_ORDER_42);
    const { openOverlay } = renderOverlay(transport);
    openOverlay();
    await screen.findByTestId('scan-overlay-close');

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });

    await waitFor(() => expect(screen.queryByTestId('scan-overlay')).toBeNull());
  });

  it('cycles focus from the last focusable back to the first on Tab', async () => {
    const transport = new StubTransport(async () => RESOLVED_ORDER_42);
    const { openOverlay } = renderOverlay(transport);
    openOverlay();

    const closeBtn = await screen.findByTestId('scan-overlay-close');

    // Snapshot the focusables list from inside the overlay (identical to
    // ScanOverlay's internal FOCUSABLE_SELECTOR). The selector excludes
    // `:disabled`, so transient submit buttons that toggle the disabled
    // attr live outside the trap list.
    const overlay = screen.getByTestId('scan-overlay');
    const focusables = Array.from(
      overlay.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    );
    expect(focusables.length).toBeGreaterThan(1);
    expect(focusables[0]).toBe(closeBtn);
    const last = focusables[focusables.length - 1];

    // Park focus on the last focusable, then dispatch a raw Tab keydown
    // (bypasses user-event's getTabDestination, which wouldn't honor our
    // preventDefault — see user-event keydown.js:109-120). The overlay's
    // keydown listener inspects activeElement and wraps focus when at the
    // trap boundary. Under a real browser, the browser's own tab logic
    // runs AFTER the keydown listener and respects preventDefault.
    act(() => last.focus());
    expect(document.activeElement).toBe(last);
    act(() => {
      document.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }),
      );
    });

    expect(document.activeElement).toBe(closeBtn);
  });

  it('reverses focus on Shift+Tab from the first focusable to the last', async () => {
    const transport = new StubTransport(async () => RESOLVED_ORDER_42);
    const { openOverlay } = renderOverlay(transport);
    openOverlay();

    const closeBtn = await screen.findByTestId('scan-overlay-close');
    const overlay = screen.getByTestId('scan-overlay');
    const focusables = Array.from(
      overlay.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    );
    expect(focusables[0]).toBe(closeBtn);
    const last = focusables[focusables.length - 1];

    act(() => closeBtn.focus());
    expect(document.activeElement).toBe(closeBtn);

    // Raw Shift+Tab keydown — as in the forward test, we bypass user-event
    // so our preventDefault can take effect.
    act(() => {
      document.dispatchEvent(
        new KeyboardEvent('keydown', {
          key: 'Tab',
          shiftKey: true,
          bubbles: true,
          cancelable: true,
        }),
      );
    });

    expect(document.activeElement).toBe(last);
  });
});
