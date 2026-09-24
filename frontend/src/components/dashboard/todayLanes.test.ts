import { describe, expect, it } from 'vitest';
import type { DashboardPendingItem, DashboardWorkItem } from '../../api/dashboard';
import {
  daysSince,
  formatDate,
  formatDaysOverdue,
  pendingAction,
  timerAction,
  workItemAction,
} from './todayLanes';

const base: Omit<DashboardPendingItem, 'kind'> = {
  id: 3,
  title: 'x',
  reference: '#9',
  since: '2026-09-20T10:00:00',
};

describe('todayLanes', () => {
  it('formats days overdue and due soon in German', () => {
    expect(formatDaysOverdue(1)).toBe('1 Tag überfällig');
    expect(formatDaysOverdue(4)).toBe('4 Tage überfällig');
    expect(formatDaysOverdue(0)).toBe('heute fällig');
    expect(formatDaysOverdue(-1)).toBe('morgen fällig');
    expect(formatDaysOverdue(-3)).toBe('in 3 Tagen fällig');
    expect(formatDate('2026-09-24')).toBe('24.09.2026');
  });

  it('counts whole days since a naive-UTC timestamp', () => {
    expect(daysSince('2026-09-20T10:00:00', new Date('2026-09-23T11:00:00Z'))).toBe(3);
    expect(daysSince('2026-09-24T10:00:00', new Date('2026-09-23T11:00:00Z'))).toBe(0);
  });

  it('links orders for every role and repairs only for workshop roles', () => {
    const order: DashboardWorkItem = {
      kind: 'order', id: 1, reference: '#1', title: 't', status: 's',
      due_date: '2026-09-24', days_overdue: 1,
    };
    const repair: DashboardWorkItem = { ...order, kind: 'repair', id: 7 };
    expect(workItemAction(order, 'VIEWER')?.to).toBe('/orders/1');
    expect(workItemAction(repair, 'goldsmith')?.to).toBe('/repairs/7');
    expect(workItemAction(repair, 'VIEWER')).toBeNull();
  });

  it('maps each pending kind to its next action', () => {
    expect(pendingAction({ ...base, kind: 'cost_change', order_id: 5 }, 'ADMIN')).toEqual({
      to: '/orders/5',
      label: 'Kostenänderung ansehen',
      orderTab: { orderId: 5, tab: 'kosten' },
    });
    expect(pendingAction({ ...base, kind: 'customer_update', order_id: 1 }, 'ADMIN')?.orderTab)
      .toEqual({ orderId: 1, tab: 'kundeninfo' });
    expect(pendingAction({ ...base, kind: 'customer_update', repair_id: 8 }, 'ADMIN')?.to)
      .toBe('/repairs/8');
    expect(pendingAction({ ...base, kind: 'repair_ready', id: 8 }, 'GOLDSMITH')?.to)
      .toBe('/repairs/8');
    expect(pendingAction({ ...base, kind: 'order_ready', id: 4 }, 'VIEWER')?.orderTab)
      .toEqual({ orderId: 4, tab: 'status' });
    expect(pendingAction({ ...base, kind: 'quote', quote_id: 3 }, 'ADMIN')?.to).toBe('/quotes');
    expect(pendingAction({ ...base, kind: 'quote', quote_id: 3 }, 'VIEWER')).toBeNull();
  });

  it('opens the order time tab for a timer', () => {
    expect(
      timerAction({
        id: 'x', order_id: 2, user_id: 1, start_time: '2026-09-25T06:00:00', is_running: true,
      }).orderTab,
    ).toEqual({ orderId: 2, tab: 'time-tracking' });
  });
});
