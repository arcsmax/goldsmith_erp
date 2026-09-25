// Standorte (W8): the configurable workshop locations behind every
// "Standort" dropdown. Staff read the active list; ADMIN manages it under
// Systemübersicht > Standorte. Deactivating keeps the location on history.
import apiClient from './client';
import type { Schema } from './generated';

export type WorkshopLocation = Schema<'LocationRead'>;
export type LocationKind = WorkshopLocation['kind'];
export type LocationCreateInput = Schema<'LocationCreate'>;
export type LocationUpdateInput = Schema<'LocationUpdate'>;

/** German labels for the location kinds (one term per concept). */
export const LOCATION_KIND_LABELS: Record<LocationKind, string> = {
  bench: 'Werkbank',
  safe: 'Tresor',
  showroom: 'Ausstellung',
  external: 'Extern',
  other: 'Sonstiges',
};

export const LOCATION_KINDS = Object.keys(LOCATION_KIND_LABELS) as LocationKind[];

/** Active locations for the picker, in the ADMIN's order. */
export const getActiveLocations = async (): Promise<WorkshopLocation[]> => {
  const response = await apiClient.get<WorkshopLocation[]>('/locations', {
    params: { active: true },
  });
  return response.data;
};

/** Every location including deactivated ones (ADMIN only). */
export const getAllLocations = async (): Promise<WorkshopLocation[]> => {
  const response = await apiClient.get<WorkshopLocation[]>('/admin/locations');
  return response.data;
};

export const createLocation = async (data: LocationCreateInput): Promise<WorkshopLocation> => {
  const response = await apiClient.post<WorkshopLocation>('/admin/locations', data);
  return response.data;
};

export const updateLocation = async (
  id: number,
  data: LocationUpdateInput,
): Promise<WorkshopLocation> => {
  const response = await apiClient.patch<WorkshopLocation>(`/admin/locations/${id}`, data);
  return response.data;
};

export const deactivateLocation = async (id: number): Promise<WorkshopLocation> => {
  const response = await apiClient.delete<WorkshopLocation>(`/admin/locations/${id}`);
  return response.data;
};
