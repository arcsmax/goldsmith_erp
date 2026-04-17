// UserSettingsPage / Werkbank-Station-Modus toggle tests — Slice 12.
//
// Scope (plan §Slice 12, AMENDMENTS A12.2):
//   * The toggle reads its checked state from ScannerContext.
//   * Clicking flips ScannerContext.benchModeEnabled (via toggleBenchMode).
//   * Value persists to localStorage across unmount/remount on the same
//     device (A12.2 — device-persistent, not session-persistent).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { UserSettingsPage } from '../pages/UserSettingsPage';
import { ScannerProvider } from '../contexts/ScannerContext';

// Avoid mounting the BenchScannerListener during these tests — we are
// asserting storage persistence, not listener wiring (covered by
// bench-scanner-listener.test.ts).
vi.mock('../lib/bench-scanner-listener', () => ({
  createBenchScannerListener: () => () => {},
}));

function renderPage(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <ScannerProvider>
        <UserSettingsPage />
      </ScannerProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('UserSettingsPage — Werkbank-Station-Modus toggle', () => {
  it('renders the Scanner-Einstellungen section with the toggle', () => {
    renderPage();
    expect(screen.getByTestId('user-settings-page')).toBeInTheDocument();
    expect(
      screen.getByTestId('toggle-setting-bench-mode-toggle'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('toggle-setting-label-bench-mode-toggle'),
    ).toHaveTextContent('Werkbank-Station-Modus aktivieren');
    expect(
      screen.getByTestId('toggle-setting-description-bench-mode-toggle'),
    ).toHaveTextContent(/USB-HID-Scanner/);
  });

  it('toggle is unchecked by default (A9.* default OFF)', () => {
    renderPage();
    const input = screen.getByTestId(
      'toggle-setting-input-bench-mode-toggle',
    ) as HTMLInputElement;
    expect(input.checked).toBe(false);
  });

  it('tapping the toggle persists to localStorage and flips state', async () => {
    const user = userEvent.setup();
    renderPage();
    const input = screen.getByTestId(
      'toggle-setting-input-bench-mode-toggle',
    ) as HTMLInputElement;

    await user.click(input);
    expect(input.checked).toBe(true);
    expect(localStorage.getItem('scan_bench_mode')).toBe('true');

    await user.click(input);
    expect(input.checked).toBe(false);
    expect(localStorage.getItem('scan_bench_mode')).toBe('false');
  });

  it('hydrates from localStorage on mount — survives unmount/remount', async () => {
    localStorage.setItem('scan_bench_mode', 'true');

    const { unmount } = renderPage();
    let input = screen.getByTestId(
      'toggle-setting-input-bench-mode-toggle',
    ) as HTMLInputElement;
    expect(input.checked).toBe(true);

    unmount();

    renderPage();
    input = screen.getByTestId(
      'toggle-setting-input-bench-mode-toggle',
    ) as HTMLInputElement;
    expect(input.checked).toBe(true);
  });
});
