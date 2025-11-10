// Metal Inventory API Service
import apiClient from './client';
import {
  MetalPurchaseType,
  MetalPurchaseCreateInput,
  MetalPurchaseUpdateInput,
  MetalInventorySummary,
  MetalType,
} from '../types';

export const metalInventoryApi = {
  /**
   * Get all metal purchases with optional filters
   */
  getAll: async (params?: {
    skip?: number;
    limit?: number;
    metal_type?: MetalType;
    depleted?: boolean;
  }): Promise<MetalPurchaseType[]> => {
    const response = await apiClient.get<MetalPurchaseType[]>('/metal-inventory/', {
      params,
    });
    return response.data;
  },

  /**
   * Get single metal purchase by ID
   */
  getById: async (id: number): Promise<MetalPurchaseType> => {
    const response = await apiClient.get<MetalPurchaseType>(`/metal-inventory/${id}`);
    return response.data;
  },

  /**
   * Create new metal purchase
   */
  create: async (purchase: MetalPurchaseCreateInput): Promise<MetalPurchaseType> => {
    const response = await apiClient.post<MetalPurchaseType>('/metal-inventory/', purchase);
    return response.data;
  },

  /**
   * Update existing metal purchase
   */
  update: async (
    id: number,
    purchase: MetalPurchaseUpdateInput
  ): Promise<MetalPurchaseType> => {
    const response = await apiClient.put<MetalPurchaseType>(
      `/metal-inventory/${id}`,
      purchase
    );
    return response.data;
  },

  /**
   * Delete metal purchase
   */
  delete: async (id: number): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.delete<{ success: boolean; message: string }>(
      `/metal-inventory/${id}`
    );
    return response.data;
  },

  /**
   * Get inventory summary (aggregated by metal type)
   */
  getSummary: async (): Promise<MetalInventorySummary[]> => {
    const response = await apiClient.get<MetalInventorySummary[]>(
      '/metal-inventory/summary/all'
    );
    return response.data;
  },

  /**
   * Get purchases by metal type
   */
  getByMetalType: async (metalType: MetalType): Promise<MetalPurchaseType[]> => {
    const response = await apiClient.get<MetalPurchaseType[]>(
      `/metal-inventory/by-type/${metalType}`
    );
    return response.data;
  },

  /**
   * Get active (non-depleted) purchases
   */
  getActive: async (): Promise<MetalPurchaseType[]> => {
    const response = await apiClient.get<MetalPurchaseType[]>(
      '/metal-inventory/active/list'
    );
    return response.data;
  },

  /**
   * Get depleted purchases
   */
  getDepleted: async (): Promise<MetalPurchaseType[]> => {
    const response = await apiClient.get<MetalPurchaseType[]>(
      '/metal-inventory/depleted/list'
    );
    return response.data;
  },

  /**
   * Calculate total inventory value
   */
  getTotalValue: async (): Promise<{ total_value: number; currency: string }> => {
    const response = await apiClient.get<{ total_value: number; currency: string }>(
      '/metal-inventory/analytics/total-value'
    );
    return response.data;
  },
};
