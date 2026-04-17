// QrCameraScanner component tests — Slice 8 of V1.1 QR/Barcode workflow.
//
// Scope (plan §Slice 8 "Required tests"):
//   * active=false: getUserMedia NOT called (no camera request on mount).
//   * active=true: getUserMedia called once.
//   * NotAllowedError → denied UI renders with autofocused manual input.
//   * NotFoundError → unavailable UI renders.
//   * Successful scan via mocked <Scanner> → onScan('camera').
//   * Manual input submit → onScan('manual').
//   * Successful scan → navigator.vibrate(200).
//   * Successful scan → audio.play() fired for OK sound.
//   * Muted (localStorage scan_audio_muted='true') → audio.play() NOT called.
//   * Torch button hidden when capabilities.torch is absent.
//   * active=false cleanup → stream track .stop() invoked.
//
// The vendor module (@yudiel/react-qr-scanner) is mocked via vi.mock so we
// never pull it into the test bundle, and so we can fire scan events
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
const playSpy = vi.fn<[], Promise<void>>(() => Promise.resolve());
// @ts-expect-error override happy-dom stub
HTMLMediaElement.prototype.play = playSpy;
// @ts-expect-error happy-dom may not implement pause
HTMLMediaElement.prototype.pause = vi.fn();

// navigator.vibrate is undefined in happy-dom — inject a spy we can assert on.
const vibrateSpy = vi.fn<[number | number[]], boolean>(() => true);
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
  it('does NOT call getUserMedia when active=false', () => {
    const getUserMedia = vi.fn();
    installMediaDevices({ getUserMedia });

    const onScan = vi.fn();
    render(<QrCameraScanner onScan={onScan} active={false} />);

    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it('calls getUserMedia exactly once when active=true', async () => {
    const track = makeMockTrack();
    const getUserMedia = vi.fn(() => Promise.resolve(makeMockStream(track)));
    installMediaDevices({ getUserMedia });

    const onScan = vi.fn();
    render(<QrCameraScanner onScan={onScan} active={true} />);

    await waitFor(() => expect(getUserMedia).toHaveBeenCalledTimes(1));
  });

  it('renders denied UI with autofocused manual input on NotAllowedError', async () => {
    const err = Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    const getUserMedia = vi.fn(() => Promise.reject(err));
    installMediaDevices({ getUserMedia });

    render(<QrCameraScanner onScan={vi.fn()} active={true} />);

    const title = await screen.findByText(/Kamera-Zugriff verweigert/i);
    expect(title).toBeInTheDocument();

    // Manual input must exist AND be autofocused — A8.2 sub-3s fallback.
    const input = screen.getByLabelText('Code manuell eingeben');
    await waitFor(() => expect(document.activeElement).toBe(input));

    // "Manuell eingeben" CTA is the spec-mandated large button.
    expect(screen.getByRole('button', { name: /manuell eingeben/i })).toBeInTheDocument();
  });

  it('renders unavailable UI on NotFoundError', async () => {
    const err = Object.assign(new Error('no cam'), { name: 'NotFoundError' });
    const getUserMedia = vi.fn(() => Promise.reject(err));
    installMediaDevices({ getUserMedia });

    render(<QrCameraScanner onScan={vi.fn()} active={true} />);

    const title = await screen.findByText(/Kamera nicht verfuegbar/i);
    expect(title).toBeInTheDocument();

    // Manual fallback still present.
    expect(screen.getByLabelText('Code manuell eingeben')).toBeInTheDocument();
  });

  it('fires onScan with source="camera" on successful detect', async () => {
    const track = makeMockTrack();
    const getUserMedia = vi.fn(() => Promise.resolve(makeMockStream(track)));
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
    const track = makeMockTrack();
    const getUserMedia = vi.fn(() => Promise.resolve(makeMockStream(track)));
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
    const track = makeMockTrack();
    const getUserMedia = vi.fn(() => Promise.resolve(makeMockStream(track)));
    installMediaDevices({ getUserMedia });

    render(<QrCameraScanner onScan={vi.fn()} active={true} />);
    await waitFor(() => expect(mockScannerRegistry.lastOnScan).not.toBeNull());

    act(() => {
      mockScannerRegistry.lastOnScan?.([{ rawValue: 'ORDER:42', format: 'qr_code' }]);
    });

    expect(vibrateSpy).toHaveBeenCalledWith(200);
  });

  it('plays the OK audio on a successful scan when not muted', async () => {
    const track = makeMockTrack();
    const getUserMedia = vi.fn(() => Promise.resolve(makeMockStream(track)));
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

    const track = makeMockTrack();
    const getUserMedia = vi.fn(() => Promise.resolve(makeMockStream(track)));
    installMediaDevices({ getUserMedia });

    render(<QrCameraScanner onScan={vi.fn()} active={true} />);
    await waitFor(() => expect(mockScannerRegistry.lastOnScan).not.toBeNull());

    playSpy.mockClear();
    act(() => {
      mockScannerRegistry.lastOnScan?.([{ rawValue: 'ORDER:42', format: 'qr_code' }]);
    });

    expect(playSpy).not.toHaveBeenCalled();
  });

  it('hides the torch button when capabilities.torch is absent', async () => {
    const track = makeMockTrack({ torch: false });
    const getUserMedia = vi.fn(() => Promise.resolve(makeMockStream(track)));
    installMediaDevices({ getUserMedia });

    render(<QrCameraScanner onScan={vi.fn()} active={true} />);
    await waitFor(() => expect(mockScannerRegistry.lastOnScan).not.toBeNull());

    expect(screen.queryByRole('button', { name: /taschenlampe/i })).toBeNull();
  });

  it('stops the video tracks when active toggles from true to false', async () => {
    const track = makeMockTrack();
    const getUserMedia = vi.fn(() => Promise.resolve(makeMockStream(track)));
    installMediaDevices({ getUserMedia });

    const { rerender } = render(<QrCameraScanner onScan={vi.fn()} active={true} />);
    await waitFor(() => expect(getUserMedia).toHaveBeenCalledTimes(1));

    rerender(<QrCameraScanner onScan={vi.fn()} active={false} />);

    await waitFor(() => expect(track.stop).toHaveBeenCalled());
  });
});
