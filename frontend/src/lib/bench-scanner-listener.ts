// BenchScannerListener — USB HID keyboard-wedge scanner listener (Slice 9).
//
// Real USB HID scanners (Zebra, Honeywell, Datalogic in keyboard-wedge mode)
// behave like a keyboard that types very fast and terminates with Enter.
// This listener distinguishes scanner bursts from human typing using a
// conservative set of guards so we never fire `onScan` on a false positive.
//
// Contract (plan §Slice 9 + V1.1-AMENDMENTS A9.1–A9.6):
//
//   const dispose = createBenchScannerListener({
//     onScan: (payload) => scannerRouter.resolve(payload, ctx),
//     debounceMs: 30,   // default (A9.1 — tightened from spec's 50ms)
//     minLength:  4,    // default
//   });
//
// The returned function MUST be called to remove the listener. Dispose is
// idempotent; calling it twice is safe.
//
// Emit precondition — ALL must hold:
//   1. Burst terminated by Enter (code === 'Enter' OR 'NumpadEnter').
//   2. Buffer length >= minLength (after stripping trailing CR/LF/Tab tails).
//   3. No key event in the burst had `isComposing === true` (A9.3 — IME /
//      macOS emoji picker dispatches synthetic keydowns).
//   4. No key event emitted an alphabetical character WHILE Shift was held
//      (A9.4 — real scanners emit capitals via the key `code` path without
//      Shift; a human typing with Shift+letter is almost never a scanner).
//   5. `document.activeElement` at emit time is not a text-input surface
//      (INPUT/TEXTAREA/SELECT, [contenteditable], role=textbox/combobox/searchbox).
//   6. Buffer contains no ASCII control chars other than Tab (Tab is a known
//      scanner tail terminator — we strip it before emit, it does not count).
//   7. Inter-key gap < debounceMs for every transition inside the burst.
//      A gap > debounceMs resets the buffer (slow typists never accumulate).

export interface BenchScannerListenerOptions {
  /** Called once per successfully-recognised scanner burst. */
  onScan: (payload: string) => void;
  /**
   * Max inter-key gap (ms) within a burst. Default 30 per A9.1. A gap larger
   * than this resets the buffer before the new key is appended.
   */
  debounceMs?: number;
  /** Minimum payload length (after stripping tails) to emit. Default 4. */
  minLength?: number;
}

// ---------------------------------------------------------------------------
// Defaults & constants
// ---------------------------------------------------------------------------

const DEFAULT_DEBOUNCE_MS = 30;
const DEFAULT_MIN_LENGTH = 4;

/**
 * Selector for activeElement surfaces we refuse to capture into. Slice 9 core
 * guard + A9.2 semantic-role extensions.
 *
 * Kept intentionally narrow: we check the specific types / roles, not "any
 * focusable element". Buttons, links, and non-text form controls are OK
 * targets for a bench scanner burst (the burst still reaches `document`
 * because focused buttons don't swallow keydown).
 */
const TEXT_INPUT_SELECTOR =
  'input, textarea, select, [contenteditable=""], [contenteditable="true"], ' +
  '[role="textbox"], [role="combobox"], [role="searchbox"]';

// ---------------------------------------------------------------------------
// Pure helpers — exported for unit testing the predicate individually.
// ---------------------------------------------------------------------------

/**
 * True if `document.activeElement` is a text-input surface per A9.2.
 *
 * We use `matches(TEXT_INPUT_SELECTOR)` rather than enumerating tag names so
 * HTMLInputElement subclasses (e.g. `<input type="search">` — which has role
 * searchbox implicitly) and custom `role=textbox` widgets both match without
 * per-type logic.
 */
export function isTextInputActive(doc: Document = document): boolean {
  const el = doc.activeElement;
  if (el === null) return false;
  if (!(el instanceof Element)) return false;
  // Body / documentElement / detached = not a text input.
  if (el === doc.body || el === doc.documentElement) return false;
  return el.matches(TEXT_INPUT_SELECTOR);
}

/**
 * True if the string contains any ASCII control char other than Tab (0x09).
 * Mirrors the defensive check in scan-router.ts for consistency.
 */
export function bufferHasForbiddenControlChars(s: string): boolean {
  for (let i = 0; i < s.length; i++) {
    const code = s.charCodeAt(i);
    if (code === 0x09) continue; // tab allowed (and stripped below anyway)
    if (code < 0x20 || code === 0x7f) return true;
  }
  return false;
}

/**
 * Strip the scanner tail characters (CR, LF, CR+LF, Tab) from the end of the
 * buffer. Scanners vary: some emit `<payload>\r`, some `<payload>\r\n`, some
 * `<payload>\t<Enter>`. The actual emit trigger is always the Enter key,
 * but the tail char(s) arrive as separate `keydown` events whose `key` is
 * captured into the buffer. We strip them before emit.
 *
 * A9.5 — "Handle barcode tail variations".
 */
export function stripTrailingTailChars(buffer: string): string {
  let end = buffer.length;
  while (end > 0) {
    const ch = buffer.charCodeAt(end - 1);
    if (ch === 0x0a /* \n */ || ch === 0x0d /* \r */ || ch === 0x09 /* \t */) {
      end -= 1;
    } else {
      break;
    }
  }
  return end === buffer.length ? buffer : buffer.slice(0, end);
}

/**
 * True if `key` is a single-char alphabetic value A–Z or a–z.
 *
 * A9.4 rationale: real USB HID scanners transmit uppercase alphabetics via
 * the `code` property (e.g. `code: 'KeyA'`, `key: 'A'`) without setting the
 * `shiftKey` modifier flag — the scanner microcontroller synthesises the
 * scan code, not a shift-then-letter pair. A human typing `A` in a burst
 * fast enough to pass the 30ms debounce almost always has Shift physically
 * held. So: if we see a burst with any key whose `shiftKey` is true AND
 * whose char is alphabetic, we treat the whole burst as human typing and
 * discard it. This is a heuristic, documented as such here and in tests.
 *
 * Caveat — a scanner emitting symbols (e.g. `!`, `@`) that require shift on
 * a QWERTY keyboard will NOT have shiftKey set either; the scanner bypasses
 * modifier state entirely in HID keyboard-wedge mode. So this heuristic is
 * safe: it never false-discards a real scanner burst (scanners never set
 * shift), it only catches humans (who do).
 */
export function isAlphabeticChar(key: string): boolean {
  if (key.length !== 1) return false;
  const code = key.charCodeAt(0);
  return (
    (code >= 0x41 /* A */ && code <= 0x5a /* Z */) ||
    (code >= 0x61 /* a */ && code <= 0x7a /* z */)
  );
}

// ---------------------------------------------------------------------------
// The listener itself.
// ---------------------------------------------------------------------------

interface ListenerState {
  buffer: string;
  lastKeyAt: number;
  hadComposingKey: boolean;
  hadShiftAlpha: boolean;
}

function freshState(): ListenerState {
  return {
    buffer: '',
    lastKeyAt: 0,
    hadComposingKey: false,
    hadShiftAlpha: false,
  };
}

export function createBenchScannerListener(
  opts: BenchScannerListenerOptions,
): () => void {
  const debounceMs =
    typeof opts.debounceMs === 'number' && opts.debounceMs > 0
      ? opts.debounceMs
      : DEFAULT_DEBOUNCE_MS;
  const minLength =
    typeof opts.minLength === 'number' && opts.minLength > 0
      ? opts.minLength
      : DEFAULT_MIN_LENGTH;

  let state = freshState();

  const handler = (event: KeyboardEvent): void => {
    // --- Terminator: Enter (plain or numpad) fires the emit attempt. -------
    if (event.code === 'Enter' || event.code === 'NumpadEnter') {
      const now = timestampOf(event);
      // If the Enter arrived after a long gap, the buffer is probably stale
      // (e.g. user hit Enter in a form earlier, then browsed). Reset and bail.
      if (state.buffer.length > 0 && now - state.lastKeyAt > debounceMs) {
        state = freshState();
        return;
      }
      tryEmit();
      return;
    }

    // --- All other keys: accumulate into buffer under guards. --------------
    const now = timestampOf(event);

    // Inter-key gap check — reset if we've waited too long since last key.
    if (state.buffer.length > 0 && now - state.lastKeyAt > debounceMs) {
      state = freshState();
    }

    // Record compose / shift-alpha flags for the whole burst, even for keys
    // we don't append (e.g. modifier keys themselves).
    if (event.isComposing) {
      state.hadComposingKey = true;
    }
    if (event.shiftKey && isAlphabeticChar(event.key)) {
      state.hadShiftAlpha = true;
    }

    // Skip pure-modifier keys — they don't contribute char content but DO
    // update the shift-alpha flag via the line above if paired with a letter.
    if (
      event.key === 'Shift' ||
      event.key === 'Control' ||
      event.key === 'Alt' ||
      event.key === 'Meta' ||
      event.key === 'CapsLock' ||
      event.key === 'NumLock' ||
      event.key === 'ScrollLock'
    ) {
      state.lastKeyAt = now;
      return;
    }

    // A9.5 — treat CR/LF/Tab as buffer terminators; we still append them so
    // the stripTrailingTailChars() helper can unify them at emit time. This
    // also means a mid-buffer tab would end up in `buffer`, which is rejected
    // by the control-char check at emit (we only strip TRAILING tails).
    //
    // Only append printable content (single-char `key`) + the tail chars.
    // `event.key === 'Tab'` arrives as key='Tab'; normalise to '\t'.
    let ch: string | null = null;
    if (event.key === 'Tab') {
      ch = '\t';
    } else if (event.key === 'Enter') {
      // Shouldn't reach here (we returned above on code==='Enter'), but be
      // defensive for synthetic events that set key without code.
      return;
    } else if (event.key.length === 1) {
      ch = event.key;
    }
    // Named non-printing keys ('ArrowLeft', 'F5', 'Escape', …) contribute
    // nothing and do not update lastKeyAt — a non-char gap in the middle of
    // a burst still lets the debounce handle it on the next printable key.

    if (ch !== null) {
      state.buffer += ch;
      state.lastKeyAt = now;
    }
  };

  const tryEmit = (): void => {
    // Capture snapshot then reset state first; if any guard rejects, we
    // discard silently. State reset before the emit guarantees reentrancy
    // safety (onScan might dispatch something that lands back on us).
    const snapshot = state;
    state = freshState();

    if (snapshot.buffer.length === 0) return;
    if (snapshot.hadComposingKey) return; // A9.3
    if (snapshot.hadShiftAlpha) return;    // A9.4
    if (isTextInputActive()) return;       // core + A9.2

    const payload = stripTrailingTailChars(snapshot.buffer);
    if (payload.length < minLength) return;
    if (bufferHasForbiddenControlChars(payload)) return;

    try {
      opts.onScan(payload);
    } catch (err) {
      // Fail loudly per project working style — don't swallow silently, but
      // don't let a consumer throw take down our listener either. Log with
      // context; tests verify the emit happened, not the log.
      // eslint-disable-next-line no-console
      console.error('[BenchScannerListener] onScan handler threw', err);
    }
  };

  document.addEventListener('keydown', handler, { capture: true });

  let disposed = false;
  return function dispose(): void {
    if (disposed) return;
    disposed = true;
    document.removeEventListener('keydown', handler, { capture: true });
  };
}

/**
 * Best-effort timestamp extraction from a KeyboardEvent.
 *
 * `event.timeStamp` is DOMHighResTimeStamp (ms relative to page load) for
 * trusted events. For synthetic events dispatched from tests, timeStamp is
 * typically 0 — fall back to `performance.now()` which is the same time base.
 */
function timestampOf(event: KeyboardEvent): number {
  if (typeof event.timeStamp === 'number' && event.timeStamp > 0) {
    return event.timeStamp;
  }
  return performance.now();
}
