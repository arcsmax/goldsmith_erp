// Valuations API Service — Wertgutachten (Insurance Valuation Certificates)
import apiClient from './client';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ValuationCertificate {
  id: number;
  certificate_number: string;
  order_id: number;
  customer_id: number;
  item_description: string;
  metal_type: string | null;
  metal_weight_g: number | null;
  metal_purity: string | null;
  gemstones_description: string | null;
  /** Gutachtenwert in EUR — financial data, GOLDSMITH/ADMIN only */
  appraised_value: number;
  valuation_date: string;  // ISO 8601
  valid_until: string;     // ISO 8601, typically valuation_date + 2 years
  goldsmith_name: string;
  goldsmith_qualification: string | null;
  pdf_path: string | null;
  created_at: string;
  created_by: number | null;
}

export interface ValuationCreateInput {
  order_id: number;
  customer_id: number;
  item_description: string;
  metal_type?: string;
  metal_weight_g?: number;
  metal_purity?: string;
  gemstones_description?: string;
  appraised_value: number;
  goldsmith_name: string;
  goldsmith_qualification?: string;
}

/**
 * Input for auto-creating a certificate from an existing order.
 * Metal and gemstone data are read from the order automatically.
 */
export interface ValuationCreateFromOrderInput {
  appraised_value: number;
  goldsmith_name: string;
  goldsmith_qualification?: string;
}

export interface ValuationListParams {
  order_id?: number;
  customer_id?: number;
  skip?: number;
  limit?: number;
}

// ── API calls ─────────────────────────────────────────────────────────────────

/**
 * List valuation certificates with optional filters.
 * Financial data — requires GOLDSMITH or ADMIN role.
 */
export const listValuations = async (
  params?: ValuationListParams
): Promise<ValuationCertificate[]> => {
  const response = await apiClient.get<ValuationCertificate[]>('/valuations', {
    params,
  });
  return response.data;
};

/**
 * Get a single certificate by id.
 */
export const getValuation = async (
  id: number
): Promise<ValuationCertificate> => {
  const response = await apiClient.get<ValuationCertificate>(
    `/valuations/${id}`
  );
  return response.data;
};

/**
 * Create a certificate with manually supplied data.
 */
export const createValuation = async (
  data: ValuationCreateInput
): Promise<ValuationCertificate> => {
  const response = await apiClient.post<ValuationCertificate>(
    '/valuations',
    data
  );
  return response.data;
};

/**
 * Auto-create a certificate from an existing order.
 *
 * The API reads order.title, order.alloy, order.metal_type,
 * order.actual_weight_g, and linked gemstone rows to pre-populate the
 * certificate.  The caller provides the appraised value and goldsmith name.
 */
export const createValuationFromOrder = async (
  orderId: number,
  data: ValuationCreateFromOrderInput
): Promise<ValuationCertificate> => {
  const response = await apiClient.post<ValuationCertificate>(
    `/orders/${orderId}/valuations`,
    data
  );
  return response.data;
};

/**
 * Download the valuation certificate as a PDF binary blob.
 *
 * The PDF is rendered on-the-fly on the server.  Use this to trigger a
 * browser download:
 *
 * ```ts
 * const blob = await downloadValuationPdf(cert.id);
 * const url = URL.createObjectURL(blob);
 * const a = document.createElement('a');
 * a.href = url;
 * a.download = `Wertgutachten_${cert.certificate_number}.pdf`;
 * a.click();
 * URL.revokeObjectURL(url);
 * ```
 */
export const downloadValuationPdf = async (id: number): Promise<Blob> => {
  const response = await apiClient.get(`/valuations/${id}/pdf`, {
    responseType: 'blob',
  });
  return response.data as Blob;
};

/**
 * Convenience helper: download and trigger browser save dialog.
 */
export const downloadAndSaveValuationPdf = async (
  id: number,
  certificateNumber: string
): Promise<void> => {
  const blob = await downloadValuationPdf(id);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `Wertgutachten_${certificateNumber}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

export const valuationsApi = {
  list: listValuations,
  get: getValuation,
  create: createValuation,
  createFromOrder: createValuationFromOrder,
  downloadPdf: downloadValuationPdf,
  downloadAndSavePdf: downloadAndSaveValuationPdf,
};
