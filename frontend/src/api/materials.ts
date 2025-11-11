// Materials API Service
import apiClient from './client';
import { MaterialType, MaterialCreateInput, MaterialUpdateInput } from '../types';

export const materialsApi = {
  /**
   * Get all materials with pagination
   * @param options - Optional object with skip and limit parameters
   */
  getAll: async (options?: { skip?: number; limit?: number }): Promise<MaterialType[]> => {
    const skip = options?.skip ?? 0;
    const limit = options?.limit ?? 100;
    const response = await apiClient.get<MaterialType[]>('/materials/', {
      params: { skip, limit },
    });
    return response.data;
  },

  /**
   * Get single material by ID
   */
  getById: async (id: number): Promise<MaterialType> => {
    const response = await apiClient.get<MaterialType>(`/materials/${id}`);
    return response.data;
  },

  /**
   * Create new material
   */
  create: async (material: MaterialCreateInput): Promise<MaterialType> => {
    const response = await apiClient.post<MaterialType>('/materials/', material);
    return response.data;
  },

  /**
   * Update existing material
   */
  update: async (id: number, material: MaterialUpdateInput): Promise<MaterialType> => {
    const response = await apiClient.put<MaterialType>(`/materials/${id}`, material);
    return response.data;
  },

  /**
   * Delete material
   */
  delete: async (id: number): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.delete<{ success: boolean; message: string }>(
      `/materials/${id}`
    );
    return response.data;
  },

  /**
   * Adjust material stock
   */
  adjustStock: async (
    id: number,
    quantity: number,
    operation: 'add' | 'subtract' = 'add'
  ): Promise<MaterialType> => {
    const response = await apiClient.post<MaterialType>(`/materials/${id}/adjust-stock`, {
      quantity,
      operation,
    });
    return response.data;
  },

  /**
   * Get low stock materials
   */
  getLowStock: async (threshold: number = 10.0): Promise<MaterialType[]> => {
    const response = await apiClient.get<MaterialType[]>('/materials/low-stock/alert', {
      params: { threshold },
    });
    return response.data;
  },

  /**
   * Get total stock value
   */
  getTotalStockValue: async (): Promise<{ total_value: number; currency: string }> => {
    const response = await apiClient.get<{ total_value: number; currency: string }>(
      '/materials/analytics/stock-value'
    );
    return response.data;
  },
};
