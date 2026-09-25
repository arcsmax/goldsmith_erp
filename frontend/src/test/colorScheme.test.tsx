// W4-05: colour scheme choice (System / Hell / Dunkel) per device, system
// fallback, and the admin primary colour validated against the active theme.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ThemeToggle } from '../components/ThemeToggle';
import {
  COLOR_SCHEME_KEY,
  THEME_DEFAULTS,
  applyTheme,
  initColorScheme,
  resolveColorScheme,
  setColorSchemePreference,
} from '../hooks/useTheme';

const html = document.documentElement;
const inline = (prop: string): string => html.style.getPropertyValue(prop);

function mockSystemDark(matches: boolean): void {
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }) as unknown as MediaQueryList,
  );
}

beforeEach(() => {
  localStorage.clear();
  mockSystemDark(false);
  // Reset the remembered admin settings (module state) while still light.
  applyTheme(THEME_DEFAULTS);
  setColorSchemePreference('system');
});

afterEach(() => {
  vi.restoreAllMocks();
  html.removeAttribute('style');
  html.classList.remove('dark', 'light');
  localStorage.clear();
});

describe('colour scheme preference', () => {
  it('defaults to "system" and follows a light OS', () => {
    initColorScheme();
    expect(html.classList.contains('light')).toBe(true);
    expect(html.classList.contains('dark')).toBe(false);
  });

  it('falls back to the OS setting when nothing is stored', () => {
    mockSystemDark(true);
    expect(resolveColorScheme('system')).toBe('dark');
    initColorScheme();
    expect(html.classList.contains('dark')).toBe(true);
  });

  it('persists an explicit choice per device and restores it', () => {
    setColorSchemePreference('dark');
    expect(localStorage.getItem(COLOR_SCHEME_KEY)).toBe('dark');

    html.classList.remove('dark', 'light');
    initColorScheme();
    expect(html.classList.contains('dark')).toBe(true);
  });

  it('an explicit "Hell" wins over a dark OS', () => {
    mockSystemDark(true);
    setColorSchemePreference('light');
    expect(html.classList.contains('light')).toBe(true);
    expect(html.classList.contains('dark')).toBe(false);
  });

  it('choosing "System" clears the stored value', () => {
    setColorSchemePreference('dark');
    setColorSchemePreference('system');
    expect(localStorage.getItem(COLOR_SCHEME_KEY)).toBeNull();
  });

  it('ignores a corrupt stored value', () => {
    localStorage.setItem(COLOR_SCHEME_KEY, 'purple');
    initColorScheme();
    expect(html.classList.contains('light')).toBe(true);
  });
});

describe('ThemeToggle', () => {
  it('offers System, Hell and Dunkel and applies the choice', async () => {
    const user = userEvent.setup();
    render(<ThemeToggle showLegend />);

    expect(screen.getByRole('group', { name: 'Farbschema' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'System' })).toBeChecked();

    await user.click(screen.getByRole('radio', { name: 'Dunkel' }));
    expect(screen.getByRole('radio', { name: 'Dunkel' })).toBeChecked();
    expect(html.classList.contains('dark')).toBe(true);
    expect(localStorage.getItem(COLOR_SCHEME_KEY)).toBe('dark');

    await user.click(screen.getByRole('radio', { name: 'Hell' }));
    expect(html.classList.contains('light')).toBe(true);
  });
});

describe('admin primary colour in both themes', () => {
  it('light: a custom primary that carries white text is applied', () => {
    applyTheme({ primary_color: '#9a3412' });
    expect(inline('--color-interactive-primary')).toBe('#9a3412');
  });

  it('dark: the unchanged light default gives way to the dark token silently', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    setColorSchemePreference('dark');
    applyTheme(THEME_DEFAULTS);

    expect(inline('--color-interactive-primary')).toBe('');
    expect(inline('--color-surface-header-gradient')).toBe('');
    expect(inline('--color-surface-page')).toBe('');
    expect(warn).not.toHaveBeenCalled();
  });

  it('dark: a custom primary that fails with dark text is dropped with a warning', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    setColorSchemePreference('dark');
    applyTheme({ primary_color: '#9a3412' });

    expect(inline('--color-interactive-primary')).toBe('');
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('dark theme'));
  });

  it('dark: a custom primary that passes with dark text is applied', () => {
    setColorSchemePreference('dark');
    applyTheme({ primary_color: '#fcd34d' });
    expect(inline('--color-interactive-primary')).toBe('#fcd34d');
  });

  it('switching theme re-validates the last admin settings', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    applyTheme({ primary_color: '#9a3412' });
    expect(inline('--color-interactive-primary')).toBe('#9a3412');

    setColorSchemePreference('dark');
    expect(inline('--color-interactive-primary')).toBe('');

    setColorSchemePreference('light');
    expect(inline('--color-interactive-primary')).toBe('#9a3412');
  });
});
