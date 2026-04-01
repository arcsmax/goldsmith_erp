// Time Tracking API Service
import apiClient from './client';
import {
  TimeEntry,
  TimeEntryWithDetails,
  TimeEntryStartInput,
  TimeEntryStopInput,
  TimeEntryUpdateInput,
  Interruption,
  InterruptionCreateInput,
  TimeTrackingStats,
} from '../types';

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
   * Get all time entries for a specific order
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
  createManual: async (data: {
    order_id: number;
    activity_id: number;
    start_time: string;
    end_time?: string;
    duration_minutes?: number;
    location?: string;
    complexity_rating?: number;
    quality_rating?: number;
    rework_required?: boolean;
    notes?: string;
    extra_metadata?: Record<string, any>;
  }): Promise<TimeEntry> => {
    const response = await apiClient.post<TimeEntry>('/time-tracking/', data);
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
