// Shared display helpers for the repair screens (W4-03). Status labels come
// from src/design/status.ts; this file holds only the piece types and dates.
import { MISSING_VALUE } from '../../lib/format';
import type { RepairItemType } from '../../types';
import { ITEM_TYPE_OPTIONS } from './intakeOptions';

export const ITEM_TYPE_LABELS: Readonly<Record<RepairItemType, string>> = Object.fromEntries(
  ITEM_TYPE_OPTIONS.map((option) => [option.value, option.label]),
) as Record<RepairItemType, string>;

export function itemTypeLabel(type: string): string {
  return ITEM_TYPE_LABELS[type as RepairItemType] ?? type;
}

const DATE = new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
const DATE_TIME = new Intl.DateTimeFormat('de-DE', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

function parse(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatRepairDate(value: string | null | undefined): string {
  const date = parse(value);
  return date ? DATE.format(date) : MISSING_VALUE;
}

export function formatRepairDateTime(value: string | null | undefined): string {
  const date = parse(value);
  return date ? DATE_TIME.format(date) : MISSING_VALUE;
}

export function customerName(
  customer: { first_name: string; last_name: string } | null | undefined,
): string | null {
  return customer ? `${customer.first_name} ${customer.last_name}` : null;
}
