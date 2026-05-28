// QrCameraScanner component tests — Slice 8 of V1.1 QR/Barcode workflow.
//
// Post black-screen-fix (2026-04-18): QrCameraScanner no longer probes the
// camera with its own getUserMedia call — LazyScanner (@yudiel/react-qr-scanner)
// owns the single gUM. Permission states are driven by:
//   * enumerateDevices() — used only to size the cameraCount for the flip UI
//   * handleScannerError (onError prop on <Scanner>) — routes NotAllowedError
//     to 'denied' and NotFoundError to 'unavailable'.
//
// Scope:
//   * active=false: the Scanner does NOT mount (idle state).
//   * active=true: the Scanner mounts exactly once.
//   * NotAllowedError via Scanner.onError → denied UI renders with
//     autofocused manual input.
//   * NotFoundError via Scanner.onError → unavailable UI renders.
//   * Successful scan via mocked <Scanner> → onScan('camera').
//   * Manual input submit → onScan('manual').
//   * Successful scan → navigator.vibrate(200).
//   * Successful scan → audio.play() fired for OK sound.
//   * Muted (localStorage scan_audio_muted='true') → audio.play() NOT called.
//   * Torch button hidden (always, in V1.1).
//   * active=false cleanup → Scanner unmounts, idle card replaces it.
//
// The vendor module (@yudiel/react-qr-scanner) is mocked via vi.mock so we
// never pull it into the test bundle, and so we can fire scan + error events
// synthetically from the test's perspective.

import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type Mock,
} from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// --- Vendor module mock ----------------------------------------------------
//
// The component dynamic-imports '@yudiel/react-qr-scanner'. vi.mock is
// hoisted above imports so both eager and lazy imports resolve to our stub.
//
// Strategy: expose the most recent `onScan` prop on a shared ref so tests can
// synthesise a detect event regardless of which render cycle the Suspense
// boundary last flushed in.

interface MockScannerRegistry {
  lastOnScan: ((codes: Array<{ rawValue: string; format: string }>) => void) | null;
  lastOnError: ((err: unknown) => void) | null;
  renderCount: number;
}
const mockScannerRegistry: MockScannerRegistry = {
  lastOnScan: null,
  lastOnError: null,
  renderCount: 0,
};

vi.mock('@yudiel/react-qr-scanner', () => {
  return {
    Scanner: (props: {
      onScan: (codes: Array<{ rawValue: string; format: string }>) => void;
      onError?: (err: unknown) => void;
    }) => {
      mockScannerRegistry.lastOnScan = props.onScan;
      mockScannerRegistry.lastOnError = props.onError ?? null;
      mockScannerRegistry.renderCount += 1;
      return <div data-testid="mock-scanner" />;
    },
  };
});

// Mock HTMLMediaElement.play in the jsdom/happy-dom environment — no real
// audio backend exists. We capture every play() call for assertions.
const playSpy = vi.fn<() => Promise<void>>(() => Promise.resolve());
HTMLMediaElement.prototype.play = playSpy;
HTMLMediaElement.prototype.pause = vi.fn();

// navigator.vibrate is undefined in happy-dom — inject a spy we can assert on.
const vibrateSpy = vi.fn<(pattern: number | number[]) => boolean>(() => true);
Object.defineProperty(navigator, 'vibrate', {
  value: vibrateSpy,
  writable: true,
  configurable: true,
});

// Now import the component under test (after all mocks are in place).
import { QrCameraScanner } from '../components/scanner/QrCameraScanner';

// --- Helpers ---------------------------------------------------------------

interface MockTrack {
  stop: Mock;
  getCapabilities: Mock;
  applyConstraints: Mock;
}

interface MockStream {
  getTracks: () => MockTrack[];
  getVideoTracks: () => MockTrack[];
}

function makeMockTrack(opts?: { torch?: boolean }): MockTrack {
  return {
    stop: vi.fn(),
    getCapabilities: vi.fn(() => (opts?.torch ? { torch: true } : {})),
    applyConstraints: vi.fn(() => Promise.resolve()),
  };
}

function makeMockStream(track: MockTrack): MockStream {
  return {
    getTracks: () => [track],
    getVideoTracks: () => [track],
  };
}

function installMediaDevices(opts: {
  getUserMedia: Mock;
  enumerateDevices?: Mock;
}): void {
  Object.defineProperty(navigator, 'mediaDevices', {
    value: {
      getUserMedia: opts.getUserMedia,
      enumerateDevices:
        opts.enumerateDevices ??
        vi.fn(() =>
          Promise.resolve([
            { kind: 'videoinput', deviceId: 'a', label: 'back', groupId: 'g1', toJSON: () => ({}) },
          ] as MediaDeviceInfo[]),
        ),
    },
    writable: true,
    configurable: true,
  });
}

// --- Lifecycle -------------------------------------------------------------

beforeEach(() => {
  mockScannerRegistry.lastOnScan = null;
  mockScannerRegistry.lastOnError = null;
  mockScannerRegistry.renderCount = 0;
  playSpy.mockClear();
  vibrateSpy.mockClear();
  window.localStorage.clear();
});

afterEach(() => {
  // Restore mediaDevices between tests so the next test's install wins.
  // happy-dom default is undefined which the component treats as unavailable.
});

// --- Tests -----------------------------------------------------------------

describe('QrCameraScanner', () => {
  it('does NOT mount the Scanner when active=false', () => {
    const getUserMedia = vi.fn();
    installMediaDevices({ getUserMedia });

    const onScan = vi.fn();
    render(<QrCameraScanner onScan={onScan} active={false} />);

    // Idle card is rendered; the Scanner never enters the tree, so the
    // vendor module never calls getUserMedia.
    expect(screen.queryByTestId('mock-scanner')).toBeNull();
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it('does NOT call getUserMedia itself when active=true (LazyScanner owns that)', async () => {
    const getUserMedia = vi.fn(() => Promise.resolve({} as MediaStream));
    installMediaDevices({ getUserMedia });

    const onScan = vi.fn();
    render(<QrCameraScanner onScan={onScan} active={true} />);

    // The Scanner mounts (our mock renders a div) as soon as we enter the
    // 'granted' state, but QrCameraScanner itself must NOT call gUM — the
    // probe-plus-LazyScanner double-call is what caused the black viewport.
    await waitFor(() => expect(mockScannerRegistry.renderCount).toBeGreaterThan(0));
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it('renders denied UI with autofocused manual input when Scanner reports NotAllowedError', async () => {
    const getUserMedia = vi.fn(() => Promise.resolve({} as MediaStream));
    installMediaDevices({ getUserMedia });

    render(<QrCameraScanner onScan={vi.fn()} active={true} />);

    // Wait for the Scanner mock to mount so onError is wired.
    await waitFor(() => expect(mockScannerRegistry.lastOnError).not.toBeNull());

    const err = Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    act(() => {
      mockScannerRegistry.lastOnError?.(err);
    });

    const title = await screen.findByText(/Kamera-Zugriff verweigert/i);
    expect(title).toBeInTheDocument();

    // Manual input must exist AND be autofocused — A8.2 sub-3s fallback.
    const input = screen.getByLabelText('Code manuell eingeben');
    await waitFor(() => expect(document.activeElement).toBe(input));

    // "Manuell eingeben" CTA is the spec-mandated large button.
    expect(screen.getByRole('button', { name: /manuell eingeben/i })).toBeInTheDocument();
  });

  it('renders unavailable UI when Scanner reports NotFoundError', async () => {
    const getUserMedia = vi.fn(() => Promise.resolve({} as MediaStream));
    installMediaDevices({ getUserMedia });

    render(<QrCameraScanner onScan={vi.fn()} active={true} />);

    await waitFor(() => expect(mockScannerRegistry.lastOnError).not.toBeNull());

    const err = Object.assign(new Error('no cam'), { name: 'NotFoundError' });
    act(() => {
      mockScannerRegistry.lastOnError?.(err);
    });

    const title = await screen.findByText(/Kamera nicht verfuegbar/i);
    expect(title).toBeInTheDocument();

    // Manual fallback still present.
    expect(screen.getByLabelText('Code manuell eingeben')).toBeInTheDocument();
  });

  it('fires onScan with source="camera" on successful detect', async () => {
    const getUserMedia = vi.fn(() => Promise.resolve({} as MediaStream));
    installMediaDevices({ getUserMedia });

    const onScan = vi.fn();
    render(<QrCameraScanner onScan={onScan} active={true} />);

    await waitFor(() => expect(mockScannerRegistry.lastOnScan).not.toBeNull());

    act(() => {
      mockScannerRegistry.lastOnScan?.([{ rawValue: 'ORDER:42', format: 'qr_code' }]);
    });

    expect(onScan).toHaveBeenCalledWith('ORDER:42', 'camera');
  });

  it('fires onScan with source="manual" when the manual form is submitted', async () => {
    const getUserMedia = vi.fn(() => Promise.resolve({} as MediaStream));
    installMediaDevices({ getUserMedia });

    const user = userEvent.setup();
    const onScan = vi.fn();
    render(<QrCameraScanner onScan={onScan} active={true} />);

    // Wait for granted state so the manual input is rendered below the viewport.
    await waitFor(() => expect(mockScannerRegistry.lastOnScan).not.toBeNull());

    const input = screen.getByLabelText('Code manuell eingeben');
    await user.type(input, 'ORDER:7{Enter}');

    expect(onScan).toHaveBeenCalledWith('ORDER:7', 'manual');
  });

  it('fires navigator.vibrate(200) on successful scan', async () => {
    const getUserMedia = vi.fn(() => Promise.resolve({} as MediaStream));
    installMediaDevices({ getUserMedia });

    render(<QrCameraScanner onScan={vi.fn()} active={true} />);
    await waitFor(() => expect(mockScannerRegistry.lastOnScan).not.toBeNull());

    act(() => {
      mockScannerRegistry.lastOnScan?.([{ rawValue: 'ORDER:42', format: 'qr_code' }]);
    });

    expect(vibrateSpy).toHaveBeenCalledWith(200);
  });

  it('plays the OK audio on a successful scan when not muted', async () => {
    const getUserMedia = vi.fn(() => Promise.resolve({} as MediaStream));
    installMediaDevices({ getUserMedia });

    render(<QrCameraScanner onScan={vi.fn()} active={true} />);
    await waitFor(() => expect(mockScannerRegistry.lastOnScan).not.toBeNull());

    playSpy.mockClear();
    act(() => {
      mockScannerRegistry.lastOnScan?.([{ rawValue: 'ORDER:42', format: 'qr_code' }]);
    });

    expect(playSpy).toHaveBeenCalled();
  });

  it('does NOT play audio when muted via localStorage', async () => {
    window.localStorage.setItem('scan_audio_muted', 'true');

    const getUserMedia = vi.fn(() => Promise.resolve({} as MediaStream));
    installMediaDevices({ getUserMedia });

    render(<QrCameraScanner onScan={vi.fn()} active={true} />);
    await waitFor(() => expect(mockScannerRegistry.lastOnScan).not.toBeNull());

    playSpy.mockClear();
    act(() => {
      mockScannerRegistry.lastOnScan?.([{ rawValue: 'ORDER:42', format: 'qr_code' }]);
    });

    expect(playSpy).not.toHaveBeenCalled();
  });

  it('hides the torch button (V1.1 has no native torch handle)', async () => {
    const getUserMedia = vi.fn(() => Promise.resolve({} as MediaStream));
    installMediaDevices({ getUserMedia });

    render(<QrCameraScanner onScan={vi.fn()} active={true} />);
    await waitFor(() => expect(mockScannerRegistry.lastOnScan).not.toBeNull());

    expect(screen.queryByRole('button', { name: /taschenlampe/i })).toBeNull();
  });

  it('unmounts the Scanner when active toggles from true to false', async () => {
    const getUserMedia = vi.fn(() => Promise.resolve({} as MediaStream));
    installMediaDevices({ getUserMedia });

    const { rerender } = render(<QrCameraScanner onScan={vi.fn()} active={true} />);
    await waitFor(() => expect(screen.queryByTestId('mock-scanner')).not.toBeNull());

    rerender(<QrCameraScanner onScan={vi.fn()} active={false} />);

    // Scanner must tear down when we leave 'granted' state — LazyScanner's
    // own cleanup is what releases the camera in real code.
    await waitFor(() => expect(screen.queryByTestId('mock-scanner')).toBeNull());
  });
});

// These helpers remain exported for other tests that do import
// installMediaDevices-style mocks; silence unused warnings in isolation.
void makeMockTrack;
void makeMockStream;
