// Invoices API Service — Rechnungsverwaltung
import apiClient from './client';
import {
  Invoice,
  InvoiceListItem,
  InvoiceListResponse,
  InvoiceCreateInput,
  InvoiceUpdateInput,
  MarkPaidInput,
} from '../types';

export interface InvoiceFilterParams {
  status?: string;
  customer_id?: number; // server-side filter (W2-12, DOM-38)
  from?: string; // ISO date string
  to?: string;   // ISO date string
  skip?: number;
  limit?: number;
}

export const invoicesApi = {
  /**
   * Create a new invoice from an existing order.
   * POST /invoices
   */
  createFromOrder: async (data: InvoiceCreateInput): Promise<Invoice> => {
    const response = await apiClient.post<Invoice>('/invoices/', data);
    return response.data;
  },

  /**
   * List invoices with optional filters.
   * GET /invoices
   */
  getInvoices: async (params?: InvoiceFilterParams): Promise<InvoiceListResponse> => {
    const response = await apiClient.get<InvoiceListResponse>('/invoices/', { params });
    return response.data;
  },

  /**
   * Fetch a single invoice by ID (includes line items).
   * GET /invoices/{id}
   */
  getInvoice: async (id: number): Promise<Invoice> => {
    const response = await apiClient.get<Invoice>(`/invoices/${id}`);
    return response.data;
  },

  /**
   * Update invoice status, due date, or notes.
   * PUT /invoices/{id}
   */
  updateInvoice: async (id: number, data: InvoiceUpdateInput): Promise<Invoice> => {
    const response = await apiClient.put<Invoice>(`/invoices/${id}`, data);
    return response.data;
  },

  /**
   * Mark an invoice as paid (Als bezahlt markieren).
   * POST /invoices/{id}/mark-paid
   */
  markAsPaid: async (id: number, data: MarkPaidInput): Promise<Invoice> => {
    const response = await apiClient.post<Invoice>(`/invoices/${id}/mark-paid`, data);
    return response.data;
  },

  /**
   * Cancel/void an invoice (Rechnung stornieren).
   *
   * Status transitions go through the dedicated action endpoints, not
   * `PUT /invoices/{id}` — see ADR-2026-09-25 (price-semantics), decision 5.
   * POST /invoices/{id}/cancel
   */
  cancelInvoice: async (id: number): Promise<Invoice> => {
    const response = await apiClient.post<Invoice>(`/invoices/${id}/cancel`);
    return response.data;
  },

  /**
   * Stornorechnung erstellen (W2-04): reverses an issued (also a paid)
   * invoice with a negative invoice that links to it. Returns the Storno.
   * POST /invoices/{id}/storno
   */
  createStorno: async (id: number, reason?: string): Promise<Invoice> => {
    const response = await apiClient.post<Invoice>(`/invoices/${id}/storno`, {
      reason: reason?.trim() || null,
    });
    return response.data;
  },
};
