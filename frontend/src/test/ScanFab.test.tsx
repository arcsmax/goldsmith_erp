// ScanFab component tests — Slice 10 of V1.1 QR/Barcode workflow.
//
// Scope (plan §Slice 10 verification + AMENDMENTS A10.1 / A10.2):
//   * Hidden on /login and /register.
//   * Visible on other authenticated routes.
//   * Hidden while the scan overlay is already open.
//   * Tap invokes openScanner() AND recordFabTap() via ScannerContext.
//   * Renders with the `.scan-fab` class it needs for CSS positioning —
//     the actual TimerWidget-stacking offset is a pure-CSS rule
//     (`.has-timer-fab .scan-fab`, ScanFab.css) driven by MainLayout's
//     ancestor class, not by anything ScanFab computes itself (A10.1); see
//     MainLayout.test.tsx for the ancestor-class assertion.
//   * aria-label present for screen readers.
//
// The ScannerContext is mocked so we can observe `openScanner` /
// `recordFabTap` calls directly.

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
// Stacking with TimerWidget (A10.1)
// ---------------------------------------------------------------------------
//
// ScanFab itself no longer computes a "stacked" state — TimerWidget always
// occupies the bottom-right slot when mounted (idle, running, or expanded),
// so the offset is a pure-CSS rule keyed off the `.has-timer-fab` ancestor
// class MainLayout sets (see ScanFab.css `.has-timer-fab .scan-fab`, and
// MainLayout.test.tsx for the ancestor-class assertion). Here we only need
// to confirm ScanFab keeps the stable `.scan-fab` hook that rule targets,
// in and out of a `.has-timer-fab` ancestor.

describe('ScanFab stacking with TimerWidget (A10.1)', () => {
  it('always renders the .scan-fab class the ancestor CSS rule targets', () => {
    renderAtRoute('/dashboard');
    const fab = screen.getByTestId('scan-fab');
    expect(fab).toHaveClass('scan-fab');
  });

  it('keeps the .scan-fab class when mounted inside a .has-timer-fab ancestor', () => {
    mockContext.scanOverlayOpen = false;
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <div className="has-timer-fab" data-testid="ancestor">
          <ScanFab />
        </div>
      </MemoryRouter>,
    );
    const ancestor = screen.getByTestId('ancestor');
    const fab = screen.getByTestId('scan-fab');
    expect(ancestor).toHaveClass('has-timer-fab');
    expect(ancestor).toContainElement(fab);
    expect(fab).toHaveClass('scan-fab');
  });
});
