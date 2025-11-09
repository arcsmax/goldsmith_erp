// Activities API Service
import apiClient from './client';
import {
  Activity,
  ActivityCategory,
  ActivityCreateInput,
  ActivityUpdateInput,
} from '../types';

export const activitiesApi = {
  /**
   * Get all activities (with optional filters)
   */
  getAll: async (options?: {
    category?: ActivityCategory;
    sortByUsage?: boolean;
    skip?: number;
    limit?: number;
  }): Promise<Activity[]> => {
    const response = await apiClient.get<Activity[]>('/activities/', {
      params: {
        category: options?.category,
        sort_by_usage: options?.sortByUsage,
        skip: options?.skip || 0,
        limit: options?.limit || 100,
      },
    });
    return response.data;
  },

  /**
   * Get most used activities (for quick-actions)
   */
  getMostUsed: async (limit: number = 10): Promise<Activity[]> => {
    const response = await apiClient.get<Activity[]>('/activities/most-used', {
      params: { limit },
    });
    return response.data;
  },

  /**
   * Get single activity by ID
   */
  getById: async (id: number): Promise<Activity> => {
    const response = await apiClient.get<Activity>(`/activities/${id}`);
    return response.data;
  },

  /**
   * Create new custom activity
   */
  create: async (activity: ActivityCreateInput): Promise<Activity> => {
    const response = await apiClient.post<Activity>('/activities/', activity);
    return response.data;
  },

  /**
   * Update existing activity
   */
  update: async (id: number, activity: ActivityUpdateInput): Promise<Activity> => {
    const response = await apiClient.put<Activity>(`/activities/${id}`, activity);
    return response.data;
  },

  /**
   * Delete activity (only custom activities can be deleted)
   */
  delete: async (id: number): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.delete<{ success: boolean; message: string }>(
      `/activities/${id}`
    );
    return response.data;
  },
};
