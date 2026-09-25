// Formatting, options and status rules shared by the invoice components (W4-03).
import type { Invoice, InvoiceListItem, InvoiceStatus, OrderType } from '../../types';

const DAY_MS = 1000 * 60 * 60 * 24;
/** An open invoice due within this many days is flagged as "bald fällig". */
const DUE_WARNING_DAYS = 7;
export const DEFAULT_PAYMENT_TERM_DAYS = 14;

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('de-DE');
}

/** Local calendar date as YYYY-MM-DD (the value format of <input type="date">). */
export function isoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

export function todayIso(): string {
  return isoDate(new Date());
}

export function inDaysIso(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return isoDate(date);
}

export type DueTone = 'overdue' | 'soon' | 'ok';

export function dueTone(dueIso: string, status: InvoiceStatus, now = Date.now()): DueTone {
  if (status === 'paid' || status === 'cancelled') return 'ok';
  const daysLeft = Math.ceil((new Date(dueIso).getTime() - now) / DAY_MS);
  if (daysLeft < 0) return 'overdue';
  if (daysLeft <= DUE_WARNING_DAYS) return 'soon';
  return 'ok';
}

/** Text next to the date, so the warning is not carried by colour alone. */
export const DUE_HINT: Record<DueTone, string | null> = {
  overdue: 'überfällig',
  soon: 'bald fällig',
  ok: null,
};

/** Values are what the backend stores today; labels are the German UI terms. */
export const PAYMENT_METHOD_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'Ueberweisung', label: 'Überweisung' },
  { value: 'Bar', label: 'Barzahlung' },
  { value: 'Karte', label: 'Kartenzahlung' },
];

export const TAX_RATE_OPTIONS = [
  { value: '19', label: '19 % (Standard)' },
  { value: '7', label: '7 % (ermäßigt)' },
  { value: '0', label: '0 % (steuerfrei)' },
] as const;

/**
 * Order statuses the backend accepts for a new invoice. Mirrors the guard in
 * `InvoiceService.create_invoice_from_order` (COMPLETED, DELIVERED; else 422),
 * so the picker never offers an order that would fail.
 */
export const INVOICEABLE_ORDER_STATUSES: ReadonlyArray<OrderType['status']> = ['completed', 'delivered'];

type InvoiceLike = Pick<Invoice, 'status'> & Partial<Pick<Invoice, 'cancels_invoice_id'>>;

export function canMarkPaid(invoice: Pick<InvoiceListItem, 'status'>): boolean {
  return invoice.status === 'sent' || invoice.status === 'overdue';
}

/** A DRAFT was never issued: it is voided (POST /cancel), no Storno needed. */
export function canVoidDraft(invoice: Pick<InvoiceListItem, 'status'>): boolean {
  return invoice.status === 'draft';
}

/**
 * W2-04: an issued invoice (also a paid one) is reversed by a linked negative
 * Stornorechnung (POST /storno). A Storno itself cannot be reversed again.
 */
export function canCreateStorno(invoice: InvoiceLike): boolean {
  const isIssued = invoice.status === 'sent' || invoice.status === 'overdue' || invoice.status === 'paid';
  return isIssued && !invoice.cancels_invoice_id;
}
