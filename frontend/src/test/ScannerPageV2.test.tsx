// ScannerPage V2 tests — Slice 12 of V1.1 QR/Barcode workflow.
//
// Scope:
//   * Camera section renders — camera stays inactive until user taps
//     "Kamera starten".
//   * Manual input submit triggers ScannerRouter.resolve() via the shared
//     apiClient, and the resolved response flows into ScannerContext.
//   * "Letzte Scans" list renders items from the mocked GET /scan/log
//     response (no localStorage access).
//   * Legacy localStorage migration fires once when
//     ``last_scanned_orders`` exists and clears the key on success; if
//     the POST fails the key is retained.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock the yudiel QR scanner so no camera is started.
vi.mock('@yudiel/react-qr-scanner', () => {
  return {
    Scanner: () => <div data-testid="mock-yudiel-scanner" />,
  };
});

// Hoisted mock instances — needed so vi.mock factories can reference them.
const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock('../api/client', () => ({
  default: {
    get: mocks.apiGet,
    post: mocks.apiPost,
    patch: vi.fn(),
  },
}));

vi.mock('react-router-dom', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
  };
});

// Stub TimeTrackingContext so the page sees no running timer.
vi.mock('../contexts/TimeTrackingContext', () => ({
  useTimeTracking: () => ({
    runningEntry: null,
    activities: [],
    isLoading: false,
    error: null,
    startTracking: vi.fn(),
    stopTracking: vi.fn(),
    switchTracking: vi.fn(),
    refreshRunningEntry: vi.fn(async () => {}),
    refreshActivities: vi.fn(),
    clearError: vi.fn(),
  }),
}));

// Import component AFTER mocks are set up.
import { ScannerPage } from '../pages/ScannerPage';
import { ScannerProvider } from '../contexts/ScannerContext';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderPage(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <ScannerProvider>
        <ScannerPage />
      </ScannerProvider>
    </MemoryRouter>,
  );
}

const HISTORY_ROWS = [
  {
    id: 'uuid-1',
    scanned_at: '2026-04-16T10:00:00Z',
    user_id: 1,
    raw_payload: 'ORDER:42',
    resolved_type: 'order',
    resolved_id: '42',
    resolution_path: 'prefix',
    action_taken: 'start_timer',
    offline_queued: false,
    synced_at: null,
  },
  {
    id: 'uuid-2',
    scanned_at: '2026-04-16T09:45:00Z',
    user_id: 1,
    raw_payload: 'OINK',
    resolved_type: null,
    resolved_id: null,
    resolution_path: 'unknown',
    action_taken: null,
    offline_queued: false,
    synced_at: null,
  },
];

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  mocks.apiGet.mockReset();
  mocks.apiPost.mockReset();
  mocks.navigate.mockReset();
  localStorage.clear();

  // Default: GET /scan/log returns two rows; POST batch and resolve succeed.
  mocks.apiGet.mockImplementation(async (url: string) => {
    if (url === '/scan/log') {
      return { data: HISTORY_ROWS };
    }
    return { data: [] };
  });
  mocks.apiPost.mockResolvedValue({ data: {} });
});

afterEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ScannerPage V2 (Slice 12)', () => {
  it('renders camera, manual input and history sections', async () => {
    renderPage();
    expect(
      screen.getByTestId('scanner-camera-section'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('scanner-manual-form')).toBeInTheDocument();
    expect(screen.getByTestId('scanner-history-section')).toBeInTheDocument();
    // Camera stays inactive until user taps "Kamera starten".
    expect(screen.getByTestId('scanner-camera-start')).toBeInTheDocument();
    expect(
      screen.queryByTestId('mock-yudiel-scanner'),
    ).not.toBeInTheDocument();
  });

  it('activates camera component only after tapping "Kamera starten"', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByTestId('scanner-camera-start'));
    // The QrCameraScanner renders an "idle" initial state (no camera yet);
    // the important contract is that the "Kamera stoppen" affordance appears.
    expect(
      await screen.findByTestId('scanner-camera-stop'),
    ).toBeInTheDocument();
  });

  it('renders "Letzte Scans" from mocked API (no localStorage)', async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByTestId('scanner-history-list'),
      ).toBeInTheDocument();
    });
    // GET called with user_id=me + limit.
    const getCall = mocks.apiGet.mock.calls.find(
      ([url]) => url === '/scan/log',
    );
    expect(getCall).toBeDefined();
    expect(getCall?.[1]?.params).toMatchObject({ user_id: 'me', limit: 20 });
    // Row labels reflect resolved entity.
    expect(
      screen.getByTestId('scanner-history-item-uuid-1'),
    ).toHaveTextContent('ORDER:42');
    // Unknown row renders the raw payload.
    expect(
      screen.getByTestId('scanner-history-item-uuid-2'),
    ).toHaveTextContent('OINK');
  });

  it('renders empty state when history is empty', async () => {
    mocks.apiGet.mockImplementation(async () => ({ data: [] }));
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByTestId('scanner-history-empty'),
      ).toBeInTheDocument();
    });
  });

  it('renders error state when history fetch fails', async () => {
    mocks.apiGet.mockImplementation(async () => {
      throw new Error('boom');
    });
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByTestId('scanner-history-error'),
      ).toBeInTheDocument();
    });
  });

  it('manual input submit calls scanner/resolve via apiClient', async () => {
    const user = userEvent.setup();
    // POST resolve returns a resolved response.
    mocks.apiPost.mockImplementation(async (url: string) => {
      if (url === '/scan/resolve') {
        return {
          data: {
            resolved: true,
            resolution_path: 'prefix',
            entity_type: 'order',
            entity_id: 42,
            entity: null,
            actions: [],
            status_hint: null,
          },
        };
      }
      return { data: {} };
    });

    renderPage();
    const input = await screen.findByTestId('scanner-manual-input');
    await user.type(input, 'ORDER:42');
    await user.click(screen.getByTestId('scanner-manual-submit'));

    await waitFor(() => {
      const call = mocks.apiPost.mock.calls.find(
        ([url]) => url === '/scan/resolve',
      );
      expect(call).toBeDefined();
      expect(call?.[1]).toMatchObject({ raw_payload: 'ORDER:42' });
    });
  });

  it('migrates legacy localStorage entries via /scan/log/batch and clears the key', async () => {
    localStorage.setItem(
      'last_scanned_orders',
      JSON.stringify([
        { id: 1, time: '10:00' },
        { id: 2, time: '10:15' },
      ]),
    );

    // Track POST /scan/log/batch.
    mocks.apiPost.mockImplementation(async (url: string) => {
      if (url === '/scan/log/batch') {
        return { data: { ingested: 2, deduplicated: 0, rejected: 0, reasons: [] } };
      }
      return { data: [] };
    });

    renderPage();

    await waitFor(() => {
      const call = mocks.apiPost.mock.calls.find(
        ([url]) => url === '/scan/log/batch',
      );
      expect(call).toBeDefined();
      expect(call?.[1]).toMatchObject({
        events: expect.arrayContaining([
          expect.objectContaining({
            raw_payload: 'ORDER:1',
            resolution_path: 'import',
          }),
        ]),
      });
    });

    // Success path: key is removed.
    await waitFor(() => {
      expect(localStorage.getItem('last_scanned_orders')).toBeNull();
    });
  });

  it('keeps legacy localStorage entries when batch POST fails', async () => {
    localStorage.setItem(
      'last_scanned_orders',
      JSON.stringify([{ id: 9, time: '11:00' }]),
    );

    mocks.apiPost.mockImplementation(async (url: string) => {
      if (url === '/scan/log/batch') {
        throw new Error('network down');
      }
      return { data: [] };
    });

    renderPage();

    // Wait until the batch attempt happens.
    await waitFor(() => {
      const call = mocks.apiPost.mock.calls.find(
        ([url]) => url === '/scan/log/batch',
      );
      expect(call).toBeDefined();
    });

    // The localStorage key survives for retry next mount.
    expect(
      localStorage.getItem('last_scanned_orders'),
    ).not.toBeNull();
  });

  it('does NOT call /scan/log/batch when legacy key is absent', async () => {
    renderPage();
    // Give the effect a tick to settle.
    await waitFor(() => {
      expect(mocks.apiGet).toHaveBeenCalledWith(
        '/scan/log',
        expect.anything(),
      );
    });
    const batchCall = mocks.apiPost.mock.calls.find(
      ([url]) => url === '/scan/log/batch',
    );
    expect(batchCall).toBeUndefined();
  });
});
