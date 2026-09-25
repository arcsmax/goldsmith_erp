// PunzierungsCheckModal tests — Slice 11, widened to a soft gate in W2-09
// (DOM-22, DOM-23, DOM-44; decision D-10).
//
// Scope (A11.3/A11.9 + Thomas §3 + DIN 8238):
//   * Two groups rendered with correct legends + divider.
//   * Confirm disabled until at least one Feingehalt mark is selected.
//   * Meisterzeichen alone keeps Confirm disabled.
//   * Payload matches server field_validator allow-list.
//   * German labels verbatim per A11.3.
//   * Esc rejects, Cancel rejects.
//   * W2-09: the widened vocabulary (333/375/900/999/Ag800/Ag999) is
//     selectable and the alloy match is suggested, not pre-checked.
//   * W2-09: "Nicht punziert (Grund)" is an alternate, equally valid path.

import { afterEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { PunzierungsCheckModal } from '../components/qc/PunzierungsCheckModal';
import type {
  PunzierungsCheckModalProps,
  PunzierungsCheckPayload,
} from '../components/qc/PunzierungsCheckModal';

// navigator.vibrate polyfill.
Object.defineProperty(navigator, 'vibrate', {
  value: vi.fn(() => true),
  writable: true,
  configurable: true,
});

afterEach(() => {
  vi.restoreAllMocks();
});

function renderModal(overrides?: Partial<PunzierungsCheckModalProps>): {
  resolve: ReturnType<typeof vi.fn<(value: PunzierungsCheckPayload) => void>>;
  reject: ReturnType<typeof vi.fn<(reason?: unknown) => void>>;
} {
  const resolve = vi.fn<(value: PunzierungsCheckPayload) => void>();
  const reject = vi.fn<(reason?: unknown) => void>();
  render(
    <PunzierungsCheckModal
      orderId={42}
      orderAlloy="750"
      orderTitle="Trauring Mueller"
      {...overrides}
      resolve={resolve}
      reject={reject}
    />,
  );
  return { resolve, reject };
}

describe('PunzierungsCheckModal rendering', () => {
  it('renders the Feingehalt group with required German labels', () => {
    renderModal();
    const group = screen.getByTestId('punz-group-feingehalt');
    expect(group.textContent).toContain('Feingehaltspunze 585');
    expect(group.textContent).toContain('Feingehaltspunze 750');
    expect(group.textContent).toContain('Feingehaltspunze 925');
    expect(group.textContent).toContain('Feingehaltspunze Pt 950');
  });

  it('renders the additional marks group with required German labels', () => {
    renderModal();
    const group = screen.getByTestId('punz-group-other');
    expect(group.textContent).toContain('Meisterzeichen');
    expect(group.textContent).toContain('Herstellerzeichen');
    expect(group.textContent).toContain('Laenderzeichen');
  });

  it('renders German title "Punzierungs-Check"', () => {
    renderModal();
    expect(document.getElementById('punz-title')?.textContent).toBe(
      'Punzierungs-Check',
    );
  });

  it('renders order context subline with orderId + optional title + alloy', () => {
    renderModal();
    const sub = screen.getByTestId('punz-sub').textContent ?? '';
    expect(sub).toContain('ORDER:42');
    expect(sub).toContain('Trauring Mueller');
    expect(sub).toContain('750');
  });

  it('renders Feingehalt fieldset with aria-required', () => {
    renderModal();
    const group = screen.getByTestId('punz-group-feingehalt');
    expect(group.getAttribute('aria-required')).toBe('true');
  });
});

describe('PunzierungsCheckModal validation', () => {
  it('Confirm is disabled initially', () => {
    renderModal();
    const confirm = screen.getByTestId('punz-confirm') as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
  });

  it('Confirm stays disabled when only Meisterzeichen is checked', async () => {
    renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('punz-option-meisterzeichen').querySelector('input')!,
    );
    const confirm = screen.getByTestId('punz-confirm') as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
  });

  it('Confirm becomes enabled once a Feingehalt mark is selected', async () => {
    renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('punz-option-feingehalt_750').querySelector('input')!,
    );
    const confirm = screen.getByTestId('punz-confirm') as HTMLButtonElement;
    expect(confirm.disabled).toBe(false);
  });

  it('inline validation hint shows while no Feingehalt is selected', () => {
    renderModal();
    expect(screen.getByTestId('punz-validation').textContent).toContain(
      'mindestens eine Feingehaltspunze',
    );
  });

  it('inline validation hint disappears once a Feingehalt is selected', async () => {
    renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('punz-option-feingehalt_585').querySelector('input')!,
    );
    expect(screen.queryByTestId('punz-validation')).toBeNull();
  });
});

describe('PunzierungsCheckModal submit flow', () => {
  it('resolve receives correctly ordered marks payload', async () => {
    const { resolve } = renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('punz-option-feingehalt_750').querySelector('input')!,
    );
    await user.click(
      screen.getByTestId('punz-option-meisterzeichen').querySelector('input')!,
    );
    await user.click(screen.getByTestId('punz-confirm'));
    expect(resolve).toHaveBeenCalledWith({
      marks: ['feingehalt_750', 'meisterzeichen'],
    });
  });

  it('resolve receives all Feingehalt marks when all are selected', async () => {
    const { resolve } = renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('punz-option-feingehalt_585').querySelector('input')!,
    );
    await user.click(
      screen.getByTestId('punz-option-feingehalt_750').querySelector('input')!,
    );
    await user.click(
      screen.getByTestId('punz-option-feingehalt_925').querySelector('input')!,
    );
    await user.click(
      screen.getByTestId('punz-option-feingehalt_950_pt').querySelector('input')!,
    );
    await user.click(screen.getByTestId('punz-confirm'));
    expect(resolve).toHaveBeenCalledWith({
      marks: [
        'feingehalt_585',
        'feingehalt_750',
        'feingehalt_925',
        'feingehalt_950_pt',
      ],
    });
  });

  it('fires navigator.vibrate(50) on Confirm per Jason §7.3', async () => {
    (navigator.vibrate as unknown as ReturnType<typeof vi.fn>).mockClear?.();
    renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('punz-option-feingehalt_750').querySelector('input')!,
    );
    await user.click(screen.getByTestId('punz-confirm'));
    expect(navigator.vibrate).toHaveBeenCalledWith(50);
  });

  it('reject called on Cancel', async () => {
    const { reject } = renderModal();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('punz-cancel'));
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

  it('reject called on close (X) button', async () => {
    const { reject } = renderModal();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('punz-close'));
    expect(reject).toHaveBeenCalled();
  });
});

// ─── W2-09: widened vocabulary (DOM-22) ────────────────────────────────────

describe('PunzierungsCheckModal widened vocabulary (DOM-22)', () => {
  it('offers Feingehalt options the original vocabulary was missing', () => {
    renderModal();
    const group = screen.getByTestId('punz-group-feingehalt');
    expect(group.textContent).toContain('Feingehaltspunze 333');
    expect(group.textContent).toContain('Feingehaltspunze 375');
    expect(group.textContent).toContain('Feingehaltspunze 900');
    expect(group.textContent).toContain('Feingehaltspunze 999');
    expect(group.textContent).toContain('Feingehaltspunze Ag 800');
  });

  it('a 333-alloy order can select feingehalt_333 and submit', async () => {
    const { resolve } = renderModal({ orderAlloy: '333' });
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('punz-option-feingehalt_333').querySelector('input')!,
    );
    await user.click(screen.getByTestId('punz-confirm'));
    expect(resolve).toHaveBeenCalledWith({ marks: ['feingehalt_333'] });
  });

  it('flags the alloy-matching option as suggested without pre-checking it', () => {
    renderModal({ orderAlloy: '333' });
    const option = screen.getByTestId('punz-option-feingehalt_333');
    expect(option.textContent).toContain('passend zur Legierung');
    // Not pre-checked — the goldsmith must confirm what they physically see.
    const checkbox = option.querySelector('input') as HTMLInputElement;
    expect(checkbox.checked).toBe(false);
    expect((screen.getByTestId('punz-confirm') as HTMLButtonElement).disabled).toBe(true);
  });

  it('does not flag an unrelated option as suggested', () => {
    renderModal({ orderAlloy: '333' });
    const other = screen.getByTestId('punz-option-feingehalt_750');
    expect(other.textContent).not.toContain('passend zur Legierung');
  });

  it('suggests the matching option for a capitalised silver/platinum alloy', () => {
    renderModal({ orderAlloy: 'Ag925' });
    expect(screen.getByTestId('punz-option-feingehalt_925').textContent).toContain(
      'passend zur Legierung',
    );
  });

  it('suggests nothing for an unknown alloy', () => {
    renderModal({ orderAlloy: '935' });
    for (const id of [
      'feingehalt_333',
      'feingehalt_585',
      'feingehalt_750',
      'feingehalt_925',
      'feingehalt_950_pt',
    ]) {
      expect(screen.getByTestId(`punz-option-${id}`).textContent).not.toContain(
        'passend zur Legierung',
      );
    }
  });
});

// ─── W2-09: "Nicht punziert (Grund)" soft-gate path (D-10) ────────────────

describe('PunzierungsCheckModal "Nicht punziert" path (D-10)', () => {
  it('renders the toggle and no reason field initially', () => {
    renderModal();
    expect(screen.getByTestId('punz-nicht-punziert-toggle').textContent).toContain(
      'Nicht punziert (Grund angeben)',
    );
    expect(screen.queryByTestId('punz-nicht-punziert-reason')).toBeNull();
  });

  it('Confirm stays disabled with the toggle checked but no reason text', async () => {
    renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('punz-nicht-punziert-toggle').querySelector('input')!,
    );
    expect((screen.getByTestId('punz-confirm') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId('punz-validation').textContent).toContain(
      'Bitte einen Grund angeben.',
    );
  });

  it('Confirm becomes enabled once a reason is typed', async () => {
    renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('punz-nicht-punziert-toggle').querySelector('input')!,
    );
    await user.type(screen.getByTestId('punz-nicht-punziert-reason'), 'Stein zu klein');
    expect((screen.getByTestId('punz-confirm') as HTMLButtonElement).disabled).toBe(false);
  });

  it('resolve receives the "nicht punziert: <Grund>" mark matching the backend prefix', async () => {
    const { resolve } = renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('punz-nicht-punziert-toggle').querySelector('input')!,
    );
    await user.type(screen.getByTestId('punz-nicht-punziert-reason'), 'Stein zu klein');
    await user.click(screen.getByTestId('punz-confirm'));
    expect(resolve).toHaveBeenCalledWith({
      marks: ['nicht punziert: Stein zu klein'],
    });
  });

  it('additional marks may still be recorded alongside a documented reason', async () => {
    const { resolve } = renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('punz-nicht-punziert-toggle').querySelector('input')!,
    );
    await user.type(screen.getByTestId('punz-nicht-punziert-reason'), 'Kunde wollte keine Punze');
    await user.click(
      screen.getByTestId('punz-option-meisterzeichen').querySelector('input')!,
    );
    await user.click(screen.getByTestId('punz-confirm'));
    expect(resolve).toHaveBeenCalledWith({
      marks: ['nicht punziert: Kunde wollte keine Punze', 'meisterzeichen'],
    });
  });

  it('checking the toggle disables and clears any selected Feingehalt mark', async () => {
    renderModal();
    const user = userEvent.setup();
    await user.click(
      screen.getByTestId('punz-option-feingehalt_750').querySelector('input')!,
    );
    await user.click(
      screen.getByTestId('punz-nicht-punziert-toggle').querySelector('input')!,
    );
    const feingehaltCheckbox = screen
      .getByTestId('punz-option-feingehalt_750')
      .querySelector('input') as HTMLInputElement;
    expect(feingehaltCheckbox.checked).toBe(false);
    expect(feingehaltCheckbox.disabled).toBe(true);
  });
});
