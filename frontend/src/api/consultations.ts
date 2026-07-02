import apiClient from './client';
import {
  Consultation,
  ConsultationCreateInput,
  ConsultationListItem,
  ConsultationPhoto,
  ConsultationPhotoKind,
  ConsultationStatus,
  ConsultationUpdateInput,
} from '../types';

const BASE = '/consultations';

/** Path helpers for AuthenticatedImage (relative to apiClient baseURL). */
export const consultationPhotoPath = (photoId: string): string =>
  `${BASE}/photos/${photoId}`;
export const consultationPhotoThumbPath = (photoId: string): string =>
  `${BASE}/photos/${photoId}/thumbnail`;

export const consultationsApi = {
  getAll: async (params?: {
    customer_id?: number;
    status?: ConsultationStatus;
    limit?: number;
    offset?: number;
  }): Promise<ConsultationListItem[]> => {
    const response = await apiClient.get<ConsultationListItem[]>(BASE + '/', { params });
    return response.data;
  },

  getById: async (id: number): Promise<Consultation> => {
    const response = await apiClient.get<Consultation>(`${BASE}/${id}`);
    return response.data;
  },

  create: async (data: ConsultationCreateInput): Promise<Consultation> => {
    const response = await apiClient.post<Consultation>(BASE + '/', data);
    return response.data;
  },

  update: async (id: number, data: ConsultationUpdateInput): Promise<Consultation> => {
    const response = await apiClient.patch<Consultation>(`${BASE}/${id}`, data);
    return response.data;
  },

  convert: async (id: number, target: 'quote' | 'order'): Promise<Consultation> => {
    const response = await apiClient.post<Consultation>(`${BASE}/${id}/convert`, { target });
    return response.data;
  },

  getPhotos: async (id: number): Promise<ConsultationPhoto[]> => {
    const response = await apiClient.get<ConsultationPhoto[]>(`${BASE}/${id}/photos`);
    return response.data;
  },

  uploadPhoto: async (
    id: number,
    file: File,
    kind: ConsultationPhotoKind,
    notes?: string
  ): Promise<ConsultationPhoto> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('kind', kind);
    if (notes) formData.append('notes', notes);
    const response = await apiClient.post<ConsultationPhoto>(`${BASE}/${id}/photos`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  deletePhoto: async (photoId: string): Promise<void> => {
    await apiClient.delete(`${BASE}/photos/${photoId}`);
  },
};
