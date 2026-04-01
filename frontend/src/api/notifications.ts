// Notifications API Service
import apiClient from './client';
import { Notification, NotificationUnreadCount } from '../types';

export const notificationsApi = {
  /**
   * Fetch the current user's notifications.
   * @param limit   Maximum number of items to return (default 10)
   * @param unreadOnly  When true, only unread notifications are returned
   */
  getNotifications: async (
    limit: number = 10,
    unreadOnly: boolean = false
  ): Promise<Notification[]> => {
    const response = await apiClient.get<Notification[]>('/notifications', {
      params: { limit, unread_only: unreadOnly },
    });
    return response.data;
  },

  /**
   * Returns the number of unread notifications for the current user.
   */
  getUnreadCount: async (): Promise<NotificationUnreadCount> => {
    const response = await apiClient.get<NotificationUnreadCount>(
      '/notifications/unread-count'
    );
    return response.data;
  },

  /**
   * Mark a single notification as read.
   */
  markAsRead: async (id: number): Promise<Notification> => {
    const response = await apiClient.put<Notification>(
      `/notifications/${id}/read`
    );
    return response.data;
  },

  /**
   * Mark all of the current user's notifications as read.
   */
  markAllRead: async (): Promise<{ updated_count: number }> => {
    const response = await apiClient.put<{ updated_count: number }>(
      '/notifications/read-all'
    );
    return response.data;
  },
};
