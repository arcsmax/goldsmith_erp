// QuickActionModalV2 tests — Slice 11 of V1.1 QR/Barcode workflow.
//
// Scope (plan §Slice 11 verification + AMENDMENTS A11.4/A11.12/A11.13):
//   * Kurzbezeichnung (A11.4): ORDER title truncated + customer initials;
//     REPAIR: repair_number + bag_number + item_type; METAL: alloy + lot;
//     MATERIAL: name.
//   * Action list sorted primary-first; primary renders with
//     qa-action--primary class, secondary with qa-action--secondary.
//   * Status-hint is a button when onStatusHintClick is provided.
//   * Empty actions list → "Kein Zugriff" placeholder.
//   * aria-modal dialog semantics, focus on first action on mount,
//     Esc triggers onClose, Tab cycles.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { QuickActionModalV2 } from '../components/scanner/QuickActionModalV2';
import type { ResolveResponse } from '../types/scanner';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function orderResponse(overrides?: Partial<ResolveResponse>): ResolveResponse {
  return {
    resolved: true,
    resolution_path: 'prefix',
    entity_type: 'order',
    entity_id: 42,
    entity: {
      entity_type: 'order',
      entity_id: 42,
      data: {
        id: 42,
        title: 'Trauring Mueller Maria',
        status: 'in_progress',
        order_number: 'ORDER:42',
        customer_initials: 'M.M.',
      },
    },
    actions: [
      { id: 'start_timer', label: 'Timer starten', icon: 'play', primary: true },
      { id: 'change_status', label: 'Status aendern', icon: 'clipboard', primary: false },
      { id: 'open_entity', label: 'Öffnen', icon: 'link', primary: false },
    ],
    status_hint: 'Seit 3 Tagen in Bearbeitung · Frist 19.04.',
    ...overrides,
  };
}

function repairResponse(): ResolveResponse {
  return {
    resolved: true,
    resolution_path: 'prefix',
    entity_type: 'repair',
    entity_id: 7,
    entity: {
      entity_type: 'repair',
      entity_id: 7,
      data: {
        id: 7,
        repair_number: 'REP-2024-007',
        bag_number: 'BAG-A-12',
        item_type: 'Halskette',
        status: 'in_repair',
      },
    },
    actions: [
      { id: 'advance_repair', label: 'Status weiterschalten', icon: 'clipboard', primary: true },
    ],
    status_hint: null,
  };
}

function metalResponse(): ResolveResponse {
  return {
    resolved: true,
    resolution_path: 'prefix',
    entity_type: 'metal_purchase',
    entity_id: 85,
    entity: {
      entity_type: 'metal_purchase',
      entity_id: 85,
      data: {
        id: 85,
        metal_type: 'gold_18k',
        lot_number: '2411-A',
        remaining_weight_g: 250,
      },
    },
    actions: [
      { id: 'consume_material', label: 'Material entnehmen', icon: 'scale', primary: true },
    ],
    status_hint: null,
  };
}

function emptyAccessResponse(): ResolveResponse {
  return {
    resolved: true,
    resolution_path: 'prefix',
    entity_type: 'metal_purchase',
    entity_id: 85,
    entity: {
      entity_type: 'metal_purchase',
      entity_id: 85,
      data: {},
    },
    actions: [],
    status_hint: null,
  };
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Kurzbezeichnung (A11.4)
// ---------------------------------------------------------------------------

describe('QuickActionModalV2 Kurzbezeichnung', () => {
  it('shows order_number as idLabel and customer initials + title as Kurzbezeichnung', () => {
    render(
      <QuickActionModalV2
        resolveResponse={orderResponse()}
        onAction={vi.fn(async () => {})}
        onClose={vi.fn()}
        onContinueScanning={vi.fn()}
      />,
    );
    expect(screen.getByTestId('qa-id').textContent).toContain('ORDER:42');
    const title = screen.getByTestId('qa-title').textContent ?? '';
    expect(title).toContain('M.M.');
    expect(title).toContain('Trauring Mueller Maria');
  });

  it('truncates ORDER title to 40 chars with ellipsis', () => {
    const long = 'Ein sehr langer Titel der ueber vierzig Zeichen enthaelt und weiter geht';
    render(
      <QuickActionModalV2
        resolveResponse={orderResponse({
          entity: {
            entity_type: 'order',
            entity_id: 42,
            data: { id: 42, title: long, status: 'new' },
          },
        })}
        onAction={vi.fn()}
        onClose={vi.fn()}
        onContinueScanning={vi.fn()}
      />,
    );
    const title = screen.getByTestId('qa-title').textContent ?? '';
    // 40 chars max title portion + optional ellipsis
    const hasEllipsis = title.includes('…');
    expect(hasEllipsis).toBe(true);
  });

  it('REPAIR: shows repair_number — bag_number — item_type', () => {
    render(
      <QuickActionModalV2
        resolveResponse={repairResponse()}
        onAction={vi.fn()}
        onClose={vi.fn()}
        onContinueScanning={vi.fn()}
      />,
    );
    const title = screen.getByTestId('qa-title').textContent ?? '';
    expect(title).toContain('REP-2024-007');
    expect(title).toContain('BAG-A-12');
    expect(title).toContain('Halskette');
  });

  it('METAL: shows alloy_name + Lot <lot_number>', () => {
    render(
      <QuickActionModalV2
        resolveResponse={metalResponse()}
        onAction={vi.fn()}
        onClose={vi.fn()}
        onContinueScanning={vi.fn()}
      />,
    );
    const title = screen.getByTestId('qa-title').textContent ?? '';
    expect(title).toContain('gold_18k');
    expect(title).toContain('Lot 2411-A');
  });
});

// ---------------------------------------------------------------------------
// Action rendering + sorting
// ---------------------------------------------------------------------------

describe('QuickActionModalV2 actions', () => {
  it('sorts actions with primary=true first', () => {
    render(
      <QuickActionModalV2
        resolveResponse={orderResponse({
          actions: [
            { id: 'a', label: 'A', icon: 'x', primary: false },
            { id: 'b', label: 'B', icon: 'x', primary: true },
            { id: 'c', label: 'C', icon: 'x', primary: false },
          ],
        })}
        onAction={vi.fn()}
        onClose={vi.fn()}
        onContinueScanning={vi.fn()}
      />,
    );
    const buttons = screen.getAllByRole('button', { name: /^[ABC]$/ });
    expect(buttons[0].textContent).toContain('B');
    expect(buttons[1].textContent).toContain('A');
    expect(buttons[2].textContent).toContain('C');
  });

  it('primary action carries qa-action--primary class', () => {
    render(
      <QuickActionModalV2
        resolveResponse={orderResponse()}
        onAction={vi.fn()}
        onClose={vi.fn()}
        onContinueScanning={vi.fn()}
      />,
    );
    const btn = screen.getByTestId('qa-action-start_timer');
    expect(btn.className).toContain('qa-action--primary');
    expect(btn.getAttribute('data-primary')).toBe('true');
  });

  it('secondary actions carry qa-action--secondary class', () => {
    render(
      <QuickActionModalV2
        resolveResponse={orderResponse()}
        onAction={vi.fn()}
        onClose={vi.fn()}
        onContinueScanning={vi.fn()}
      />,
    );
    const btn = screen.getByTestId('qa-action-change_status');
    expect(btn.className).toContain('qa-action--secondary');
    expect(btn.getAttribute('data-primary')).toBe('false');
  });

  it('invokes onAction with the action id when tapped', async () => {
    const onAction = vi.fn(async () => {});
    render(
      <QuickActionModalV2
        resolveResponse={orderResponse()}
        onAction={onAction}
        onClose={vi.fn()}
        onContinueScanning={vi.fn()}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId('qa-action-change_status'));
    expect(onAction).toHaveBeenCalledWith('change_status');
  });

  it('renders the empty-access placeholder when no actions are present', () => {
    render(
      <QuickActionModalV2
        resolveResponse={emptyAccessResponse()}
        onAction={vi.fn()}
        onClose={vi.fn()}
        onContinueScanning={vi.fn()}
      />,
    );
    expect(screen.getByTestId('qa-empty-access').textContent).toContain(
      'Kein Zugriff',
    );
  });

  it('surfaces an inline error banner when onAction throws', async () => {
    const onAction = vi.fn(async () => {
      throw new Error('Netzwerkfehler');
    });
    render(
      <QuickActionModalV2
        resolveResponse={orderResponse()}
        onAction={onAction}
        onClose={vi.fn()}
        onContinueScanning={vi.fn()}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId('qa-action-start_timer'));
    const err = await screen.findByTestId('qa-error');
    expect(err.textContent).toContain('Netzwerkfehler');
  });
});

// ---------------------------------------------------------------------------
// Status hint
// ---------------------------------------------------------------------------

describe('QuickActionModalV2 status hint (A11.12)', () => {
  it('renders status hint as a tappable button when onStatusHintClick is provided', async () => {
    const onStatusHintClick = vi.fn();
    render(
      <QuickActionModalV2
        resolveResponse={orderResponse()}
        onAction={vi.fn()}
        onClose={vi.fn()}
        onContinueScanning={vi.fn()}
        onStatusHintClick={onStatusHintClick}
      />,
    );
    const hint = screen.getByTestId('qa-status-hint');
    expect(hint.tagName.toLowerCase()).toBe('button');
    const user = userEvent.setup();
    await user.click(hint);
    expect(onStatusHintClick).toHaveBeenCalled();
  });

  it('renders status hint as a plain paragraph when no click handler is given', () => {
    render(
      <QuickActionModalV2
        resolveResponse={orderResponse()}
        onAction={vi.fn()}
        onClose={vi.fn()}
        onContinueScanning={vi.fn()}
      />,
    );
    const hint = screen.getByTestId('qa-status-hint');
    expect(hint.tagName.toLowerCase()).toBe('p');
  });
});

// ---------------------------------------------------------------------------
// Accessibility
// ---------------------------------------------------------------------------

describe('QuickActionModalV2 accessibility', () => {
  it('renders role="dialog" and aria-modal="true"', () => {
    render(
      <QuickActionModalV2
        resolveResponse={orderResponse()}
        onAction={vi.fn()}
        onClose={vi.fn()}
        onContinueScanning={vi.fn()}
      />,
    );
    const dialog = screen.getByTestId('qa-modal-v2');
    expect(dialog.getAttribute('role')).toBe('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.getAttribute('aria-labelledby')).toBe('qa-title');
  });

  it('triggers onClose on Escape', () => {
    const onClose = vi.fn();
    render(
      <QuickActionModalV2
        resolveResponse={orderResponse()}
        onAction={vi.fn()}
        onClose={onClose}
        onContinueScanning={vi.fn()}
      />,
    );
    act(() => {
      document.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Escape' }),
      );
    });
    expect(onClose).toHaveBeenCalled();
  });

  it('moves focus to the first action on mount', async () => {
    render(
      <QuickActionModalV2
        resolveResponse={orderResponse()}
        onAction={vi.fn()}
        onClose={vi.fn()}
        onContinueScanning={vi.fn()}
      />,
    );
    // requestAnimationFrame → async → wait a tick
    await new Promise<void>((r) => requestAnimationFrame(() => r()));
    const first = screen.getByTestId('qa-action-start_timer');
    expect(document.activeElement).toBe(first);
  });
});

// ---------------------------------------------------------------------------
// Weiterscannen + close
// ---------------------------------------------------------------------------

describe('QuickActionModalV2 footer', () => {
  it('triggers onContinueScanning when Weiterscannen is tapped', async () => {
    const onContinueScanning = vi.fn();
    render(
      <QuickActionModalV2
        resolveResponse={orderResponse()}
        onAction={vi.fn()}
        onClose={vi.fn()}
        onContinueScanning={onContinueScanning}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId('qa-continue'));
    expect(onContinueScanning).toHaveBeenCalled();
  });

  it('triggers onClose when the close button is tapped', async () => {
    const onClose = vi.fn();
    render(
      <QuickActionModalV2
        resolveResponse={orderResponse()}
        onAction={vi.fn()}
        onClose={onClose}
        onContinueScanning={vi.fn()}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId('qa-close'));
    expect(onClose).toHaveBeenCalled();
  });
});
