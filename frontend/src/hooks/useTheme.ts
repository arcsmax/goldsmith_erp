/**
 * useTheme — applies the two theme layers on document.documentElement:
 *
 *  A. Colour scheme (W4-05): "System", "Hell" or "Dunkel", stored per device
 *     in localStorage. The resolved scheme is set as the `.light` / `.dark`
 *     class on <html>; styles/brand-tokens.css carries the dark token values
 *     under `:root.dark` (and a prefers-color-scheme fallback before JS runs).
 *     `useColorScheme()` reads and changes it (ThemeToggle).
 *
 *  B. Admin brand settings (/api/v1/theme): primary and header colours as CSS
 *     custom properties. Every colour that carries text is contrast-checked
 *     against the active scheme's text colour and dropped with a warning if it
 *     fails, so the AA token from brand-tokens.css applies instead.
 *
 * Strategy for B:
 *  1. On mount, read cached settings from localStorage for instant paint.
 *  2. Fetch /api/v1/theme in background. If settings changed, re-apply and
 *     update the cache. This way the UI is never blocked on a network round-trip.
 *  3. Exported `applyTheme` is also used by the admin theme editor for live preview.
 */

import { useEffect, useSyncExternalStore } from 'react';
import apiClient from '../api/client';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ThemeSettings {
  primary_color: string;
  primary_dark: string;
  header_gradient_start: string;
  header_gradient_end: string;
  accent_color: string;
  page_background: string;
  workshop_name: string;
  logo_url: string | null;
}

/** What the user picked. "system" follows the operating system. */
export type ColorSchemePreference = 'system' | 'light' | 'dark';
/** What is actually shown. */
export type ResolvedColorScheme = 'light' | 'dark';

// Defaults match the AA tokens in styles/brand-tokens.css (W4-01): white text
// on the default primary is 5.02:1, on the old cta-600 only 3.19:1.
export const THEME_DEFAULTS: ThemeSettings = {
  primary_color: '#b45309',
  primary_dark: '#92400e',
  header_gradient_start: '#b45309',
  header_gradient_end: '#78350f',
  accent_color: '#f59e0b',
  page_background: '#faf8f4',
  workshop_name: 'Goldschmiede Werkstatt',
  logo_url: null,
};

const CACHE_KEY = 'goldsmith_erp_theme';
export const COLOR_SCHEME_KEY = 'goldsmith_erp_color_scheme';
const THEME_ENDPOINT = '/api/v1/theme';
const DARK_QUERY = '(prefers-color-scheme: dark)';

// ─── Contrast (WCAG 2.x, playbook Appendix B) ─────────────────────────────────

/** WCAG AA minimum for normal-size text (labels on buttons and header). */
const MIN_TEXT_CONTRAST = 4.5;
const HEX6 = /^#[0-9a-fA-F]{6}$/;
const WHITE = '#ffffff';
/**
 * Text on primary fills and the header, per scheme. Mirrors
 * --color-primary-contrast in brand-tokens.css (light: white, dark: stone-900);
 * themeTokens.test.ts keeps the two in sync.
 */
export const CONTRAST_TEXT: Record<ResolvedColorScheme, string> = {
  light: WHITE,
  dark: '#1c1917',
};

function relativeLuminance(hex: string): number {
  const channel = (offset: number): number => {
    const c = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

/**
 * WCAG contrast ratio of two #rrggbb colours (order does not matter).
 * Returns null when either value is not a #rrggbb colour.
 */
export function contrastRatio(a: string, b: string): number | null {
  if (!HEX6.test(a) || !HEX6.test(b)) return null;
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Contrast ratio of white text on `hex` (WCAG 2.x, playbook Appendix B).
 * Returns null when `hex` is not a #rrggbb colour and so cannot be checked.
 */
export function contrastWithWhite(hex: string): number | null {
  return contrastRatio(WHITE, hex);
}

/** True when the scheme's contrast text on `hex` passes AA. */
export function carriesContrastText(hex: string, scheme: ResolvedColorScheme): boolean {
  const ratio = contrastRatio(CONTRAST_TEXT[scheme], hex);
  return ratio !== null && ratio >= MIN_TEXT_CONTRAST;
}

// ─── Colour scheme (A) ────────────────────────────────────────────────────────

function isPreference(value: unknown): value is ColorSchemePreference {
  return value === 'system' || value === 'light' || value === 'dark';
}

function readPreference(): ColorSchemePreference {
  try {
    const stored = localStorage.getItem(COLOR_SCHEME_KEY);
    return isPreference(stored) ? stored : 'system';
  } catch {
    return 'system';
  }
}

function writePreference(preference: ColorSchemePreference): void {
  try {
    if (preference === 'system') localStorage.removeItem(COLOR_SCHEME_KEY);
    else localStorage.setItem(COLOR_SCHEME_KEY, preference);
  } catch (error) {
    // Private mode or blocked storage: the choice still applies for this visit.
    console.warn('[theme] could not store the colour scheme choice', error);
  }
}

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(DARK_QUERY).matches
    : false;
}

export function resolveColorScheme(preference: ColorSchemePreference): ResolvedColorScheme {
  if (preference !== 'system') return preference;
  return systemPrefersDark() ? 'dark' : 'light';
}

interface ColorSchemeState {
  preference: ColorSchemePreference;
  resolved: ResolvedColorScheme;
}

let schemeState: ColorSchemeState = { preference: 'system', resolved: 'light' };
const schemeListeners = new Set<() => void>();

/** The scheme currently on <html>; applyTheme validates colours against it. */
function activeScheme(): ResolvedColorScheme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}

function commitScheme(preference: ColorSchemePreference): void {
  const resolved = resolveColorScheme(preference);
  const root = document.documentElement;
  root.classList.toggle('dark', resolved === 'dark');
  root.classList.toggle('light', resolved === 'light');
  const changed = resolved !== schemeState.resolved || preference !== schemeState.preference;
  schemeState = { preference, resolved };
  // Admin colours were validated for the previous scheme: check them again.
  if (lastSettings) applyTheme(lastSettings);
  if (changed) schemeListeners.forEach((listener) => listener());
}

/** Store and apply a colour scheme choice for this device. */
export function setColorSchemePreference(preference: ColorSchemePreference): void {
  writePreference(preference);
  commitScheme(preference);
}

/** Read the stored choice and apply it (app start, tests). */
export function initColorScheme(): void {
  commitScheme(readPreference());
}

function subscribeScheme(listener: () => void): () => void {
  schemeListeners.add(listener);
  return () => schemeListeners.delete(listener);
}

const getSchemeState = (): ColorSchemeState => schemeState;

/** Current choice, resolved scheme and a setter; for ThemeToggle. */
export function useColorScheme(): ColorSchemeState & {
  setPreference: (preference: ColorSchemePreference) => void;
} {
  const state = useSyncExternalStore(subscribeScheme, getSchemeState, getSchemeState);
  return { ...state, setPreference: setColorSchemePreference };
}

// ─── Admin brand settings (B) ─────────────────────────────────────────────────

let lastSettings: Partial<ThemeSettings> | null = null;

type TextBearingKey = 'primary_color' | 'primary_dark' | 'header_gradient_start' | 'header_gradient_end';

/**
 * Set a colour that carries text only if it passes AA in the active scheme;
 * otherwise drop any inline override so the token from brand-tokens.css
 * applies (DES-27, W4-05). In dark mode an unchanged light default is not an
 * admin choice, so it gives way to the dark token without a warning.
 */
function setTextBearingColour(
  prop: string,
  key: TextBearingKey,
  hex: string,
  scheme: ResolvedColorScheme,
): boolean {
  const root = document.documentElement;
  if (scheme === 'dark' && hex === THEME_DEFAULTS[key]) {
    root.style.removeProperty(prop);
    return false;
  }
  if (carriesContrastText(hex, scheme)) {
    root.style.setProperty(prop, hex);
    return true;
  }
  root.style.removeProperty(prop);
  console.warn(
    `[theme] ${prop} ${hex} fails WCAG AA with the ${scheme} theme's text colour ` +
      `${CONTRAST_TEXT[scheme]} (needs ${MIN_TEXT_CONTRAST}:1); using the default token.`,
  );
  return false;
}

export function applyTheme(partial: Partial<ThemeSettings>): void {
  lastSettings = partial;
  const t: ThemeSettings = { ...THEME_DEFAULTS, ...partial };
  const root = document.documentElement;
  const scheme = activeScheme();

  setTextBearingColour('--color-interactive-primary', 'primary_color', t.primary_color, scheme);
  setTextBearingColour('--color-interactive-primary-hover', 'primary_dark', t.primary_dark, scheme);
  const startOk = setTextBearingColour(
    '--color-surface-header-start', 'header_gradient_start', t.header_gradient_start, scheme,
  );
  const endOk = setTextBearingColour(
    '--color-surface-header-end', 'header_gradient_end', t.header_gradient_end, scheme,
  );
  if (startOk && endOk) {
    root.style.setProperty(
      '--color-surface-header-gradient',
      `linear-gradient(135deg, ${t.header_gradient_start}, ${t.header_gradient_end})`
    );
  } else {
    root.style.removeProperty('--color-surface-header-gradient');
  }
  root.style.setProperty('--color-brand-cta-500', t.accent_color);
  // The admin page background is a light-theme colour; in dark mode the dark
  // surface token applies.
  if (scheme === 'dark') root.style.removeProperty('--color-surface-page');
  else root.style.setProperty('--color-surface-page', t.page_background);

  // Store workshop name as a data attribute for CSS ::before content use if needed
  root.setAttribute('data-workshop-name', t.workshop_name);
}

// ─── Cache helpers ────────────────────────────────────────────────────────────

function readCache(): Partial<ThemeSettings> | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as Partial<ThemeSettings>;
  } catch {
    return null;
  }
}

function writeCache(settings: ThemeSettings): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(settings));
  } catch {
    // localStorage can be unavailable in some environments — ignore
  }
}

// ─── Fetch & apply ────────────────────────────────────────────────────────────

async function fetchAndApply(): Promise<void> {
  try {
    const resp = await fetch(THEME_ENDPOINT, {
      headers: { Accept: 'application/json' },
      // Don't send credentials — this is a public endpoint
      credentials: 'omit',
    });

    if (!resp.ok) return;

    const data: ThemeSettings = await resp.json();
    applyTheme(data);
    writeCache(data);
  } catch {
    // Network failure — silently keep cached / default values
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

/**
 * Wire this at the App root. It applies the stored colour scheme, follows OS
 * changes while the choice is "System", and fires a background refresh of the
 * admin theme so stale themes are updated without blocking the first render.
 *
 * @example
 * // In App.tsx:
 * import { useTheme } from './hooks/useTheme';
 * const App = () => { useTheme(); return <Router>…</Router>; };
 */
export function useTheme(): void {
  useEffect(() => {
    // 1. Instant paint from cache (avoids flash of wrong colours)
    const cached = readCache();
    if (cached) {
      applyTheme(cached);
    }

    // 2. Background refresh — picks up admin changes made in another session
    fetchAndApply();
  }, []);

  useEffect(() => {
    initColorScheme();
    if (typeof window.matchMedia !== 'function') return undefined;
    const media = window.matchMedia(DARK_QUERY);
    const onSystemChange = (): void => {
      if (schemeState.preference === 'system') commitScheme('system');
    };
    media.addEventListener('change', onSystemChange);
    return () => media.removeEventListener('change', onSystemChange);
  }, []);
}

// Apply the stored scheme as soon as the module loads (App.tsx imports it
// before the first render), so a stored "Dunkel" does not flash light.
if (typeof document !== 'undefined') initColorScheme();

// ─── Utility exported for admin theme editor ──────────────────────────────────

/**
 * Save theme to the backend and update cache + CSS variables.
 * Throws if the request fails (caller should show an error message).
 */
export async function saveTheme(
  settings: ThemeSettings,
): Promise<ThemeSettings> {
  const resp = await apiClient.put('/theme', settings);
  const saved: ThemeSettings = resp.data;
  applyTheme(saved);
  writeCache(saved);
  return saved;
}

/**
 * Fetch the current theme from the backend (bypasses cache).
 * Used by the admin editor to populate the initial form state.
 */
export async function fetchTheme(): Promise<ThemeSettings> {
  const resp = await apiClient.get('/theme');
  return resp.data;
}
