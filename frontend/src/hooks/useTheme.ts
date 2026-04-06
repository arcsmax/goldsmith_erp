/**
 * useTheme — fetches admin-configurable theme settings and applies them as
 * CSS custom properties on document.documentElement.
 *
 * Strategy:
 *  1. On mount, read cached settings from localStorage for instant paint.
 *  2. Fetch /api/v1/theme in background. If settings changed, re-apply and
 *     update the cache. This way the UI is never blocked on a network round-trip.
 *  3. Exported `applyTheme` is also used by the admin theme editor for live preview.
 */

import { useEffect } from 'react';
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

const DEFAULTS: ThemeSettings = {
  primary_color: '#d97706',
  primary_dark: '#92400e',
  header_gradient_start: '#d97706',
  header_gradient_end: '#92400e',
  accent_color: '#f59e0b',
  page_background: '#faf8f4',
  workshop_name: 'Goldschmiede Werkstatt',
  logo_url: null,
};

const CACHE_KEY = 'goldsmith_erp_theme';
const THEME_ENDPOINT = '/api/v1/theme';

// ─── CSS variable mapping ─────────────────────────────────────────────────────

/**
 * Apply a ThemeSettings object to document.documentElement CSS variables.
 * Safe to call with a partial object — missing keys fall back to defaults.
 */
export function applyTheme(partial: Partial<ThemeSettings>): void {
  const t: ThemeSettings = { ...DEFAULTS, ...partial };
  const root = document.documentElement;

  root.style.setProperty('--color-interactive-primary', t.primary_color);
  root.style.setProperty('--color-interactive-primary-hover', t.primary_dark);
  root.style.setProperty('--color-surface-header-start', t.header_gradient_start);
  root.style.setProperty('--color-surface-header-end', t.header_gradient_end);
  root.style.setProperty(
    '--color-surface-header-gradient',
    `linear-gradient(135deg, ${t.header_gradient_start}, ${t.header_gradient_end})`
  );
  root.style.setProperty('--color-brand-cta-500', t.accent_color);
  root.style.setProperty('--color-surface-page', t.page_background);

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
 * Wire this at the App root. It runs once on mount and fires a background
 * refresh so stale themes are updated without blocking the initial render.
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
}

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
