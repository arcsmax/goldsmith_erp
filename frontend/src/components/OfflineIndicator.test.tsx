// FE-09 — the offline banner used to promise a background sync that does
// not exist ("Daten werden synchronisiert, sobald die Verbindung
// wiederhergestellt ist"). There is no offline mutation queue anywhere in
// the app (no Workbox BackgroundSync, all /api/ mutations are NetworkOnly —
// see frontend/src/pwa/cachingRules.ts), so a goldsmith who stops a timer or
// saves a note offline was told their work would sync later when it was
// actually lost. The copy must say so honestly.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { OfflineIndicator } from './OfflineIndicator';

describe('OfflineIndicator', () => {
  let originalOnLine: PropertyDescriptor | undefined;

  beforeEach(() => {
    originalOnLine = Object.getOwnPropertyDescriptor(navigator, 'onLine');
  });

  afterEach(() => {
    if (originalOnLine) {
      Object.defineProperty(navigator, 'onLine', originalOnLine);
    }
  });

  const setOnline = (online: boolean) => {
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: online,
    });
  };

  it('shows an honest offline message with no promise of sync (FE-09)', () => {
    setOnline(false);
    render(<OfflineIndicator />);

    expect(
      screen.getByText('Offline: Änderungen werden nicht gespeichert'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/synchronisiert/i)).not.toBeInTheDocument();
  });

  it('shows nothing while online', () => {
    setOnline(true);
    render(<OfflineIndicator />);

    expect(
      screen.queryByText('Offline: Änderungen werden nicht gespeichert'),
    ).not.toBeInTheDocument();
  });

  it('switches to the offline message when the browser goes offline', () => {
    setOnline(true);
    render(<OfflineIndicator />);

    act(() => {
      window.dispatchEvent(new Event('offline'));
    });

    expect(
      screen.getByText('Offline: Änderungen werden nicht gespeichert'),
    ).toBeInTheDocument();
  });
});
