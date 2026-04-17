// Slice 11 primary value scenario — end-to-end integration test.
//
// Scenario (from plan §Slice 11 + task brief):
//
//   1. Timer is running on ORDER:1 (runningEntry supplied by mocked
//      TimeTrackingContext).
//   2. User opens the ScanOverlay and scans ORDER:2 via the manual input.
//   3. QuickActionModalV2 renders with "Timer wechseln" as the primary
//      action.
//   4. User taps "Timer wechseln".
//   5. ORDER:1 timer is stopped (POST /time-tracking/<id>/stop).
//   6. ORDER:2 timer is started (POST /time-tracking/start).
//   7. The overlay closes.
//
// The test mocks apiClient directly so we never hit the network. It is
// deliberately lightweight — bigger surface tests belong in each
// component's own test file. This pins the full happy-path wire-through.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// --- Mock the yudiel QR scanner so we never start a camera. --------------
vi.mock('@yudiel/react-qr-scanner', () => {
  return {
    Scanner: () => <div data-testid="mock-yudiel-scanner" />,
  };
});

// --- Mock TimeTrackingContext with runningEntry on ORDER:1. --------------
// Must use `vi.hoisted` because vi.mock factories execute before module
// imports — plain `const mocks.refreshTimer = vi.fn()` would be initialised
// AFTER the mock factory runs.
const mocks = vi.hoisted(() => ({
  refreshTimer: vi.fn(async () => {}),
  navigate: vi.fn(),
  apiPost: vi.fn(async () => ({ data: {} })),
  apiPatch: vi.fn(async () => ({ data: {} })),
  apiGet: vi.fn(async () => ({ data: {} })),
}));

vi.mock('../contexts/TimeTrackingContext', () => ({
  useTimeTracking: () => ({
    runningEntry: {
      id: 'entry-original',
      order_id: 1,
      activity_id: 9,
      user_id: 1,
      start_time: new Date().toISOString(),
    },
    activities: [],
    isLoading: false,
    error: null,
    startTracking: vi.fn(),
    stopTracking: vi.fn(),
    switchTracking: vi.fn(),
    refreshRunningEntry: mocks.refreshTimer,
    refreshActivities: vi.fn(),
    clearError: vi.fn(),
  }),
}));

// --- Stub react-router useNavigate. --------------------------------------
vi.mock('react-router-dom', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
  };
});

// --- Mock apiClient so we can assert the exact request sequence. ---------
vi.mock('../api/client', () => ({
  default: {
    post: mocks.apiPost,
    patch: mocks.apiPatch,
    get: mocks.apiGet,
  },
}));

// --- HTMLMediaElement shims for jsdom/happy-dom audio kit. --------------
// @ts-expect-error happy-dom stub
HTMLMediaElement.prototype.play = vi.fn(() => Promise.resolve());
// @ts-expect-error happy-dom stub
HTMLMediaElement.prototype.pause = vi.fn();
Object.defineProperty(navigator, 'vibrate', {
  value: vi.fn(() => true),
  writable: true,
  configurable: true,
});
Object.defineProperty(navigator, 'mediaDevices', {
  value: {
    getUserMedia: vi.fn(() =>
      Promise.reject(
        Object.assign(new Error('denied'), { name: 'NotAllowedError' }),
      ),
    ),
    enumerateDevices: vi.fn(() => Promise.resolve([])),
  },
  writable: true,
  configurable: true,
});

// Set up a last-used activity so start_timer proceeds without a warning
// toast. The handler reads localStorage to source activityId when none
// is passed explicitly — matches the real Slice 12 flow.
beforeEach(() => {
  localStorage.setItem('scanner_last_activity_id', '9');
  mocks.apiPost.mockClear();
  mocks.apiPatch.mockClear();
  mocks.refreshTimer.mockClear();
  mocks.navigate.mockClear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

import { ScanOverlay } from '../components/scanner/ScanOverlay';
import {
  ScannerProvider,
  useScannerContext,
} from '../contexts/ScannerContext';
import type {
  ResolveResponse,
  ScanContext,
  Transport,
  ScanEvent,
  ActionExecution,
  ActionResult,
} from '../types/scanner';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const RESOLVED_ORDER_2: ResolveResponse = {
  resolved: true,
  resolution_path: 'prefix',
  entity_type: 'order',
  entity_id: 2,
  entity: {
    entity_type: 'order',
    entity_id: 2,
    data: {
      id: 2,
      title: 'Kette Schmidt',
      status: 'in_progress',
      customer_initials: 'S.',
    },
  },
  actions: [
    // "Timer wechseln" is primary per the scanner_service logic when
    // runningEntry.order_id !== scanned order id.
    { id: 'switch_timer', label: 'Timer wechseln', icon: 'swap', primary: true },
    { id: 'change_status', label: 'Status ändern', icon: 'clipboard', primary: false },
    { id: 'open_entity', label: 'Öffnen', icon: 'link', primary: false },
  ],
  status_hint: null,
};

class StubTransport implements Transport {
  async resolve(
    _payload: string,
    _context: ScanContext,
  ): Promise<ResolveResponse> {
    return RESOLVED_ORDER_2;
  }
  async logScan(_event: ScanEvent): Promise<void> {}
  async executeAction(_action: ActionExecution): Promise<ActionResult> {
    return { success: true };
  }
}

function renderScenario(): {
  openOverlay: () => void;
} {
  let openOverlayFn: () => void = () => {};
  const Harness: React.FC = () => {
    const ctx = useScannerContext();
    openOverlayFn = ctx.openScanner;
    return <ScanOverlay transport={new StubTransport()} />;
  };
  render(
    <ScannerProvider>
      <Harness />
    </ScannerProvider>,
  );
  return {
    openOverlay: () => act(() => openOverlayFn()),
  };
}

// ---------------------------------------------------------------------------
// Test
// ---------------------------------------------------------------------------

describe('Slice 11 primary value scenario — scan ORDER:2 → switch_timer', () => {
  it('scans ORDER:2, taps Timer wechseln, stops ORDER:1 timer + starts ORDER:2 timer', async () => {
    const { openOverlay } = renderScenario();
    openOverlay();

    const input = await screen.findByLabelText('Code manuell eingeben');
    const user = userEvent.setup();
    await user.type(input, 'ORDER:2{Enter}');

    // QuickActionModalV2 mounted.
    await screen.findByTestId('qa-modal-v2');
    // First action is the primary "Timer wechseln".
    const switchBtn = screen.getByTestId('qa-action-switch_timer');
    expect(switchBtn.className).toContain('qa-action--primary');

    // Tap the action.
    await user.click(switchBtn);

    // Assert the sequence: stop(entry-original) then start(order_id: 2).
    await waitFor(() => {
      expect(mocks.apiPost.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
    const calls = mocks.apiPost.mock.calls;
    const stopCall = calls.find((c) => c[0] === '/time-tracking/entry-original/stop');
    const startCall = calls.find((c) => c[0] === '/time-tracking/start');
    expect(stopCall).toBeDefined();
    expect(startCall).toBeDefined();
    expect(startCall?.[1]).toEqual(
      expect.objectContaining({
        order_id: 2,
        activity_id: 9,
      }),
    );

    // Timer refresh fired so TimerWidget will re-render.
    expect(mocks.refreshTimer).toHaveBeenCalled();

    // Overlay closed.
    await waitFor(() => {
      expect(screen.queryByTestId('scan-overlay')).toBeNull();
    });
  });
});
