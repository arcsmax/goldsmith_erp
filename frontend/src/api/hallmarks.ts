// Hallmarks API Service — Punzierung (Hallmarking)
import apiClient from './client';

// ── Types ─────────────────────────────────────────────────────────────────────

export type HallmarkType =
  | 'fineness_mark'
  | 'makers_mark'
  | 'assay_office'
  | 'common_control'
  | 'date_letter';

export type HallmarkStatus =
  | 'pending'
  | 'submitted'
  | 'approved'
  | 'rejected'
  | 'stamped';

/** German labels for hallmark types shown in UI dropdowns. */
export const HALLMARK_TYPE_LABELS: Record<HallmarkType, string> = {
  fineness_mark: 'Feingehaltsstempel',
  makers_mark: 'Herstellermarke / Meisterpunze',
  assay_office: 'Beschauzeichen der Pruefstelle',
  common_control: 'Gemeinsames Kontrollzeichen (CCM)',
  date_letter: 'Datumsbuchstabe',
};

/** German labels for hallmark statuses shown in badges. */
export const HALLMARK_STATUS_LABELS: Record<HallmarkStatus, string> = {
  pending: 'Ausstehend',
  submitted: 'Eingereicht',
  approved: 'Genehmigt',
  rejected: 'Abgelehnt',
  stamped: 'Gestempelt',
};

/** Badge colour for each hallmark status (Tailwind CSS classes). */
export const HALLMARK_STATUS_COLORS: Record<HallmarkStatus, string> = {
  pending: 'bg-gray-100 text-gray-700',
  submitted: 'bg-blue-100 text-blue-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  stamped: 'bg-amber-100 text-amber-800',
};

export interface Hallmark {
  id: number;
  order_id: number;
  hallmark_type: HallmarkType;
  status: HallmarkStatus;
  assay_office: string | null;
  certificate_number: string | null;
  submitted_at: string | null;
  approved_at: string | null;
  stamped_at: string | null;
  notes: string | null;
  created_at: string;
  created_by: number | null;
}

export interface HallmarkCreateInput {
  hallmark_type: HallmarkType;
  assay_office?: string;
  notes?: string;
}

export interface HallmarkUpdateInput {
  assay_office?: string;
  certificate_number?: string;
  notes?: string;
}

export interface HallmarkStatusUpdateInput {
  new_status: HallmarkStatus;
  certificate_number?: string;
  notes?: string;
}

// ── API calls ─────────────────────────────────────────────────────────────────

/**
 * List all hallmark records for an order, newest first.
 */
export const getHallmarksForOrder = async (
  orderId: number
): Promise<Hallmark[]> => {
  const response = await apiClient.get<Hallmark[]>(
    `/orders/${orderId}/hallmarks`
  );
  return response.data;
};

/**
 * Get a single hallmark record.
 */
export const getHallmark = async (
  orderId: number,
  hallmarkId: number
): Promise<Hallmark> => {
  const response = await apiClient.get<Hallmark>(
    `/orders/${orderId}/hallmarks/${hallmarkId}`
  );
  return response.data;
};

/**
 * Create a new hallmark record for an order.
 * Starts in PENDING status.
 */
export const createHallmark = async (
  orderId: number,
  data: HallmarkCreateInput
): Promise<Hallmark> => {
  const response = await apiClient.post<Hallmark>(
    `/orders/${orderId}/hallmarks`,
    data
  );
  return response.data;
};

/**
 * Update mutable fields on a hallmark record (no status change).
 */
export const updateHallmark = async (
  orderId: number,
  hallmarkId: number,
  data: HallmarkUpdateInput
): Promise<Hallmark> => {
  const response = await apiClient.patch<Hallmark>(
    `/orders/${orderId}/hallmarks/${hallmarkId}`,
    data
  );
  return response.data;
};

/**
 * Transition hallmark to a new status.
 *
 * Valid transitions:
 *   PENDING -> SUBMITTED
 *   SUBMITTED -> APPROVED | REJECTED
 *   APPROVED -> STAMPED
 *   REJECTED -> SUBMITTED  (re-submission after rework)
 */
export const updateHallmarkStatus = async (
  orderId: number,
  hallmarkId: number,
  data: HallmarkStatusUpdateInput
): Promise<Hallmark> => {
  const response = await apiClient.post<Hallmark>(
    `/orders/${orderId}/hallmarks/${hallmarkId}/status`,
    data
  );
  return response.data;
};

/**
 * Delete a hallmark record.
 * Only allowed when status === 'pending'.
 */
export const deleteHallmark = async (
  orderId: number,
  hallmarkId: number
): Promise<void> => {
  await apiClient.delete(`/orders/${orderId}/hallmarks/${hallmarkId}`);
};

export const hallmarksApi = {
  getForOrder: getHallmarksForOrder,
  get: getHallmark,
  create: createHallmark,
  update: updateHallmark,
  updateStatus: updateHallmarkStatus,
  delete: deleteHallmark,
};
