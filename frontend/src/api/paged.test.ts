// W3-03: typed paged fetchers always send offset, drop empty filters and
// refuse a non-envelope answer.
import { afterEach, describe, expect, it, vi } from 'vitest';

const mockGet = vi.fn();
vi.mock('./client', () => ({ default: { get: (...a: unknown[]) => mockGet(...a) } }));

import { compactParams, fetchPage, pageInfo, pagedApi } from './paged';
import { queryKeys } from './queryKeys';
import { shouldRetryQuery } from '../lib/queryClient';

const EMPTY_PAGE = { items: [], total: 0, limit: 25, offset: 0, next_offset: null };

afterEach(() => mockGet.mockReset());

describe('paged fetchers', () => {
  it('calls /orders/ with limit, offset, status and q', async () => {
    mockGet.mockResolvedValue({ data: EMPTY_PAGE });
    await pagedApi.orders({ limit: 25, offset: 50, status: 'in_progress', q: 'Ring' });
    expect(mockGet).toHaveBeenCalledWith('/orders/', {
      params: { limit: 25, offset: 50, status: 'in_progress', q: 'Ring' },
      signal: undefined,
    });
  });

  it('drops empty filters from the params', () => {
    expect(compactParams({ limit: 25, offset: 0, q: '', status: undefined, x: null })).toEqual({
      limit: 25,
      offset: 0,
    });
  });

  it('throws on a legacy list answer instead of showing an empty page', async () => {
    mockGet.mockResolvedValue({ data: [] });
    await expect(fetchPage('/api/v1/orders/', { limit: 25, offset: 0 })).rejects.toThrow(
      /Seiten-Hülle/,
    );
  });

  it('passes the abort signal through', async () => {
    mockGet.mockResolvedValue({ data: EMPTY_PAGE });
    const controller = new AbortController();
    await pagedApi.orders({ limit: 25, offset: 0 }, controller.signal);
    expect(mockGet.mock.calls[0][1].signal).toBe(controller.signal);
  });

  it('computes the 1-based page number and page count', () => {
    expect(pageInfo({ total: 51, limit: 25, offset: 25 })).toEqual({ pageNumber: 2, pageCount: 3 });
    expect(pageInfo({ total: 0, limit: 25, offset: 0 })).toEqual({ pageNumber: 1, pageCount: 1 });
  });
});

describe('queryKeys', () => {
  it('nests every orders key under the ["orders"] root', () => {
    expect(queryKeys.orders.page({ limit: 25, offset: 0 }).slice(0, 1)).toEqual(['orders']);
    expect(queryKeys.orders.legacyList(100).slice(0, 1)).toEqual(['orders']);
    expect(queryKeys.orders.detail(3).slice(0, 1)).toEqual(['orders']);
  });
});

describe('shouldRetryQuery', () => {
  it('retries a network error once', () => {
    expect(shouldRetryQuery(0, new Error('network'))).toBe(true);
    expect(shouldRetryQuery(1, new Error('network'))).toBe(false);
  });

  it('never retries a 4xx answer', () => {
    expect(shouldRetryQuery(0, { response: { status: 403 } })).toBe(false);
    expect(shouldRetryQuery(0, { response: { status: 503 } })).toBe(true);
  });
});
