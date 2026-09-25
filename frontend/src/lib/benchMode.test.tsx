// Werkbank-Modus (W4-03, UI-UX-PLAYBOOK 5.5): the bench layout toggle is
// per device (localStorage), sets :root.bench and survives a reload.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import {
  BENCH_MODE_STORAGE_KEY,
  BENCH_ROOT_CLASS,
  setBenchMode,
  syncBenchModeFromStorage,
  useBenchMode,
} from './benchMode';
import { BenchModeToggle } from '../components/scanner/BenchModeToggle';

const rootHasBench = () => document.documentElement.classList.contains(BENCH_ROOT_CLASS);

beforeEach(() => {
  localStorage.clear();
  act(() => {
    syncBenchModeFromStorage();
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  act(() => setBenchMode(false));
  localStorage.clear();
});

describe('Werkbank-Modus toggle', () => {
  it('starts off on a fresh device', () => {
    render(<BenchModeToggle />);
    const toggle = screen.getByRole('button', { name: 'Werkbank-Modus' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    expect(rootHasBench()).toBe(false);
  });

  it('turns bench mode on and off, sets :root.bench and persists per device', async () => {
    const user = userEvent.setup();
    render(<BenchModeToggle />);
    const toggle = screen.getByRole('button', { name: 'Werkbank-Modus' });

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    expect(rootHasBench()).toBe(true);
    expect(localStorage.getItem(BENCH_MODE_STORAGE_KEY)).toBe('1');

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    expect(rootHasBench()).toBe(false);
    expect(localStorage.getItem(BENCH_MODE_STORAGE_KEY)).toBe('0');
  });

  it('restores the stored choice after a reload', () => {
    localStorage.setItem(BENCH_MODE_STORAGE_KEY, '1');
    act(() => {
      syncBenchModeFromStorage();
    });
    render(<BenchModeToggle />);
    expect(screen.getByRole('button', { name: 'Werkbank-Modus' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(rootHasBench()).toBe(true);
  });

  it('keeps every toggle on the page in sync', async () => {
    const user = userEvent.setup();
    const Probe: React.FC = () => {
      const { isBenchMode } = useBenchMode();
      return <span data-testid="probe">{isBenchMode ? 'an' : 'aus'}</span>;
    };
    render(
      <>
        <BenchModeToggle />
        <Probe />
      </>,
    );
    await user.click(screen.getByRole('button', { name: 'Werkbank-Modus' }));
    expect(screen.getByTestId('probe')).toHaveTextContent('an');
  });

  it('still switches for the session when storage is blocked', async () => {
    const user = userEvent.setup();
    vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    render(<BenchModeToggle />);
    await user.click(screen.getByRole('button', { name: 'Werkbank-Modus' }));
    expect(rootHasBench()).toBe(true);
    expect(warn).toHaveBeenCalled();
  });
});
