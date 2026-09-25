// Order status vocabulary for the order page (W2-08; DOM-17, DOM-18).
//
// Labels follow UI-UX-PLAYBOOK 3.2 and the backend's single label source
// (services/order_workflow.py ORDER_STATUS_LABELS). This module is the
// stopgap until src/design/status.ts exists (Wave 4); when it lands, move
// ORDER_STATUS_LABELS there and re-export it from here.
//
// ALLOWED_TRANSITIONS mirrors order_workflow.ALLOWED_TRANSITIONS so the
// "Weiter" button only offers moves the backend accepts. The backend stays
// the authority: a 409 carries its German message, which the page shows.
import type { OrderStatus } from '../../types';

export const ORDER_STATUS_LABELS: Readonly<Record<OrderStatus, string>> = {
  draft: 'Entwurf',
  new: 'Neu',
  confirmed: 'Bestätigt',
  in_progress: 'In Bearbeitung',
  waiting_for_fitting: 'Wartet auf Anprobe',
  fitting_done: 'Anprobe abgeschlossen',
  ready_for_setting: 'Bereit zum Fassen',
  quality_check: 'Qualitätskontrolle',
  completed: 'Fertiggestellt',
  delivered: 'Ausgeliefert',
  on_hold: 'Pausiert',
  cancelled: 'Storniert',
};

/** Enum declaration order of the backend (OrderStatusEnum). */
const STATUS_ORDER: readonly OrderStatus[] = [
  'new',
  'draft',
  'confirmed',
  'in_progress',
  'waiting_for_fitting',
  'fitting_done',
  'ready_for_setting',
  'quality_check',
  'completed',
  'delivered',
  'on_hold',
  'cancelled',
];

const PRODUCTION: readonly OrderStatus[] = [
  'in_progress',
  'waiting_for_fitting',
  'fitting_done',
  'ready_for_setting',
  'quality_check',
];

const LEAVE_PRODUCTION: readonly OrderStatus[] = ['completed', 'on_hold', 'cancelled'];

function productionTargets(stage: OrderStatus): OrderStatus[] {
  return [...PRODUCTION.filter((s) => s !== stage), ...LEAVE_PRODUCTION];
}

export const ALLOWED_TRANSITIONS: Readonly<Record<OrderStatus, readonly OrderStatus[]>> = {
  draft: ['confirmed', 'cancelled'],
  new: ['draft', 'confirmed', 'on_hold', 'cancelled', ...PRODUCTION],
  confirmed: ['draft', 'in_progress', 'waiting_for_fitting', 'on_hold', 'cancelled'],
  in_progress: productionTargets('in_progress'),
  waiting_for_fitting: productionTargets('waiting_for_fitting'),
  fitting_done: productionTargets('fitting_done'),
  ready_for_setting: productionTargets('ready_for_setting'),
  quality_check: productionTargets('quality_check'),
  on_hold: ['confirmed', 'cancelled', ...PRODUCTION],
  completed: ['delivered', 'quality_check', 'in_progress'],
  delivered: [],
  cancelled: ['draft'],
};

/**
 * The one obvious next step per status (the big "Weiter" button). null
 * means there is no forward step: delivered is final, and reopening a
 * cancelled order is a deliberate menu choice, not "Weiter".
 */
export const PRIMARY_NEXT_STATUS: Readonly<Record<OrderStatus, OrderStatus | null>> = {
  draft: 'confirmed',
  new: 'confirmed',
  confirmed: 'in_progress',
  in_progress: 'quality_check',
  waiting_for_fitting: 'fitting_done',
  fitting_done: 'in_progress',
  ready_for_setting: 'quality_check',
  quality_check: 'completed',
  completed: 'delivered',
  on_hold: 'in_progress',
  delivered: null,
  cancelled: null,
};

/** Targets that need a reason (and, for on_hold, an optional resume date). */
export const REASON_REQUIRED: readonly OrderStatus[] = ['on_hold', 'cancelled'];

export function statusLabel(status: string): string {
  return ORDER_STATUS_LABELS[status as OrderStatus] ?? status;
}

export function isKnownStatus(status: string): status is OrderStatus {
  return Object.prototype.hasOwnProperty.call(ORDER_STATUS_LABELS, status);
}

export function allowedNextStatuses(current: string): OrderStatus[] {
  if (!isKnownStatus(current)) return [];
  const allowed = ALLOWED_TRANSITIONS[current];
  return STATUS_ORDER.filter((s) => allowed.includes(s));
}

export function primaryNextStatus(current: string): OrderStatus | null {
  return isKnownStatus(current) ? PRIMARY_NEXT_STATUS[current] : null;
}

/** Every allowed target except the primary one, cancel last (destructive). */
export function secondaryStatuses(current: string): OrderStatus[] {
  const primary = primaryNextStatus(current);
  const rest = allowedNextStatuses(current).filter((s) => s !== primary);
  return [...rest.filter((s) => s !== 'cancelled'), ...rest.filter((s) => s === 'cancelled')];
}

export function needsReason(status: OrderStatus): boolean {
  return REASON_REQUIRED.includes(status);
}

/**
 * Mirrors Permission.ORDER_EDIT (ADMIN + GOLDSMITH). A VIEWER never sees
 * the status controls; the backend would 403 them anyway.
 */
export function canChangeOrderStatus(role?: string | null): boolean {
  const normalized = (role ?? '').toUpperCase();
  return normalized === 'ADMIN' || normalized === 'GOLDSMITH';
}

const FALLBACK_STATUS_ERROR = 'Status konnte nicht geändert werden. Bitte erneut versuchen.';

interface ErrorLike {
  response?: { data?: { detail?: unknown } };
}

/**
 * German message for a failed PATCH /orders/{id}/status. The backend sends
 * `detail.message` for 409/422 transition errors, a plain string for older
 * errors, and a list for Pydantic validation errors.
 */
export function statusChangeErrorMessage(err: unknown): string {
  const detail = (err as ErrorLike | null)?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === 'string' && message.trim()) return message;
  }
  return FALLBACK_STATUS_ERROR;
}
