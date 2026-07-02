// Customers API Service
import apiClient from './client';
import {
  Customer,
  CustomerListItem,
  CustomerCreateInput,
  CustomerUpdateInput,
  CustomerStats,
  NoGo,
  NoGoCreateInput,
  NoGoConflict,
  StyleProfile,
} from '../types';

export const customersApi = {
  /**
   * Get all customers with optional filtering
   */
  getAll: async (params?: {
    skip?: number;
    limit?: number;
    search?: string;
    customer_type?: string;
    is_active?: boolean;
    tag?: string;
  }): Promise<CustomerListItem[]> => {
    const response = await apiClient.get<CustomerListItem[]>('/customers/', {
      params,
    });
    return response.data;
  },

  /**
   * Search customers (autocomplete)
   */
  search: async (query: string, limit?: number): Promise<CustomerListItem[]> => {
    const response = await apiClient.get<CustomerListItem[]>('/customers/search', {
      params: { q: query, limit },
    });
    return response.data;
  },

  /**
   * Get top customers
   */
  getTop: async (limit?: number, by?: 'revenue' | 'orders' | 'recent'): Promise<any[]> => {
    const response = await apiClient.get<any[]>('/customers/top', {
      params: { limit, by },
    });
    return response.data;
  },

  /**
   * Get single customer by ID
   */
  getById: async (id: number): Promise<Customer> => {
    const response = await apiClient.get<Customer>(`/customers/${id}`);
    return response.data;
  },

  /**
   * Get customer statistics
   */
  getStats: async (id: number): Promise<CustomerStats> => {
    const response = await apiClient.get<CustomerStats>(`/customers/${id}/stats`);
    return response.data;
  },

  /**
   * Create new customer
   */
  create: async (customer: CustomerCreateInput): Promise<Customer> => {
    const response = await apiClient.post<Customer>('/customers/', customer);
    return response.data;
  },

  /**
   * Update customer
   */
  update: async (id: number, customer: CustomerUpdateInput): Promise<Customer> => {
    const response = await apiClient.patch<Customer>(`/customers/${id}`, customer);
    return response.data;
  },

  /**
   * Delete customer (soft delete)
   */
  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/customers/${id}`);
  },

  // ── V1.1: No-Gos & Stilprofil ──────────────────────────────────────────
  getNoGos: async (customerId: number): Promise<NoGo[]> => {
    const response = await apiClient.get<NoGo[]>(`/customers/${customerId}/no-gos`);
    return response.data;
  },
  addNoGo: async (customerId: number, data: NoGoCreateInput): Promise<NoGo> => {
    const response = await apiClient.post<NoGo>(`/customers/${customerId}/no-gos`, data);
    return response.data;
  },
  deleteNoGo: async (customerId: number, noGoId: number): Promise<void> => {
    await apiClient.delete(`/customers/${customerId}/no-gos/${noGoId}`);
  },
  checkNoGoConflicts: async (
    customerId: number,
    candidates: string[]
  ): Promise<NoGoConflict[]> => {
    const params = new URLSearchParams();
    candidates.forEach((c) => params.append('candidate', c));
    const response = await apiClient.get<NoGoConflict[]>(
      `/customers/${customerId}/no-gos/check`,
      { params }
    );
    return response.data;
  },
  getStyleProfile: async (customerId: number): Promise<StyleProfile> => {
    const response = await apiClient.get<StyleProfile>(`/customers/${customerId}/style-profile`);
    return response.data;
  },
  updateStyleProfile: async (
    customerId: number,
    data: Partial<StyleProfile>
  ): Promise<StyleProfile> => {
    const response = await apiClient.patch<StyleProfile>(
      `/customers/${customerId}/style-profile`,
      data
    );
    return response.data;
  },
};
