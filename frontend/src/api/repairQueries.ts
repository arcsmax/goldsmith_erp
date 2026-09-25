/**
 * TanStack Query keys and options for repairs (W4-03). See
 * docs/technical/FRONTEND_DATA_LAYER.md.
 *
 * Every key starts with the ['repairs'] root, so invalidating
 * `repairKeys.all` refreshes the list pages, the details and their
 * sub-resources in one call. The keys live here (not in queryKeys.ts) while
 * the repairs migration runs in isolation; they have the same shape and can
 * move into queryKeys.ts as `queryKeys.repairs` unchanged.
 */
import { customerUpdatesApi } from './customer-updates';
import { repairsApi, type RepairPageParams } from './repairs';

export const repairKeys = {
  all: ['repairs'] as const,
  lists: () => [...repairKeys.all, 'list'] as const,
  /** GET /repairs/?offset=… (Page envelope, status filter, `q`, `sort`). */
  page: (params: RepairPageParams) => [...repairKeys.lists(), 'page', params] as const,
  detail: (id: number) => [...repairKeys.all, 'detail', id] as const,
  /** Nested under detail(id): refreshing the repair refreshes its Kundeninfo. */
  customerUpdates: (id: number) => [...repairKeys.detail(id), 'customer-updates'] as const,
};

export function repairDetailQuery(id: number) {
  return {
    queryKey: repairKeys.detail(id),
    queryFn: () => repairsApi.getById(id),
  } as const;
}

export function repairCustomerUpdatesQuery(id: number) {
  return {
    queryKey: repairKeys.customerUpdates(id),
    queryFn: () => customerUpdatesApi.listRepairUpdates(id),
  } as const;
}
