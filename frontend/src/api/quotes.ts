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

/**
 * DOM-11d: how the customer agreed to the quote — mirrors the backend
 * `CostChangeResponseMethod` enum (models/quote.py ApproveQuoteRequest).
 * Local type (types.ts is out of scope for W2-05).
 */
export type QuoteApprovalMethod = 'in_person' | 'email_reply' | 'phone';

export interface ApproveQuotePayload extends ApproveQuoteInput {
  response_method: QuoteApprovalMethod;
}

/** DOM-11: how a sent quote reached the customer. */
export type QuoteDeliveryMethod = 'email' | 'pdf_manual';

/** Quote as returned by GET /quotes/{id} and POST /quotes/{id}/send. */
export interface QuoteWithDelivery extends Quote {
  delivery_method?: QuoteDeliveryMethod | null;
  sent_at?: string | null;
}

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
  getQuote: async (id: number): Promise<QuoteWithDelivery> => {
    const response = await apiClient.get<QuoteWithDelivery>(`/quotes/${id}`);
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
   * Send a DRAFT quote (versenden). With SMTP the backend emails the PDF
   * (delivery_method "email"); without SMTP it records "pdf_manual" and the
   * caller downloads the PDF. A failed email returns 502 and the quote stays
   * a draft.
   * POST /quotes/{id}/send
   */
  sendQuote: async (id: number): Promise<QuoteWithDelivery> => {
    const response = await apiClient.post<QuoteWithDelivery>(`/quotes/${id}/send`, {});
    return response.data;
  },

  /**
   * Approve a quote: how the customer agreed (required) and an optional
   * signature.
   * POST /quotes/{id}/approve
   */
  approveQuote: async (id: number, data: ApproveQuotePayload): Promise<Quote> => {
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
