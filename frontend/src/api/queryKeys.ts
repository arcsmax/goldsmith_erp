/**
 * Query-key factory for TanStack Query (W3-03). See
 * docs/technical/FRONTEND_DATA_LAYER.md.
 *
 * Every key starts with its domain root (`['orders']`, `['customers']`, ...)
 * so one `invalidateQueries({ queryKey: queryKeys.orders.all })` refreshes
 * the list, the pages and the details of that domain. Realtime hints
 * invalidate by root (lib/realtimeInvalidation.ts):
 *
 *   order_updates          → orders, dashboard, handoffs, calendar
 *   time_tracking_updates  → timer, dashboard
 *   notifications          → notifications, handoffs
 *
 * Never build a key inline in a component; add it here so invalidation
 * stays in sync.
 */
import type { OrderPageParams } from './paged';

export interface CustomerListParams {
  skip: number;
  limit: number;
  search?: string;
  customer_type?: string;
  is_active?: boolean;
}

export interface DateRange {
  start_date: string;
  end_date: string;
}

export const queryKeys = {
  orders: {
    all: ['orders'] as const,
    lists: () => [...queryKeys.orders.all, 'list'] as const,
    /** GET /orders/?offset=… (Page envelope, server-side filters). */
    page: (params: OrderPageParams) => [...queryKeys.orders.lists(), 'page', params] as const,
    /** GET /orders/?limit=… without offset (legacy list; dashboard widgets). */
    legacyList: (limit: number) => [...queryKeys.orders.lists(), 'legacy', { limit }] as const,
    detail: (id: number) => [...queryKeys.orders.all, 'detail', id] as const,
    // Order-detail sub-resources (W4-03). Nested under detail(id), so an
    // order_updates hint (root ['orders']) or invalidating detail(id)
    // refreshes the order together with its photos, Verlauf, costs …
    photos: (id: number) => [...queryKeys.orders.detail(id), 'photos'] as const,
    timeline: (id: number) => [...queryKeys.orders.detail(id), 'timeline'] as const,
    comparison: (id: number) => [...queryKeys.orders.detail(id), 'comparison'] as const,
    projectedCost: (id: number) => [...queryKeys.orders.detail(id), 'projected-cost'] as const,
    costChanges: (id: number) => [...queryKeys.orders.detail(id), 'cost-changes'] as const,
    customerUpdates: (id: number) => [...queryKeys.orders.detail(id), 'customer-updates'] as const,
    messageContext: (id: number) => [...queryKeys.orders.detail(id), 'message-context'] as const,
    gemstones: (id: number) => [...queryKeys.orders.detail(id), 'gemstones'] as const,
    valuation: (id: number) => [...queryKeys.orders.detail(id), 'valuation'] as const,
  },
  customers: {
    all: ['customers'] as const,
    /** GET /customers/ (legacy list; the backend has no Page envelope yet). */
    list: (params: CustomerListParams) => [...queryKeys.customers.all, 'list', params] as const,
    detail: (id: number) => [...queryKeys.customers.all, 'detail', id] as const,
    /** GET /customers/search?q=… (header search). */
    search: (q: string, limit: number) => [...queryKeys.customers.all, 'search', { q, limit }] as const,
  },
  dashboard: {
    all: ['dashboard'] as const,
    today: () => [...queryKeys.dashboard.all, 'today'] as const,
    alerts: () => [...queryKeys.dashboard.all, 'alerts'] as const,
  },
  handoffs: {
    all: ['handoffs'] as const,
    pending: () => [...queryKeys.handoffs.all, 'pending'] as const,
    forOrder: (orderId: number) => [...queryKeys.handoffs.all, 'order', orderId] as const,
  },
  users: {
    all: ['users'] as const,
    list: (skip: number, limit: number) => [...queryKeys.users.all, 'list', { skip, limit }] as const,
  },
  admin: {
    all: ['admin'] as const,
    emailConfig: () => [...queryKeys.admin.all, 'email-config'] as const,
  },
  invoices: {
    all: ['invoices'] as const,
    recent: (limit: number) => [...queryKeys.invoices.all, 'recent', { limit }] as const,
  },
  timer: {
    all: ['timer'] as const,
    summary: (range: DateRange) => [...queryKeys.timer.all, 'summary', range] as const,
  },
  notifications: {
    all: ['notifications'] as const,
    unreadCount: () => [...queryKeys.notifications.all, 'unread-count'] as const,
    list: (limit: number) => [...queryKeys.notifications.all, 'list', { limit }] as const,
  },
  metalInventory: {
    all: ['metal-inventory'] as const,
    statistics: () => [...queryKeys.metalInventory.all, 'statistics'] as const,
    purchases: () => [...queryKeys.metalInventory.all, 'purchases'] as const,
  },
  materials: {
    all: ['materials'] as const,
    lowStock: (threshold: number) => [...queryKeys.materials.all, 'low-stock', { threshold }] as const,
    /** GET /materials/?limit=… (header search index). */
    list: (limit: number) => [...queryKeys.materials.all, 'list', { limit }] as const,
  },
  users: {
    all: ['users'] as const,
    /** GET /users/ (admin list, legacy skip/limit). */
    list: () => [...queryKeys.users.all, 'list'] as const,
  },
  calendar: {
    all: ['calendar'] as const,
    /** GET /calendar/events for one visible date range. */
    events: (range: DateRange) => [...queryKeys.calendar.all, 'events', range] as const,
  },
} as const;
