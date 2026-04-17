// HID burst-detection hook tests — Slice 12 / A12.1.
//
// Scope:
//   * 5 rapid keydowns + Enter on document.body → onBurstDetected fires.
//   * Same burst while an <input> is focused → never fires.
//   * Inter-key gap > maxGapMs → burst resets (slow typist protected).
//   * After HID_NUDGE_MAX_DISMISSALS dismissals → never fires.
//   * `enabled=false` → no listener registered.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

import {
  HID_NUDGE_DISMISSED_KEY,
  HID_NUDGE_MAX_DISMISSALS,
  incrementDismissedCount,
  isTextInputActiveForNudge,
  readDismissedCount,
  useHidBurstDetection,
} from '../hooks/useHidBurstDetection';

// ---------------------------------------------------------------------------
// Timing helpers — we stub performance.now so the detection logic sees
// a deterministic monotonic clock regardless of test harness speed.
// ---------------------------------------------------------------------------

let nowValue = 0;
let nowMock: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  localStorage.clear();
  nowValue = 0;
  nowMock = vi.spyOn(performance, 'now').mockImplementation(() => nowValue);
  // Reset focus to the body so the "no text input focused" guard holds.
  if (document.activeElement instanceof HTMLElement) {
    document.activeElement.blur();
  }
});

afterEach(() => {
  nowMock.mockRestore();
  vi.clearAllMocks();
});

/**
 * Dispatch a keydown to the document body. `at` sets the virtual clock
 * so the hook's inter-key gap logic runs deterministically.
 */
function dispatchKey(
  key: string,
  opts: { at: number; code?: string } = { at: 0 },
): void {
  nowValue = opts.at;
  const ev = new KeyboardEvent('keydown', {
    key,
    code: opts.code ?? key,
    bubbles: true,
    cancelable: true,
  });
  document.dispatchEvent(ev);
}

// ---------------------------------------------------------------------------
// Direct function tests
// ---------------------------------------------------------------------------

describe('HID nudge pure helpers', () => {
  it('isTextInputActiveForNudge recognises input, textarea, role=textbox', () => {
    const input = document.createElement('input');
    const textarea = document.createElement('textarea');
    const select = document.createElement('select');
    const div = document.createElement('div');
    const roleBox = document.createElement('div');
    roleBox.setAttribute('role', 'textbox');
    const ce = document.createElement('div');
    ce.setAttribute('contenteditable', 'true');

    expect(isTextInputActiveForNudge(input)).toBe(true);
    expect(isTextInputActiveForNudge(textarea)).toBe(true);
    expect(isTextInputActiveForNudge(select)).toBe(true);
    expect(isTextInputActiveForNudge(roleBox)).toBe(true);
    expect(isTextInputActiveForNudge(ce)).toBe(true);
    expect(isTextInputActiveForNudge(div)).toBe(false);
    expect(isTextInputActiveForNudge(null)).toBe(false);
  });

  it('readDismissedCount defaults to 0 and recovers from malformed storage', () => {
    expect(readDismissedCount()).toBe(0);
    localStorage.setItem(HID_NUDGE_DISMISSED_KEY, 'oops');
    expect(readDismissedCount()).toBe(0);
    localStorage.setItem(HID_NUDGE_DISMISSED_KEY, '-5');
    expect(readDismissedCount()).toBe(0);
    localStorage.setItem(HID_NUDGE_DISMISSED_KEY, '2');
    expect(readDismissedCount()).toBe(2);
  });

  it('incrementDismissedCount bumps the counter by 1', () => {
    incrementDismissedCount();
    expect(readDismissedCount()).toBe(1);
    incrementDismissedCount();
    incrementDismissedCount();
    expect(readDismissedCount()).toBe(3);
  });
});

// ---------------------------------------------------------------------------
// Hook integration tests
// ---------------------------------------------------------------------------

describe('useHidBurstDetection — emit behaviour', () => {
  it('fires after 5 rapid keydowns + Enter on document.body', () => {
    const onBurstDetected = vi.fn();
    renderHook(() =>
      useHidBurstDetection({ enabled: true, onBurstDetected }),
    );

    for (let i = 0; i < 5; i++) {
      dispatchKey(String.fromCharCode(65 + i), { at: i * 5 });
    }
    dispatchKey('Enter', { at: 30, code: 'Enter' });

    expect(onBurstDetected).toHaveBeenCalledTimes(1);
  });

  it('does NOT fire when an <input> is focused at the Enter moment', () => {
    const onBurstDetected = vi.fn();
    renderHook(() =>
      useHidBurstDetection({ enabled: true, onBurstDetected }),
    );

    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    for (let i = 0; i < 5; i++) {
      dispatchKey(String.fromCharCode(65 + i), { at: i * 5 });
    }
    dispatchKey('Enter', { at: 30, code: 'Enter' });

    expect(onBurstDetected).not.toHaveBeenCalled();
    input.remove();
  });

  it('does NOT fire when the burst is too slow (gap > maxGapMs)', () => {
    const onBurstDetected = vi.fn();
    renderHook(() =>
      useHidBurstDetection({
        enabled: true,
        onBurstDetected,
        maxGapMs: 30,
      }),
    );

    // First 4 keys at gap 5ms — fast.
    for (let i = 0; i < 4; i++) {
      dispatchKey(String.fromCharCode(65 + i), { at: i * 5 });
    }
    // 5th key 200ms later — too slow, buffer resets to length 1.
    dispatchKey('E', { at: 220 });
    dispatchKey('Enter', { at: 230, code: 'Enter' });

    expect(onBurstDetected).not.toHaveBeenCalled();
  });

  it('does NOT fire after HID_NUDGE_MAX_DISMISSALS dismissals', () => {
    for (let i = 0; i < HID_NUDGE_MAX_DISMISSALS; i++) {
      incrementDismissedCount();
    }

    const onBurstDetected = vi.fn();
    renderHook(() =>
      useHidBurstDetection({ enabled: true, onBurstDetected }),
    );

    for (let i = 0; i < 5; i++) {
      dispatchKey(String.fromCharCode(65 + i), { at: i * 5 });
    }
    dispatchKey('Enter', { at: 30, code: 'Enter' });

    expect(onBurstDetected).not.toHaveBeenCalled();
  });

  it('does NOT fire twice within a single session even if a second burst occurs', () => {
    const onBurstDetected = vi.fn();
    renderHook(() =>
      useHidBurstDetection({ enabled: true, onBurstDetected }),
    );

    for (let i = 0; i < 5; i++) {
      dispatchKey(String.fromCharCode(65 + i), { at: i * 5 });
    }
    dispatchKey('Enter', { at: 30, code: 'Enter' });
    expect(onBurstDetected).toHaveBeenCalledTimes(1);

    // Second burst on the same session — hook already fired, no-op.
    for (let i = 0; i < 5; i++) {
      dispatchKey(String.fromCharCode(65 + i), { at: 1000 + i * 5 });
    }
    dispatchKey('Enter', { at: 1030, code: 'Enter' });
    expect(onBurstDetected).toHaveBeenCalledTimes(1);
  });

  it('does not register a listener when enabled=false', () => {
    const onBurstDetected = vi.fn();
    renderHook(() =>
      useHidBurstDetection({ enabled: false, onBurstDetected }),
    );

    for (let i = 0; i < 5; i++) {
      dispatchKey(String.fromCharCode(65 + i), { at: i * 5 });
    }
    dispatchKey('Enter', { at: 30, code: 'Enter' });
    expect(onBurstDetected).not.toHaveBeenCalled();
  });
});
