// W2-01 / DOM-01 — scanner "Foto" on an order scan deep-links to the order's
// Fotos tab with the camera auto-opened: /orders/{id}?tab=fotos&capture=1.
// This is tap 1 of the 3-tap DoD (Foto → Kundeninfo → tick photo).

import { beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@yudiel/react-qr-scanner', () => ({
  Scanner: () => <div data-testid="mock-yudiel-scanner" />,
}));

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}));

vi.mock('../contexts/TimeTrackingContext', () => ({
  useTimeTracking: () => ({
    runningEntry: null,
    refreshRunningEntry: vi.fn(async () => {}),
  }),
}));

vi.mock('react-router-dom', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock('../api/client', () => ({
  default: {
    post: vi.fn(async () => ({ data: {} })),
    patch: vi.fn(async () => ({ data: {} })),
    get: vi.fn(async () => ({ data: {} })),
  },
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

// Mirrors scanner_service._compute_order_actions for a GOLDSMITH.
const RESOLVED_ORDER_7: ResolveResponse = {
  resolved: true,
  resolution_path: 'prefix',
  entity_type: 'order',
  entity_id: 7,
  entity: { id: 7, title: 'Trauring' },
  actions: [
    { id: 'start_timer', label: 'Timer starten', icon: 'play', primary: true },
    { id: 'take_photo', label: 'Foto aufnehmen', icon: 'camera', primary: false },
    { id: 'open_entity', label: 'Öffnen', icon: 'open', primary: false },
  ],
  status_hint: null,
};

class StubTransport implements Transport {
  async resolve(): Promise<ResolveResponse> {
    return RESOLVED_ORDER_7;
  }
  async logScan(_event: ScanEvent): Promise<void> {}
  async executeAction(_action: ActionExecution): Promise<ActionResult> {
    return { success: true };
  }
}

function renderOverlay(): () => void {
  let open: () => void = () => {};
  const Harness: React.FC = () => {
    open = useScannerContext().openScanner;
    return <ScanOverlay transport={new StubTransport()} />;
  };
  render(
    <ScannerProvider>
      <Harness />
    </ScannerProvider>,
  );
  return () => act(() => open());
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

describe('ScanOverlay — Foto on an order scan (W2-01)', () => {
  it('shows a Foto action and deep-links to the Fotos tab with the camera', async () => {
    const openOverlay = renderOverlay();
    openOverlay();
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText('Code manuell eingeben'), 'ORDER:7{Enter}');
    const fotoButton = await screen.findByTestId('qa-action-take_photo');
    expect(fotoButton).toHaveTextContent(/Foto/);

    await user.click(fotoButton);

    await waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith('/orders/7?tab=fotos&capture=1'),
    );
    await waitFor(() => expect(screen.queryByTestId('scan-overlay')).toBeNull());
  });
});
