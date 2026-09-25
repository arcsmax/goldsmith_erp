// HidScannerListener — 2026-09 audit, scanner-tracking fix item 1.
//
// Verifies the USB/keyboard-wedge scanner is actually connected end-to-end
// once ScannerContext's burst detector (Werkbank-Station-Modus armed) fires:
// resolve -> log -> hand off -> open the sheet, exactly like the camera and
// manual-entry paths. Also verifies the field-focused guard (already
// enforced inside lib/bench-scanner-listener.ts) still holds through this
// wiring: a burst typed into a focused text input must NOT reach the
// handler.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

vi.mock('../api/client', () => ({
  default: { get: mocks.apiGet, post: mocks.apiPost, patch: vi.fn() },
}));

vi.mock('../contexts/TimeTrackingContext', () => ({
  useTimeTracking: () => ({
    runningEntry: null,
    activities: [],
    isLoading: false,
    error: null,
    refreshRunningEntry: vi.fn(async () => {}),
  }),
}));

import { ScannerProvider, useScannerContext } from '../contexts/ScannerContext';
import { ToastProvider } from '../contexts/ToastContext';
import { HidScannerListener, type HidBurstHandler } from '../components/scanner';
import type { ResolveResponse, ScanContext, ScanEvent, Transport } from '../types/scanner';

function orderResolve(): ResolveResponse {
  return {
    resolved: true,
    resolution_path: 'prefix',
    entity_type: 'order',
    entity_id: 42,
    entity: { entity_type: 'order', entity_id: 42, data: { id: 42, status: 'IN_PROGRESS' } },
    actions: [{ id: 'log_only', label: 'Nur erfassen', icon: 'check', primary: false }],
    status_hint: null,
  };
}

function makeTransport(resolveFn: (payload: string, ctx: ScanContext) => Promise<ResolveResponse>): Transport {
  return {
    resolve: resolveFn,
    logScan: vi.fn(async () => {}),
    executeAction: vi.fn(),
  };
}

function Consumer(): React.ReactElement {
  const { scanOverlayOpen, lastScan, inputSource } = useScannerContext();
  return (
    <div
      data-testid="consumer-state"
      data-open={String(scanOverlayOpen)}
      data-resolved={String(lastScan?.resolved ?? '')}
      data-input-source={inputSource}
    />
  );
}

function Harness({
  transport,
  handlerRef,
}: {
  transport: Transport;
  handlerRef: React.MutableRefObject<HidBurstHandler | null>;
}): React.ReactElement {
  const bridge = React.useCallback<HidBurstHandler>(
    (payload) => handlerRef.current?.(payload),
    [handlerRef],
  );
  return (
    <ScannerProvider onBenchScan={bridge}>
      <ToastProvider>
        <HidScannerListener handlerRef={handlerRef} transport={transport} />
        <Consumer />
        <input data-testid="text-field" />
      </ToastProvider>
    </ScannerProvider>
  );
}

/** Dispatch a scanner-speed keystroke burst on `document`, terminated by Enter. */
function dispatchBurst(payload: string): void {
  const codeFor = (ch: string): string => {
    if (/[0-9]/.test(ch)) return `Digit${ch}`;
    if (ch === ':') return 'Semicolon';
    return `Key${ch.toUpperCase()}`;
  };
  const nowSpy = vi.spyOn(performance, 'now');
  let t = 0;
  act(() => {
    for (const ch of payload) {
      nowSpy.mockReturnValue(t);
      document.dispatchEvent(
        new KeyboardEvent('keydown', { code: codeFor(ch), key: ch, bubbles: true }),
      );
      t += 5;
    }
    nowSpy.mockReturnValue(t);
    document.dispatchEvent(
      new KeyboardEvent('keydown', { code: 'Enter', key: 'Enter', bubbles: true }),
    );
  });
  nowSpy.mockRestore();
}

let rowCounter = 0;

beforeEach(() => {
  localStorage.clear();
  rowCounter = 0;
  mocks.apiGet.mockReset();
  mocks.apiPost.mockReset().mockImplementation(async (url: string, body: Record<string, unknown>) => {
    if (url === '/scan/log') {
      rowCounter += 1;
      return { data: { id: `00000000-0000-4000-8000-00000000000${rowCounter}`, ...body } };
    }
    if (url === '/scan/log/batch') return { data: { ingested: 0 } };
    return { data: {} };
  });
  // Werkbank-Station-Modus armed: the burst-detection listener mounts.
  localStorage.setItem('scan_bench_mode', 'true');
});

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('HidScannerListener', () => {
  it('resolves, logs and opens the action sheet for a burst with no field focused', async () => {
    const resolveSpy = vi.fn(async () => orderResolve());
    const transport = makeTransport(resolveSpy);
    const handlerRef: React.MutableRefObject<HidBurstHandler | null> = { current: null };

    render(<Harness transport={transport} handlerRef={handlerRef} />);

    // Nothing focused (document.body is active by default in jsdom).
    dispatchBurst('ORDER:42');

    await waitFor(() => expect(resolveSpy).toHaveBeenCalledWith('ORDER:42', expect.anything()));
    await waitFor(() =>
      expect(screen.getByTestId('consumer-state')).toHaveAttribute('data-open', 'true'),
    );
    expect(screen.getByTestId('consumer-state')).toHaveAttribute('data-resolved', 'true');
    expect(screen.getByTestId('consumer-state')).toHaveAttribute('data-input-source', 'usb_hid');

    // Logged before the sheet counts as "opened" — one scan_only row.
    const logCalls = mocks.apiPost.mock.calls.filter((c) => c[0] === '/scan/log');
    expect(logCalls).toHaveLength(1);
    expect((logCalls[0][1] as ScanEvent).action_taken).toBe('scan_only');
    expect((logCalls[0][1] as ScanEvent).context?.input_source).toBe('usb_hid');
  });

  it('ignores a burst typed while a text field is focused', async () => {
    const resolveSpy = vi.fn(async () => orderResolve());
    const transport = makeTransport(resolveSpy);
    const handlerRef: React.MutableRefObject<HidBurstHandler | null> = { current: null };

    render(<Harness transport={transport} handlerRef={handlerRef} />);

    const field = screen.getByTestId('text-field');
    act(() => {
      field.focus();
    });
    expect(document.activeElement).toBe(field);

    dispatchBurst('ORDER:42');

    // Give any (incorrectly fired) async handler a tick to run before asserting.
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(resolveSpy).not.toHaveBeenCalled();
    expect(mocks.apiPost.mock.calls.filter((c) => c[0] === '/scan/log')).toHaveLength(0);
    expect(screen.getByTestId('consumer-state')).toHaveAttribute('data-open', 'false');
  });
});
