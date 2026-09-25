// FE-02 end-to-end (component level): fresh device, no running timer, no
// localStorage. Scan ORDER:2 → tap "Timer starten" → ActivityPicker opens →
// pick an activity → POST /time-tracking/start carries activity_id.

import { beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import { QueryWrapper, createTestQueryClient } from './queryWrapper';
import userEvent from '@testing-library/user-event';

vi.mock('@yudiel/react-qr-scanner', () => ({
  Scanner: () => <div data-testid="mock-yudiel-scanner" />,
}));

const mocks = vi.hoisted(() => ({
  refreshTimer: vi.fn(async () => {}),
  navigate: vi.fn(),
  apiPost: vi.fn(async (_url: string, _body?: unknown) => ({ data: {} })),
  getAll: vi.fn(),
  getMostUsed: vi.fn(),
}));

vi.mock('../contexts/TimeTrackingContext', () => ({
  useTimeTracking: () => ({
    runningEntry: null,
    refreshRunningEntry: mocks.refreshTimer,
  }),
}));

vi.mock('react-router-dom', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock('../api/client', () => ({
  default: {
    post: mocks.apiPost,
    patch: vi.fn(async () => ({ data: {} })),
    get: vi.fn(async () => ({ data: {} })),
  },
}));

vi.mock('../api/activities', () => ({
  activitiesApi: { getAll: mocks.getAll, getMostUsed: mocks.getMostUsed },
}));

HTMLMediaElement.prototype.play = vi.fn(() => Promise.resolve());
HTMLMediaElement.prototype.pause = vi.fn();
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
import { ScannerProvider, useScannerContext } from '../contexts/ScannerContext';
import type {
  ActionExecution,
  ActionResult,
  ResolveResponse,
  ScanEvent,
  Transport,
} from '../types/scanner';

const RESOLVED_ORDER_2: ResolveResponse = {
  resolved: true,
  resolution_path: 'prefix',
  entity_type: 'order',
  entity_id: 2,
  entity: { entity_type: 'order', entity_id: 2, data: { id: 2, title: 'Kette' } },
  actions: [{ id: 'start_timer', label: 'Timer starten', icon: 'play', primary: true }],
  status_hint: null,
};

class StubTransport implements Transport {
  async resolve(): Promise<ResolveResponse> {
    return RESOLVED_ORDER_2;
  }
  async logScan(_event: ScanEvent): Promise<void> {}
  async executeAction(_action: ActionExecution): Promise<ActionResult> {
    return { success: true };
  }
}

const ACTIVITY = {
  id: 12,
  name: 'Polieren',
  category: 'fabrication',
  icon: null,
  color: null,
  usage_count: 3,
  average_duration_minutes: null,
  is_custom: false,
};

function renderOverlay(): () => void {
  let open: () => void = () => {};
  const Harness: React.FC = () => {
    open = useScannerContext().openScanner;
    return <ScanOverlay transport={new StubTransport()} />;
  };
  // W4-03: the ActivityPicker reads activities through TanStack Query.
  render(
    <QueryWrapper client={createTestQueryClient()}>
      <ScannerProvider>
        <Harness />
      </ScannerProvider>
    </QueryWrapper>,
  );
  return () => act(() => open());
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  mocks.getAll.mockResolvedValue([ACTIVITY]);
  mocks.getMostUsed.mockResolvedValue([]);
});

describe('ScanOverlay — start timer on a fresh device (FE-02)', () => {
  it('asks for an activity and sends activity_id with the start call', async () => {
    const openOverlay = renderOverlay();
    openOverlay();
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText('Code manuell eingeben'), 'ORDER:2{Enter}');
    await user.click(await screen.findByTestId('qa-action-start_timer'));

    // Picker is shown instead of a dead-end warning.
    await screen.findByTestId('activity-picker-modal');
    await user.click(await screen.findByRole('button', { name: /Polieren/ }));

    await waitFor(() => {
      expect(mocks.apiPost).toHaveBeenCalledWith(
        '/time-tracking/start',
        expect.objectContaining({ order_id: 2, activity_id: 12 }),
      );
    });
    await waitFor(() => expect(screen.queryByTestId('scan-overlay')).toBeNull());
  });

  it('shows a German error and does not start when the picker is cancelled', async () => {
    const openOverlay = renderOverlay();
    openOverlay();
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText('Code manuell eingeben'), 'ORDER:2{Enter}');
    await user.click(await screen.findByTestId('qa-action-start_timer'));
    await screen.findByTestId('activity-picker-modal');
    // W4-03: the picker is a src/ui Sheet; its close button is "Schließen".
    const sheet = await screen.findByRole('dialog', { name: 'Aktivität für den Timer wählen' });
    await user.click(within(sheet).getByRole('button', { name: 'Schließen' }));

    expect(await screen.findByTestId('qa-error')).toHaveTextContent(/Keine Aktivität gewählt/);
    // Only the scan-log rows went out (scan tracking); no timer start.
    const timerCalls = mocks.apiPost.mock.calls.filter(
      (call: unknown[]) => !String(call[0]).startsWith('/scan/log'),
    );
    expect(timerCalls).toHaveLength(0);
  });
});
