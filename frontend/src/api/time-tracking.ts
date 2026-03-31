// Time Tracking API Service
import apiClient from './client';
import {
  TimeEntryType,
  TimeEntryCreateInput,
  TimeEntryUpdateInput,
  ActivityType,
  ActivityCreateInput,
  TimeSummaryStats,
  WeeklyTimeData,
  ActivityBreakdownData,
} from '../types';

export const timeTrackingApi = {
  // ==================== TIME ENTRIES ====================

  /**
   * Get all time entries with optional filters
   */
  getAll: async (params?: {
    skip?: number;
    limit?: number;
    order_id?: number;
    user_id?: number;
    start_date?: string;
    end_date?: string;
  }): Promise<TimeEntryType[]> => {
    const response = await apiClient.get<TimeEntryType[]>('/time-entries/', {
      params,
    });
    return response.data;
  },

  /**
   * Get single time entry by ID
   */
  getById: async (id: string): Promise<TimeEntryType> => {
    const response = await apiClient.get<TimeEntryType>(`/time-entries/${id}`);
    return response.data;
  },

  /**
   * Create new time entry
   */
  create: async (entry: TimeEntryCreateInput): Promise<TimeEntryType> => {
    const response = await apiClient.post<TimeEntryType>('/time-entries/', entry);
    return response.data;
  },

  /**
   * Update existing time entry
   */
  update: async (id: string, entry: TimeEntryUpdateInput): Promise<TimeEntryType> => {
    const response = await apiClient.put<TimeEntryType>(`/time-entries/${id}`, entry);
    return response.data;
  },

  /**
   * Delete time entry
   */
  delete: async (id: string): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.delete<{ success: boolean; message: string }>(
      `/time-entries/${id}`
    );
    return response.data;
  },

  /**
   * Stop an active time entry (set end_time to now)
   */
  stop: async (id: string): Promise<TimeEntryType> => {
    const response = await apiClient.post<TimeEntryType>(`/time-entries/${id}/stop`);
    return response.data;
  },

  // ==================== ANALYTICS ====================

  /**
   * Get summary statistics for a time period
   */
  getSummary: async (params?: {
    start_date?: string;
    end_date?: string;
    user_id?: number;
  }): Promise<TimeSummaryStats> => {
    const response = await apiClient.get<TimeSummaryStats>('/time-entries/analytics/summary', {
      params,
    });
    return response.data;
  },

  /**
   * Get weekly time data for trend analysis
   */
  getWeeklyReport: async (params?: {
    weeks?: number;
    user_id?: number;
  }): Promise<WeeklyTimeData[]> => {
    const response = await apiClient.get<WeeklyTimeData[]>(
      '/time-entries/analytics/weekly',
      {
        params,
      }
    );
    return response.data;
  },

  /**
   * Get activity breakdown (time spent per activity)
   */
  getActivityBreakdown: async (params?: {
    start_date?: string;
    end_date?: string;
    user_id?: number;
  }): Promise<ActivityBreakdownData[]> => {
    const response = await apiClient.get<ActivityBreakdownData[]>(
      '/time-entries/analytics/activity-breakdown',
      {
        params,
      }
    );
    return response.data;
  },

  /**
   * Get daily distribution (hours per day of week)
   */
  getDailyDistribution: async (params?: {
    start_date?: string;
    end_date?: string;
    user_id?: number;
  }): Promise<{ day: string; hours: number }[]> => {
    const response = await apiClient.get<{ day: string; hours: number }[]>(
      '/time-entries/analytics/daily-distribution',
      {
        params,
      }
    );
    return response.data;
  },

  // ==================== ACTIVITIES ====================

  /**
   * Get all activities
   */
  getAllActivities: async (): Promise<ActivityType[]> => {
    const response = await apiClient.get<ActivityType[]>('/activities/');
    return response.data;
  },

  /**
   * Get activity by ID
   */
  getActivityById: async (id: number): Promise<ActivityType> => {
    const response = await apiClient.get<ActivityType>(`/activities/${id}`);
    return response.data;
  },

  /**
   * Create new activity
   */
  createActivity: async (activity: ActivityCreateInput): Promise<ActivityType> => {
    const response = await apiClient.post<ActivityType>('/activities/', activity);
    return response.data;
  },

  /**
   * Get active time entry for current user
   */
  getActiveEntry: async (): Promise<TimeEntryType | null> => {
    try {
      const response = await apiClient.get<TimeEntryType>('/time-entries/active/current');
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  },
};
