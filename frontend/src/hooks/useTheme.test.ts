import { afterEach, describe, expect, it, vi } from 'vitest';
import { applyTheme, contrastWithWhite } from './useTheme';

// W4-01 / DES-01, DES-27: admin theme colours carry white text (buttons,
// header). A colour that fails WCAG AA with white must not override the AA
// token from brand-tokens.css.

const root = () => document.documentElement.style;

afterEach(() => {
  document.documentElement.removeAttribute('style');
  vi.restoreAllMocks();
});

describe('contrastWithWhite', () => {
  it('matches the playbook Appendix B values', () => {
    expect(contrastWithWhite('#d97706')).toBeCloseTo(3.19, 2);
    expect(contrastWithWhite('#b45309')).toBeCloseTo(5.02, 2);
  });

  it('returns null for values that are not 6-digit hex colours', () => {
    expect(contrastWithWhite('red')).toBeNull();
    expect(contrastWithWhite('#fff')).toBeNull();
  });
});

describe('applyTheme contrast guard', () => {
  it('applies primary and header colours that pass AA with white text', () => {
    applyTheme({
      primary_color: '#b45309',
      primary_dark: '#92400e',
      header_gradient_start: '#b45309',
      header_gradient_end: '#78350f',
    });

    expect(root().getPropertyValue('--color-interactive-primary')).toBe('#b45309');
    expect(root().getPropertyValue('--color-surface-header-start')).toBe('#b45309');
    expect(root().getPropertyValue('--color-surface-header-gradient')).toContain('#78350f');
  });

  it('keeps the stylesheet token when the configured primary fails AA', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

    applyTheme({ primary_color: '#d97706', header_gradient_start: '#d97706' });

    expect(root().getPropertyValue('--color-interactive-primary')).toBe('');
    expect(root().getPropertyValue('--color-surface-header-start')).toBe('');
    expect(root().getPropertyValue('--color-surface-header-gradient')).toBe('');
    expect(warn).toHaveBeenCalled();
  });

  it('still applies non-text colours such as the page background', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});

    applyTheme({ primary_color: '#d97706', page_background: '#fdf8f0' });

    expect(root().getPropertyValue('--color-surface-page')).toBe('#fdf8f0');
  });
});
