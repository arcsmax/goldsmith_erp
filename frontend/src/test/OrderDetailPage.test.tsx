// OrderDetailPage regression tests.
//
// Scope:
//   * The "Angebot erstellen" button must NOT render the literal string
//     "F4DD" in front of its label. This was a CSS escape bug — content
//     was set to "F4DD" instead of the proper Unicode escape "\01F4DD"
//     for U+1F4DD (memo emoji), causing browsers to render the raw hex
//     characters next to the button label.
//   * We assert against the raw CSS source because JSDOM does not
//     compute ::before pseudo-element content; reading the file gives
//     us the only reliable signal.

import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

describe('OrderDetailPage — "Angebot erstellen" button mojibake regression', () => {
  it('does not contain the literal string "F4DD" in the button CSS', () => {
    const cssPath = resolve(__dirname, '../styles/order-detail.css');
    const css = readFileSync(cssPath, 'utf-8');

    // Find the .btn-create-quote::before block.
    const blockMatch = css.match(/\.btn-create-quote::before\s*\{[^}]*\}/);
    expect(blockMatch).not.toBeNull();
    const block = blockMatch![0];

    // Must NOT contain bare "F4DD" (the mojibake symptom). The fixed
    // CSS uses the escape sequence \01F4DD which contains a backslash
    // before the F, so this regex still excludes the broken form.
    expect(block).not.toMatch(/"F4DD/);

    // Must NOT contain a stray SOH control char () that snuck in
    // alongside the original broken escape.
    expect(block).not.toContain('');

    // Must contain a proper CSS Unicode escape that resolves to U+1F4DD
    // (memo emoji). Both \01F4DD and \1F4DD are valid CSS forms.
    expect(block).toMatch(/\\0?1F4DD/i);
  });
});
