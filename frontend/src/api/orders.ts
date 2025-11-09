// Orders API Service
import apiClient from './client';
import { OrderType, OrderCreateInput, OrderUpdateInput } from '../types';

export const ordersApi = {
  /**
   * Get all orders with pagination
   */
  getAll: async (skip: number = 0, limit: number = 100): Promise<OrderType[]> => {
    const response = await apiClient.get<OrderType[]>('/orders/', {
      params: { skip, limit },
    });
    return response.data;
  },

  /**
   * Get single order by ID
   */
  getById: async (id: number): Promise<OrderType> => {
    const response = await apiClient.get<OrderType>(`/orders/${id}`);
    return response.data;
  },

  /**
   * Create new order
   */
  create: async (order: OrderCreateInput): Promise<OrderType> => {
    const response = await apiClient.post<OrderType>('/orders/', order);
    return response.data;
  },

  /**
   * Update existing order
   */
  update: async (id: number, order: OrderUpdateInput): Promise<OrderType> => {
    const response = await apiClient.put<OrderType>(`/orders/${id}`, order);
    return response.data;
  },

  /**
   * Delete order
   */
  delete: async (id: number): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.delete<{ success: boolean; message: string }>(
      `/orders/${id}`
    );
    return response.data;
  },

  /**
   * Update order status
   */
  updateStatus: async (
    id: number,
    status: 'new' | 'in_progress' | 'completed' | 'delivered'
  ): Promise<OrderType> => {
    const response = await apiClient.patch<OrderType>(`/orders/${id}/status`, { status });
    return response.data;
  },
};
