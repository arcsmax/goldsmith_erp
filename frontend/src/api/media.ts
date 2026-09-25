// Media API — unified media_assets endpoints (routers/media.py, ARCH phase 4).
//
// Order photos are also media assets with the same id, so the photo tab can
// read and toggle `customer_visible` without a second id mapping. Reading
// needs DESIGN_VIEW (GOLDSMITH/ADMIN); the toggle also needs the owner's
// edit permission. Files are served only through authenticated endpoints,
// render them with AuthenticatedImage.
import apiClient from './client';
import type { components } from './generated';

export type MediaAsset = components['schemas']['MediaAssetRead'];
export type MediaOwnerType = components['schemas']['MediaOwnerType'];

export const mediaFilePath = (mediaId: string): string => `/media/${mediaId}`;
export const mediaThumbnailPath = (mediaId: string): string => `/media/${mediaId}/thumbnail`;

export const mediaApi = {
  listForOwner: async (ownerType: MediaOwnerType, ownerId: number): Promise<MediaAsset[]> => {
    const response = await apiClient.get<MediaAsset[]>('/media', {
      params: { owner_type: ownerType, owner_id: ownerId },
    });
    return response.data ?? [];
  },

  /** "Für Kunden sichtbar": the photo may go into Kundeninfo and the status report. */
  setCustomerVisible: async (mediaId: string, customerVisible: boolean): Promise<MediaAsset> => {
    const response = await apiClient.patch<MediaAsset>(`/media/${mediaId}`, {
      customer_visible: customerVisible,
    });
    return response.data;
  },
};
