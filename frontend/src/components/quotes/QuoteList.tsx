// The quote list (W4-03): status filter and search (server-side, paged
// `/quotes/?offset=…`), DataTable with StatusBadge and formatEur, Pager.
// A row links to `?quote_id=…`, which opens the quote in the editor below.
import React, { useState } from 'react';
import { DEFAULT_PAGE_SIZE, pageInfo } from '../../api/paged';
import type { QuotesPage } from '../../api/quotes';
import { QUOTE_STATUS } from '../../design/status';
import { getErrorMessage } from '../../lib/errors';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import { useDebouncedValue } from '../../lib/useDebouncedValue';
import type { QuoteStatus } from '../../types';
import { Button, DataTable, Field, type Column, type PageStateValue } from '../../ui';
import { StatusBadge } from '../../ui/StatusBadge';
import { Pager } from '../Pager';
import { formatDate, VALIDITY_HINT, validityTone } from './quoteFormat';
import { useQuotesPage } from './useQuoteQueries';

type QuoteRow = QuotesPage['items'][number];

/** LV2-06: the resolved name (job_list_item's _customer_summary on the
 * backend), falling back to the old placeholder only if it's ever absent
 * (e.g. an older/unresolved row). */
function customerLabel(q: QuoteRow): string {
  return q.customer?.display_name ?? `Kunde #${q.customer_id}`;
}

/** Backend `q` accepts 1-100 characters. */
const MAX_SEARCH_LENGTH = 100;
const STATUS_OPTIONS = (Object.keys(QUOTE_STATUS) as QuoteStatus[]).map((value) => ({
  value,
  label: QUOTE_STATUS[value].label,
}));

const COLUMNS: Column<QuoteRow>[] = [
  {
    key: 'number',
    header: 'KV-Nummer',
    render: (q) => <span className="ui-num">{q.quote_number}</span>,
  },
  { key: 'customer', header: 'Kunde', render: (q) => customerLabel(q) },
  { key: 'created', header: 'Erstellt', numeric: true, hideBelow: 'desktop', render: (q) => formatDate(q.created_at) },
  {
    key: 'valid',
    header: 'Gültig bis',
    numeric: true,
    render: (q) => {
      const hint = VALIDITY_HINT[validityTone(q.valid_until, q.status)];
      return (
        <>
          {formatDate(q.valid_until)}
          {hint && <span className="quote-validity"> ({hint})</span>}
        </>
      );
    },
  },
  {
    key: 'total',
    header: 'Betrag',
    numeric: true,
    render: (q) => <span className={MONEY_CLASS}>{formatEur(q.total)}</span>,
  },
  { key: 'status', header: 'Status', render: (q) => <StatusBadge kind="quote" status={q.status} /> },
];

function listState(query: ReturnType<typeof useQuotesPage>): PageStateValue {
  if (query.isPending) return { status: 'loading' };
  if (query.isError && !query.data) {
    return {
      status: 'error',
      error: getErrorMessage(query.error, 'Kostenvoranschläge konnten nicht geladen werden.'),
      retry: () => void query.refetch(),
    };
  }
  return { status: query.data?.items.length ? 'ready' : 'empty' };
}

interface QuoteListProps {
  onCreate: () => void;
  canCreate: boolean;
}

export const QuoteList: React.FC<QuoteListProps> = ({ onCreate, canCreate }) => {
  const [status, setStatus] = useState<QuoteStatus | ''>('');
  const [searchInput, setSearchInput] = useState('');
  const q = useDebouncedValue(searchInput).trim().slice(0, MAX_SEARCH_LENGTH);
  const [pageIndex, setPageIndex] = useState(0);

  // A new filter starts again at page 1 (derived during render, no effect).
  const filterKey = `${status}|${q}`;
  const [lastFilterKey, setLastFilterKey] = useState(filterKey);
  if (filterKey !== lastFilterKey) {
    setLastFilterKey(filterKey);
    setPageIndex(0);
  }

  const query = useQuotesPage({ status, q, pageIndex, pageSize: DEFAULT_PAGE_SIZE });
  const rows = query.data?.items ?? [];
  const hasFilter = Boolean(status || q);
  const { pageNumber, pageCount } = query.data ? pageInfo(query.data) : { pageNumber: 1, pageCount: 1 };

  const emptyAction = hasFilter ? (
    <Button
      variant="secondary"
      onClick={() => {
        setStatus('');
        setSearchInput('');
      }}
    >
      Filter zurücksetzen
    </Button>
  ) : canCreate ? (
    <Button icon="plus" onClick={onCreate}>
      Erstes Angebot erstellen
    </Button>
  ) : undefined;

  return (
    <>
      <div className="quote-filters">
        <Field label="Suche" name="q" inputMode="search">
          <input
            id="quotes-search"
            type="search"
            placeholder="KV-Nummer oder Kunde …"
            maxLength={MAX_SEARCH_LENGTH}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </Field>
        <Field label="Status" name="status">
          <select
            id="status-filter"
            value={status}
            onChange={(e) => setStatus(e.target.value as QuoteStatus | '')}
          >
            <option value="">Alle</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <DataTable
        className="quote-list"
        caption="Kostenvoranschläge"
        rows={rows}
        columns={COLUMNS}
        getRowKey={(q) => q.id}
        rowHref={(q) => `?quote_id=${q.id}`}
        state={listState(query)}
        cardMeta={(q) => (
          <>
            {`${customerLabel(q)} · gültig bis ${formatDate(q.valid_until)} · `}
            <span className={`ui-num ${MONEY_CLASS}`}>{formatEur(q.total)}</span>
          </>
        )}
        cardBadges={(q) => <StatusBadge kind="quote" status={q.status} />}
        empty={{
          icon: 'file-text',
          title: hasFilter ? 'Keine Kostenvoranschläge gefunden' : 'Noch keine Kostenvoranschläge',
          body: hasFilter ? 'Suche oder Filter ändern.' : undefined,
          action: emptyAction,
        }}
      />

      {query.data && query.data.total > 0 && (
        <Pager
          label="Seiten der Kostenvoranschläge"
          pageNumber={pageNumber}
          pageCount={pageCount}
          summary={`${query.data.total} Kostenvoranschläge`}
          hasNext={query.data.next_offset != null}
          isFetching={query.isFetching}
          onPrevious={() => setPageIndex((i) => Math.max(i - 1, 0))}
          onNext={() => setPageIndex((i) => i + 1)}
        />
      )}
    </>
  );
};
