// Calendar API Service
import apiClient from './client';
import { OrderType } from '../types';

export const calendarApi = {
  /**
   * Get orders with deadlines in a date range for calendar display
   * @param start - ISO date string for range start
   * @param end - ISO date string for range end
   */
  getDeadlines: async (start?: string, end?: string): Promise<OrderType[]> => {
    const params = new URLSearchParams();
    if (start) params.append('start', start);
    if (end) params.append('end', end);
    const { data } = await apiClient.get<OrderType[]>(`/orders/calendar/deadlines?${params}`);
    return data;
  },
};
