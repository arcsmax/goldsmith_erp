// Scrap Gold (Altgold) API Service
import apiClient from './client';
import type { ApiScrapGold, ApiScrapGoldItem } from './generated';

// ==================== INTERFACES ====================

/**
 * Generated from the backend `ScrapGoldItemRead` (FE-12, W3-02). `alloy` is
 * the canonical alloy/fineness code, e.g. "585", "750", "ag925", "pt950",
 * matching the backend's `AlloyType` values (a string; the old `number` type
 * made every add-item request 422, see DOM-19).
 */
export type ScrapGoldItem = ApiScrapGoldItem;

/**
 * Wire values of the backend `ScrapGoldStatus` enum (db/models.py). The
 * read schema declares `status: str`, so the union is kept here. The last
 * state is "credited" (applied to an invoice); the old "settled" never
 * came back from the API.
 */
export type ScrapGoldStatus = 'received' | 'calculated' | 'signed' | 'credited';

export type ScrapGold = Omit<ApiScrapGold, 'status'> & { status: ScrapGoldStatus };

export interface ScrapGoldCreateInput {
  notes?: string;
}

export interface ScrapGoldItemCreateInput {
  description: string;
  /** Canonical alloy/fineness code — see ScrapGoldItem.alloy. */
  alloy: string;
  weight_g: number;
}

export interface AlloyCalculation {
  alloy: string;
  weight_g: number;
  fine_content_g: number;
  fine_content_percent: number;
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
  calculateAlloy: async (alloy: string, weightG: number): Promise<AlloyCalculation> => {
    const response = await apiClient.get<AlloyCalculation>(
      '/scrap-gold/alloy-calculator',
      { params: { alloy, weight_g: weightG } }
    );
    return response.data;
  },

  /**
   * Upload a photo for a scrap gold item.
   * Accepts JPEG, PNG, or WEBP; returns the updated item on success.
   */
  uploadItemPhoto: async (
    scrapGoldId: number,
    itemId: number,
    file: File
  ): Promise<ScrapGoldItem> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post<ScrapGoldItem>(
      `/scrap-gold/${scrapGoldId}/items/${itemId}/photo`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    return response.data;
  },

  /**
   * Build the URL for serving a scrap gold item photo.
   */
  getItemPhotoUrl: (scrapGoldId: number, itemId: number): string =>
    `/api/v1/scrap-gold/${scrapGoldId}/items/${itemId}/photo`,
};
