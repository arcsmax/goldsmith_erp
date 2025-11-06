/**
 * Materials API
 */
import { apiClient } from './client';

export interface Material {
  id: number;
  name: string;
  material_type: 'gold' | 'silver' | 'platinum' | 'stone' | 'tool' | 'other';
  description?: string;
  unit_price: number;
  stock: number;
  unit: 'g' | 'kg' | 'pcs' | 'ct';
  min_stock: number;
  properties?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface MaterialWithStock extends Material {
  is_low_stock: boolean;
  stock_value: number;
}

export interface MaterialCreate {
  name: string;
  material_type: string;
  description?: string;
  unit_price: number;
  stock?: number;
  unit: string;
  min_stock?: number;
  properties?: Record<string, any>;
}

export interface MaterialUpdate {
  name?: string;
  material_type?: string;
  description?: string;
  unit_price?: number;
  stock?: number;
  unit?: string;
  min_stock?: number;
  properties?: Record<string, any>;
}

export interface MaterialList {
  items: Material[];
  total: number;
  skip: number;
  limit: number;
  has_more: boolean;
}

/**
 * Get materials list
 */
export const getMaterials = async (params?: {
  skip?: number;
  limit?: number;
  material_type?: string;
  search?: string;
}): Promise<MaterialList> => {
  const response = await apiClient.get<MaterialList>('/materials/', { params });
  return response.data;
};

/**
 * Get material by ID
 */
export const getMaterial = async (id: number): Promise<MaterialWithStock> => {
  const response = await apiClient.get<MaterialWithStock>(`/materials/${id}`);
  return response.data;
};

/**
 * Create material
 */
export const createMaterial = async (data: MaterialCreate): Promise<Material> => {
  const response = await apiClient.post<Material>('/materials/', data);
  return response.data;
};

/**
 * Update material
 */
export const updateMaterial = async (
  id: number,
  data: MaterialUpdate
): Promise<Material> => {
  const response = await apiClient.put<Material>(`/materials/${id}`, data);
  return response.data;
};

/**
 * Delete material
 */
export const deleteMaterial = async (id: number): Promise<void> => {
  await apiClient.delete(`/materials/${id}`);
};

/**
 * Get low stock materials
 */
export const getLowStockMaterials = async (
  threshold?: number
): Promise<MaterialWithStock[]> => {
  const response = await apiClient.get<MaterialWithStock[]>('/materials/low-stock', {
    params: { threshold_factor: threshold },
  });
  return response.data;
};

/**
 * Adjust stock
 */
export const adjustStock = async (
  id: number,
  quantity: number,
  operation: 'add' | 'subtract'
): Promise<Material> => {
  const response = await apiClient.patch<Material>(`/materials/${id}/stock`, {
    quantity,
    operation,
  });
  return response.data;
};
