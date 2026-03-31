// Scrap Gold (Altgold) API Service
import apiClient from './client';

// ==================== INTERFACES ====================

export interface ScrapGoldItem {
  id: number;
  scrap_gold_id: number;
  description: string;
  alloy: number;
  weight_g: number;
  fine_content_g: number;
  photo_path: string | null;
  created_at: string;
}

export interface ScrapGold {
  id: number;
  order_id: number;
  customer_id: number;
  status: ScrapGoldStatus;
  total_fine_gold_g: number;
  total_value_eur: number;
  gold_price_per_g: number;
  price_source: string | null;
  signature_data: string | null;
  signed_at: string | null;
  notes: string | null;
  items: ScrapGoldItem[];
  created_at: string;
  updated_at: string;
}

export type ScrapGoldStatus = 'received' | 'calculated' | 'signed' | 'settled';

export interface ScrapGoldCreateInput {
  notes?: string;
}

export interface ScrapGoldItemCreateInput {
  description: string;
  alloy: number;
  weight_g: number;
}

export interface AlloyCalculation {
  alloy: number;
  weight_g: number;
  fine_content_g: number;
  fine_percentage: number;
}

export interface ScrapGoldSignInput {
  signature_data: string;
}

// ==================== API ====================

export const scrapGoldApi = {
  /**
   * Get scrap gold entry for an order
   */
  getForOrder: async (orderId: number): Promise<ScrapGold | null> => {
    try {
      const response = await apiClient.get<ScrapGold>(`/orders/${orderId}/scrap-gold`);
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  },

  /**
   * Create scrap gold entry for an order
   */
  create: async (orderId: number, input?: ScrapGoldCreateInput): Promise<ScrapGold> => {
    const response = await apiClient.post<ScrapGold>(
      `/orders/${orderId}/scrap-gold`,
      input || {}
    );
    return response.data;
  },

  /**
   * Add item to scrap gold entry
   */
  addItem: async (scrapGoldId: number, item: ScrapGoldItemCreateInput): Promise<ScrapGoldItem> => {
    const response = await apiClient.post<ScrapGoldItem>(
      `/scrap-gold/${scrapGoldId}/items`,
      item
    );
    return response.data;
  },

  /**
   * Remove item from scrap gold entry
   */
  removeItem: async (scrapGoldId: number, itemId: number): Promise<void> => {
    await apiClient.delete(`/scrap-gold/${scrapGoldId}/items/${itemId}`);
  },

  /**
   * Recalculate totals for scrap gold entry
   */
  calculate: async (scrapGoldId: number): Promise<ScrapGold> => {
    const response = await apiClient.post<ScrapGold>(
      `/scrap-gold/${scrapGoldId}/calculate`
    );
    return response.data;
  },

  /**
   * Submit digital signature for scrap gold entry
   */
  sign: async (scrapGoldId: number, signatureData: string): Promise<ScrapGold> => {
    const response = await apiClient.post<ScrapGold>(
      `/scrap-gold/${scrapGoldId}/sign`,
      { signature_data: signatureData }
    );
    return response.data;
  },

  /**
   * Calculate fine content for an alloy and weight (server-side)
   */
  calculateAlloy: async (alloy: number, weightG: number): Promise<AlloyCalculation> => {
    const response = await apiClient.get<AlloyCalculation>(
      '/scrap-gold/alloy-calculator',
      { params: { alloy, weight_g: weightG } }
    );
    return response.data;
  },
};
