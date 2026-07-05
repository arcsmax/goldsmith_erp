// Quotes API Service — Kostenvoranschlag
import apiClient from './client';
import {
  Quote,
  QuoteListItem,
  QuoteListResponse,
  QuoteCreateInput,
  QuoteUpdateInput,
  QuoteLineItemInput,
  ApproveQuoteInput,
  RejectQuoteInput,
  EstimatorMetadata,
} from '../types';

export interface QuoteFilterParams {
  status?: string;
  customer_id?: number;
  skip?: number;
  limit?: number;
}

export const quotesApi = {
  /**
   * Create a new quote (Kostenvoranschlag erstellen).
   * POST /quotes
   */
  createQuote: async (data: QuoteCreateInput): Promise<Quote> => {
    const response = await apiClient.post<Quote>('/quotes/', data);
    return response.data;
  },

  /**
   * List quotes with optional filters.
   * GET /quotes
   */
  getQuotes: async (params?: QuoteFilterParams): Promise<QuoteListResponse> => {
    const response = await apiClient.get<QuoteListResponse>('/quotes/', { params });
    return response.data;
  },

  /**
   * Fetch a single quote by ID (includes line items).
   * GET /quotes/{id}
   */
  getQuote: async (id: number): Promise<Quote> => {
    const response = await apiClient.get<Quote>(`/quotes/${id}`);
    return response.data;
  },

  /**
   * Update quote status, validity, or notes.
   * PUT /quotes/{id}
   */
  updateQuote: async (id: number, data: QuoteUpdateInput): Promise<Quote> => {
    const response = await apiClient.put<Quote>(`/quotes/${id}`, data);
    return response.data;
  },

  /**
   * Mark quote as SENT (versenden).
   * POST /quotes/{id}/send
   */
  sendQuote: async (id: number): Promise<Quote> => {
    const response = await apiClient.post<Quote>(`/quotes/${id}/send`, {});
    return response.data;
  },

  /**
   * Approve a quote with optional customer signature.
   * POST /quotes/{id}/approve
   */
  approveQuote: async (id: number, data: ApproveQuoteInput): Promise<Quote> => {
    const response = await apiClient.post<Quote>(`/quotes/${id}/approve`, data);
    return response.data;
  },

  /**
   * Reject a quote with optional reason.
   * POST /quotes/{id}/reject
   */
  rejectQuote: async (id: number, data: RejectQuoteInput): Promise<Quote> => {
    const response = await apiClient.post<Quote>(`/quotes/${id}/reject`, data);
    return response.data;
  },

  /**
   * Convert an approved quote into a confirmed order.
   * POST /quotes/{id}/convert
   */
  convertQuote: async (id: number): Promise<Quote> => {
    const response = await apiClient.post<Quote>(`/quotes/${id}/convert`, {});
    return response.data;
  },

  /**
   * Delete a DRAFT or REJECTED quote.
   * DELETE /quotes/{id}
   */
  deleteQuote: async (id: number): Promise<void> => {
    await apiClient.delete(`/quotes/${id}`);
  },

  /**
   * Add a line item to a DRAFT quote; returns the quote with recomputed totals.
   * POST /quotes/{id}/line-items
   */
  addLineItem: async (quoteId: number, item: QuoteLineItemInput): Promise<Quote> => {
    const response = await apiClient.post<Quote>(`/quotes/${quoteId}/line-items`, item);
    return response.data;
  },

  /**
   * Update a line item on a DRAFT quote; returns the quote with recomputed totals.
   * PATCH /quotes/{id}/line-items/{itemId}
   */
  updateLineItem: async (
    quoteId: number,
    itemId: number,
    item: QuoteLineItemInput
  ): Promise<Quote> => {
    const response = await apiClient.patch<Quote>(
      `/quotes/${quoteId}/line-items/${itemId}`,
      item
    );
    return response.data;
  },

  /**
   * Remove a line item from a DRAFT quote; returns the quote with recomputed totals.
   * DELETE /quotes/{id}/line-items/{itemId}
   */
  deleteLineItem: async (quoteId: number, itemId: number): Promise<Quote> => {
    const response = await apiClient.delete<Quote>(
      `/quotes/${quoteId}/line-items/${itemId}`
    );
    return response.data;
  },

  /**
   * Download quote as PDF (Kostenvoranschlag PDF).
   * GET /quotes/{id}/pdf
   */
  downloadPdf: async (id: number, quoteNumber: string): Promise<void> => {
    const response = await apiClient.get(`/quotes/${id}/pdf`, {
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `kostenvoranschlag_${quoteNumber}.pdf`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};
