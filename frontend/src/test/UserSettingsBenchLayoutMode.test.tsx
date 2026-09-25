// UserSettingsPage / Werkbank-Modus (layout) toggle tests — W7 followup.
//
// Not to be confused with the Werkbank-Station-Modus (HID scanner) toggle
// covered by UserSettingsBenchMode.test.tsx — this is the layout bench mode
// from lib/benchMode.ts (UI-UX-PLAYBOOK 5.5), also exercised end to end by
// layouts/MainLayout.test.tsx.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { UserSettingsPage } from '../pages/UserSettingsPage';
import { ScannerProvider } from '../contexts/ScannerContext';
import { BENCH_ROOT_CLASS, setBenchMode } from '../lib/benchMode';

vi.mock('../lib/bench-scanner-listener', () => ({
  createBenchScannerListener: () => () => {},
}));

const rootHasBench = () => document.documentElement.classList.contains(BENCH_ROOT_CLASS);

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
  act(() => setBenchMode(false));
  localStorage.clear();
});

describe('UserSettingsPage — Werkbank-Modus (layout) toggle', () => {
  it('renders the Anzeige section with the toggle, off by default', () => {
    renderPage();
    expect(
      screen.getByTestId('toggle-setting-bench-layout-mode-toggle'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('toggle-setting-label-bench-layout-mode-toggle'),
    ).toHaveTextContent('Werkbank-Modus aktivieren');
    const input = screen.getByTestId(
      'toggle-setting-input-bench-layout-mode-toggle',
    ) as HTMLInputElement;
    expect(input.checked).toBe(false);
    expect(rootHasBench()).toBe(false);
  });

  it('tapping the toggle sets :root.bench and persists per device', async () => {
    const user = userEvent.setup();
    renderPage();
    const input = screen.getByTestId(
      'toggle-setting-input-bench-layout-mode-toggle',
    ) as HTMLInputElement;

    await user.click(input);
    expect(input.checked).toBe(true);
    expect(rootHasBench()).toBe(true);

    await user.click(input);
    expect(input.checked).toBe(false);
    expect(rootHasBench()).toBe(false);
  });

  it('is independent from the Werkbank-Station-Modus (HID) toggle', async () => {
    const user = userEvent.setup();
    renderPage();
    const layoutInput = screen.getByTestId(
      'toggle-setting-input-bench-layout-mode-toggle',
    ) as HTMLInputElement;
    const hidInput = screen.getByTestId(
      'toggle-setting-input-bench-mode-toggle',
    ) as HTMLInputElement;

    await user.click(layoutInput);
    expect(layoutInput.checked).toBe(true);
    expect(hidInput.checked).toBe(false);
  });
});
