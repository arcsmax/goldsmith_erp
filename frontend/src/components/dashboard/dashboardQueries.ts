// Shared queries of the Kennzahlen widgets (W3-03, FE-20).
//
// DashboardKPIs and AlertsWidget both read the recent orders. They use the
// SAME query options, so TanStack Query sends one GET /orders/?limit=100 per
// mount instead of one per widget (the old "4x dashboard fetch").
//
// TODO(W3-08 follow-up): these KPIs still count client-side over the newest
// 100 orders; a server-side KPI endpoint would make them exact.
import { queryOptions } from '@tanstack/react-query';
import { materialsApi, metalInventoryApi, ordersApi } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import { logError } from '../../lib/logError';

/** Log a failed widget source with context, then let the query see the error. */
function logged<T>(label: string, load: () => Promise<T>): () => Promise<T> {
  return async () => {
    try {
      return await load();
    } catch (err) {
      logError(`Dashboard-Kennzahlen: ${label} konnte nicht geladen werden`, err);
      throw err;
    }
  };
}

/** Rows the widgets aggregate over (legacy list, newest first). */
export const WIDGET_ORDER_LIMIT = 100;
/** Materials below this many units raise the low-stock alert. */
export const LOW_STOCK_THRESHOLD = 10;

export function widgetOrdersQuery() {
  return queryOptions({
    queryKey: queryKeys.orders.legacyList(WIDGET_ORDER_LIMIT),
    queryFn: logged('Aufträge', () => ordersApi.getAll({ limit: WIDGET_ORDER_LIMIT })),
  });
}

export function inventoryStatisticsQuery() {
  return queryOptions({
    queryKey: queryKeys.metalInventory.statistics(),
    queryFn: logged('Inventarwert', () => metalInventoryApi.getStatistics()),
  });
}

export function metalPurchasesQuery() {
  return queryOptions({
    queryKey: queryKeys.metalInventory.purchases(),
    queryFn: logged('Metallinventar', () => metalInventoryApi.listPurchases()),
  });
}

export function lowStockQuery() {
  return queryOptions({
    queryKey: queryKeys.materials.lowStock(LOW_STOCK_THRESHOLD),
    queryFn: logged('Materialbestand', () => materialsApi.getLowStock(LOW_STOCK_THRESHOLD)),
  });
}
