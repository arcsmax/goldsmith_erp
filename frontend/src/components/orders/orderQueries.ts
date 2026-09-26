// Shared TanStack Query options for the order detail page group (W4-03).
//
// Components that need the same server data use the same queryOptions so
// they share one request (docs/technical/FRONTEND_DATA_LAYER.md). Every key
// is nested under queryKeys.orders.detail(id), so an `order_updates`
// realtime hint (root ['orders']) refreshes the order with its photos and
// Verlauf; a mutation on one order invalidates `orderDetailKey(id)`.
import { queryOptions, type QueryClient } from '@tanstack/react-query';
// Through the api barrel, the same module the page and its tests mock.
import { ordersApi } from '../../api';
import { photosApi } from '../../api/photos';
import { queryKeys } from '../../api/queryKeys';
import { logError } from '../../lib/logError';
import type { OrderWithStatusFields } from './OrderOverviewTab';

export const orderDetailKey = (orderId: number) => queryKeys.orders.detail(orderId);

export const orderQuery = (orderId: number) =>
  queryOptions({
    queryKey: queryKeys.orders.detail(orderId),
    queryFn: async () => {
      try {
        return (await ordersApi.getById(orderId)) as OrderWithStatusFields;
      } catch (err: unknown) {
        logError('OrderDetailPage.load', err);
        throw err;
      }
    },
  });

export const orderPhotosQuery = (orderId: number) =>
  queryOptions({
    queryKey: queryKeys.orders.photos(orderId),
    queryFn: async () => {
      try {
        return (await photosApi.getForOrder(orderId)).data ?? [];
      } catch (err: unknown) {
        logError('OrderDetailPage.loadPhotos', err);
        throw err;
      }
    },
  });

export const orderTimelineQuery = (orderId: number) =>
  queryOptions({
    queryKey: queryKeys.orders.timeline(orderId),
    queryFn: async () => {
      try {
        return await ordersApi.getTimeline(orderId);
      } catch (err: unknown) {
        logError(`OrderTimeline.load order=${orderId}`, err);
        throw err;
      }
    },
  });

/** Refresh one order and everything nested under it (photos, Verlauf, costs …). */
export function invalidateOrder(client: QueryClient, orderId: number): Promise<void> {
  return client.invalidateQueries({ queryKey: orderDetailKey(orderId) });
}
