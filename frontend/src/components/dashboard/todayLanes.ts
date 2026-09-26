// Pure helpers for the "Heute" lanes (W2-03): next-action links and texts.
// Every row on the Heute view links to its natural next action (CLAUDE.md).
import type { OrderTab } from '../../contexts/OrderContext';
import { formatEur } from '../../lib/format';
import type {
  DashboardPendingItem,
  DashboardTimerItem,
  DashboardWorkItem,
} from '../../api/dashboard';

export interface RowAction {
  /** Route to open. */
  to: string;
  /** Verb + noun, shown on the row. */
  label: string;
  /** Order-detail tab to open first (OrderContext remembers it per order). */
  orderTab?: { orderId: number; tab: OrderTab };
}

/** Repair pages are routed for ADMIN and GOLDSMITH only (App.tsx). */
export function canOpenRepairs(role?: string | null): boolean {
  const normalized = (role ?? '').toUpperCase();
  return normalized === 'ADMIN' || normalized === 'GOLDSMITH';
}

/** Quotes are routed for ADMIN and GOLDSMITH only (App.tsx). */
export const canOpenQuotes = canOpenRepairs;

export function formatDaysOverdue(days: number): string {
  if (days === 1) return '1 Tag überfällig';
  if (days > 1) return `${days} Tage überfällig`;
  if (days === 0) return 'heute fällig';
  if (days === -1) return 'morgen fällig';
  return `in ${Math.abs(days)} Tagen fällig`;
}

export function formatDate(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split('-');
  return `${day}.${month}.${year}`;
}

/** Naive-UTC ISO timestamp from the API -> Date. */
export function parseUtc(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
}

const MS_PER_DAY = 24 * 60 * 60 * 1000;

/** Whole days between ``iso`` (naive UTC) and ``now``; never negative. */
export function daysSince(iso: string, now: Date = new Date()): number {
  return Math.max(0, Math.floor((now.getTime() - parseUtc(iso).getTime()) / MS_PER_DAY));
}

export function formatTime(iso: string): string {
  return parseUtc(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
}

export function formatAmount(amount: number): string {
  return formatEur(amount);
}

export function workItemAction(
  item: DashboardWorkItem,
  role?: string | null,
): RowAction | null {
  if (item.kind === 'repair') {
    if (!canOpenRepairs(role)) return null;
    return { to: `/repairs/${item.id}`, label: 'Reparatur öffnen' };
  }
  return { to: `/orders/${item.id}`, label: 'Auftrag öffnen' };
}

function orderAction(orderId: number, tab: OrderTab, label: string): RowAction {
  return { to: `/orders/${orderId}`, label, orderTab: { orderId, tab } };
}

export function pendingAction(
  item: DashboardPendingItem,
  role?: string | null,
): RowAction | null {
  switch (item.kind) {
    case 'cost_change':
      return item.order_id ? orderAction(item.order_id, 'kosten', 'Kostenänderung ansehen') : null;
    case 'customer_update':
      if (item.repair_id) {
        return canOpenRepairs(role)
          ? { to: `/repairs/${item.repair_id}`, label: 'Kundeninfo erneut senden' }
          : null;
      }
      return item.order_id
        ? orderAction(item.order_id, 'kundeninfo', 'Kundeninfo erneut senden')
        : null;
    case 'repair_ready':
      return canOpenRepairs(role)
        ? { to: `/repairs/${item.id}`, label: 'Abholung erfassen' }
        : null;
    case 'order_ready':
      return orderAction(item.id, 'status', 'Übergabe erfassen');
    case 'quote':
      return canOpenQuotes(role) ? { to: '/quotes', label: 'Angebot nachfassen' } : null;
    default:
      return null;
  }
}

export const PENDING_KIND_LABEL: Readonly<Record<DashboardPendingItem['kind'], string>> = {
  cost_change: 'Kostenänderung wartet auf Zustimmung',
  customer_update: 'Kundeninfo nicht zugestellt',
  repair_ready: 'Reparatur abholbereit',
  order_ready: 'Auftrag abholbereit',
  quote: 'Angebot wartet auf Antwort',
};

/** Failed updates are red (a retry is due), waiting answers amber, pickups green. */
export const PENDING_KIND_TONE: Readonly<Record<DashboardPendingItem['kind'], 'urgent' | 'soon' | 'ok'>> = {
  cost_change: 'soon',
  customer_update: 'urgent',
  repair_ready: 'ok',
  order_ready: 'ok',
  quote: 'soon',
};

export function timerAction(item: DashboardTimerItem): RowAction {
  return orderAction(item.order_id, 'time-tracking', 'Zeiten ansehen');
}
