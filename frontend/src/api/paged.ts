/**
 * Typed fetchers for the paged list endpoints (W3-03 / W3-08).
 *
 * The backend answers a list request that carries `offset` with a Page
 * envelope `{ items, total, limit, offset, next_offset }` and applies
 * filters and `q` search server-side (src/goldsmith_erp/models/pagination.py).
 * Without `offset` it sends the deprecated plain list. Every fetcher here
 * always sends `offset`, so it always gets the envelope.
 *
 * Types come from the generated OpenAPI schema: the query parameters and the
 * Page item type of a path are read from `paths`, never written by hand.
 */
import apiClient from './client';
import type { paths } from './generated';

const API_PREFIX = '/api/v1';

/** Default page size of the list screens; the backend caps paged lists at 200. */
export const DEFAULT_PAGE_SIZE = 25;
export const MAX_PAGE_SIZE = 200;

type GetOperation<P extends keyof paths> = paths[P] extends { get: infer Op } ? Op : never;

type JsonOk<Op> = Op extends { responses: { 200: { content: { 'application/json': infer Body } } } }
  ? Body
  : never;

/** The Page envelope a path returns in paged mode (the member with `items`). */
export type PageResponse<P extends keyof paths> = Extract<
  JsonOk<GetOperation<P>>,
  { items: unknown[]; total: number }
>;

/** Paths whose GET answers with a Page envelope when `offset` is sent. */
export type PagedPath = {
  [P in keyof paths]: [PageResponse<P>] extends [never] ? never : P;
}[keyof paths];

/** Query parameters of a path's GET, from the generated schema. */
export type ListQueryParams<P extends keyof paths> = GetOperation<P> extends {
  parameters: { query?: infer Query };
}
  ? NonNullable<Query>
  : never;

/** Paged params: `limit` and `offset` are required, the legacy `skip` is gone. */
export type PageParams<P extends PagedPath> = Omit<ListQueryParams<P>, 'skip' | 'limit' | 'offset'> & {
  limit: number;
  offset: number;
};

export type PageItem<P extends PagedPath> = PageResponse<P>['items'][number];

/** Drop empty values so they neither reach the URL nor split the query key. */
export function compactParams<T extends object>(params: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(params).filter(
      ([, value]) => value !== undefined && value !== null && value !== '',
    ),
  ) as Partial<T>;
}

function isPageEnvelope(body: unknown): body is { items: unknown[]; total: number } {
  if (body === null || typeof body !== 'object') return false;
  const candidate = body as { items?: unknown; total?: unknown };
  return Array.isArray(candidate.items) && typeof candidate.total === 'number';
}

/**
 * GET one page of `path`. Throws when the server answers without the
 * envelope (an endpoint that is not paged yet), instead of rendering a
 * silently empty list.
 */
export async function fetchPage<P extends PagedPath>(
  path: P,
  params: PageParams<P>,
  signal?: AbortSignal,
): Promise<PageResponse<P>> {
  const url = String(path).startsWith(API_PREFIX) ? String(path).slice(API_PREFIX.length) : String(path);
  const response = await apiClient.get<unknown>(url, { params: compactParams(params), signal });
  if (!isPageEnvelope(response.data)) {
    throw new Error(`Unerwartete Antwort von ${url}: keine Seiten-Hülle (items/total).`);
  }
  return response.data as PageResponse<P>;
}

// ---- Orders ----------------------------------------------------------------

export type OrdersPage = PageResponse<'/api/v1/orders/'>;
export type OrderPageItem = PageItem<'/api/v1/orders/'>;
export type OrderPageParams = PageParams<'/api/v1/orders/'>;

export const pagedApi = {
  orders: (params: OrderPageParams, signal?: AbortSignal): Promise<OrdersPage> =>
    fetchPage('/api/v1/orders/', params, signal),
};

/** 1-based page number and page count for pagination controls. */
export function pageInfo(page: { total: number; limit: number; offset: number }): {
  pageNumber: number;
  pageCount: number;
} {
  const limit = Math.max(page.limit, 1);
  return {
    pageNumber: Math.floor(page.offset / limit) + 1,
    pageCount: Math.max(Math.ceil(page.total / limit), 1),
  };
}
