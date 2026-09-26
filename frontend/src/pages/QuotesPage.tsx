// Quotes page — Kostenvoranschläge (W4-03). List template (playbook 5.1)
// with the selected quote in an editor region below the list.
//
// URL state:
//   ?quote_id=…                    the quote open in the editor (row links,
//                                  consultation wizard hand-off)
//   ?order_id=…&customer_id=…      FE-18 hand-off from the order page: opens
//                                  "Neues Angebot" pre-filled; consumed once
//
// Server state goes through TanStack Query (components/quotes/useQuoteQueries).
// The backend publishes no quote events, so there is no realtime channel for
// quotes yet; mutations invalidate the ['quotes'] root and the linked order
// query rides on the ['orders'] root, which `order_updates` invalidates.
import React, { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../contexts';
import { getErrorMessage } from '../lib/errors';
import { logError } from '../lib/logError';
import type { QuoteCreateInput } from '../types';
import { Button, PageHeader, PageState, type PageStateValue } from '../ui';
import { CreateQuoteModal, type CreateQuotePrefill } from '../components/quotes/CreateQuoteModal';
import { QuoteEditor } from '../components/quotes/QuoteEditor';
import { QuoteList } from '../components/quotes/QuoteList';
import { useQuoteDetail, useQuoteMutations } from '../components/quotes/useQuoteQueries';
import '../styles/pages.css';
// consultations.css: the .typeahead dropdown styles used by CustomerTypeahead (LV-02).
import '../styles/consultations.css';
import '../styles/quotes.css';

// Kept as named exports of the page for the existing tests and callers.
export { sendOutcomeMessage } from '../components/quotes/quoteFormat';
export { EditableLineItems } from '../components/quotes/QuoteLineItems';

function parseQuoteId(value: string | null): number | null {
  const id = Number(value);
  return Number.isInteger(id) && id > 0 ? id : null;
}

function detailState(query: ReturnType<typeof useQuoteDetail>): PageStateValue {
  if (query.isPending) return { status: 'loading' };
  if (query.isError) {
    return {
      status: 'error',
      error: getErrorMessage(query.error, 'Kostenvoranschlag konnte nicht geladen werden.'),
      retry: () => void query.refetch(),
    };
  }
  return { status: 'ready' };
}

/** FE-18: turn `?order_id&customer_id` into a one-time prefill for the create dialog. */
function useCreateHandOff(open: () => void): CreateQuotePrefill {
  const [searchParams, setSearchParams] = useSearchParams();
  const [prefill, setPrefill] = useState<CreateQuotePrefill>({});
  useEffect(() => {
    const orderId = searchParams.get('order_id') ?? undefined;
    const customerId = searchParams.get('customer_id') ?? undefined;
    if (!orderId && !customerId) return;
    const next = new URLSearchParams(searchParams);
    next.delete('order_id');
    next.delete('customer_id');
    setSearchParams(next, { replace: true });
    setPrefill({ customerId, orderId });
    open();
  }, [searchParams, setSearchParams, open]);
  return prefill;
}

export const QuotesPage: React.FC = () => {
  const { showToast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const openCreate = useCallback(() => setIsCreateOpen(true), []);
  const prefill = useCreateHandOff(openCreate);

  const selectedId = parseQuoteId(searchParams.get('quote_id'));
  const detail = useQuoteDetail(selectedId);
  const mutations = useQuoteMutations();

  const selectQuote = (id: number | null) => {
    const next = new URLSearchParams(searchParams);
    if (id) next.set('quote_id', String(id));
    else next.delete('quote_id');
    setSearchParams(next, { replace: true });
  };

  const handleCreate = async (data: QuoteCreateInput) => {
    try {
      const created = await mutations.create.mutateAsync(data);
      showToast('Angebot erstellt.', 'success');
      setIsCreateOpen(false);
      selectQuote(created.id);
    } catch (err) {
      logError('quote.create', err);
      showToast(getErrorMessage(err, 'Angebot konnte nicht erstellt werden.'), 'error');
      throw err;
    }
  };

  return (
    <div className="page-container quotes-page">
      <PageHeader
        title="Kostenvoranschläge"
        primaryAction={
          <Button icon="plus" onClick={openCreate}>
            Neues Angebot
          </Button>
        }
      />

      <QuoteList onCreate={openCreate} canCreate />

      {selectedId !== null && (
        <PageState state={detailState(detail)} skeleton="detail">
          {detail.data && (
            <QuoteEditor
              key={detail.data.id}
              quote={detail.data}
              mutations={mutations}
              onClose={() => selectQuote(null)}
            />
          )}
        </PageState>
      )}

      <CreateQuoteModal
        open={isCreateOpen}
        prefill={prefill}
        onClose={() => setIsCreateOpen(false)}
        onSubmit={handleCreate}
      />
    </div>
  );
};

