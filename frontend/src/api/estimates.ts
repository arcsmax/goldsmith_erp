// Estimates API Service — V1.3 Labor Estimator
import type { LaborEstimateRequest, LaborEstimateResponse, CalibrationResponse } from "../types";
import apiClient from "./client";

export const estimatesApi = {
  /**
   * Request a statistical labor-hours + labor-cost estimate.
   * POST /estimates/labor
   */
  getLaborEstimate: async (req: LaborEstimateRequest): Promise<LaborEstimateResponse> => {
    const { data } = await apiClient.post<LaborEstimateResponse>("/estimates/labor", req);
    return data;
  },

  /**
   * Fetch estimator accuracy calibration metrics.
   * GET /estimates/accuracy
   */
  getAccuracy: async (params?: { order_type?: string; limit?: number }): Promise<CalibrationResponse> => {
    const { data } = await apiClient.get<CalibrationResponse>("/estimates/accuracy", { params });
    return data;
  },
};
