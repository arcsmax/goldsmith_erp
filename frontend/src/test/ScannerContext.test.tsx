// ScannerContext unit tests — Slice 9 of V1.1 QR/Barcode workflow.
//
// Verifies:
//   * Provider renders children and exposes the full value surface.
//   * openScanner / closeScanner flip scanOverlayOpen.
//   * setLastScan writes the ResolveResponse.
//   * benchModeEnabled hydrates from localStorage and persists on toggle (A12.2).
//   * currentLocation hydrates from localStorage with 12h TTL clearance (A9.6).
//   * toggleBenchMode mounts and unmounts the BenchScannerListener —
//     asserted by spying on document.addEventListener/removeEventListener.

import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type MockInstance,
} from 'vitest';
import React from 'react';
import { act, render, renderHook } from '@testing-library/react';

import {
  ScannerProvider,
  useScannerContext,
  type ScannerContextValue,
} from '../contexts/ScannerContext';
import type { ResolveResponse } from '../types/scanner';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const STUB_RESPONSE: ResolveResponse = {
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

function wrapper(
  props: { children: React.ReactNode; onBenchScan?: (payload: string) => void },
): React.ReactElement {
  return (
    <ScannerProvider onBenchScan={props.onBenchScan}>
      {props.children}
    </ScannerProvider>
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Basic provider behaviour
// ---------------------------------------------------------------------------

describe('ScannerProvider basic behaviour', () => {
  it('renders children', () => {
    const { container } = render(
      <ScannerProvider>
        <div data-testid="child">hello</div>
      </ScannerProvider>,
    );
    expect(container.textContent).toBe('hello');
  });

  it('useScannerContext throws outside a provider', () => {
    // Suppress the React error log noise.
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useScannerContext())).toThrow(
      /must be used within a ScannerProvider/,
    );
    errSpy.mockRestore();
  });

  it('exposes the full value surface with correct initial state', () => {
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });
    const v: ScannerContextValue = result.current;
    expect(v.lastScan).toBeNull();
    expect(v.scanOverlayOpen).toBe(false);
    expect(v.inputSource).toBe('manual');
    expect(v.currentLocation).toBeNull();
    expect(v.benchModeEnabled).toBe(false);
    expect(v.lastClientTapAt).toBeNull();
    expect(typeof v.openScanner).toBe('function');
    expect(typeof v.closeScanner).toBe('function');
    expect(typeof v.setLastScan).toBe('function');
    expect(typeof v.setInputSource).toBe('function');
    expect(typeof v.setCurrentLocation).toBe('function');
    expect(typeof v.toggleBenchMode).toBe('function');
    expect(typeof v.recordFabTap).toBe('function');
  });
});

// ---------------------------------------------------------------------------
// Scanner overlay + lastScan
// ---------------------------------------------------------------------------

describe('ScannerContext scanner overlay + lastScan', () => {
  it('openScanner sets scanOverlayOpen=true', () => {
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });
    expect(result.current.scanOverlayOpen).toBe(false);
    act(() => {
      result.current.openScanner();
    });
    expect(result.current.scanOverlayOpen).toBe(true);
  });

  it('closeScanner sets scanOverlayOpen=false', () => {
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });
    act(() => {
      result.current.openScanner();
    });
    expect(result.current.scanOverlayOpen).toBe(true);
    act(() => {
      result.current.closeScanner();
    });
    expect(result.current.scanOverlayOpen).toBe(false);
  });

  it('setLastScan stores the response and clears to null', () => {
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });
    act(() => {
      result.current.setLastScan(STUB_RESPONSE);
    });
    expect(result.current.lastScan).toEqual(STUB_RESPONSE);
    act(() => {
      result.current.setLastScan(null);
    });
    expect(result.current.lastScan).toBeNull();
  });

  it('setInputSource updates inputSource', () => {
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });
    act(() => {
      result.current.setInputSource('camera');
    });
    expect(result.current.inputSource).toBe('camera');
    act(() => {
      result.current.setInputSource('usb_hid');
    });
    expect(result.current.inputSource).toBe('usb_hid');
  });
});

// ---------------------------------------------------------------------------
// benchModeEnabled persistence (A12.2)
// ---------------------------------------------------------------------------

describe('ScannerContext benchModeEnabled persistence', () => {
  it('starts false by default', () => {
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });
    expect(result.current.benchModeEnabled).toBe(false);
  });

  it('hydrates from localStorage on boot', () => {
    localStorage.setItem('scan_bench_mode', 'true');
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });
    expect(result.current.benchModeEnabled).toBe(true);
  });

  it('toggleBenchMode flips state AND persists', () => {
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });
    expect(result.current.benchModeEnabled).toBe(false);
    act(() => {
      result.current.toggleBenchMode();
    });
    expect(result.current.benchModeEnabled).toBe(true);
    expect(localStorage.getItem('scan_bench_mode')).toBe('true');

    act(() => {
      result.current.toggleBenchMode();
    });
    expect(result.current.benchModeEnabled).toBe(false);
    expect(localStorage.getItem('scan_bench_mode')).toBe('false');
  });
});

// ---------------------------------------------------------------------------
// currentLocation persistence with 12h TTL (A9.6)
// ---------------------------------------------------------------------------

describe('ScannerContext currentLocation 12h TTL', () => {
  it('starts null when localStorage is empty', () => {
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });
    expect(result.current.currentLocation).toBeNull();
  });

  it('hydrates from localStorage when within TTL', () => {
    const entry = { value: 'BENCH-A', timestamp: Date.now() - 1000 };
    localStorage.setItem('scan_location', JSON.stringify(entry));
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });
    expect(result.current.currentLocation).toBe('BENCH-A');
  });

  it('clears stale entries older than 12h and returns null', () => {
    const stale = { value: 'BENCH-A', timestamp: Date.now() - (13 * 3600 * 1000) };
    localStorage.setItem('scan_location', JSON.stringify(stale));
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });
    expect(result.current.currentLocation).toBeNull();
    // Entry is removed so a later read doesn't resurrect it.
    expect(localStorage.getItem('scan_location')).toBeNull();
  });

  it('setCurrentLocation persists value and timestamp', () => {
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });
    const before = Date.now();
    act(() => {
      result.current.setCurrentLocation('BENCH-B');
    });
    const raw = localStorage.getItem('scan_location');
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw as string) as { value: string; timestamp: number };
    expect(parsed.value).toBe('BENCH-B');
    expect(parsed.timestamp).toBeGreaterThanOrEqual(before);
    expect(parsed.timestamp).toBeLessThanOrEqual(Date.now());
  });

  it('setCurrentLocation(null) removes the entry', () => {
    localStorage.setItem(
      'scan_location',
      JSON.stringify({ value: 'X', timestamp: Date.now() }),
    );
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });
    act(() => {
      result.current.setCurrentLocation(null);
    });
    expect(result.current.currentLocation).toBeNull();
    expect(localStorage.getItem('scan_location')).toBeNull();
  });

  it('ignores poisoned localStorage entries', () => {
    localStorage.setItem('scan_location', '{not json]');
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });
    expect(result.current.currentLocation).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// BenchScannerListener lifecycle integration
// ---------------------------------------------------------------------------

describe('ScannerContext mounts/unmounts BenchScannerListener', () => {
  // Count `document.addEventListener('keydown', …, {capture:true})` calls as
  // a proxy for "listener mounted". Spying happens per-test so we don't
  // contaminate the baseline.

  function isBenchAdd(args: unknown[]): boolean {
    return (
      args[0] === 'keydown' &&
      typeof args[1] === 'function' &&
      typeof args[2] === 'object' &&
      args[2] !== null &&
      (args[2] as { capture?: boolean }).capture === true
    );
  }

  let addSpy: MockInstance;
  let removeSpy: MockInstance;

  beforeEach(() => {
    addSpy = vi.spyOn(document, 'addEventListener');
    removeSpy = vi.spyOn(document, 'removeEventListener');
  });

  it('does not mount listener when bench mode is off', () => {
    render(
      <ScannerProvider>
        <div />
      </ScannerProvider>,
    );
    const benchMounts = addSpy.mock.calls.filter((c) => isBenchAdd(c));
    expect(benchMounts.length).toBe(0);
  });

  it('mounts listener when bench mode is on at boot', () => {
    localStorage.setItem('scan_bench_mode', 'true');
    render(
      <ScannerProvider>
        <div />
      </ScannerProvider>,
    );
    const benchMounts = addSpy.mock.calls.filter((c) => isBenchAdd(c));
    expect(benchMounts.length).toBe(1);
  });

  it('mounts / unmounts listener on toggle', () => {
    const { result } = renderHook(() => useScannerContext(), {
      wrapper: ({ children }) => wrapper({ children }),
    });

    // Initial: OFF → no mount.
    expect(addSpy.mock.calls.filter((c) => isBenchAdd(c)).length).toBe(0);

    // Toggle ON → mount.
    act(() => {
      result.current.toggleBenchMode();
    });
    expect(addSpy.mock.calls.filter((c) => isBenchAdd(c)).length).toBe(1);
    expect(removeSpy.mock.calls.filter((c) => isBenchAdd(c)).length).toBe(0);

    // Toggle OFF → unmount.
    act(() => {
      result.current.toggleBenchMode();
    });
    expect(removeSpy.mock.calls.filter((c) => isBenchAdd(c)).length).toBe(1);
  });

  it('onBenchScan fires when a real scanner burst arrives while bench mode is on', () => {
    localStorage.setItem('scan_bench_mode', 'true');
    const onBenchScan = vi.fn();
    render(
      <ScannerProvider onBenchScan={onBenchScan}>
        <div />
      </ScannerProvider>,
    );

    // Simulate a scanner burst directly on document.
    const keys = ['O', 'R', 'D', 'E', 'R', ':', '4', '2'];
    const codes = ['KeyO', 'KeyR', 'KeyD', 'KeyE', 'KeyR', 'Semicolon', 'Digit4', 'Digit2'];
    const nowSpy = vi.spyOn(performance, 'now');
    keys.forEach((key, i) => {
      nowSpy.mockReturnValue(100 + i * 5);
      document.dispatchEvent(
        new KeyboardEvent('keydown', { code: codes[i], key, bubbles: true }),
      );
    });
    nowSpy.mockReturnValue(150);
    document.dispatchEvent(
      new KeyboardEvent('keydown', { code: 'Enter', key: 'Enter', bubbles: true }),
    );
    nowSpy.mockRestore();

    expect(onBenchScan).toHaveBeenCalledWith('ORDER:42');
  });

  it('setting inputSource flips to usb_hid automatically on bench scan', () => {
    localStorage.setItem('scan_bench_mode', 'true');
    let latest: ScannerContextValue | null = null;
    const Capture: React.FC = () => {
      latest = useScannerContext();
      return null;
    };
    render(
      <ScannerProvider>
        <Capture />
      </ScannerProvider>,
    );

    // Pre: manual.
    expect(latest!.inputSource).toBe('manual');

    const nowSpy = vi.spyOn(performance, 'now');
    act(() => {
      const codes = ['KeyA', 'KeyB', 'KeyC', 'KeyD'];
      const keys = ['A', 'B', 'C', 'D'];
      keys.forEach((k, i) => {
        nowSpy.mockReturnValue(i * 5);
        document.dispatchEvent(
          new KeyboardEvent('keydown', { code: codes[i], key: k, bubbles: true }),
        );
      });
      nowSpy.mockReturnValue(25);
      document.dispatchEvent(
        new KeyboardEvent('keydown', { code: 'Enter', key: 'Enter', bubbles: true }),
      );
    });
    nowSpy.mockRestore();

    expect(latest!.inputSource).toBe('usb_hid');
  });
});
