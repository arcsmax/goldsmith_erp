// useHidBurstDetection — Slice 12 / A12.1.
//
// Lena's killer #2 mitigation. The Werkbank-Station-Modus toggle is
// default-OFF (per Henrik Q5) which means a goldsmith who plugs in a USB
// keyboard-wedge scanner will see… nothing. The burst of characters
// ends up in whatever input happened to be focused, or in no input at
// all — a silent failure from the user's perspective.
//
// This hook watches for a suspected HID burst on `document.body` (i.e.
// the listener fires ONLY when no input-like element has focus) and
// surfaces a one-time toast offering to enable Werkbank-Modus in the
// settings page.
//
// Detection heuristic:
//   * 5 or more rapid keydowns, each < 30ms from the previous keydown
//     (matches the BenchScannerListener default debounce per A9.1).
//   * Terminated by Enter (or NumpadEnter).
//   * activeElement at the time of emit is NOT a text-input surface.
//
// Dismissal tracking:
//   * localStorage key `hid_nudge_dismissed_count` — integer.
//   * After 3 dismissals we never show the nudge again (legitimate
//     non-scanner setups would already be in a different failure mode).
//   * The toast itself does not dismiss — the count is bumped by the
//     onDismiss callback wired at the call site.
//
// The hook is a pure listener + callback surface. It does NOT render
// any UI — the caller (MainLayout) owns the toast + the CTA to
// /settings. That keeps the hook portable between tests and the real
// toast system, and lets us unit-test the detection logic without a
// React tree.

import { useEffect, useRef } from 'react';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const HID_NUDGE_DISMISSED_KEY = 'hid_nudge_dismissed_count';
export const HID_NUDGE_MAX_DISMISSALS = 3;

const DEFAULT_BURST_MIN_LENGTH = 5;
const DEFAULT_BURST_MAX_GAP_MS = 30;

// Matches the activeElement guard used by BenchScannerListener so the
// two stay behaviourally consistent — a focused text-input surface must
// NOT trigger the nudge (the user is typing, not scanning).
const TEXT_INPUT_TAG_SELECTOR =
  'input, textarea, select, [contenteditable="true"], [role="textbox"], [role="combobox"], [role="searchbox"]';

// ---------------------------------------------------------------------------
// Pure detection API (exposed for unit tests)
// ---------------------------------------------------------------------------

/**
 * Returns true when the currently focused element is a text-input surface
 * and should swallow the burst. Pure function over a DOM Element reference
 * — safe to call without React state.
 */
export function isTextInputActiveForNudge(element: Element | null): boolean {
  if (element === null) return false;
  if (!(element instanceof HTMLElement)) return false;
  // `matches` throws on invalid selectors; ours is static + valid, but we
  // still guard defensively so a surprising focus target (e.g. SVG) does
  // not crash the hook.
  try {
    return element.matches(TEXT_INPUT_TAG_SELECTOR);
  } catch {
    return false;
  }
}

/**
 * Returns the current dismissed count (0-n). Reads localStorage
 * defensively so private-browsing / quota failures never throw.
 */
export function readDismissedCount(): number {
  try {
    const raw = localStorage.getItem(HID_NUDGE_DISMISSED_KEY);
    if (raw === null) return 0;
    const parsed = Number.parseInt(raw, 10);
    if (Number.isNaN(parsed) || parsed < 0) return 0;
    return parsed;
  } catch {
    return 0;
  }
}

/** Bump the dismissed counter by 1. Silent on storage errors. */
export function incrementDismissedCount(): void {
  try {
    const next = readDismissedCount() + 1;
    localStorage.setItem(HID_NUDGE_DISMISSED_KEY, String(next));
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface HidBurstDetectionOptions {
  /**
   * When false the hook is fully disabled — does not register any
   * listeners. Supplied by the caller from ScannerContext.benchModeEnabled
   * (already-on → no nudge needed) and from the AuthContext role check
   * (nudge only fires for GOLDSMITH today).
   */
  enabled: boolean;
  /**
   * Called at most once per page lifetime when a suspected HID burst is
   * detected. The caller owns the toast UI.
   */
  onBurstDetected: () => void;
  /**
   * Optional override for the minimum number of rapid keydowns required
   * before Enter. Default 5 per A12.1.
   */
  minLength?: number;
  /**
   * Optional override for the inter-key gap (ms). Default 30ms.
   */
  maxGapMs?: number;
}

/**
 * Mount a document-level keydown listener that fires
 * `onBurstDetected` once if a probable HID burst is observed while
 * bench-mode is OFF, the current user is eligible, and the dismissed
 * count is below the configured ceiling.
 */
export function useHidBurstDetection(
  opts: HidBurstDetectionOptions,
): void {
  const { enabled, onBurstDetected } = opts;
  const minLength = opts.minLength ?? DEFAULT_BURST_MIN_LENGTH;
  const maxGapMs = opts.maxGapMs ?? DEFAULT_BURST_MAX_GAP_MS;

  // Keep the latest callback in a ref so listener identity stays stable —
  // avoids re-registering the document listener on every render.
  const callbackRef = useRef(onBurstDetected);
  useEffect(() => {
    callbackRef.current = onBurstDetected;
  }, [onBurstDetected]);

  useEffect(() => {
    if (!enabled) return;

    // Respect the max-dismissals gate at mount time. We re-check on every
    // burst in case the count was written by another tab.
    if (readDismissedCount() >= HID_NUDGE_MAX_DISMISSALS) return;

    let count = 0;
    let lastTs = 0;
    let firedThisSession = false;

    const reset = (): void => {
      count = 0;
      lastTs = 0;
    };

    const now = (): number => {
      // `performance.now()` is monotonic and always available in the
      // environments we target; fall back to Date.now() only if something
      // very unusual strips it from the page.
      if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
        return performance.now();
      }
      return Date.now();
    };

    const handler = (event: KeyboardEvent): void => {
      if (firedThisSession) return;

      // 1. Guard: focus must be on a non-input surface.
      if (isTextInputActiveForNudge(document.activeElement)) {
        reset();
        return;
      }

      const isEnter = event.key === 'Enter' || event.code === 'Enter' || event.code === 'NumpadEnter';

      const ts = now();
      if (isEnter) {
        if (count >= minLength) {
          // 2. Guard: dismissed-count below ceiling.
          if (readDismissedCount() >= HID_NUDGE_MAX_DISMISSALS) {
            reset();
            return;
          }
          firedThisSession = true;
          // Invoke through the ref so the caller always gets the
          // latest callback closure.
          try {
            callbackRef.current();
          } finally {
            reset();
          }
        } else {
          reset();
        }
        return;
      }

      // 3. Burst accounting: a printable single-character key continues
      // the burst; anything else (modifiers, arrows, function keys, …)
      // resets. We trust BenchScannerListener's filters for modifier
      // handling; the nudge's job is to spot "lots of text arrived very
      // fast and ended with Enter".
      if (event.key.length !== 1) {
        reset();
        return;
      }

      if (count === 0) {
        count = 1;
        lastTs = ts;
        return;
      }

      const gap = ts - lastTs;
      if (gap > maxGapMs) {
        // Too slow — probably a human typist. Reset and start fresh.
        count = 1;
        lastTs = ts;
        return;
      }

      count += 1;
      lastTs = ts;
    };

    document.addEventListener('keydown', handler, true);
    return () => {
      document.removeEventListener('keydown', handler, true);
    };
  }, [enabled, minLength, maxGapMs]);
}
