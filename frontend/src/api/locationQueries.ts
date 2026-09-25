// TanStack Query options for the Standorte (W8). Kept apart from
// api/locations.ts so tests can mock the fetchers module.
import { queryOptions } from '@tanstack/react-query';
import { getActiveLocations, getAllLocations } from './locations';
import { queryKeys } from './queryKeys';

/** The picker list changes rarely; ADMIN edits invalidate it. */
const ACTIVE_LOCATIONS_STALE_MS = 5 * 60_000;

export const activeLocationsQuery = () =>
  queryOptions({
    queryKey: queryKeys.locations.active(),
    queryFn: getActiveLocations,
    staleTime: ACTIVE_LOCATIONS_STALE_MS,
  });

export const allLocationsQuery = () =>
  queryOptions({ queryKey: queryKeys.locations.admin(), queryFn: getAllLocations });
