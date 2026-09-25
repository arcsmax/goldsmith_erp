// Time Tracking API Service
import apiClient from './client';
import {
  TimeEntry,
  TimeEntryStartInput,
  TimeEntryStopInput,
  TimeEntryCreateInput,
  TimeEntryUpdateInput,
  Interruption,
  InterruptionCreateInput,
  TimeTrackingStats,
  TimeSummaryStats,
} from '../types';
import type { TimeEntryPageParams } from './queryKeys';

/** Page envelope of the time-entry lists (W3-08, models/pagination.py). */
export interface TimeEntriesPage {
  items: TimeEntry[];
  total: number;
  limit: number;
  offset: number;
  next_offset: number | null;
}

function assertTimeEntriesPage(body: unknown, url: string): TimeEntriesPage {
  const candidate = body as Partial<TimeEntriesPage> | null;
  if (!candidate || !Array.isArray(candidate.items) || typeof candidate.total !== 'number') {
    throw new Error(`Unerwartete Antwort von ${url}: keine Seiten-Hülle (items/total).`);
  }
  return candidate as TimeEntriesPage;
}

async function fetchTimeEntriesPage(
  url: string,
  params: TimeEntryPageParams,
  signal?: AbortSignal,
): Promise<TimeEntriesPage> {
  const response = await apiClient.get<unknown>(url, { params, signal });
  return assertTimeEntriesPage(response.data, url);
}

export interface SwitchTimerInput {
  new_order_id: number;
  activity_id: number;
  location?: string;
}

export const timeTrackingApi = {
  /**
   * Start time tracking for an order
   */
  start: async (data: TimeEntryStartInput): Promise<TimeEntry> => {
    const response = await apiClient.post<TimeEntry>('/time-tracking/start', data);
    return response.data;
  },

  /**
   * Stop time tracking
   */
  stop: async (entryId: string, data: TimeEntryStopInput): Promise<TimeEntry> => {
    const response = await apiClient.post<TimeEntry>(
      `/time-tracking/${entryId}/stop`,
      data
    );
    return response.data;
  },

  /**
   * Get currently running time entry for current user
   */
  getRunning: async (): Promise<TimeEntry | null> => {
    const response = await apiClient.get<TimeEntry | null>('/time-tracking/running');
    return response.data;
  },

  /**
   * D-15: manually pause a running entry (opens an Interruption).
   * 409 if already paused or not running.
   */
  pause: async (entryId: string): Promise<TimeEntry> => {
    const response = await apiClient.post<TimeEntry>(
      `/time-tracking/${entryId}/pause`
    );
    return response.data;
  },

  /**
   * D-15: end the current manual pause (closes the open Interruption).
   * 409 if not paused or not running.
   */
  resume: async (entryId: string): Promise<TimeEntry> => {
    const response = await apiClient.post<TimeEntry>(
      `/time-tracking/${entryId}/resume`
    );
    return response.data;
  },

  /**
   * H18: atomic stop-old + start-new (POST /time-tracking/{id}/switch).
   * One transaction, one pubsub event. The idempotency key makes a retried
   * tap safe.
   */
  switchTimer: async (
    entryId: string,
    data: SwitchTimerInput,
    idempotencyKey: string = crypto.randomUUID(),
  ): Promise<TimeEntry> => {
    const response = await apiClient.post<TimeEntry>(`/time-tracking/${entryId}/switch`, data, {
      headers: {
        'Idempotency-Key': idempotencyKey,
        'X-Client-Created-At': new Date().toISOString(),
      },
    });
    return response.data;
  },

  /** One page of a user's entries (always sends `offset`, so always a Page). */
  getUserPage: (
    userId: number,
    params: TimeEntryPageParams,
    signal?: AbortSignal,
  ): Promise<TimeEntriesPage> =>
    fetchTimeEntriesPage(`/time-tracking/user/${userId}`, params, signal),

  /** One page of an order's entries (Page envelope). */
  getOrderPage: (
    orderId: number,
    params: TimeEntryPageParams,
    signal?: AbortSignal,
  ): Promise<TimeEntriesPage> =>
    fetchTimeEntriesPage(`/time-tracking/order/${orderId}`, params, signal),

  /**
   * Get all time entries for a specific order (legacy plain list)
   */
  getForOrder: async (
    orderId: number,
    skip: number = 0,
    limit: number = 100
  ): Promise<TimeEntry[]> => {
    const response = await apiClient.get<TimeEntry[]>(
      `/time-tracking/order/${orderId}`,
      {
        params: { skip, limit },
      }
    );
    return response.data;
  },

  /**
   * Get total time statistics for an order
   */
  getTotalForOrder: async (orderId: number): Promise<TimeTrackingStats> => {
    const response = await apiClient.get<TimeTrackingStats>(
      `/time-tracking/order/${orderId}/total`
    );
    return response.data;
  },

  /**
   * Get time entries for a specific user (with optional date filter)
   */
  getForUser: async (
    userId: number,
    startDate?: string,
    endDate?: string,
    skip: number = 0,
    limit: number = 100
  ): Promise<TimeEntry[]> => {
    const response = await apiClient.get<TimeEntry[]>(
      `/time-tracking/user/${userId}`,
      {
        params: {
          start_date: startDate,
          end_date: endDate,
          skip,
          limit,
        },
      }
    );
    return response.data;
  },

  /**
   * Get a single time entry by ID
   */
  getById: async (entryId: string): Promise<TimeEntry> => {
    const response = await apiClient.get<TimeEntry>(`/time-tracking/${entryId}`);
    return response.data;
  },

  /**
   * Create a manual time entry (with start and end time)
   */
  createManual: async (data: TimeEntryCreateInput): Promise<TimeEntry> => {
    const response = await apiClient.post<TimeEntry>('/time-tracking/', data);
    return response.data;
  },

  /**
   * Get aggregated time-tracking statistics for a date range.
   * GET /time-tracking/summary?start_date=&end_date=
   *
   * NOTE: the backend endpoint is not yet implemented; callers
   * (DashboardKPIs, TimeSummaryCards) guard against failure and degrade
   * gracefully. This method makes the intended contract explicit so it
   * works automatically once the endpoint lands.
   */
  getSummary: async (params: {
    start_date: string;
    end_date: string;
  }): Promise<TimeSummaryStats> => {
    const response = await apiClient.get<TimeSummaryStats>(
      '/time-tracking/summary',
      { params }
    );
    return response.data;
  },

  /**
   * Update a time entry
   */
  update: async (entryId: string, data: TimeEntryUpdateInput): Promise<TimeEntry> => {
    const response = await apiClient.put<TimeEntry>(`/time-tracking/${entryId}`, data);
    return response.data;
  },

  /**
   * Delete a time entry
   */
  delete: async (entryId: string): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.delete<{ success: boolean; message: string }>(
      `/time-tracking/${entryId}`
    );
    return response.data;
  },

  /**
   * Add an interruption to a time entry
   */
  addInterruption: async (
    entryId: string,
    data: Omit<InterruptionCreateInput, 'time_entry_id'>
  ): Promise<Interruption> => {
    const response = await apiClient.post<Interruption>(
      `/time-tracking/${entryId}/interruptions`,
      data
    );
    return response.data;
  },
};
