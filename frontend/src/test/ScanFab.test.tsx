// ScanFab component tests — Slice 10 of V1.1 QR/Barcode workflow.
//
// Scope (plan §Slice 10 verification + AMENDMENTS A10.1 / A10.2):
//   * Hidden on /login and /register.
//   * Visible on other authenticated routes.
//   * Hidden while the scan overlay is already open.
//   * Tap invokes openScanner() AND recordFabTap() via ScannerContext.
//   * `.scan-fab--stacked` class applied when a timer is running.
//   * aria-label present for screen readers.
//
// The ScannerContext is mocked so we can observe `openScanner` /
// `recordFabTap` calls directly, and the TimeTracking hook is mocked so we
// can flip `runningEntry` between tests without spinning up the real
// WebSocket machinery.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { ScanFab } from '../components/scanner/ScanFab';
import type { ScannerContextValue } from '../contexts/ScannerContext';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

interface MockScannerContextOverrides {
  scanOverlayOpen?: boolean;
}

const mockContext: ScannerContextValue = {
  lastScan: null,
  scanOverlayOpen: false,
  openScanner: vi.fn(),
  closeScanner: vi.fn(),
  setLastScan: vi.fn(),
  inputSource: 'manual',
  setInputSource: vi.fn(),
  currentLocation: null,
  setCurrentLocation: vi.fn(),
  benchModeEnabled: false,
  toggleBenchMode: vi.fn(),
  lastClientTapAt: null,
  recordFabTap: vi.fn(),
};

vi.mock('../contexts/ScannerContext', async () => {
  const actual = await vi.importActual<typeof import('../contexts/ScannerContext')>(
    '../contexts/ScannerContext',
  );
  return {
    ...actual,
    useScannerContext: (): ScannerContextValue => mockContext,
  };
});

interface MockTimeTracking {
  runningEntry: unknown;
}
const mockTimeTracking: MockTimeTracking = { runningEntry: null };

vi.mock('../contexts', async () => {
  const actual = await vi.importActual<typeof import('../contexts')>('../contexts');
  return {
    ...actual,
    useTimeTracking: () => mockTimeTracking,
  };
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderAtRoute(
  path: string,
  overrides: MockScannerContextOverrides = {},
): ReturnType<typeof render> {
  mockContext.scanOverlayOpen = overrides.scanOverlayOpen ?? false;
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ScanFab />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  // Reset mock state between tests.
  mockContext.scanOverlayOpen = false;
  mockContext.openScanner = vi.fn();
  mockContext.recordFabTap = vi.fn();
  mockTimeTracking.runningEntry = null;
});

// ---------------------------------------------------------------------------
// Visibility
// ---------------------------------------------------------------------------

describe('ScanFab visibility', () => {
  it('is hidden on /login', () => {
    renderAtRoute('/login');
    expect(screen.queryByTestId('scan-fab')).toBeNull();
  });

  it('is hidden on /register', () => {
    renderAtRoute('/register');
    expect(screen.queryByTestId('scan-fab')).toBeNull();
  });

  it('is visible on /dashboard', () => {
    renderAtRoute('/dashboard');
    expect(screen.getByTestId('scan-fab')).toBeInTheDocument();
  });

  it('is visible on /orders', () => {
    renderAtRoute('/orders');
    expect(screen.getByTestId('scan-fab')).toBeInTheDocument();
  });

  it('is visible on nested routes like /orders/42', () => {
    renderAtRoute('/orders/42');
    expect(screen.getByTestId('scan-fab')).toBeInTheDocument();
  });

  it('is hidden when the scan overlay is already open', () => {
    renderAtRoute('/dashboard', { scanOverlayOpen: true });
    expect(screen.queryByTestId('scan-fab')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Accessibility
// ---------------------------------------------------------------------------

describe('ScanFab accessibility', () => {
  it('has a German aria-label', () => {
    renderAtRoute('/dashboard');
    expect(
      screen.getByRole('button', { name: 'QR-Code scannen' }),
    ).toBeInTheDocument();
  });

  it('renders as a <button type="button"> (not a form submit)', () => {
    renderAtRoute('/dashboard');
    const fab = screen.getByTestId('scan-fab');
    expect(fab.tagName).toBe('BUTTON');
    expect(fab.getAttribute('type')).toBe('button');
  });
});

// ---------------------------------------------------------------------------
// Tap wiring (A10.2)
// ---------------------------------------------------------------------------

describe('ScanFab tap wiring', () => {
  it('invokes openScanner on tap', async () => {
    const user = userEvent.setup();
    renderAtRoute('/dashboard');
    await user.click(screen.getByTestId('scan-fab'));
    expect(mockContext.openScanner).toHaveBeenCalledTimes(1);
  });

  it('records the FAB tap timestamp via recordFabTap (A10.2)', async () => {
    const user = userEvent.setup();
    renderAtRoute('/dashboard');
    await user.click(screen.getByTestId('scan-fab'));
    expect(mockContext.recordFabTap).toHaveBeenCalledTimes(1);
  });

  it('records the tap BEFORE opening the overlay (timing guarantees)', async () => {
    const order: string[] = [];
    mockContext.recordFabTap = vi.fn(() => {
      order.push('recordFabTap');
    });
    mockContext.openScanner = vi.fn(() => {
      order.push('openScanner');
    });
    const user = userEvent.setup();
    renderAtRoute('/dashboard');
    await user.click(screen.getByTestId('scan-fab'));
    expect(order).toEqual(['recordFabTap', 'openScanner']);
  });
});

// ---------------------------------------------------------------------------
// Stacked class (A10.1)
// ---------------------------------------------------------------------------

describe('ScanFab stacking with TimerWidget (A10.1)', () => {
  it('does NOT apply scan-fab--stacked when no timer is running', () => {
    mockTimeTracking.runningEntry = null;
    renderAtRoute('/dashboard');
    const fab = screen.getByTestId('scan-fab');
    expect(fab.className).toContain('scan-fab');
    expect(fab.className).not.toContain('scan-fab--stacked');
  });

  it('applies scan-fab--stacked when a timer is running', () => {
    mockTimeTracking.runningEntry = {
      id: 1,
      order_id: 42,
      activity_id: 7,
      start_time: new Date().toISOString(),
    };
    renderAtRoute('/dashboard');
    const fab = screen.getByTestId('scan-fab');
    expect(fab.className).toContain('scan-fab--stacked');
  });
});
