// Metal Types API Service
// Provides access to the unified metal-type list (built-in + custom)
// and CRUD operations for custom types (ADMIN only).
import apiClient from './client';
import {
  MetalTypeOption,
  CustomMetalTypeCreate,
  CustomMetalTypeUpdate,
  CustomMetalTypeRead,
} from '../types';

export const metalTypesApi = {
  /**
   * List all metal types — built-in enum values + active custom types.
   * Sorted by base_metal then display_name.
   * GET /api/v1/metal-types
   */
  getAll: async (): Promise<MetalTypeOption[]> => {
    const response = await apiClient.get<MetalTypeOption[]>('/metal-types');
    return response.data;
  },

  /**
   * Create a new custom metal type (ADMIN only).
   * POST /api/v1/metal-types
   */
  create: async (data: CustomMetalTypeCreate): Promise<CustomMetalTypeRead> => {
    const response = await apiClient.post<CustomMetalTypeRead>('/metal-types', data);
    return response.data;
  },

  /**
   * Update an existing custom metal type (ADMIN only).
   * PUT /api/v1/metal-types/{id}
   */
  update: async (id: number, data: CustomMetalTypeUpdate): Promise<CustomMetalTypeRead> => {
    const response = await apiClient.put<CustomMetalTypeRead>(`/metal-types/${id}`, data);
    return response.data;
  },

  /**
   * Soft-delete (deactivate) a custom metal type (ADMIN only).
   * DELETE /api/v1/metal-types/{id}
   */
  remove: async (id: number): Promise<void> => {
    await apiClient.delete(`/metal-types/${id}`);
  },
};
