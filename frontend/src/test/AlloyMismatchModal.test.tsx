// AlloyMismatchModal tests — Slice 11.
//
// Scope (A11.1/A11.2 + Anna B3 + Jason §3):
//   * Amber banner rendered with role="alert".
//   * Abbrechen primary + autofocus on mount.
//   * Override disabled until BOTH category + reason (3–200) valid.
//   * PII-deny (B3): @ sign OR alphabetic token > 15 chars blocks submit.
//   * onConfirm called with the correct payload shape.
//   * Cancel triggers reject; Esc triggers reject.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import {
  AlloyMismatchModal,
  reasonHasPiiSignal,
} from '../components/scanner/AlloyMismatchModal';
import type {
  AlloyMismatchModalProps,
  AlloyOverridePayload,
} from '../components/scanner/AlloyMismatchModal';

// navigator.vibrate polyfill.
Object.defineProperty(navigator, 'vibrate', {
  value: vi.fn(() => true),
  writable: true,
  configurable: true,
});

beforeEach(() => {
  (navigator.vibrate as unknown as ReturnType<typeof vi.fn>).mockClear?.();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function renderModal(overrides?: Partial<AlloyMismatchModalProps>): {
  resolve: ReturnType<typeof vi.fn<[AlloyOverridePayload], void>>;
  reject: ReturnType<typeof vi.fn<[unknown?], void>>;
} {
  const resolve = vi.fn<[AlloyOverridePayload], void>();
  const reject = vi.fn<[unknown?], void>();
  render(
    <AlloyMismatchModal
      orderAlloy="750"
      metalAlloy="585"
      weightGrams={12.5}
      orderTitle="Trauring Mueller"
      {...overrides}
      resolve={resolve}
      reject={reject}
    />,
  );
  return { resolve, reject };
}

describe('AlloyMismatchModal rendering', () => {
  it('renders amber banner with role=alert and German title', () => {
    renderModal();
    const banner = screen.getByTestId('alloy-banner');
    expect(banner.getAttribute('role')).toBe('alert');
    expect(banner.textContent).toContain('Legierungsabweichung');
  });

  it('shows orderAlloy → metalAlloy + weight', () => {
    renderModal();
    expect(screen.getByTestId('alloy-order-alloy').textContent).toBe('750');
    expect(screen.getByTestId('alloy-metal-alloy').textContent).toBe('585');
    expect(screen.getByTestId('alloy-weight').textContent).toContain('12.50');
  });

  it('renders all four category radios with German labels', () => {
    renderModal();
    expect(
      screen.getByTestId('alloy-category-charge_abweichung').textContent,
    ).toContain('Charge-Abweichung');
    expect(
      screen.getByTestId('alloy-category-kleinteil').textContent,
    ).toContain('Kleinteil');
    expect(
      screen.getByTestId('alloy-category-notfall').textContent,
    ).toContain('Notfall');
    expect(
      screen.getByTestId('alloy-category-sonstiges').textContent,
    ).toContain('Sonstiges');
  });

  it('Abbrechen is primary (btn-primary) and Override is warning (btn-warning)', () => {
    renderModal();
    const cancel = screen.getByTestId('alloy-cancel');
    const override = screen.getByTestId('alloy-override');
    expect(cancel.className).toContain('btn-primary');
    expect(override.className).toContain('btn-warning');
  });

  it('focuses Abbrechen on mount (A11.1)', async () => {
    renderModal();
    await new Promise<void>((r) => requestAnimationFrame(() => r()));
    expect(document.activeElement).toBe(screen.getByTestId('alloy-cancel'));
  });
});

describe('AlloyMismatchModal validation', () => {
  it('Override is disabled initially', () => {
    renderModal();
    const override = screen.getByTestId('alloy-override') as HTMLButtonElement;
    expect(override.disabled).toBe(true);
  });

  it('Override stays disabled when only category is set', async () => {
    renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('alloy-category-charge_abweichung').querySelector('input')!,
    );
    const override = screen.getByTestId('alloy-override') as HTMLButtonElement;
    expect(override.disabled).toBe(true);
  });

  it('Override stays disabled when only reason is set', async () => {
    renderModal();
    const user = userEvent.setup();
    const textarea = screen.getByTestId('alloy-reason-textarea') as HTMLTextAreaElement;
    await user.type(textarea, 'Legierungstausch');
    const override = screen.getByTestId('alloy-override') as HTMLButtonElement;
    expect(override.disabled).toBe(true);
  });

  it('Override becomes enabled when BOTH category + reason (3+ chars) are valid', async () => {
    renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('alloy-category-kleinteil').querySelector('input')!,
    );
    await user.type(
      screen.getByTestId('alloy-reason-textarea'),
      'Restmaterial',
    );
    const override = screen.getByTestId('alloy-override') as HTMLButtonElement;
    expect(override.disabled).toBe(false);
  });

  it('reason with only 2 chars keeps Override disabled', async () => {
    renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('alloy-category-kleinteil').querySelector('input')!,
    );
    await user.type(screen.getByTestId('alloy-reason-textarea'), 'ab');
    const override = screen.getByTestId('alloy-override') as HTMLButtonElement;
    expect(override.disabled).toBe(true);
  });

  it('character counter updates and caps at 200', async () => {
    renderModal();
    const user = userEvent.setup();
    const textarea = screen.getByTestId(
      'alloy-reason-textarea',
    ) as HTMLTextAreaElement;
    await user.type(textarea, 'Restmaterial');
    expect(screen.getByTestId('alloy-reason-counter').textContent).toContain(
      '12/200',
    );
  });

  it('shows explicit PII warning when @ sign present + disables Override', async () => {
    renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('alloy-category-sonstiges').querySelector('input')!,
    );
    await user.type(
      screen.getByTestId('alloy-reason-textarea'),
      'Kontakt via x@y.de',
    );
    expect(screen.getByTestId('alloy-pii-warn')).toBeInTheDocument();
    const override = screen.getByTestId('alloy-override') as HTMLButtonElement;
    expect(override.disabled).toBe(true);
  });

  it('shows PII warning when a single alphabetic token exceeds 15 chars', async () => {
    renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('alloy-category-sonstiges').querySelector('input')!,
    );
    await user.type(
      screen.getByTestId('alloy-reason-textarea'),
      'Überlangeeingabetokenname',
    );
    expect(screen.getByTestId('alloy-pii-warn')).toBeInTheDocument();
  });
});

describe('AlloyMismatchModal PII heuristic (reasonHasPiiSignal)', () => {
  it('blocks @ sign', () => {
    expect(reasonHasPiiSignal('name@example.com')).toBe(true);
  });

  it('blocks alphabetic token > 15 chars', () => {
    expect(reasonHasPiiSignal('abcdefghijklmnopq')).toBe(true);
  });

  it('allows short multi-token content', () => {
    expect(reasonHasPiiSignal('Falsche Legierung')).toBe(false);
    expect(reasonHasPiiSignal('750 statt 585 gewaehlt')).toBe(false);
  });

  it('allows numeric long tokens (chargennummern are safe)', () => {
    expect(reasonHasPiiSignal('Charge 12345678901234567')).toBe(false);
  });
});

describe('AlloyMismatchModal submit flow', () => {
  it('resolve receives the correct payload on Override tap', async () => {
    const { resolve } = renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('alloy-category-notfall').querySelector('input')!,
    );
    await user.type(
      screen.getByTestId('alloy-reason-textarea'),
      'Kunde wartet',
    );
    await user.click(screen.getByTestId('alloy-override'));
    expect(resolve).toHaveBeenCalledWith({
      override_reason_category: 'notfall',
      override_reason: 'Kunde wartet',
    });
  });

  it('fires navigator.vibrate(200) on Override confirm', async () => {
    renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('alloy-category-notfall').querySelector('input')!,
    );
    await user.type(
      screen.getByTestId('alloy-reason-textarea'),
      'Kunde wartet',
    );
    await user.click(screen.getByTestId('alloy-override'));
    expect(navigator.vibrate).toHaveBeenCalledWith(200);
  });

  it('reject called on Cancel', async () => {
    const { reject } = renderModal();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('alloy-cancel'));
    expect(reject).toHaveBeenCalled();
  });

  it('reject called on Esc', () => {
    const { reject } = renderModal();
    act(() => {
      document.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Escape' }),
      );
    });
    expect(reject).toHaveBeenCalled();
  });

  it('trims surrounding whitespace from the submitted reason', async () => {
    const { resolve } = renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('alloy-category-kleinteil').querySelector('input')!,
    );
    await user.type(
      screen.getByTestId('alloy-reason-textarea'),
      '  Restmaterial  ',
    );
    await user.click(screen.getByTestId('alloy-override'));
    expect(resolve).toHaveBeenCalledWith({
      override_reason_category: 'kleinteil',
      override_reason: 'Restmaterial',
    });
  });
});
