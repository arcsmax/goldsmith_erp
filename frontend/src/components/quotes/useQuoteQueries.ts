// Server state of the quotes screen (W4-03): TanStack Query hooks around
// api/quotes.ts. See docs/technical/FRONTEND_DATA_LAYER.md.
//
// Every mutation writes the returned quote into its detail cache entry and
// invalidates the quote lists. Detail entries are keyed by id, so a slow
// response for quote A can never overwrite the panel of quote B (the old
// page needed an `applyIfCurrent` guard for that).
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ordersApi } from '../../api/orders';
import { compactParams } from '../../api/paged';
import { queryKeys } from '../../api/queryKeys';
import {
  quotesApi,
  type ApproveQuotePayload,
  type QuotePageParams,
  type QuoteWithDelivery,
} from '../../api/quotes';
import { logError } from '../../lib/logError';
import type { Quote, QuoteCreateInput, QuoteLineItemInput, QuoteStatus } from '../../types';

export interface QuoteListFilter {
  status: QuoteStatus | '';
  q: string;
  pageIndex: number;
  pageSize: number;
}

export function useQuotesPage(filter: QuoteListFilter) {
  const params = compactParams({
    limit: filter.pageSize,
    offset: filter.pageIndex * filter.pageSize,
    status: filter.status || undefined,
    q: filter.q || undefined,
  }) as QuotePageParams;
  return useQuery({
    queryKey: queryKeys.quotes.page(params),
    queryFn: ({ signal }) => quotesApi.getQuotesPage(params, signal),
    placeholderData: keepPreviousData,
  });
}

export function useQuoteDetail(quoteId: number | null) {
  return useQuery({
    queryKey: queryKeys.quotes.detail(quoteId ?? 0),
    queryFn: async (): Promise<QuoteWithDelivery> => {
      try {
        return await quotesApi.getQuote(quoteId as number);
      } catch (err) {
        logError(`quote.loadDetail#${quoteId}`, err);
        throw err;
      }
    },
    enabled: quoteId !== null && quoteId > 0,
  });
}

/**
 * The order a quote references, so the EstimatorPanel can pre-fill
 * order_type / surface_finish / alloy. An orphan order_id (404) just leaves
 * the estimator with empty inputs, so there is no retry and no error UI.
 */
export function useLinkedOrder(orderId: number | null | undefined) {
  return useQuery({
    queryKey: queryKeys.orders.detail(orderId ?? 0),
    queryFn: () => ordersApi.getById(orderId as number),
    enabled: Boolean(orderId),
    retry: false,
  });
}

export function useQuoteMutations() {
  const queryClient = useQueryClient();

  const store = async (quote: Quote) => {
    queryClient.setQueryData(queryKeys.quotes.detail(quote.id), quote);
    await queryClient.invalidateQueries({ queryKey: queryKeys.quotes.lists() });
  };

  const create = useMutation({
    mutationFn: (data: QuoteCreateInput) => quotesApi.createQuote(data),
    onSuccess: store,
  });
  const send = useMutation({
    mutationFn: (id: number) => quotesApi.sendQuote(id),
    onSuccess: store,
  });
  const approve = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: ApproveQuotePayload }) =>
      quotesApi.approveQuote(id, payload),
    onSuccess: store,
  });
  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) =>
      quotesApi.rejectQuote(id, { reason }),
    onSuccess: store,
  });
  const convert = useMutation({
    mutationFn: (id: number) => quotesApi.convertQuote(id),
    onSuccess: async (quote) => {
      await store(quote);
      // The conversion creates an order: refresh the order lists and "Heute".
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.orders.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all }),
      ]);
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => quotesApi.deleteQuote(id),
    onSuccess: async (_data, id) => {
      queryClient.removeQueries({ queryKey: queryKeys.quotes.detail(id) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.quotes.lists() });
    },
  });
  const addLine = useMutation({
    mutationFn: ({ quoteId, data }: { quoteId: number; data: QuoteLineItemInput }) =>
      quotesApi.addLineItem(quoteId, data),
    onSuccess: store,
  });
  const saveLine = useMutation({
    mutationFn: ({ quoteId, itemId, data }: { quoteId: number; itemId: number; data: QuoteLineItemInput }) =>
      quotesApi.updateLineItem(quoteId, itemId, data),
    onSuccess: store,
  });
  const removeLine = useMutation({
    mutationFn: ({ quoteId, itemId }: { quoteId: number; itemId: number }) =>
      quotesApi.deleteLineItem(quoteId, itemId),
    onSuccess: store,
  });

  return { create, send, approve, reject, convert, remove, addLine, saveLine, removeLine };
}

export type QuoteMutations = ReturnType<typeof useQuoteMutations>;
