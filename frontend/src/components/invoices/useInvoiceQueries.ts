// Server state of the invoices screen (W4-03): TanStack Query hooks around
// api/invoices.ts. See docs/technical/FRONTEND_DATA_LAYER.md.
//
// `/invoices/` is not on the Page envelope yet: it answers the legacy
// `{ items, total, skip, limit }` for skip/limit. The list keeps that call
// inside useQuery (like CustomersPage) until the backend gets `offset`.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { invoicesApi } from '../../api/invoices';
import { compactParams, pagedApi } from '../../api/paged';
import { queryKeys } from '../../api/queryKeys';
import { logError } from '../../lib/logError';
import type { Invoice, InvoiceCreateInput, InvoiceStatus, MarkPaidInput } from '../../types';

/** W7 hygiene: the create picker used to fetch up to 500 orders
 * unconditionally (legacy list). It now fetches the same 100-row page other
 * order pickers use via the paged endpoint, plus an optional `q` search
 * (CreateInvoiceModal's search box) so an order outside that page is still
 * reachable by number/title/customer. */
export const INVOICE_ORDER_PICKER_PAGE_SIZE = 100;

export interface InvoiceListFilter {
  status: InvoiceStatus | '';
  from: string;
  to: string;
  pageIndex: number;
  pageSize: number;
}

export function useInvoicesList(filter: InvoiceListFilter) {
  const params = compactParams({
    status: filter.status || undefined,
    from: filter.from || undefined,
    to: filter.to || undefined,
    skip: filter.pageIndex * filter.pageSize,
    limit: filter.pageSize,
  });
  return useQuery({
    queryKey: queryKeys.invoices.list(params),
    queryFn: () => invoicesApi.getInvoices(params),
    placeholderData: keepPreviousData,
  });
}

export function useInvoiceDetail(invoiceId: number | null) {
  return useQuery({
    queryKey: queryKeys.invoices.detail(invoiceId ?? 0),
    queryFn: async (): Promise<Invoice> => {
      try {
        return await invoicesApi.getInvoice(invoiceId as number);
      } catch (err) {
        logError(`invoice.loadDetail#${invoiceId}`, err);
        throw err;
      }
    },
    enabled: invoiceId !== null && invoiceId > 0,
  });
}

/** Orders for the "Rechnung erstellen" picker; only fetched while the dialog
 * is open. `q` (debounced by the caller) searches order number/title/
 * customer server-side instead of loading every order. */
export function useInvoiceableOrders(enabled: boolean, q: string = '') {
  const params = { limit: INVOICE_ORDER_PICKER_PAGE_SIZE, offset: 0, q: q || undefined };
  return useQuery({
    queryKey: queryKeys.orders.page(params),
    queryFn: ({ signal }) => pagedApi.orders(params, signal),
    enabled,
  });
}

export function useInvoiceMutations() {
  const queryClient = useQueryClient();

  const store = async (invoice: Invoice) => {
    queryClient.setQueryData(queryKeys.invoices.detail(invoice.id), invoice);
    await queryClient.invalidateQueries({ queryKey: queryKeys.invoices.all });
  };

  const create = useMutation({
    mutationFn: (data: InvoiceCreateInput) => invoicesApi.createFromOrder(data),
    onSuccess: store,
  });
  const markPaid = useMutation({
    mutationFn: ({ id, data }: { id: number; data: MarkPaidInput }) => invoicesApi.markAsPaid(id, data),
    onSuccess: store,
  });
  const voidDraft = useMutation({
    mutationFn: (id: number) => invoicesApi.cancelInvoice(id),
    onSuccess: store,
  });
  /** W2-04: returns the new Stornorechnung; the original is now CANCELLED. */
  const storno = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) => invoicesApi.createStorno(id, reason),
    onSuccess: store,
  });

  return { create, markPaid, voidDraft, storno };
}

export type InvoiceMutations = ReturnType<typeof useInvoiceMutations>;
