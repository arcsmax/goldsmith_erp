// QrCameraScanner — Slice 8 of V1.1 QR/Barcode workflow.
//
// Wraps `@yudiel/react-qr-scanner` behind a small state machine that covers
// the four camera-permission states goldsmiths actually hit in the workshop:
//
//   idle        — component mounted, camera not yet requested (no user tap)
//   granted     — live camera stream, scanning
//   denied      — user refused permission; must render a sub-3-second manual
//                 fallback (A8.2): big "Manuell eingeben" CTA + auto-focused
//                 text input + platform-specific help link
//   unavailable — device has no camera (NotFoundError)
//
// Critical design decisions:
//
//   * The heavy `@yudiel/react-qr-scanner` module is loaded via dynamic import
//     inside a lazy boundary (see `LazyScanner` below). This keeps the scanner
//     chunk isolated from the main bundle per M7 (<= 250KB gzip).
//   * `getUserMedia` is NEVER called on mount. It is only invoked once
//     `active === true` AND the user has interacted with the component (the
//     parent ScanFab is responsible for the tap semantics — we just honor the
//     `active` prop). [R1]
//   * Permission denial ALWAYS renders the manual input *immediately*, with
//     `autofocus`. No second click required. [A8.2]
//
// Non-goals (handled elsewhere):
//   * Scan routing / canonicalization — `ScannerRouter` (Slice 7)
//   * Global scan state + FAB — `ScannerContext`, `ScanFab` (Slices 9, 10)
//   * Quick-action modals — Slice 11
//
// References:
//   docs/superpowers/plans/qr-barcode-workflow/V1.1-IMPLEMENTATION-PLAN.md (§Slice 8)
//   docs/superpowers/plans/qr-barcode-workflow/V1.1-AMENDMENTS.md (A8.1–A8.4)
//   docs/superpowers/plans/qr-barcode-workflow/V1.1-UI-DESIGN-SPEC.md

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import type {
  ChangeEvent,
  ComponentType,
  FormEvent,
  KeyboardEvent as ReactKeyboardEvent,
} from 'react';

import type { IDetectedBarcode, ScannerProps } from './scanner-types';
import './QrCameraScanner.css';

// -----------------------------------------------------------------------------
// Public contract
// -----------------------------------------------------------------------------

export type ScanSource = 'camera' | 'manual';

export interface QrCameraScannerProps {
  /** Called with the raw payload on every accepted scan. */
  onScan: (payload: string, source: ScanSource) => void;
  /** Called with any camera / decode error that escapes the component. */
  onError?: (error: Error) => void;
  /**
   * Controls whether the camera stream is live. When false, the stream is
   * torn down and no getUserMedia call is made. Parent (ScanFab) flips this
   * to true only after a user tap, never on mount.
   */
  active: boolean;
}

// -----------------------------------------------------------------------------
// Lazy-load the heavy vendor module. Vite still code-splits on dynamic import;
// we resolve the module via useState + useEffect rather than React.lazy so we
// don't trip Suspense machinery — concurrent-mode unmounts of a pending
// boundary (ScanOverlay flips `active=false` the moment a scan resolves) were
// observed to wedge the subtree in tests and in some dev builds.
// -----------------------------------------------------------------------------

type ScannerComponent = ComponentType<ScannerProps>;

function loadScannerModule(): Promise<ScannerComponent> {
  return import('@yudiel/react-qr-scanner').then(
    (mod) => mod.Scanner as unknown as ScannerComponent,
  );
}

// -----------------------------------------------------------------------------
// Permission state
// -----------------------------------------------------------------------------

type PermissionState = 'idle' | 'granted' | 'denied' | 'unavailable';

type Platform = 'ios-safari' | 'android-chrome' | 'desktop';

const AUDIO_VOLUME_KEY = 'scan_audio_volume';
const AUDIO_MUTED_KEY = 'scan_audio_muted';
const DEFAULT_VOLUME = 0.8;
const SCAN_PAUSE_MS = 800;

/**
 * Platform-specific help link copy — shown on denied/unavailable states.
 * We don't link out to an external URL (privacy); we just tell the user
 * *how* to flip the toggle on their device. German per Slice 8 spec.
 */
function detectPlatform(): Platform {
  if (typeof navigator === 'undefined') return 'desktop';
  const ua = navigator.userAgent;
  // iOS Safari — includes iPad now reporting as Mac; check touch points too.
  const isIOS =
    /iPad|iPhone|iPod/.test(ua) ||
    (ua.includes('Mac') && typeof document !== 'undefined' && 'ontouchend' in document);
  if (isIOS) return 'ios-safari';
  if (/Android/.test(ua)) return 'android-chrome';
  return 'desktop';
}

function helpCopyForPlatform(platform: Platform): string {
  switch (platform) {
    case 'ios-safari':
      return 'Einstellungen → Safari → Kamera → "Erlauben". Danach Seite neu laden.';
    case 'android-chrome':
      return 'Schloss-Symbol neben der URL antippen → Berechtigungen → Kamera → "Zulassen".';
    case 'desktop':
      return 'Schloss-Symbol in der Adressleiste antippen → Kamera erlauben → Seite neu laden.';
  }
}

// -----------------------------------------------------------------------------
// Audio feedback (A8.1). Preloaded on first activation, not on module load.
// -----------------------------------------------------------------------------

interface AudioKit {
  ok: HTMLAudioElement;
  error: HTMLAudioElement;
}

function readAudioVolume(): number {
  if (typeof window === 'undefined') return DEFAULT_VOLUME;
  const raw = window.localStorage.getItem(AUDIO_VOLUME_KEY);
  if (raw === null) return DEFAULT_VOLUME;
  const parsed = Number.parseFloat(raw);
  if (!Number.isFinite(parsed)) return DEFAULT_VOLUME;
  // Clamp to [0, 1]
  return Math.max(0, Math.min(1, parsed));
}

function readAudioMuted(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(AUDIO_MUTED_KEY) === 'true';
}

function writeAudioMuted(muted: boolean): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(AUDIO_MUTED_KEY, muted ? 'true' : 'false');
}

function createAudioKit(): AudioKit {
  // Use /public/sounds/*.mp3. If the files are missing the browser silently
  // no-ops play() — we catch any rejected promise downstream.
  const ok = new Audio('/sounds/scan-ok.mp3');
  const error = new Audio('/sounds/scan-error.mp3');
  ok.preload = 'auto';
  error.preload = 'auto';
  return { ok, error };
}

// -----------------------------------------------------------------------------
// Component
// -----------------------------------------------------------------------------

export function QrCameraScanner(props: QrCameraScannerProps): JSX.Element {
  const { onScan, onError, active } = props;

  const [permission, setPermission] = useState<PermissionState>('idle');
  const [torchSupported, setTorchSupported] = useState<boolean>(false);
  const [torchOn, setTorchOn] = useState<boolean>(false);
  const [cameraCount, setCameraCount] = useState<number>(0);
  const [facingMode, setFacingMode] = useState<'environment' | 'user'>('environment');
  const [paused, setPaused] = useState<boolean>(false);
  const [muted, setMuted] = useState<boolean>(() => readAudioMuted());
  const [manualValue, setManualValue] = useState<string>('');
  const [ScannerComp, setScannerComp] = useState<ScannerComponent | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const audioRef = useRef<AudioKit | null>(null);
  const pauseTimerRef = useRef<number | null>(null);
  const manualInputRef = useRef<HTMLInputElement | null>(null);

  const platform = detectPlatform();

  // ---------------------------------------------------------------------------
  // Stream lifecycle
  // ---------------------------------------------------------------------------

  const stopStream = useCallback((): void => {
    const stream = streamRef.current;
    if (stream !== null) {
      for (const track of stream.getTracks()) {
        track.stop();
      }
      streamRef.current = null;
    }
    setTorchSupported(false);
    setTorchOn(false);
  }, []);

  const requestCamera = useCallback(async (): Promise<void> => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices) {
      setPermission('unavailable');
      return;
    }

    // V1.1: no getUserMedia probe here. An earlier attempt probed the camera
    // to detect torch + enumerate devices, then stopped the probe stream
    // before LazyScanner mounted. The "stop-then-re-open" pattern races with
    // the browser's async camera-handle release on Chromium/macOS and iOS
    // Safari — the Scanner's own getUserMedia then lands on a track that
    // never produces frames (observable as a black viewport). We now do ONE
    // getUserMedia call in total: @yudiel/react-qr-scanner's own, initiated
    // when LazyScanner mounts below. Denial and missing-camera states are
    // routed through handleScannerError (onError prop on <Scanner>).
    setTorchSupported(false);

    // enumerateDevices works without permission (labels are empty but
    // kind === 'videoinput' and the count are populated on Chrome/Safari).
    // We only use the count to decide whether to show the "flip camera"
    // button. On engines that return 0 before permission (e.g. Firefox
    // private mode), we fall back to 1 and skip the flip button.
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoInputs = devices.filter((d) => d.kind === 'videoinput');
      setCameraCount(videoInputs.length > 0 ? videoInputs.length : 1);
    } catch {
      setCameraCount(1);
    }

    // Optimistic — LazyScanner drives the native permission prompt when it
    // mounts. If the user denies, onError fires and we flip to 'denied'.
    setPermission('granted');
  }, []);

  // Load the vendor module on first activation. The module is tiny (~30KB
  // gzip) so it usually resolves before the user has dismissed the
  // permission dialog. Unlike React.lazy, this avoids a Suspense boundary
  // — the boundary would otherwise still be pending when handleScan flips
  // `active` back to false after a successful scan, leaving the parent
  // tree wedged in the fallback.
  useEffect(() => {
    if (!active || ScannerComp !== null) return;
    let cancelled = false;
    void loadScannerModule().then((component) => {
      if (!cancelled) setScannerComp(() => component);
    });
    return () => {
      cancelled = true;
    };
  }, [active, ScannerComp]);

  // Drive the stream from `active`. We intentionally do NOT call getUserMedia
  // on mount — only when `active` flips to true. Parent gates activation on
  // the FAB tap (R1, spec §4).
  useEffect(() => {
    if (active) {
      // Lazy-create audio kit on first activation (after user gesture).
      if (audioRef.current === null) {
        audioRef.current = createAudioKit();
      }
      void requestCamera();
    } else {
      stopStream();
      setPermission('idle');
      setPaused(false);
      if (pauseTimerRef.current !== null) {
        window.clearTimeout(pauseTimerRef.current);
        pauseTimerRef.current = null;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  // Unmount cleanup.
  useEffect(() => {
    return () => {
      stopStream();
      if (pauseTimerRef.current !== null) {
        window.clearTimeout(pauseTimerRef.current);
      }
    };
  }, [stopStream]);

  // Autofocus the manual input when we land in denied/unavailable. A8.2.
  useEffect(() => {
    if (permission === 'denied' || permission === 'unavailable') {
      // rAF so the element exists in the DOM before focus call.
      const id = window.requestAnimationFrame(() => {
        manualInputRef.current?.focus();
      });
      return () => window.cancelAnimationFrame(id);
    }
    return undefined;
  }, [permission]);

  // ---------------------------------------------------------------------------
  // Feedback helpers
  // ---------------------------------------------------------------------------

  const playAudio = useCallback(
    (kind: 'ok' | 'error'): void => {
      if (muted) return;
      const kit = audioRef.current;
      if (kit === null) return;
      const el = kind === 'ok' ? kit.ok : kit.error;
      el.volume = readAudioVolume();
      // Reset to start so rapid scans don't skip the beep.
      try {
        el.currentTime = 0;
      } catch {
        /* ignore — some browsers throw on currentTime if not seekable */
      }
      const p = el.play();
      if (typeof p !== 'undefined' && typeof p.catch === 'function') {
        p.catch(() => {
          // Autoplay block (iOS before first gesture) — progressive enhancement.
        });
      }
    },
    [muted],
  );

  const haptic = useCallback((kind: 'ok' | 'error'): void => {
    if (typeof navigator === 'undefined') return;
    if (typeof navigator.vibrate !== 'function') return;
    if (kind === 'ok') {
      navigator.vibrate(200);
    } else {
      navigator.vibrate([60, 40, 60]);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Scan handlers
  // ---------------------------------------------------------------------------

  const emitScan = useCallback(
    (payload: string, source: ScanSource): void => {
      haptic('ok');
      playAudio('ok');
      // Pause camera for SCAN_PAUSE_MS to prevent the library from firing the
      // same code twice in rapid succession (we run with allowMultiple=false
      // already, but users scan two codes back-to-back).
      setPaused(true);
      if (pauseTimerRef.current !== null) {
        window.clearTimeout(pauseTimerRef.current);
      }
      pauseTimerRef.current = window.setTimeout(() => {
        setPaused(false);
        pauseTimerRef.current = null;
      }, SCAN_PAUSE_MS);
      onScan(payload, source);
    },
    [haptic, playAudio, onScan],
  );

  const handleScannerDetect = useCallback(
    (codes: IDetectedBarcode[]): void => {
      const first = codes[0];
      if (typeof first === 'undefined') return;
      const raw = first.rawValue?.trim();
      if (typeof raw !== 'string' || raw.length === 0) return;
      emitScan(raw, 'camera');
    },
    [emitScan],
  );

  const handleScannerError = useCallback(
    (err: unknown): void => {
      // LazyScanner is now the sole getUserMedia caller (see requestCamera),
      // so permission / no-device errors surface here instead of our probe.
      // Route them to the right permission state before playing error audio
      // — a denied prompt should jump straight to the manual fallback card,
      // not beep at the user.
      if (err instanceof Error) {
        const name = (err as DOMException).name;
        if (name === 'NotAllowedError' || name === 'SecurityError') {
          setPermission('denied');
          if (typeof onError === 'function') onError(err);
          return;
        }
        if (name === 'NotFoundError' || name === 'OverconstrainedError') {
          setPermission('unavailable');
          if (typeof onError === 'function') onError(err);
          return;
        }
      }
      playAudio('error');
      haptic('error');
      if (typeof onError === 'function' && err instanceof Error) {
        onError(err);
      }
    },
    [haptic, onError, playAudio],
  );

  const handleManualChange = useCallback((e: ChangeEvent<HTMLInputElement>): void => {
    setManualValue(e.target.value);
  }, []);

  const handleManualSubmit = useCallback(
    (e: FormEvent<HTMLFormElement>): void => {
      e.preventDefault();
      const value = manualValue.trim();
      if (value.length === 0) return;
      onScan(value, 'manual');
      setManualValue('');
    },
    [manualValue, onScan],
  );

  const handleManualKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLInputElement>): void => {
      if (e.key === 'Enter') {
        // Form onSubmit will fire; default Enter-submits-form behaviour is enough.
        // Explicitly early-return so TS doesn't complain about the callback.
      }
    },
    [],
  );

  // ---------------------------------------------------------------------------
  // Torch + flip handlers
  // ---------------------------------------------------------------------------

  const handleTorchToggle = useCallback(async (): Promise<void> => {
    const stream = streamRef.current;
    if (stream === null) return;
    const [videoTrack] = stream.getVideoTracks();
    if (typeof videoTrack === 'undefined') return;
    const next = !torchOn;
    try {
      // `torch` isn't in the standard MediaTrackConstraints — cast locally.
      await videoTrack.applyConstraints({
        advanced: [{ torch: next } as MediaTrackConstraintSet & { torch: boolean }],
      });
      setTorchOn(next);
    } catch (err) {
      if (typeof onError === 'function' && err instanceof Error) {
        onError(err);
      }
    }
  }, [onError, torchOn]);

  const handleFlipCamera = useCallback((): void => {
    // Flipping just toggles the facingMode state; the new value flows into
    // LazyScanner's `constraints` prop, which the vendor module picks up
    // via its internal updateConstraints path. No manual stop/re-request —
    // that used to cause the black-screen race (see requestCamera).
    setFacingMode((prev) => (prev === 'environment' ? 'user' : 'environment'));
  }, []);

  const handleMuteToggle = useCallback((): void => {
    setMuted((prev) => {
      const next = !prev;
      writeAudioMuted(next);
      return next;
    });
  }, []);

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const renderManualFallback = (): JSX.Element => (
    <form className="qrs-manual" onSubmit={handleManualSubmit}>
      <label htmlFor="qrs-manual-input" className="qrs-manual-label">
        Code manuell eingeben
      </label>
      <div className="qrs-manual-row">
        <input
          id="qrs-manual-input"
          ref={manualInputRef}
          className="qrs-manual-input"
          type="text"
          inputMode="numeric"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          value={manualValue}
          onChange={handleManualChange}
          onKeyDown={handleManualKeyDown}
          placeholder="z. B. ORDER:42 oder 42"
          aria-label="Code manuell eingeben"
        />
        <button
          type="submit"
          className="qrs-manual-submit"
          disabled={manualValue.trim().length === 0}
        >
          Senden
        </button>
      </div>
    </form>
  );

  const renderDenied = (): JSX.Element => (
    <div className="qrs-state qrs-state--denied" role="alert">
      <div className="qrs-state-icon" aria-hidden="true">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
          <line x1="2" y1="2" x2="22" y2="22" />
        </svg>
      </div>
      <h2 className="qrs-state-title">Kamera-Zugriff verweigert</h2>
      <p className="qrs-state-body">
        Wir benoetigen die Kamera, um Codes zu lesen. Du kannst den Code manuell eingeben
        oder die Berechtigung in den Browser-Einstellungen aktivieren.
      </p>
      <button
        type="button"
        className="qrs-manual-cta"
        onClick={() => manualInputRef.current?.focus()}
      >
        Manuell eingeben
      </button>
      <p className="qrs-state-help">{helpCopyForPlatform(platform)}</p>
    </div>
  );

  const renderUnavailable = (): JSX.Element => (
    <div className="qrs-state qrs-state--unavailable" role="alert">
      <div className="qrs-state-icon" aria-hidden="true">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      </div>
      <h2 className="qrs-state-title">Kamera nicht verfuegbar</h2>
      <p className="qrs-state-body">
        Auf diesem Geraet wurde keine Kamera erkannt. Bitte Code manuell eingeben.
      </p>
      <button
        type="button"
        className="qrs-manual-cta"
        onClick={() => manualInputRef.current?.focus()}
      >
        Manuell eingeben
      </button>
      <p className="qrs-state-help">{helpCopyForPlatform(platform)}</p>
    </div>
  );

  const renderIdle = (): JSX.Element => (
    <div className="qrs-state qrs-state--idle">
      <p className="qrs-state-body">Scanner bereit. Tippe, um zu starten.</p>
    </div>
  );

  const renderGranted = (): JSX.Element => (
    <div className="qrs-stage">
      <div className="qrs-viewport">
        {ScannerComp !== null ? (
          <ScannerComp
            onScan={handleScannerDetect}
            onError={handleScannerError}
            paused={paused}
            scanDelay={300}
            allowMultiple={false}
            formats={[
              'qr_code',
              'ean_13',
              'ean_8',
              'code_128',
              'code_39',
              'data_matrix',
            ]}
            components={{
              audio: false, // we handle our own audio (A8.1)
              torch: false, // we render a native torch button
              zoom: false,
              onOff: false,
              finder: false,
            }}
            classNames={{
              container: 'qrs-scanner-container',
              video: 'qrs-scanner-video',
            }}
            constraints={{ facingMode: { ideal: facingMode } }}
          />
        ) : (
          <div className="qrs-loading">Scanner laedt&hellip;</div>
        )}
        <div className="qrs-finder" aria-hidden="true" />
        <div className="qrs-controls">
          {torchSupported ? (
            <button
              type="button"
              className={`qrs-ctrl qrs-ctrl--torch${torchOn ? ' is-on' : ''}`}
              onClick={() => void handleTorchToggle()}
              aria-pressed={torchOn}
              aria-label="Taschenlampe umschalten"
            >
              {torchOn ? 'Licht aus' : 'Licht an'}
            </button>
          ) : null}
          {cameraCount > 1 ? (
            <button
              type="button"
              className="qrs-ctrl qrs-ctrl--flip"
              onClick={handleFlipCamera}
              aria-label="Kamera wechseln"
            >
              Kamera wechseln
            </button>
          ) : null}
          <button
            type="button"
            className={`qrs-ctrl qrs-ctrl--mute${muted ? ' is-on' : ''}`}
            onClick={handleMuteToggle}
            aria-pressed={muted}
            aria-label={muted ? 'Ton einschalten' : 'Ton stummschalten'}
          >
            {muted ? 'Ton an' : 'Stumm'}
          </button>
        </div>
      </div>
    </div>
  );

  // ---------------------------------------------------------------------------
  // Main render
  // ---------------------------------------------------------------------------

  return (
    <div className="qrs-root" data-permission={permission}>
      {permission === 'idle' ? renderIdle() : null}
      {permission === 'granted' ? renderGranted() : null}
      {permission === 'denied' ? renderDenied() : null}
      {permission === 'unavailable' ? renderUnavailable() : null}
      {/* The manual-entry form must keep DOM identity across permission
          transitions (idle → granted in particular). Users and tests both
          grab a reference to the input once and keep typing; nesting the
          form inside each state's tree would re-mount it on every state
          change and silently drop focus + in-flight input. */}
      {renderManualFallback()}
    </div>
  );
}

export default QrCameraScanner;
