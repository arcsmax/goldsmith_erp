/**
 * TanStack Query options for repairs (W4-03). See
 * docs/technical/FRONTEND_DATA_LAYER.md.
 *
 * The keys themselves moved to `api/queryKeys.ts` as `queryKeys.repairs`
 * (W7 followup) — this file keeps `repairKeys` as a re-export for one
 * release so existing imports keep working; update them to
 * `queryKeys.repairs` and drop this alias afterwards.
 */
import { customerUpdatesApi } from './customer-updates';
import { queryKeys } from './queryKeys';
import { repairsApi } from './repairs';

/** @deprecated use `queryKeys.repairs` (api/queryKeys.ts) instead. */
export const repairKeys = queryKeys.repairs;

export function repairDetailQuery(id: number) {
  return {
    queryKey: queryKeys.repairs.detail(id),
    queryFn: () => repairsApi.getById(id),
  } as const;
}

export function repairCustomerUpdatesQuery(id: number) {
  return {
    queryKey: queryKeys.repairs.customerUpdates(id),
    queryFn: () => customerUpdatesApi.listRepairUpdates(id),
  } as const;
}
