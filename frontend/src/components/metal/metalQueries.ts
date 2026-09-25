// Query options for the metal inventory screens (W4-03). Every key sits
// under the ['metal-inventory'] root, so one invalidation after a purchase
// or a booking refreshes statistics, lists, usage, forecast and prices.
// All endpoints here are legacy plain responses (no Page envelope).
import { queryOptions } from '@tanstack/react-query';
import apiClient from '../../api/client';
import { metalInventoryApi } from '../../api';
import { queryKeys, type MetalPurchaseListParams } from '../../api/queryKeys';
import type { MetalType } from '../../types';

export interface ForecastItem {
  metal_type: MetalType;
  remaining_stock_g: number;
  weekly_consumption_g: number;
  depletion_date: string | null;
  weeks_until_depletion: number | null;
  reorder_by: string | null;
  reorder_is_overdue: boolean;
  reorder_message: string;
  confidence: string;
  confidence_note: string;
}

interface ForecastResponse {
  forecasts: ForecastItem[];
  generated_at: string;
  lookback_days: number;
  lead_time_days: number;
}

export interface PricePoint {
  fetched_at: string;
  price_per_gram_eur: number;
  source: string;
}

export interface PriceHistoryResponse {
  metal_type: MetalType;
  days: number;
  points: PricePoint[];
  avg_7d: number;
  avg_30d: number;
  current_price: number;
}

export const USAGE_LIMIT = 100;

export function statisticsQuery() {
  return queryOptions({
    queryKey: queryKeys.metalInventory.statistics(),
    queryFn: () => metalInventoryApi.getStatistics(),
  });
}

export function spotPricesQuery() {
  return queryOptions({
    queryKey: queryKeys.metalInventory.spotPrices(),
    queryFn: () => metalInventoryApi.getSpotPrices(),
  });
}

export function forecastQuery() {
  return queryOptions({
    queryKey: queryKeys.metalInventory.forecast(),
    queryFn: async () => (await apiClient.get<ForecastResponse>('/metal-inventory/forecast')).data,
  });
}

export function purchasesQuery(params: MetalPurchaseListParams) {
  return queryOptions({
    queryKey: queryKeys.metalInventory.purchaseList(params),
    queryFn: () =>
      metalInventoryApi.listPurchases({
        metal_type: params.metal_type as MetalType | undefined,
        include_depleted: params.include_depleted,
      }),
  });
}

export function usageQuery(metalType: MetalType | '') {
  const params = { metal_type: metalType || undefined, limit: USAGE_LIMIT };
  return queryOptions({
    queryKey: queryKeys.metalInventory.usage(params),
    queryFn: () => metalInventoryApi.getUsageHistory({ metal_type: metalType || undefined, limit: USAGE_LIMIT }),
  });
}

export function priceHistoryQuery(metalType: MetalType, days: number) {
  return queryOptions({
    queryKey: queryKeys.metalInventory.priceHistory(metalType, days),
    queryFn: async ({ signal }) =>
      (
        await apiClient.get<PriceHistoryResponse>('/metal-prices/history', {
          params: { metal_type: metalType, days },
          signal,
        })
      ).data,
  });
}
