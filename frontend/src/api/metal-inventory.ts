// Metal Inventory API Service
import apiClient from './client';
import {
  MetalPurchaseType,
  MetalPurchaseListItem,
  MetalPurchaseCreateInput,
  MetalPurchaseUpdateInput,
  InventoryStatistics,
  MaterialUsageCreateInput,
  MaterialUsageRead,
  OrderMaterialAllocation,
  MetalPriceListResponse,
  MetalPriceResponse,
  MetalType,
  CostingMethod,
} from '../types';

export const metalInventoryApi = {
  /**
   * List metal purchases with optional filters.
   * GET /metal-inventory/purchases
   */
  listPurchases: async (params?: {
    metal_type?: MetalType;
    include_depleted?: boolean;
    skip?: number;
    limit?: number;
  }): Promise<MetalPurchaseListItem[]> => {
    const response = await apiClient.get<MetalPurchaseListItem[]>(
      '/metal-inventory/purchases',
      { params }
    );
    return response.data;
  },

  /**
   * Create a new metal purchase record.
   * POST /metal-inventory/purchases
   */
  createPurchase: async (
    purchase: MetalPurchaseCreateInput
  ): Promise<MetalPurchaseType> => {
    const response = await apiClient.post<MetalPurchaseType>(
      '/metal-inventory/purchases',
      purchase
    );
    return response.data;
  },

  /**
   * Get a single metal purchase by ID.
   * GET /metal-inventory/purchases/{id}
   */
  getPurchase: async (id: number): Promise<MetalPurchaseType> => {
    const response = await apiClient.get<MetalPurchaseType>(
      `/metal-inventory/purchases/${id}`
    );
    return response.data;
  },

  /**
   * Update metadata on an existing metal purchase.
   * Only supplier, invoice_number, notes, and lot_number are accepted.
   * PATCH /metal-inventory/purchases/{id}
   */
  updatePurchase: async (
    id: number,
    update: MetalPurchaseUpdateInput
  ): Promise<MetalPurchaseType> => {
    const response = await apiClient.patch<MetalPurchaseType>(
      `/metal-inventory/purchases/${id}`,
      update
    );
    return response.data;
  },

  /**
   * Get comprehensive inventory statistics (value, weight, by-type breakdown).
   * GET /metal-inventory/statistics
   */
  getStatistics: async (): Promise<InventoryStatistics> => {
    const response = await apiClient.get<InventoryStatistics>(
      '/metal-inventory/statistics'
    );
    return response.data;
  },

  /**
   * Consume metal from inventory for an order.
   * POST /metal-inventory/usage?metal_type=...
   */
  consumeMaterial: async (
    usage: MaterialUsageCreateInput,
    metal_type: MetalType
  ): Promise<MaterialUsageRead> => {
    const response = await apiClient.post<MaterialUsageRead>(
      '/metal-inventory/usage',
      usage,
      { params: { metal_type } }
    );
    return response.data;
  },

  /**
   * Get material usage history with optional filters.
   * GET /metal-inventory/usage
   */
  getUsageHistory: async (params?: {
    order_id?: number;
    metal_type?: MetalType;
    skip?: number;
    limit?: number;
  }): Promise<MaterialUsageRead[]> => {
    const response = await apiClient.get<MaterialUsageRead[]>(
      '/metal-inventory/usage',
      { params }
    );
    return response.data;
  },

  /**
   * Preview material allocation without consuming inventory.
   * POST /metal-inventory/allocate-preview?metal_type=...&required_weight_g=...&costing_method=...
   */
  previewAllocation: async (params: {
    metal_type: MetalType;
    required_weight_g: number;
    costing_method?: CostingMethod;
    specific_purchase_id?: number;
  }): Promise<OrderMaterialAllocation> => {
    const response = await apiClient.post<OrderMaterialAllocation>(
      '/metal-inventory/allocate-preview',
      null,
      { params }
    );
    return response.data;
  },

  /**
   * Get current spot prices for all metal alloys.
   * GET /metal-prices
   */
  getSpotPrices: async (): Promise<MetalPriceListResponse> => {
    const response = await apiClient.get<MetalPriceListResponse>('/metal-prices');
    return response.data;
  },

  /**
   * Get current spot price for a single metal alloy.
   * GET /metal-prices/{metal_type}
   */
  getSpotPrice: async (metal_type: MetalType): Promise<MetalPriceResponse> => {
    const response = await apiClient.get<MetalPriceResponse>(
      `/metal-prices/${metal_type}`
    );
    return response.data;
  },
};
