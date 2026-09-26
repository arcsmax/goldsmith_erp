/**
 * TanStack Query options for time tracking (W4-03, bench UI).
 *
 * One definition per server resource, shared by every screen that shows it,
 * so the TimerWidget, the ScanFab, the scanner page and the time-tracking
 * page read the running timer from one cache entry (one request, one
 * source of truth). Keys live in queryKeys.ts under ['timer']; a
 * `time_tracking_updates` hint invalidates the whole root
 * (lib/realtimeInvalidation.ts), so no screen needs its own socket handler.
 */
import { keepPreviousData, queryOptions } from '@tanstack/react-query';

import { activitiesApi } from './activities';
import { ordersApi } from './orders';
import { queryKeys, type TimeEntryPageParams } from './queryKeys';
import { timeTrackingApi } from './time-tracking';

/** Poll the running timer while one runs (a stop on another device without a socket). */
export const RUNNING_POLL_INTERVAL_MS = 5000;
/** Default page size of the entry lists; the backend caps paged lists at 200. */
export const TIME_ENTRY_PAGE_SIZE = 25;
export const MOST_USED_ACTIVITY_LIMIT = 5;

export function runningEntryQuery(userId: number | null) {
  return queryOptions({
    queryKey: queryKeys.timer.running(userId),
    queryFn: async () => {
      try {
        return await timeTrackingApi.getRunning();
      } catch (err) {
        console.error('Laufender Timer konnte nicht geladen werden', { userId, err });
        throw err;
      }
    },
    enabled: userId !== null,
    // FE-19: poll only while a timer runs; stop once the server says none.
    refetchInterval: (query) => (query.state.data ? RUNNING_POLL_INTERVAL_MS : false),
  });
}

export function activitiesQuery(sortByUsage = true) {
  return queryOptions({
    queryKey: queryKeys.timer.activities(sortByUsage),
    queryFn: () => activitiesApi.getAll(sortByUsage ? { sortByUsage: true } : undefined),
  });
}

export function mostUsedActivitiesQuery(limit = MOST_USED_ACTIVITY_LIMIT) {
  return queryOptions({
    queryKey: queryKeys.timer.mostUsedActivities(limit),
    queryFn: () => activitiesApi.getMostUsed(limit),
  });
}

export function userEntriesQuery(userId: number, params: TimeEntryPageParams) {
  return queryOptions({
    queryKey: queryKeys.timer.userEntries(userId, params),
    queryFn: ({ signal }) => timeTrackingApi.getUserPage(userId, params, signal),
    placeholderData: keepPreviousData,
  });
}

/** Orders for the timer and entry pickers (shares the dashboard's legacy list). */
export const ORDER_PICKER_LIMIT = 100;

export function orderPickerQuery() {
  return queryOptions({
    queryKey: queryKeys.orders.legacyList(ORDER_PICKER_LIMIT),
    queryFn: () => ordersApi.getAll({ limit: ORDER_PICKER_LIMIT }),
  });
}

export function orderEntriesQuery(orderId: number, params: TimeEntryPageParams) {
  return queryOptions({
    queryKey: queryKeys.timer.orderEntries(orderId, params),
    queryFn: ({ signal }) => timeTrackingApi.getOrderPage(orderId, params, signal),
    placeholderData: keepPreviousData,
  });
}
