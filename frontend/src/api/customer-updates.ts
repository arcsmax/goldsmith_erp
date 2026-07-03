// Customer Updates & §649 Cost-Change API Client (V1.2) — Kundeninfo & Kostenfreigabe
//
// Types intentionally live in THIS module (not ../types.ts) to avoid the
// pre-existing `CustomerUpdateInput` name collision at types.ts:112 (Customer
// profile edit) — see docs/planning/phase-plans/2026-07-03-v1.2-frontend-plan.md.
import apiClient from './client';

// ---------------------------------------------------------------------------
// Enums — these backend enums serialize by value = lowercase (verbatim).
// ---------------------------------------------------------------------------

export type CustomerUpdateKind = 'progress' | 'cost_change' | 'ready_for_pickup' | 'custom';
export type CustomerUpdateStatus = 'draft' | 'sent' | 'send_failed';
export type UpdateDeliveryMethod = 'email' | 'pdf_manual';
export type CostChangeStatus = 'draft' | 'sent' | 'approved' | 'declined' | 'superseded';
export type CostChangeResponseMethod = 'email_reply' | 'in_person' | 'phone';
export type CostChangeLineItemKind = 'add' | 'remove' | 'change';

// ---------------------------------------------------------------------------
// Interfaces — fields exactly per Backend Contract
// (api/routers/customer_updates.py + models/customer_update.py)
// ---------------------------------------------------------------------------

export interface CustomerUpdate {
  id: number;
  order_id?: number | null;
  repair_job_id?: number | null;
  kind: CustomerUpdateKind;
  subject: string;
  body: string;
  photo_ids: string[];
  cost_change_request_id?: number | null;
  token: string;
  status: CustomerUpdateStatus;
  sent_at?: string | null;
  sent_by: number;
  delivery_method?: UpdateDeliveryMethod | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerUpdateCreateInput {
  kind: CustomerUpdateKind;
  subject?: string;
  body?: string;
  photo_ids?: string[];
}

export interface CustomerUpdateSendResult {
  update: CustomerUpdate;
  delivered: boolean;
  method?: UpdateDeliveryMethod | null;
}

export interface CostChangeLineItem {
  label: string;
  amount: number;
  kind: CostChangeLineItemKind;
}

export interface CostChange {
  id: number;
  order_id: number;
  quote_id?: number | null;
  original_amount: number;
  new_amount: number;
  delta_percent: number;
  reason: string;
  line_items: CostChangeLineItem[];
  status: CostChangeStatus;
  response_method?: CostChangeResponseMethod | null;
  response_evidence?: string | null;
  responded_at?: string | null;
  recorded_by?: number | null;
  created_at: string;
  created_by: number;
  updated_at: string;
}

export interface CostChangeCreateInput {
  new_amount: number;
  reason: string;
  line_items?: CostChangeLineItem[];
}

export interface CostChangeRecordResponseInput {
  status: 'approved' | 'declined';
  response_method: CostChangeResponseMethod;
  response_evidence: string;
}

/**
 * All amounts are NET (netto) — matches Quote.subtotal, not Quote.total.
 * `baseline_source` tells the caller whether `quote_total` (and the derived
 * deltas) were computed against the original Kostenvoranschlag or the latest
 * APPROVED cost-change request (issue #27).
 */
export interface ProjectedCost {
  material_cost: number;
  gemstone_cost: number;
  labor_minutes_billable: number;
  labor_cost: number;
  projected_total: number;
  quote_id?: number | null;
  quote_total?: number | null;
  delta_percent?: number | null;
  delta_abs?: number | null;
  over_threshold: boolean;
  baseline_source?: 'quote' | 'approved_change' | null;
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const customerUpdatesApi = {
  /**
   * List a order's customer-update history (newest-first is a UI concern).
   * GET /orders/{orderId}/updates
   */
  listUpdates: async (orderId: number): Promise<CustomerUpdate[]> => {
    const response = await apiClient.get<CustomerUpdate[]>(`/orders/${orderId}/updates`);
    return response.data;
  },

  /**
   * Create a new draft customer update for an order.
   * POST /orders/{orderId}/updates
   */
  createUpdate: async (
    orderId: number,
    input: CustomerUpdateCreateInput
  ): Promise<CustomerUpdate> => {
    const response = await apiClient.post<CustomerUpdate>(`/orders/${orderId}/updates`, input);
    return response.data;
  },

  /**
   * Send an existing draft update to the customer.
   * POST /updates/{updateId}/send
   */
  sendUpdate: async (updateId: number): Promise<CustomerUpdateSendResult> => {
    const response = await apiClient.post<CustomerUpdateSendResult>(
      `/updates/${updateId}/send`,
      {}
    );
    return response.data;
  },

  /**
   * Confirm manual (PDF) delivery of an update.
   * POST /updates/{updateId}/mark-delivered
   */
  markDelivered: async (updateId: number): Promise<CustomerUpdate> => {
    const response = await apiClient.post<CustomerUpdate>(
      `/updates/${updateId}/mark-delivered`,
      { method: 'pdf_manual' }
    );
    return response.data;
  },

  /**
   * Download a customer update as a PDF blob (pure read — does not mark
   * delivered). Mirrors quotesApi.downloadPdf's responseType:'blob' call;
   * unlike that helper this returns the Blob for the caller to handle.
   * GET /updates/{updateId}/pdf
   */
  downloadUpdatePdf: async (updateId: number): Promise<Blob> => {
    const response = await apiClient.get<Blob>(`/updates/${updateId}/pdf`, {
      responseType: 'blob',
    });
    return response.data;
  },

  /**
   * List a order's §649 cost-change request history.
   * GET /orders/{orderId}/cost-changes
   */
  listCostChanges: async (orderId: number): Promise<CostChange[]> => {
    const response = await apiClient.get<CostChange[]>(`/orders/${orderId}/cost-changes`);
    return response.data;
  },

  /**
   * Create a new §649 cost-change request for an order.
   * POST /orders/{orderId}/cost-changes
   */
  createCostChange: async (
    orderId: number,
    input: CostChangeCreateInput
  ): Promise<CostChange> => {
    const response = await apiClient.post<CostChange>(`/orders/${orderId}/cost-changes`, input);
    return response.data;
  },

  /**
   * Send an existing draft cost-change request to the customer.
   * POST /cost-changes/{costChangeId}/send
   */
  sendCostChange: async (costChangeId: number): Promise<CustomerUpdateSendResult> => {
    const response = await apiClient.post<CustomerUpdateSendResult>(
      `/cost-changes/${costChangeId}/send`,
      {}
    );
    return response.data;
  },

  /**
   * Record the customer's response (approval/decline) to a sent cost-change.
   * POST /cost-changes/{costChangeId}/record-response
   */
  recordCostChangeResponse: async (
    costChangeId: number,
    input: CostChangeRecordResponseInput
  ): Promise<CostChange> => {
    const response = await apiClient.post<CostChange>(
      `/cost-changes/${costChangeId}/record-response`,
      input
    );
    return response.data;
  },

  /**
   * Fetch the projected net cost for an order (§649 cost-watch).
   * GET /orders/{orderId}/projected-cost
   */
  getProjectedCost: async (orderId: number): Promise<ProjectedCost> => {
    const response = await apiClient.get<ProjectedCost>(`/orders/${orderId}/projected-cost`);
    return response.data;
  },
};
