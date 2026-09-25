// Gemstones API (W2-06, DOM-04): stones on an order.
//
// Reads return a role projection: without FINANCIAL_VIEW there is no cost,
// without DESIGN_VIEW (VIEWER) only type, count and the Kundenstein flag.
import apiClient from './client';
import type { ApiGemstone, ApiGemstoneCreate, ApiGemstoneUpdate } from './generated';

export type Gemstone = ApiGemstone;
/** `cost` has a server default (0); a Kundenstein never sends one. */
export type GemstoneCreateInput = Omit<ApiGemstoneCreate, 'cost'> & { cost?: number };
export type GemstoneUpdateInput = ApiGemstoneUpdate;

export const gemstonesApi = {
  list: async (orderId: number): Promise<Gemstone[]> => {
    const response = await apiClient.get<Gemstone[]>(`/orders/${orderId}/gemstones`);
    return response.data;
  },

  create: async (orderId: number, input: GemstoneCreateInput): Promise<Gemstone> => {
    const response = await apiClient.post<Gemstone>(`/orders/${orderId}/gemstones`, input);
    return response.data;
  },

  update: async (gemstoneId: number, input: GemstoneUpdateInput): Promise<Gemstone> => {
    const response = await apiClient.patch<Gemstone>(`/gemstones/${gemstoneId}`, input);
    return response.data;
  },

  remove: async (gemstoneId: number): Promise<void> => {
    await apiClient.delete(`/gemstones/${gemstoneId}`);
  },
};
