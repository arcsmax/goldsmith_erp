/**
 * The staff app's TanStack Query client (W3-03, review 04 section F item 3).
 *
 * One client per signed-in session: AppQueryProvider (queryProvider.tsx)
 * creates it inside ProtectedRoute, so logging out unmounts the provider and
 * drops the cache (no customer data or prices survive into the next session).
 * /portal and /login never get a client.
 */
import { QueryClient } from '@tanstack/react-query';

/** Data counts as fresh for 30 s; a remount inside that window does not refetch. */
export const QUERY_STALE_TIME_MS = 30_000;
/** One retry for transient failures; 4xx answers are never retried. */
export const QUERY_RETRY_COUNT = 1;

const HTTP_CLIENT_ERROR_MIN = 400;
const HTTP_CLIENT_ERROR_MAX = 499;

function httpStatusOf(error: unknown): number | undefined {
  if (error === null || typeof error !== 'object') return undefined;
  const response = (error as { response?: { status?: unknown } }).response;
  return typeof response?.status === 'number' ? response.status : undefined;
}

/** Retry once, but never on 4xx (auth, permission, validation will not heal). */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  const status = httpStatusOf(error);
  if (status !== undefined && status >= HTTP_CLIENT_ERROR_MIN && status <= HTTP_CLIENT_ERROR_MAX) {
    return false;
  }
  return failureCount < QUERY_RETRY_COUNT;
}

export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: QUERY_STALE_TIME_MS,
        retry: shouldRetryQuery,
        refetchOnWindowFocus: true,
      },
      mutations: {
        retry: false,
      },
    },
  });
}
