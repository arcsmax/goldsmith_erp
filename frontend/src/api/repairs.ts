// Repairs API Service — Reparaturverwaltung
import apiClient from './client';
import {
  IntakeChecklistItem,
  RepairCompleteInput,
  RepairDiagnoseInput,
  RepairJob,
  RepairJobCreateInput,
  RepairJobListItem,
  RepairJobStatus,
  RepairPhoto,
  RepairPhotoPhase,
  RepairStatusUpdateInput,
} from '../types';

const BASE = '/repairs';

/** Path helpers for AuthenticatedImage (relative to apiClient baseURL). */
export const repairPhotoPath = (photoId: number): string => `${BASE}/photos/${photoId}`;
export const repairPhotoThumbPath = (photoId: number): string =>
  `${BASE}/photos/${photoId}/thumbnail`;

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
   * Upload a photo to a repair job (multipart, real file upload).
   *
   * Replaces the former JSON `addPhoto` shape, which only ever sent a
   * client-side `blob:` URL string that never reached the server — no file
   * was ever stored, and GDPR erasure of repair photos was a silent no-op.
   */
  uploadPhoto: async (
    repairId: number,
    file: File,
    phase: RepairPhotoPhase,
    notes?: string
  ): Promise<RepairPhoto> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('phase', phase);
    if (notes) formData.append('notes', notes);
    const response = await apiClient.post<RepairPhoto>(`${BASE}/${repairId}/photos`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  /**
   * List all photos for a repair job.
   */
  getPhotos: async (repairId: number): Promise<RepairPhoto[]> => {
    const response = await apiClient.get<RepairPhoto[]>(`${BASE}/${repairId}/photos`);
    return response.data;
  },

  /**
   * Delete a repair photo (file + thumbnail + DB row).
   *
   * The backend auto-downgrades any intake_checklist item linked to this
   * photo back to "open" — callers MUST refetch the repair afterwards
   * rather than trust locally-held checklist state.
   */
  deletePhoto: async (photoId: number): Promise<void> => {
    await apiClient.delete(`${BASE}/photos/${photoId}`);
  },

  /**
   * Replace the full intake checklist (Eingangs-Checkliste).
   *
   * The backend expects the COMPLETE item array on every call (full
   * replace, not a partial patch) — always resubmit every item.
   */
  updateIntakeChecklist: async (
    repairId: number,
    items: IntakeChecklistItem[]
  ): Promise<RepairJob> => {
    const response = await apiClient.put<RepairJob>(`${BASE}/${repairId}/intake-checklist`, {
      items,
    });
    return response.data;
  },
};
