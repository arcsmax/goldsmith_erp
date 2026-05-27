// BenchScannerListener unit tests — Slice 9 of V1.1 QR/Barcode workflow.
//
// Covers the full guard matrix per V1.1-TESTABILITY-REVIEW §3 + V1.1-AMENDMENTS
// A9.1–A9.6:
//   - Basic firing (body focus, NumpadEnter, tail strip variants).
//   - activeElement guards (INPUT/TEXTAREA/SELECT/[contenteditable]/role textbox/combobox/searchbox).
//   - Buffer content guards (min length, control chars, isComposing, shift-alpha).
//   - Debounce (gap > debounceMs resets buffer; gap <= debounceMs keeps it).
//   - Autofill simulation (1Password-style synthetic events, non-trusted dispatch).
//   - Cleanup (dispose removes listener; listener dispatch post-dispose is a no-op).
//
// Dispatch strategy: we dispatch real `new KeyboardEvent('keydown', {...})`
// instances against `document` to match production wiring (listener registers
// with capture:true on document). We control the relative time between keys by
// stubbing `performance.now()` — happy-dom's `event.timeStamp` is unreliable
// for synthetic events (comes through as 0), so the listener falls back to
// `performance.now()` which we drive deterministically.

import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type MockInstance,
} from 'vitest';

import {
  bufferHasForbiddenControlChars,
  createBenchScannerListener,
  isAlphabeticChar,
  isTextInputActive,
  stripTrailingTailChars,
} from '../lib/bench-scanner-listener';

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

interface DispatchOpts {
  code?: string;
  key?: string;
  shiftKey?: boolean;
  isComposing?: boolean;
}

/** Dispatch a keydown with explicit timing control via performance.now() mock. */
function dispatchKey(opts: DispatchOpts & { at?: number }): void {
  if (typeof opts.at === 'number') {
    nowMock.mockReturnValue(opts.at);
  }
  const ev = new KeyboardEvent('keydown', {
    code: opts.code ?? '',
    key: opts.key ?? opts.code ?? '',
    shiftKey: opts.shiftKey ?? false,
    isComposing: opts.isComposing ?? false,
    bubbles: true,
    cancelable: true,
  });
  document.dispatchEvent(ev);
}

/** Type a sequence of printable chars as individual keydown events. */
function typeChars(chars: string, startAt = 100, stepMs = 5): void {
  let t = startAt;
  for (const ch of chars) {
    // Derive a plausible `code` from the char. Uppercase -> KeyX, digit -> DigitN.
    let code = '';
    if (/[a-zA-Z]/.test(ch)) {
      code = `Key${ch.toUpperCase()}`;
    } else if (/\d/.test(ch)) {
      code = `Digit${ch}`;
    } else if (ch === '\t') {
      code = 'Tab';
    } else if (ch === '\r' || ch === '\n') {
      // Used for tail-stripping tests: we dispatch via event.key without
      // a code 'Enter' so the Enter terminator doesn't fire yet.
      code = 'NonEnterCRLF';
    } else {
      code = ch;
    }
    dispatchKey({ code, key: ch === '\t' ? 'Tab' : ch, at: t });
    t += stepMs;
  }
}

/** Press Enter terminator to trigger the emit attempt. */
function pressEnter(at: number, numpad = false): void {
  dispatchKey({ code: numpad ? 'NumpadEnter' : 'Enter', key: 'Enter', at });
}

/** Remove all children from document.body without using innerHTML. */
function clearBody(): void {
  while (document.body.firstChild !== null) {
    document.body.removeChild(document.body.firstChild);
  }
}

let nowMock: MockInstance<() => number>;

beforeEach(() => {
  nowMock = vi.spyOn(performance, 'now').mockReturnValue(0);
  // Ensure body is the activeElement between tests.
  if (document.activeElement instanceof HTMLElement && document.activeElement !== document.body) {
    document.activeElement.blur();
  }
  clearBody();
});

afterEach(() => {
  nowMock.mockRestore();
  clearBody();
});

// ---------------------------------------------------------------------------
// Pure-predicate unit tests
// ---------------------------------------------------------------------------

describe('BenchScannerListener pure helpers', () => {
  describe('isAlphabeticChar', () => {
    it('recognises A-Z and a-z', () => {
      for (const c of 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz') {
        expect(isAlphabeticChar(c)).toBe(true);
      }
    });
    it('rejects digits, symbols, multi-char strings', () => {
      for (const c of '01234567890!@#$%^&*()') {
        expect(isAlphabeticChar(c)).toBe(false);
      }
      expect(isAlphabeticChar('ab')).toBe(false);
      expect(isAlphabeticChar('')).toBe(false);
      // Non-ASCII letters intentionally not matched (scanners emit ASCII).
      expect(isAlphabeticChar('ä')).toBe(false);
    });
  });

  describe('bufferHasForbiddenControlChars', () => {
    it('allows tab', () => {
      expect(bufferHasForbiddenControlChars('hello\tworld')).toBe(false);
    });
    it('rejects null byte', () => {
      expect(bufferHasForbiddenControlChars('hello\x00world')).toBe(true);
    });
    it('rejects DEL', () => {
      expect(bufferHasForbiddenControlChars('hello\x7fworld')).toBe(true);
    });
    it('accepts plain printable ASCII', () => {
      expect(bufferHasForbiddenControlChars('ORDER:42')).toBe(false);
    });
  });

  describe('stripTrailingTailChars', () => {
    it('strips CR', () => {
      expect(stripTrailingTailChars('ORDER:42\r')).toBe('ORDER:42');
    });
    it('strips LF', () => {
      expect(stripTrailingTailChars('ORDER:42\n')).toBe('ORDER:42');
    });
    it('strips CR+LF', () => {
      expect(stripTrailingTailChars('ORDER:42\r\n')).toBe('ORDER:42');
    });
    it('strips Tab', () => {
      expect(stripTrailingTailChars('ORDER:42\t')).toBe('ORDER:42');
    });
    it('strips combined Tab+CR+LF', () => {
      expect(stripTrailingTailChars('ORDER:42\t\r\n')).toBe('ORDER:42');
    });
    it('leaves no-tail strings alone', () => {
      expect(stripTrailingTailChars('ORDER:42')).toBe('ORDER:42');
    });
    it('only strips trailing, not embedded', () => {
      expect(stripTrailingTailChars('a\tb\r')).toBe('a\tb');
    });
  });

  describe('isTextInputActive', () => {
    it('is false with body focused', () => {
      expect(isTextInputActive()).toBe(false);
    });
    it('is true with INPUT focused', () => {
      const input = document.createElement('input');
      document.body.appendChild(input);
      input.focus();
      expect(isTextInputActive()).toBe(true);
    });
    it('is true with TEXTAREA focused', () => {
      const ta = document.createElement('textarea');
      document.body.appendChild(ta);
      ta.focus();
      expect(isTextInputActive()).toBe(true);
    });
    it('is true with SELECT focused', () => {
      const sel = document.createElement('select');
      document.body.appendChild(sel);
      sel.focus();
      expect(isTextInputActive()).toBe(true);
    });
    it('is true with contenteditable=true focused', () => {
      const d = document.createElement('div');
      d.setAttribute('contenteditable', 'true');
      d.setAttribute('tabindex', '0');
      document.body.appendChild(d);
      d.focus();
      expect(isTextInputActive()).toBe(true);
    });
    it('is true with role=textbox focused', () => {
      const d = document.createElement('div');
      d.setAttribute('role', 'textbox');
      d.setAttribute('tabindex', '0');
      document.body.appendChild(d);
      d.focus();
      expect(isTextInputActive()).toBe(true);
    });
    it('is true with role=combobox focused', () => {
      const d = document.createElement('div');
      d.setAttribute('role', 'combobox');
      d.setAttribute('tabindex', '0');
      document.body.appendChild(d);
      d.focus();
      expect(isTextInputActive()).toBe(true);
    });
    it('is true with role=searchbox focused', () => {
      const d = document.createElement('div');
      d.setAttribute('role', 'searchbox');
      d.setAttribute('tabindex', '0');
      document.body.appendChild(d);
      d.focus();
      expect(isTextInputActive()).toBe(true);
    });
    it('is false with BUTTON focused (buttons are not text input)', () => {
      const b = document.createElement('button');
      document.body.appendChild(b);
      b.focus();
      expect(isTextInputActive()).toBe(false);
    });
  });
});

// ---------------------------------------------------------------------------
// End-to-end listener behaviour
// ---------------------------------------------------------------------------

describe('createBenchScannerListener — basic firing', () => {
  it('emits on Enter when activeElement is body', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    typeChars('ORDER:42', 100, 5);
    pressEnter(150);

    expect(onScan).toHaveBeenCalledTimes(1);
    expect(onScan).toHaveBeenCalledWith('ORDER:42');
    dispose();
  });

  it('emits via NumpadEnter', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    typeChars('REPAIR:7', 100, 5);
    pressEnter(150, true);

    expect(onScan).toHaveBeenCalledWith('REPAIR:7');
    dispose();
  });

  it('strips CR terminator before Enter', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    typeChars('ORDER:42', 100, 5);
    // CR arrives as event.key='\r' BEFORE the Enter terminator.
    dispatchKey({ code: 'Unidentified', key: '\r', at: 140 });
    pressEnter(145);

    expect(onScan).toHaveBeenCalledWith('ORDER:42');
    dispose();
  });

  it('strips LF terminator before Enter', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    typeChars('ORDER:42', 100, 5);
    dispatchKey({ code: 'Unidentified', key: '\n', at: 140 });
    pressEnter(145);

    expect(onScan).toHaveBeenCalledWith('ORDER:42');
    dispose();
  });

  it('strips CR+LF terminator before Enter', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    typeChars('ORDER:42', 100, 5);
    dispatchKey({ code: 'Unidentified', key: '\r', at: 140 });
    dispatchKey({ code: 'Unidentified', key: '\n', at: 143 });
    pressEnter(148);

    expect(onScan).toHaveBeenCalledWith('ORDER:42');
    dispose();
  });

  it('strips Tab terminator before Enter', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    typeChars('ORDER:42', 100, 5);
    dispatchKey({ code: 'Tab', key: 'Tab', at: 140 });
    pressEnter(145);

    expect(onScan).toHaveBeenCalledWith('ORDER:42');
    dispose();
  });
});

describe('createBenchScannerListener — activeElement guards', () => {
  // Parameterised over the full selector matrix (A9.2).
  interface Fixture {
    label: string;
    build: () => HTMLElement;
  }
  const fixtures: Fixture[] = [
    {
      label: 'INPUT',
      build: () => document.createElement('input'),
    },
    {
      label: 'TEXTAREA',
      build: () => document.createElement('textarea'),
    },
    {
      label: 'SELECT',
      build: () => {
        const s = document.createElement('select');
        const o = document.createElement('option');
        o.value = 'x';
        s.appendChild(o);
        return s;
      },
    },
    {
      label: '[contenteditable="true"]',
      build: () => {
        const d = document.createElement('div');
        d.setAttribute('contenteditable', 'true');
        d.setAttribute('tabindex', '0');
        return d;
      },
    },
    {
      label: '[role="textbox"]',
      build: () => {
        const d = document.createElement('div');
        d.setAttribute('role', 'textbox');
        d.setAttribute('tabindex', '0');
        return d;
      },
    },
    {
      label: '[role="combobox"]',
      build: () => {
        const d = document.createElement('div');
        d.setAttribute('role', 'combobox');
        d.setAttribute('tabindex', '0');
        return d;
      },
    },
    {
      label: '[role="searchbox"]',
      build: () => {
        const d = document.createElement('div');
        d.setAttribute('role', 'searchbox');
        d.setAttribute('tabindex', '0');
        return d;
      },
    },
  ];

  for (const fx of fixtures) {
    it(`does NOT emit when ${fx.label} is focused`, () => {
      const onScan = vi.fn();
      const dispose = createBenchScannerListener({ onScan });

      const el = fx.build();
      document.body.appendChild(el);
      el.focus();

      typeChars('ORDER:42', 100, 5);
      pressEnter(150);

      expect(onScan).not.toHaveBeenCalled();
      dispose();
    });
  }

  it('does emit when BUTTON is focused (buttons are not text input)', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    const btn = document.createElement('button');
    document.body.appendChild(btn);
    btn.focus();

    typeChars('ORDER:42', 100, 5);
    pressEnter(150);

    expect(onScan).toHaveBeenCalledWith('ORDER:42');
    dispose();
  });
});

describe('createBenchScannerListener — buffer content guards', () => {
  it('discards buffer < 4 chars', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    typeChars('ABC', 100, 5);
    pressEnter(150);

    expect(onScan).not.toHaveBeenCalled();
    dispose();
  });

  it('respects custom minLength', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan, minLength: 2 });

    // Keep Enter within debounce window of last key so buffer isn't reset.
    typeChars('AB', 100, 5);
    pressEnter(115);

    expect(onScan).toHaveBeenCalledWith('AB');
    dispose();
  });

  it('discards buffer with embedded (non-trailing) control chars', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    // Embed a control char mid-buffer via event.key; trailing tail-strip
    // only touches the end, so \x01 survives and the control-char guard
    // rejects the whole buffer at emit.
    typeChars('OR', 100, 5);
    dispatchKey({ code: 'Unidentified', key: '\x01', at: 115 });
    typeChars('DER', 120, 5);
    pressEnter(150);

    expect(onScan).not.toHaveBeenCalled();
    dispose();
  });

  it('discards buffer if ANY event has isComposing=true (emoji picker / IME)', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    // First 2 keys normal, 3rd has isComposing=true (a macOS emoji-picker
    // synthetic key), remainder normal, Enter terminates.
    dispatchKey({ code: 'KeyO', key: 'O', at: 100 });
    dispatchKey({ code: 'KeyR', key: 'R', at: 105 });
    dispatchKey({ code: 'KeyD', key: 'D', isComposing: true, at: 110 });
    dispatchKey({ code: 'KeyE', key: 'E', at: 115 });
    dispatchKey({ code: 'KeyR', key: 'R', at: 120 });
    pressEnter(125);

    expect(onScan).not.toHaveBeenCalled();
    dispose();
  });

  it('discards buffer if Shift was held on any alphabetic char (human typing)', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    // Human types "OrDer" holding shift for O/D — heuristic rejects.
    dispatchKey({ code: 'KeyO', key: 'O', shiftKey: true, at: 100 });
    dispatchKey({ code: 'KeyR', key: 'r', at: 110 });
    dispatchKey({ code: 'KeyD', key: 'D', shiftKey: true, at: 120 });
    dispatchKey({ code: 'KeyE', key: 'e', at: 130 });
    dispatchKey({ code: 'KeyR', key: 'r', at: 135 });
    pressEnter(140);

    expect(onScan).not.toHaveBeenCalled();
    dispose();
  });

  it('DOES emit for scanner emitting capitals via scan-code (no shiftKey)', () => {
    // Documents the A9.4 heuristic: real USB HID scanners transmit capitals
    // via the `code` path (event.key='A', shiftKey=false) because the
    // microcontroller bypasses modifier state. This must NOT be discarded.
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    dispatchKey({ code: 'KeyO', key: 'O', shiftKey: false, at: 100 });
    dispatchKey({ code: 'KeyR', key: 'R', shiftKey: false, at: 105 });
    dispatchKey({ code: 'KeyD', key: 'D', shiftKey: false, at: 110 });
    dispatchKey({ code: 'KeyE', key: 'E', shiftKey: false, at: 115 });
    dispatchKey({ code: 'KeyR', key: 'R', shiftKey: false, at: 120 });
    pressEnter(125);

    expect(onScan).toHaveBeenCalledWith('ORDER');
    dispose();
  });

  it('DOES emit for scanner emitting shift-required symbols (e.g. ":" on QWERTY)', () => {
    // The colon on QWERTY is a shift-key symbol but the scanner HID path
    // does not set shiftKey. Since the char is NOT alphabetic, our heuristic
    // doesn't apply — the ':' appended with shiftKey=false is accepted.
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    dispatchKey({ code: 'KeyO', key: 'O', at: 100 });
    dispatchKey({ code: 'KeyR', key: 'R', at: 105 });
    dispatchKey({ code: 'KeyD', key: 'D', at: 110 });
    dispatchKey({ code: 'KeyE', key: 'E', at: 115 });
    dispatchKey({ code: 'KeyR', key: 'R', at: 120 });
    dispatchKey({ code: 'Semicolon', key: ':', at: 125 }); // shift-required on QWERTY
    dispatchKey({ code: 'Digit4', key: '4', at: 130 });
    dispatchKey({ code: 'Digit2', key: '2', at: 135 });
    pressEnter(140);

    expect(onScan).toHaveBeenCalledWith('ORDER:42');
    dispose();
  });
});

describe('createBenchScannerListener — debounce', () => {
  it('resets buffer after gap > debounceMs', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan, debounceMs: 30 });

    // Type first 4 chars, then wait 100ms, then type 4 more + Enter.
    typeChars('ORDE', 100, 5); // 100,105,110,115
    // Next keystroke comes after 100ms gap — buffer resets.
    typeChars('R:42', 220, 5); // 220, 225, 230, 235
    pressEnter(240);

    // Only "R:42" survives, but it's only 4 chars — still emits if min=4.
    expect(onScan).toHaveBeenCalledTimes(1);
    expect(onScan).toHaveBeenCalledWith('R:42');
    dispose();
  });

  it('keeps buffer if gap <= debounceMs', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan, debounceMs: 30 });

    // All chars within 30ms of each other.
    dispatchKey({ code: 'KeyO', key: 'O', at: 100 });
    dispatchKey({ code: 'KeyR', key: 'R', at: 125 });
    dispatchKey({ code: 'KeyD', key: 'D', at: 150 });
    dispatchKey({ code: 'KeyE', key: 'E', at: 175 });
    dispatchKey({ code: 'KeyR', key: 'R', at: 200 });
    pressEnter(225);

    expect(onScan).toHaveBeenCalledWith('ORDER');
    dispose();
  });

  it('uses default debounce 30ms when none provided', () => {
    // Explicitly exercise the default: gap of 35ms must break the buffer.
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    dispatchKey({ code: 'KeyA', key: 'a', at: 100 });
    dispatchKey({ code: 'KeyA', key: 'a', at: 135 }); // +35ms > 30
    dispatchKey({ code: 'KeyA', key: 'a', at: 140 });
    dispatchKey({ code: 'KeyA', key: 'a', at: 145 });
    dispatchKey({ code: 'KeyA', key: 'a', at: 150 });
    pressEnter(155);

    expect(onScan).toHaveBeenCalledWith('aaaa');
    dispose();
  });
});

describe('createBenchScannerListener — autofill simulation', () => {
  // V1.1-TESTABILITY-REVIEW §3 "false-fire" matrix: 1Password, Bitwarden,
  // browser autofill all dispatch synthetic keydowns. Our defence relies on
  // activeElement (these autofill into an INPUT) plus the shift-alpha /
  // isComposing heuristics. Assert emit never fires for these patterns.

  it('does NOT emit when 1Password-style synthetic keydowns target a focused input', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    // 1Password / Bitwarden dispatch synthetic keydowns at machine speed.
    // Even without activeElement guard this would be a 20-char burst with
    // shift-alpha set for uppercase letters (typical of passwords).
    dispatchKey({ code: 'KeyS', key: 'S', shiftKey: true, at: 100 });
    dispatchKey({ code: 'KeyE', key: 'E', shiftKey: true, at: 102 });
    dispatchKey({ code: 'KeyC', key: 'C', shiftKey: true, at: 104 });
    dispatchKey({ code: 'KeyR', key: 'R', shiftKey: true, at: 106 });
    dispatchKey({ code: 'KeyE', key: 'E', shiftKey: true, at: 108 });
    dispatchKey({ code: 'KeyT', key: 'T', shiftKey: true, at: 110 });
    pressEnter(115);

    expect(onScan).not.toHaveBeenCalled();
    dispose();
  });

  it('does NOT emit when browser autofill dispatches into an input surface', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    const input = document.createElement('input');
    input.setAttribute('autocomplete', 'email');
    document.body.appendChild(input);
    input.focus();

    // Chrome autofill dispatches lowercase chars at machine speed.
    typeChars('user@example.com', 100, 2);
    pressEnter(150);

    expect(onScan).not.toHaveBeenCalled();
    dispose();
  });

  it('does NOT emit when macOS emoji-picker fires isComposing keys on body', () => {
    // Even without focused input, the isComposing guard catches this path.
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });

    dispatchKey({ code: 'KeyS', key: 's', isComposing: true, at: 100 });
    dispatchKey({ code: 'KeyM', key: 'm', isComposing: true, at: 105 });
    dispatchKey({ code: 'KeyI', key: 'i', isComposing: true, at: 110 });
    dispatchKey({ code: 'KeyL', key: 'l', isComposing: true, at: 115 });
    dispatchKey({ code: 'KeyE', key: 'e', isComposing: true, at: 120 });
    pressEnter(125);

    expect(onScan).not.toHaveBeenCalled();
    dispose();
  });
});

describe('createBenchScannerListener — cleanup', () => {
  it('cleanup function removes event listener', () => {
    const onScan = vi.fn();
    const addSpy = vi.spyOn(document, 'addEventListener');
    const removeSpy = vi.spyOn(document, 'removeEventListener');

    const dispose = createBenchScannerListener({ onScan });
    expect(addSpy).toHaveBeenCalledWith('keydown', expect.any(Function), { capture: true });

    dispose();
    expect(removeSpy).toHaveBeenCalledWith('keydown', expect.any(Function), { capture: true });

    addSpy.mockRestore();
    removeSpy.mockRestore();
  });

  it('post-dispose dispatches do not fire onScan', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });
    dispose();

    typeChars('ORDER:42', 100, 5);
    pressEnter(150);

    expect(onScan).not.toHaveBeenCalled();
  });

  it('dispose is idempotent', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });
    expect(() => {
      dispose();
      dispose();
      dispose();
    }).not.toThrow();
  });

  it('consumer exception does not take down the listener', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const onScan = vi.fn<() => void>(() => {
      throw new Error('boom');
    });
    const dispose = createBenchScannerListener({ onScan });

    typeChars('ORDER:42', 100, 5);
    pressEnter(150);

    expect(onScan).toHaveBeenCalledTimes(1);
    expect(errorSpy).toHaveBeenCalled();

    // Second burst still dispatches cleanly.
    onScan.mockImplementation(() => {}); // swap to non-throwing
    typeChars('REPAIR:1', 200, 5);
    pressEnter(250);
    expect(onScan).toHaveBeenCalledTimes(2);

    errorSpy.mockRestore();
    dispose();
  });
});

// A9 amendments explicit cross-reference — a smoke block that fails loudly if
// any guard is removed in the future.
describe('createBenchScannerListener — A9 amendment smoke', () => {
  it('A9.1 — default debounce is 30ms (35ms gap breaks buffer)', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });
    dispatchKey({ code: 'KeyA', key: 'a', at: 0 });
    dispatchKey({ code: 'KeyB', key: 'b', at: 35 });
    dispatchKey({ code: 'KeyC', key: 'c', at: 40 });
    dispatchKey({ code: 'KeyD', key: 'd', at: 45 });
    dispatchKey({ code: 'KeyE', key: 'e', at: 50 });
    pressEnter(55);
    expect(onScan).toHaveBeenCalledWith('bcde'); // "a" dropped by debounce
    dispose();
  });

  it('A9.2 — role=textbox/combobox/searchbox all block', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });
    for (const role of ['textbox', 'combobox', 'searchbox']) {
      const d = document.createElement('div');
      d.setAttribute('role', role);
      d.setAttribute('tabindex', '0');
      document.body.appendChild(d);
      d.focus();
      typeChars('ORDER:42', 100, 5);
      pressEnter(150);
      d.remove();
    }
    expect(onScan).not.toHaveBeenCalled();
    dispose();
  });

  it('A9.3 — single isComposing event anywhere in burst discards it', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });
    dispatchKey({ code: 'KeyA', key: 'a', at: 0 });
    dispatchKey({ code: 'KeyB', key: 'b', at: 5 });
    dispatchKey({ code: 'KeyC', key: 'c', isComposing: true, at: 10 });
    dispatchKey({ code: 'KeyD', key: 'd', at: 15 });
    pressEnter(20);
    expect(onScan).not.toHaveBeenCalled();
    dispose();
  });

  it('A9.4 — shift+alpha anywhere in burst discards it', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan });
    dispatchKey({ code: 'KeyA', key: 'a', at: 0 });
    dispatchKey({ code: 'KeyB', key: 'b', at: 5 });
    dispatchKey({ code: 'KeyC', key: 'C', shiftKey: true, at: 10 });
    dispatchKey({ code: 'KeyD', key: 'd', at: 15 });
    pressEnter(20);
    expect(onScan).not.toHaveBeenCalled();
    dispose();
  });

  it('A9.5 — CR/LF/Tab tails all get stripped before min-length check', () => {
    const onScan = vi.fn();
    const dispose = createBenchScannerListener({ onScan, minLength: 4 });
    // Payload is exactly 4 chars; an unstripped CR would make it 5. If the
    // min-length check ran on the un-stripped buffer we'd still pass — but
    // onScan MUST receive the stripped form per A9.5.
    typeChars('ABCD', 0, 5);
    dispatchKey({ code: 'Unidentified', key: '\r', at: 25 });
    dispatchKey({ code: 'Unidentified', key: '\n', at: 30 });
    pressEnter(35);
    expect(onScan).toHaveBeenCalledWith('ABCD'); // no trailing whitespace
    dispose();
  });
});
