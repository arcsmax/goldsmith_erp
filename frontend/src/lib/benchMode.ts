/**
 * Werkbank-Modus (UI-UX-PLAYBOOK 5.5): the bench layout of this device.
 *
 * Sets `:root.bench` (brand-tokens.css raises type and touch targets to
 * 56px) and persists the choice per device in localStorage. It is a device
 * setting, not a user setting: the bench tablet stays in bench mode across
 * logins, so AuthContext's logout cleanup deliberately leaves this key.
 *
 * Not to be confused with ScannerContext.benchModeEnabled ("Werkbank-
 * Station-Modus", A12.2), which arms the USB/HID keyboard-wedge listener.
 * The two are independent switches.
 *
 * One store for the whole app (useSyncExternalStore), so every toggle and
 * every reader stay in sync without a context provider.
 */
import { useCallback, useSyncExternalStore } from 'react';

export const BENCH_MODE_STORAGE_KEY = 'bench_layout_mode';
export const BENCH_ROOT_CLASS = 'bench';

type Listener = () => void;
const listeners = new Set<Listener>();

function readStored(): boolean {
  try {
    return localStorage.getItem(BENCH_MODE_STORAGE_KEY) === '1';
  } catch (err) {
    console.warn('Werkbank-Modus: localStorage nicht lesbar', err);
    return false;
  }
}

let current = typeof window === 'undefined' ? false : readStored();

function applyRootClass(enabled: boolean): void {
  if (typeof document === 'undefined') return;
  document.documentElement.classList.toggle(BENCH_ROOT_CLASS, enabled);
}

export function isBenchModeEnabled(): boolean {
  return current;
}

export function setBenchMode(enabled: boolean): void {
  current = enabled;
  try {
    localStorage.setItem(BENCH_MODE_STORAGE_KEY, enabled ? '1' : '0');
  } catch (err) {
    // Private mode / quota: the switch still works for this session.
    console.warn('Werkbank-Modus: localStorage nicht schreibbar', err);
  }
  applyRootClass(enabled);
  listeners.forEach((listener) => listener());
}

/** Re-read storage and apply the root class (app start, tests). */
export function syncBenchModeFromStorage(): boolean {
  current = readStored();
  applyRootClass(current);
  listeners.forEach((listener) => listener());
  return current;
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export interface BenchModeState {
  isBenchMode: boolean;
  setBenchMode: (enabled: boolean) => void;
  toggleBenchMode: () => void;
}

export function useBenchMode(): BenchModeState {
  const isBenchMode = useSyncExternalStore(subscribe, isBenchModeEnabled, () => false);
  const toggleBenchMode = useCallback(() => setBenchMode(!isBenchModeEnabled()), []);
  return { isBenchMode, setBenchMode, toggleBenchMode };
}

// Apply the stored choice as soon as any bench screen or the timer loads.
applyRootClass(current);
