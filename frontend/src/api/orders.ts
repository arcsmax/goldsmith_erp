// Orders API Service
import apiClient from './client';
import { OrderType, OrderCreateInput, OrderUpdateInput, OrderComparison } from '../types';

export interface LocationHistoryEntry {
  id: number;
  order_id: number;
  location: string;
  timestamp: string;
  changed_by: number;
}

export const ordersApi = {
  /**
   * Get all orders with pagination and optional server-side filtering.
   * @param options - skip, limit, and optional customer_id filter
   */
  getAll: async (options?: { skip?: number; limit?: number; customer_id?: number }): Promise<OrderType[]> => {
    const skip = options?.skip ?? 0;
    const limit = options?.limit ?? 100;
    const params: Record<string, unknown> = { skip, limit };
    if (options?.customer_id !== undefined) {
      params.customer_id = options.customer_id;
    }
    const response = await apiClient.get<OrderType[]>('/orders/', { params });
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

  /**
   * Change current location of an order.
   * Creates a LocationHistory entry and updates order.current_location.
   */
  changeLocation: async (orderId: number, location: string): Promise<OrderType> => {
    const response = await apiClient.post<OrderType>(`/orders/${orderId}/location`, {
      location,
    });
    return response.data;
  },

  /**
   * Fetch the full location history of an order.
   */
  getLocationHistory: async (orderId: number): Promise<LocationHistoryEntry[]> => {
    const response = await apiClient.get<LocationHistoryEntry[]>(
      `/orders/${orderId}/location-history`
    );
    return response.data;
  },

  /**
   * Fetch Soll/Ist comparison for a completed or delivered order.
   * Returns null when the backend responds with 404 (no comparison data yet).
   */
  getComparison: async (orderId: number): Promise<OrderComparison | null> => {
    try {
      const response = await apiClient.get<OrderComparison>(
        `/orders/${orderId}/comparison`
      );
      return response.data;
    } catch (err: any) {
      if (err.response?.status === 404) {
        return null;
      }
      throw err;
    }
  },
};
