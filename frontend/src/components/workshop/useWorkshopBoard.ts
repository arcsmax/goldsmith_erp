// Data for the Werkstatt board: one GET /jobs page per status column
// (≤ 200 cards each), plus the "Weiter" mutation. Realtime order hints
// invalidate the ['jobs'] root (lib/realtimeInvalidation.ts).
import { useMutation, useQueries, useQueryClient } from '@tanstack/react-query';

import { jobsApi, type JobListItem, type JobPageParams, type JobStatus } from '../../api/jobs';
import { compactParams } from '../../api/paged';
import { queryKeys } from '../../api/queryKeys';
import { getErrorMessage } from '../../lib/errors';
import { BOARD_COLUMN_LIMIT, BOARD_COLUMNS, BOARD_SORT, advanceStep, type JobKindFilter } from './boardModel';

export interface BoardFilters {
  kind: JobKindFilter;
  customerId: number | null;
}

export interface ColumnData {
  status: JobStatus;
  jobs: readonly JobListItem[];
  total: number | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function columnParams(status: JobStatus, filters: BoardFilters): JobPageParams {
  return compactParams({
    status: [status],
    kind: filters.kind === 'all' ? undefined : filters.kind,
    customer_id: filters.customerId ?? undefined,
    sort: BOARD_SORT,
    limit: BOARD_COLUMN_LIMIT,
    offset: 0,
  }) as JobPageParams;
}

export function useBoardColumns(filters: BoardFilters): ColumnData[] {
  const results = useQueries({
    queries: BOARD_COLUMNS.map((status) => {
      const params = columnParams(status, filters);
      return {
        queryKey: queryKeys.jobs.page(params),
        queryFn: ({ signal }: { signal: AbortSignal }) => jobsApi.page(params, signal),
      };
    }),
  });
  return BOARD_COLUMNS.map((status, index) => {
    const result = results[index];
    return {
      status,
      jobs: result.data?.items ?? [],
      total: result.data?.total ?? null,
      isLoading: result.isPending,
      error: result.isError ? getErrorMessage(result.error, 'Spalte konnte nicht geladen werden.') : null,
      refetch: () => {
        void result.refetch();
      },
    };
  });
}

/** Advance one card; refreshes the board, the order lists and "Heute". */
export function useAdvanceJob(handlers: {
  onSuccess: (job: JobListItem) => void;
  onError: (job: JobListItem, err: unknown) => void;
}) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (job: JobListItem) => {
      const step = advanceStep(job);
      if (!step) throw new Error(`Kein nächster Schritt für ${job.number}`);
      await step.run();
      return job;
    },
    onSuccess: async (job) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.jobs.all }),
        client.invalidateQueries({ queryKey: queryKeys.orders.all }),
        client.invalidateQueries({ queryKey: queryKeys.dashboard.all }),
      ]);
      handlers.onSuccess(job);
    },
    onError: (err, job) => handlers.onError(job, err),
  });
}
