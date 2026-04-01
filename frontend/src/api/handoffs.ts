// Handoffs API Service — Übergaben zwischen Goldschmieden
import apiClient from './client';

export interface HandoffCreateInput {
  to_user_id: number;
  handoff_type: string;
  notes?: string;
}

export interface HandoffResponseInput {
  response_notes?: string;
}

export const handoffsApi = {
  create: (orderId: number, data: HandoffCreateInput) =>
    apiClient.post(`/orders/${orderId}/handoff`, data),

  accept: (id: number, data?: HandoffResponseInput) =>
    apiClient.put(`/handoffs/${id}/accept`, data || {}),

  decline: (id: number, data: { response_notes: string }) =>
    apiClient.put(`/handoffs/${id}/decline`, data),

  getPending: () =>
    apiClient.get('/handoffs/pending'),

  getForOrder: (orderId: number) =>
    apiClient.get(`/orders/${orderId}/handoffs`),
};
