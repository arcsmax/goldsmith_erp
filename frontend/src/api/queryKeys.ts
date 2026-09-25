/**
 * Query-key factory for TanStack Query (W3-03). See
 * docs/technical/FRONTEND_DATA_LAYER.md.
 *
 * Every key starts with its domain root (`['orders']`, `['customers']`, ...)
 * so one `invalidateQueries({ queryKey: queryKeys.orders.all })` refreshes
 * the list, the pages and the details of that domain. Realtime hints
 * invalidate by root (lib/realtimeInvalidation.ts):
 *
 *   order_updates          → orders, dashboard, handoffs
 *   time_tracking_updates  → timer, dashboard
 *   notifications          → notifications, handoffs
 *
 * Never build a key inline in a component; add it here so invalidation
 * stays in sync.
 */
import type { MaterialPageParams, OrderPageParams } from './paged';

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
  },
  customers: {
    all: ['customers'] as const,
    /** GET /customers/ (legacy list; the backend has no Page envelope yet). */
    list: (params: CustomerListParams) => [...queryKeys.customers.all, 'list', params] as const,
    detail: (id: number) => [...queryKeys.customers.all, 'detail', id] as const,
  },
  dashboard: {
    all: ['dashboard'] as const,
    today: () => [...queryKeys.dashboard.all, 'today'] as const,
    alerts: () => [...queryKeys.dashboard.all, 'alerts'] as const,
  },
  handoffs: {
    all: ['handoffs'] as const,
    pending: () => [...queryKeys.handoffs.all, 'pending'] as const,
  },
  timer: {
    all: ['timer'] as const,
    summary: (range: DateRange) => [...queryKeys.timer.all, 'summary', range] as const,
  },
  notifications: {
    all: ['notifications'] as const,
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
  },
} as const;
