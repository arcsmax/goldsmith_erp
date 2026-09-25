/**
 * Query-key factory for TanStack Query (W3-03). See
 * docs/technical/FRONTEND_DATA_LAYER.md.
 *
 * Every key starts with its domain root (`['orders']`, `['customers']`, ...)
 * so one `invalidateQueries({ queryKey: queryKeys.orders.all })` refreshes
 * the list, the pages and the details of that domain. Realtime hints
 * invalidate by root (lib/realtimeInvalidation.ts):
 *
 *   order_updates          → orders, dashboard, handoffs, calendar, jobs
 *   time_tracking_updates  → timer, dashboard
 *   notifications          → notifications, handoffs
 *   repair_updates         → repairs, jobs
 *
 * Never build a key inline in a component; add it here so invalidation
 * stays in sync.
 */
import type { JobPageParams } from './jobs';
import type { MaterialPageParams, OrderPageParams } from './paged';
import type { RepairPageParams } from './repairs';

export interface CustomerListParams {
  skip: number;
  limit: number;
  search?: string;
  customer_type?: string;
  is_active?: boolean;
}

export interface MetalPurchaseListParams {
  metal_type?: string;
  include_depleted?: boolean;
}

export interface TimeEntryPageParams {
  limit: number;
  offset: number;
  sort?: string;
  start_date?: string;
  end_date?: string;
}

export interface DateRange {
  start_date: string;
  end_date: string;
}

/** Filters of the Scan-Verlauf search (GET /scan/history). */
export interface ScanHistorySearchParams {
  q?: string;
  user?: number;
  from?: string;
  to?: string;
  limit: number;
  offset: number;
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
    /** GET /invoices/?skip=… (legacy envelope; the backend has no Page envelope yet). */
    list: (params: object) => [...queryKeys.invoices.all, 'list', params] as const,
    detail: (id: number) => [...queryKeys.invoices.all, 'detail', id] as const,
  },
  timer: {
    all: ['timer'] as const,
    summary: (range: DateRange) => [...queryKeys.timer.all, 'summary', range] as const,
    // W4-03 bench UI. All under ['timer'], so a time_tracking_updates hint
    // refreshes the running timer, the entry lists and the activity usage.
    /** GET /time-tracking/running for one signed-in user. */
    running: (userId: number | null) => [...queryKeys.timer.all, 'running', userId] as const,
    /** GET /time-tracking/user/{id}?offset=… (Page envelope). */
    userEntries: (userId: number, params: TimeEntryPageParams) =>
      [...queryKeys.timer.all, 'user-entries', userId, params] as const,
    /** GET /time-tracking/order/{id}?offset=… (Page envelope). */
    orderEntries: (orderId: number, params: TimeEntryPageParams) =>
      [...queryKeys.timer.all, 'order-entries', orderId, params] as const,
    /** GET /activities/ (usage counts change when a timer stops). */
    activities: (sortByUsage: boolean) =>
      [...queryKeys.timer.all, 'activities', { sortByUsage }] as const,
    mostUsedActivities: (limit: number) =>
      [...queryKeys.timer.all, 'activities', 'most-used', { limit }] as const,
  },
  scanLog: {
    all: ['scan-log'] as const,
    /** GET /scan/log?user_id=me (the "Letzte Scans" list). */
    history: (limit: number) => [...queryKeys.scanLog.all, 'history', { limit }] as const,
    /** GET /orders/{id}/scans or /repairs/{id}/scans (Scan-Verlauf of one piece). */
    piece: (entityType: 'order' | 'repair', id: number, limit: number) =>
      [...queryKeys.scanLog.all, 'piece', entityType, id, { limit }] as const,
    /** GET /scan/history (ADMIN/GOLDSMITH search across pieces and users). */
    search: (params: ScanHistorySearchParams) =>
      [...queryKeys.scanLog.all, 'search', params] as const,
  },
  notifications: {
    all: ['notifications'] as const,
    unreadCount: () => [...queryKeys.notifications.all, 'unread-count'] as const,
    list: (limit: number) => [...queryKeys.notifications.all, 'list', { limit }] as const,
  },
  quotes: {
    all: ['quotes'] as const,
    lists: () => [...queryKeys.quotes.all, 'list'] as const,
    /** GET /quotes/?offset=… (Page envelope, status filter and `q`). */
    page: (params: object) => [...queryKeys.quotes.lists(), 'page', params] as const,
    detail: (id: number) => [...queryKeys.quotes.all, 'detail', id] as const,
  },
  metalInventory: {
    all: ['metal-inventory'] as const,
    statistics: () => [...queryKeys.metalInventory.all, 'statistics'] as const,
    purchases: () => [...queryKeys.metalInventory.all, 'purchases'] as const,
    /** GET /metal-inventory/purchases with filters (legacy plain list, no Page envelope). */
    purchaseList: (params: MetalPurchaseListParams) =>
      [...queryKeys.metalInventory.all, 'purchases', 'list', params] as const,
    /** GET /metal-inventory/usage (legacy plain list). */
    usage: (params: { metal_type?: string; limit: number }) =>
      [...queryKeys.metalInventory.all, 'usage', params] as const,
    forecast: () => [...queryKeys.metalInventory.all, 'forecast'] as const,
    /** GET /metal-prices (spot prices; kept under this root so a booking refreshes them too). */
    spotPrices: () => [...queryKeys.metalInventory.all, 'spot-prices'] as const,
    priceHistory: (metalType: string, days: number) =>
      [...queryKeys.metalInventory.all, 'price-history', { metalType, days }] as const,
  },
  consultations: {
    all: ['consultations'] as const,
    /** GET /consultations/ (legacy plain list; no Page envelope yet). */
    list: (status: string | undefined) => [...queryKeys.consultations.all, 'list', { status }] as const,
    detail: (id: number) => [...queryKeys.consultations.all, 'detail', id] as const,
  },
  scrapGold: {
    all: ['scrap-gold'] as const,
    /** GET /orders/{id}/scrap-gold (null when the order has no Altgold yet). */
    forOrder: (orderId: number) => [...queryKeys.scrapGold.all, 'order', orderId] as const,
  },
  materials: {
    all: ['materials'] as const,
    lowStock: (threshold: number) => [...queryKeys.materials.all, 'low-stock', { threshold }] as const,
    /** GET /materials/?offset=… (Page envelope, `q` searches name and supplier). */
    page: (params: MaterialPageParams) => [...queryKeys.materials.all, 'page', params] as const,
    /** GET /materials/purchase-list (legacy plain list, grouped by supplier). */
    purchaseList: () => [...queryKeys.materials.all, 'purchase-list'] as const,
    /** GET /materials/?limit=… (header search index). */
    list: (limit: number) => [...queryKeys.materials.all, 'list', { limit }] as const,
  },
  jobs: {
    all: ['jobs'] as const,
    /** GET /jobs/?offset=… (Page envelope; the Werkstatt board asks per status). */
    page: (params: JobPageParams) => [...queryKeys.jobs.all, 'page', params] as const,
  },
  repairs: {
    all: ['repairs'] as const,
    lists: () => [...queryKeys.repairs.all, 'list'] as const,
    /** GET /repairs/?offset=… (Page envelope, status filter, `q`, `sort`). */
    page: (params: RepairPageParams) => [...queryKeys.repairs.lists(), 'page', params] as const,
    detail: (id: number) => [...queryKeys.repairs.all, 'detail', id] as const,
    /** Nested under detail(id): refreshing the repair refreshes its Kundeninfo. */
    customerUpdates: (id: number) => [...queryKeys.repairs.detail(id), 'customer-updates'] as const,
  },
  calendar: {
    all: ['calendar'] as const,
    /** GET /calendar/events for one visible date range. */
    events: (range: DateRange) => [...queryKeys.calendar.all, 'events', range] as const,
  },
} as const;
