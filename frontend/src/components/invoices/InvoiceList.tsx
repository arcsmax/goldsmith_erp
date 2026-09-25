// The invoice list (W4-03): filters, page summary, DataTable with
// StatusBadge and formatEur, Pager. A row links to `?invoice_id=…`, which
// opens the invoice below the list. One row action at most: "Bezahlt" for
// open invoices, "Stornieren" (void) for drafts; everything else lives in
// the detail region.
import React from 'react';
import { INVOICE_STATUS } from '../../design/status';
import { getErrorMessage } from '../../lib/errors';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import type { InvoiceListItem, InvoiceStatus } from '../../types';
import { Button, ButtonLink, DataTable, Field, type Column, type PageStateValue } from '../../ui';
import { StatusBadge } from '../../ui/StatusBadge';
import { Pager } from '../Pager';
import { canMarkPaid, canVoidDraft, DUE_HINT, dueTone, formatDate } from './invoiceFormat';
import { useInvoicesList, type InvoiceListFilter } from './useInvoiceQueries';

const STATUS_OPTIONS = (Object.keys(INVOICE_STATUS) as InvoiceStatus[]).map((value) => ({
  value,
  label: INVOICE_STATUS[value].label,
}));

interface InvoiceListProps {
  filter: InvoiceListFilter;
  onFilterChange: (next: Partial<InvoiceListFilter>) => void;
  onResetFilter: () => void;
  canCancel: boolean;
  onMarkPaid: (invoice: InvoiceListItem) => void;
  onVoidDraft: (invoice: InvoiceListItem) => void;
}

function listState(query: ReturnType<typeof useInvoicesList>): PageStateValue {
  if (query.isPending) return { status: 'loading' };
  if (query.isError && !query.data) {
    return {
      status: 'error',
      error: getErrorMessage(query.error, 'Rechnungen konnten nicht geladen werden.'),
      retry: () => void query.refetch(),
    };
  }
  return { status: query.data?.items.length ? 'ready' : 'empty' };
}

function DueDate({ invoice }: { invoice: InvoiceListItem }) {
  const hint = DUE_HINT[dueTone(invoice.due_date, invoice.status)];
  return (
    <>
      {formatDate(invoice.due_date)}
      {hint && <span className="invoice-due"> ({hint})</span>}
    </>
  );
}

type RowActionProps = { invoice: InvoiceListItem } & Pick<
  InvoiceListProps,
  'canCancel' | 'onMarkPaid' | 'onVoidDraft'
>;

function RowAction({ invoice, canCancel, onMarkPaid, onVoidDraft }: RowActionProps) {
  if (canMarkPaid(invoice)) {
    return (
      <Button variant="secondary" onClick={() => onMarkPaid(invoice)}>
        Bezahlt
      </Button>
    );
  }
  if (canCancel && canVoidDraft(invoice)) {
    return (
      <Button variant="ghost" onClick={() => onVoidDraft(invoice)}>
        Stornieren
      </Button>
    );
  }
  return null;
}

function PageSummary({ items }: { items: InvoiceListItem[] }) {
  const totalAmount = items.reduce((sum, inv) => sum + inv.total, 0);
  const overdue = items.filter((inv) => inv.status === 'overdue').length;
  const paid = items.filter((inv) => inv.status === 'paid').length;
  return (
    <dl className="invoice-summary-bar">
      <div>
        <dt>Gesamt (Seite)</dt>
        <dd className={`ui-num ${MONEY_CLASS}`}>{formatEur(totalAmount)}</dd>
      </div>
      <div>
        <dt>Überfällig</dt>
        <dd className="ui-num">{overdue}</dd>
      </div>
      <div>
        <dt>Bezahlt</dt>
        <dd className="ui-num">{paid}</dd>
      </div>
      <div>
        <dt>Einträge</dt>
        <dd className="ui-num">{items.length}</dd>
      </div>
    </dl>
  );
}

export const InvoiceList: React.FC<InvoiceListProps> = ({
  filter,
  onFilterChange,
  onResetFilter,
  ...rowActions
}) => {
  const query = useInvoicesList(filter);
  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const hasFilter = Boolean(filter.status || filter.from || filter.to);
  const pageCount = Math.max(Math.ceil(total / filter.pageSize), 1);

  const columns: Column<InvoiceListItem>[] = [
    { key: 'number', header: 'Rechnungsnummer', render: (inv) => <span className="ui-num">{inv.invoice_number}</span> },
    { key: 'order', header: 'Auftrag', render: (inv) => `#${inv.order_id}` },
    { key: 'issued', header: 'Ausgestellt', numeric: true, hideBelow: 'desktop', render: (inv) => formatDate(inv.issue_date) },
    { key: 'due', header: 'Fällig', numeric: true, render: (inv) => <DueDate invoice={inv} /> },
    { key: 'total', header: 'Gesamtbetrag', numeric: true, render: (inv) => <span className={MONEY_CLASS}>{formatEur(inv.total)}</span> },
    { key: 'status', header: 'Status', render: (inv) => <StatusBadge kind="invoice" status={inv.status} /> },
    { key: 'actions', header: 'Aktion', hideBelow: 'tablet', render: (inv) => <RowAction invoice={inv} {...rowActions} /> },
  ];

  return (
    <>
      <div className="invoice-filters invoice-no-print">
        <Field label="Status" name="status">
          <select
            id="invoices-filter-status"
            value={filter.status}
            onChange={(e) => onFilterChange({ status: e.target.value as InvoiceStatus | '' })}
          >
            <option value="">Alle</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Von" name="from">
          <input id="invoices-filter-from" type="date" value={filter.from} onChange={(e) => onFilterChange({ from: e.target.value })} />
        </Field>
        <Field label="Bis" name="to">
          <input id="invoices-filter-to" type="date" value={filter.to} onChange={(e) => onFilterChange({ to: e.target.value })} />
        </Field>
        {hasFilter && items.length > 0 && (
          <Button variant="secondary" onClick={onResetFilter}>
            Filter zurücksetzen
          </Button>
        )}
      </div>

      {items.length > 0 && <PageSummary items={items} />}

      <DataTable
        className="invoice-list"
        caption="Rechnungen"
        rows={items}
        columns={columns}
        getRowKey={(inv) => inv.id}
        rowHref={(inv) => `?invoice_id=${inv.id}`}
        state={listState(query)}
        cardMeta={(inv) => (
          <>
            {`Auftrag #${inv.order_id} · fällig ${formatDate(inv.due_date)} · `}
            <span className={`ui-num ${MONEY_CLASS}`}>{formatEur(inv.total)}</span>
          </>
        )}
        cardBadges={(inv) => <StatusBadge kind="invoice" status={inv.status} />}
        empty={{
          icon: 'receipt',
          title: hasFilter ? 'Keine Rechnungen für diese Filter gefunden' : 'Noch keine Rechnungen vorhanden',
          body: hasFilter ? undefined : 'Rechnungen entstehen aus abgeschlossenen oder ausgelieferten Aufträgen.',
          action: hasFilter ? (
            <Button variant="secondary" onClick={onResetFilter}>
              Filter zurücksetzen
            </Button>
          ) : (
            <ButtonLink to="/orders?status=completed" variant="secondary">
              Abgeschlossene Aufträge ansehen
            </ButtonLink>
          ),
        }}
      />

      {total > filter.pageSize && (
        <Pager
          label="Seiten der Rechnungen"
          pageNumber={filter.pageIndex + 1}
          pageCount={pageCount}
          summary={`${total} Rechnungen`}
          hasNext={filter.pageIndex + 1 < pageCount}
          isFetching={query.isFetching}
          onPrevious={() => onFilterChange({ pageIndex: Math.max(filter.pageIndex - 1, 0) })}
          onNext={() => onFilterChange({ pageIndex: filter.pageIndex + 1 })}
        />
      )}
    </>
  );
};
