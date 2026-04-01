// Repairs API Service — Reparaturverwaltung
import apiClient from './client';
import {
  RepairCompleteInput,
  RepairDiagnoseInput,
  RepairJob,
  RepairJobCreateInput,
  RepairJobListItem,
  RepairJobStatus,
  RepairPhoto,
  RepairStatusUpdateInput,
} from '../types';

const BASE = '/repairs';

export const repairsApi = {
  /**
   * List repair jobs with optional filters.
   */
  getAll: async (params?: {
    skip?: number;
    limit?: number;
    status?: RepairJobStatus;
    customer_id?: number;
    search?: string;
  }): Promise<RepairJobListItem[]> => {
    const response = await apiClient.get<RepairJobListItem[]>(BASE + '/', { params });
    return response.data;
  },

  /**
   * Get full repair job detail including photos.
   */
  getById: async (id: number): Promise<RepairJob> => {
    const response = await apiClient.get<RepairJob>(`${BASE}/${id}`);
    return response.data;
  },

  /**
   * Create a new repair intake (Eingang).
   */
  create: async (data: RepairJobCreateInput): Promise<RepairJob> => {
    const response = await apiClient.post<RepairJob>(BASE + '/', data);
    return response.data;
  },

  /**
   * Diagnose the repair piece and record the cost estimate.
   * Advances status: RECEIVED -> DIAGNOSED -> QUOTED
   */
  diagnose: async (id: number, data: RepairDiagnoseInput): Promise<RepairJob> => {
    const response = await apiClient.post<RepairJob>(`${BASE}/${id}/diagnose`, data);
    return response.data;
  },

  /**
   * Customer approved the quote.
   * Advances status: QUOTED -> APPROVED
   */
  approve: async (id: number, data?: RepairStatusUpdateInput): Promise<RepairJob> => {
    const response = await apiClient.post<RepairJob>(`${BASE}/${id}/approve`, data ?? {});
    return response.data;
  },

  /**
   * Begin repair work.
   * Advances status: APPROVED -> IN_REPAIR
   */
  startRepair: async (id: number): Promise<RepairJob> => {
    const response = await apiClient.post<RepairJob>(`${BASE}/${id}/start`, {});
    return response.data;
  },

  /**
   * Submit for quality check.
   * Advances status: IN_REPAIR -> QUALITY_CHECK
   */
  submitQualityCheck: async (id: number): Promise<RepairJob> => {
    const response = await apiClient.post<RepairJob>(`${BASE}/${id}/quality-check`, {});
    return response.data;
  },

  /**
   * Mark repair as READY (Fertigmeldung), notify customer.
   * Advances status: QUALITY_CHECK -> READY
   */
  complete: async (id: number, data: RepairCompleteInput): Promise<RepairJob> => {
    const response = await apiClient.post<RepairJob>(`${BASE}/${id}/complete`, data);
    return response.data;
  },

  /**
   * Confirm customer pickup.
   * Advances status: READY -> PICKED_UP
   */
  pickup: async (id: number): Promise<RepairJob> => {
    const response = await apiClient.post<RepairJob>(`${BASE}/${id}/pickup`, {});
    return response.data;
  },

  /**
   * Cancel the repair from any active state.
   */
  cancel: async (id: number, data?: RepairStatusUpdateInput): Promise<RepairJob> => {
    const response = await apiClient.post<RepairJob>(`${BASE}/${id}/cancel`, data ?? {});
    return response.data;
  },

  /**
   * Soft-delete (only PICKED_UP or CANCELLED repairs).
   */
  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`${BASE}/${id}`);
  },

  /**
   * Add a photo to a repair job.
   */
  addPhoto: async (
    repairId: number,
    data: { phase: string; file_path: string; notes?: string }
  ): Promise<RepairPhoto> => {
    const response = await apiClient.post<RepairPhoto>(`${BASE}/${repairId}/photos`, data);
    return response.data;
  },

  /**
   * List all photos for a repair job.
   */
  getPhotos: async (repairId: number): Promise<RepairPhoto[]> => {
    const response = await apiClient.get<RepairPhoto[]>(`${BASE}/${repairId}/photos`);
    return response.data;
  },
};
