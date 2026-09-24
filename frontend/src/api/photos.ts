// Photos API — order photo endpoints (routers/photos.py).
//
// Photos are design IP: every endpoint needs DESIGN_VIEW (read) or
// ORDER_EDIT (upload/delete), i.e. GOLDSMITH/ADMIN. Files are served only
// through the authenticated /photos/{id}/file|thumbnail endpoints, so render
// them with AuthenticatedImage, never a raw <img src={file_path}>.
import apiClient from './client';
import type { OrderPhoto } from '../types';

/** Mirrors settings.PHOTO_MAX_SIZE_MB (backend default 8). */
export const MAX_PHOTO_MB = 8;
export const MAX_PHOTO_BYTES = MAX_PHOTO_MB * 1024 * 1024;

export interface PhotoUploadOptions {
  notes?: string;
  /** Called with 0–100 while the file is sent. */
  onProgress?: (percent: number) => void;
}

export const photoThumbnailPath = (photoId: string): string =>
  `/photos/${photoId}/thumbnail`;

export const photoFilePath = (photoId: string): string => `/photos/${photoId}/file`;

export const photosApi = {
  getForOrder: (orderId: number) =>
    apiClient.get<OrderPhoto[]>(`/orders/${orderId}/photos`),

  /** Upload one photo (multipart field `file`, optional `notes`). */
  upload: async (
    orderId: number,
    file: File,
    options: PhotoUploadOptions = {}
  ): Promise<OrderPhoto> => {
    const formData = new FormData();
    formData.append('file', file);
    if (options.notes) formData.append('notes', options.notes);
    const response = await apiClient.post<OrderPhoto>(`/orders/${orderId}/photos`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (event: { loaded: number; total?: number }) => {
        if (!options.onProgress || !event.total) return;
        options.onProgress(Math.round((event.loaded / event.total) * 100));
      },
    });
    return response.data;
  },
};

const SIZE_FALLBACK = `Foto ist zu groß. Maximum: ${MAX_PHOTO_MB} MB.`;
const FORMAT_FALLBACK = 'Foto konnte nicht verarbeitet werden. Erlaubt sind JPEG, PNG und WEBP.';
const NETWORK_MESSAGE = 'Keine Verbindung zum Server. Foto wurde nicht hochgeladen.';
const GENERIC_MESSAGE = 'Foto konnte nicht hochgeladen werden. Bitte erneut versuchen.';

/** Client-side size check, same limit and wording as the backend. */
export function getPhotoSizeError(file: File): string | null {
  return file.size > MAX_PHOTO_BYTES ? SIZE_FALLBACK : null;
}

/**
 * German message for a failed upload. 413 (request-size middleware) and
 * 422 (PhotoValidationError) carry a German `detail` string, which is shown
 * as is; a missing or structured detail falls back to a German text.
 */
export function getPhotoUploadErrorMessage(err: unknown): string {
  const response = (err as { response?: { status?: number; data?: unknown } }).response;
  if (!response) return NETWORK_MESSAGE;
  const data = response.data as { detail?: unknown } | undefined;
  const detail = data && typeof data === 'object' ? data.detail : undefined;
  if (typeof detail === 'string' && detail.trim().length > 0) return detail;
  if (response.status === 413) return SIZE_FALLBACK;
  if (response.status === 422) return FORMAT_FALLBACK;
  return GENERIC_MESSAGE;
}
