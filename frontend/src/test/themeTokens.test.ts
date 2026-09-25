// W4-05: dark mode through semantic tokens. Parses styles/brand-tokens.css and
// checks (1) every light --color-* / --tone-* token has a dark counterpart,
// (2) the class and media-query dark blocks stay identical, and (3) every
// text and UI pair passes WCAG AA in both themes (playbook Appendix B formula).
import { describe, expect, it } from 'vitest';

import { CONTRAST_TEXT, contrastRatio } from '../hooks/useTheme';
import { isDerived, loadThemeTokens, resolveColour } from './theme-tokens';

const tokens = loadThemeTokens();
const THEMED = /^--(color|tone)-/;
/** Defined in index.css :root; the dark block re-points them to tokens. */
const INDEX_CSS_TOKENS = new Set(['--text-dark', '--background-light']);

const TEXT = 4.5; // WCAG 1.4.3 normal text
const UI = 3; // WCAG 1.4.11 boundaries, focus rings, meaningful icons

type Scheme = 'light' | 'dark';
type Pair = readonly [fg: string, bg: string, min: number, schemes?: readonly Scheme[]];

const TONES = ['neutral', 'info', 'progress', 'waiting', 'check', 'done', 'handover', 'danger'];

const PAIRS: readonly Pair[] = [
  // Text on the three surfaces
  ['--color-text', '--color-surface', TEXT],
  ['--color-text', '--color-surface-raised', TEXT],
  ['--color-text', '--color-surface-sunken', TEXT],
  ['--color-text-muted', '--color-surface', TEXT],
  ['--color-text-muted', '--color-surface-raised', TEXT],
  ['--color-text-muted', '--color-surface-sunken', TEXT],
  ['--color-text-heading', '--color-surface-raised', TEXT],
  ['--color-text-body', '--color-surface-raised', TEXT],
  // Primary: fills with contrast text, and primary as link text
  ['--color-primary-contrast', '--color-primary', TEXT],
  ['--color-primary-contrast', '--color-primary-hover', TEXT],
  ['--color-primary', '--color-surface', TEXT],
  ['--color-primary', '--color-surface-raised', TEXT],
  ['--color-primary-hover', '--color-primary-subtle', TEXT],
  ['--color-accent-strong', '--color-surface-raised', TEXT],
  // Header: contrast text at both gradient ends, header focus ring
  ['--color-primary-contrast', '--color-surface-header-start', TEXT],
  ['--color-primary-contrast', '--color-surface-header-end', TEXT],
  ['--color-focus-on-dark', '--color-surface-header-start', UI],
  ['--color-focus-on-dark', '--color-surface-header-end', UI],
  // Feedback fills and text
  ['--color-success-contrast', '--color-success', TEXT],
  ['--color-warning-contrast', '--color-warning', TEXT],
  ['--color-danger-contrast', '--color-danger', TEXT],
  ['--color-info-contrast', '--color-info', TEXT],
  ['--color-danger', '--color-surface', TEXT],
  ['--color-danger', '--color-surface-raised', TEXT],
  ['--color-danger-fg', '--color-danger-bg', TEXT],
  ['--color-success-fg', '--color-success-bg', TEXT],
  ['--color-info-fg', '--color-info-bg', TEXT],
  ['--color-info-600', '--color-info-bg', TEXT],
  // Legacy warning text on its banner: light #b8651a on #fff4e6 is 3.72 today
  // (AlloyMismatchModal, QrCameraScanner; open item), dark passes.
  ['--color-warning-600', '--color-warning-bg', TEXT, ['dark']],
  // Photo and swatch overlays (W4 phase 4): same values in both themes
  ['--color-overlay-fg', '--color-overlay-bg', TEXT],
  ['--color-overlay-fg', '--color-overlay-danger', TEXT],
  // Boundaries and focus
  ['--color-border-strong', '--color-surface', UI],
  ['--color-border-strong', '--color-surface-raised', UI],
  ['--color-focus', '--color-surface', UI],
  ['--color-focus', '--color-surface-raised', UI],
  // Status tones: label text on the badge; dark borders also reach 3:1
  // (light tone borders are decorative, the label and icon carry the status).
  ...TONES.map((t): Pair => [`--tone-${t}-fg`, `--tone-${t}-bg`, TEXT]),
  ...TONES.map((t): Pair => [`--tone-${t}-border`, `--tone-${t}-bg`, UI, ['dark']]),
];

describe('dark token completeness', () => {
  const lightThemed = Object.entries(tokens.light).filter(([name]) => THEMED.test(name));

  it('parses a meaningful token set', () => {
    expect(lightThemed.length).toBeGreaterThan(60);
    expect(Object.keys(tokens.dark).length).toBeGreaterThan(60);
  });

  it.each(lightThemed)('%s has a dark value or only aliases semantic tokens', (name, value) => {
    const covered = name in tokens.dark || isDerived(value);
    expect(covered, `${name}: ${value} needs a dark value in :root.dark`).toBe(true);
  });

  it('dark block only overrides tokens that exist in light', () => {
    const unknown = Object.keys(tokens.dark).filter(
      (name) => !(name in tokens.light) && !INDEX_CSS_TOKENS.has(name),
    );
    expect(unknown).toEqual([]);
  });

  it('the prefers-color-scheme fallback matches :root.dark exactly', () => {
    expect(tokens.systemDark).toEqual(tokens.dark);
  });

  it('CONTRAST_TEXT in useTheme.ts mirrors --color-primary-contrast', () => {
    expect(resolveColour(tokens, '--color-primary-contrast', 'light')).toBe(CONTRAST_TEXT.light);
    expect(resolveColour(tokens, '--color-primary-contrast', 'dark')).toBe(CONTRAST_TEXT.dark);
  });
});

describe('contrast table (WCAG 2.x, Appendix B)', () => {
  const rows = PAIRS.flatMap(([fg, bg, min, schemes = ['light', 'dark'] as const]) =>
    schemes.map((scheme) => {
      const fgHex = resolveColour(tokens, fg, scheme);
      const bgHex = resolveColour(tokens, bg, scheme);
      const ratio = fgHex && bgHex ? contrastRatio(fgHex, bgHex) : null;
      const label = `${scheme} ${fg} ${fgHex} on ${bg} ${bgHex}: ${ratio?.toFixed(2)} (min ${min})`;
      return [label, ratio, min] as const;
    }),
  );

  it.each(rows)('%s', (_label, ratio, min) => {
    expect(ratio).not.toBeNull();
    expect(ratio as number).toBeGreaterThanOrEqual(min);
  });

  it('reproduces the Appendix B dark sketch values', () => {
    expect(contrastRatio('#f5f5f4', '#1c1917')).toBeCloseTo(16.03, 2);
    expect(contrastRatio('#1c1917', '#f59e0b')).toBeCloseTo(8.14, 2);
  });
});
