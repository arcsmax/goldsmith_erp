// One invoice below the list (W4-03): header, dates, the Storno links,
// line items and the totals. Rendered as a block sibling of the list, never
// inside the table, so its width follows the page (the totals were clipped
// when it lived in a `<td colspan>`), and it is what the print CSS keeps.
import React from 'react';
import { Link } from 'react-router-dom';
import { getErrorMessage } from '../../lib/errors';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import type { Invoice } from '../../types';
import { PageState, type PageStateValue } from '../../ui';
import { StatusBadge } from '../../ui/StatusBadge';
import { InvoiceActions } from './InvoiceActions';
import { DUE_HINT, dueTone, formatDate } from './invoiceFormat';
import { useInvoiceDetail, type InvoiceMutations } from './useInvoiceQueries';

interface InvoiceDetailProps {
  invoiceId: number;
  mutations: InvoiceMutations;
  canCancel: boolean;
  onMarkPaid: (invoice: Invoice) => void;
  onVoidDraft: (invoice: Invoice) => void;
  onSelect: (invoiceId: number) => void;
  onClose: () => void;
}

function MetaItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="invoice-meta__item">
      <dt>{label}</dt>
      <dd className="ui-num">{children}</dd>
    </div>
  );
}

function detailState(query: ReturnType<typeof useInvoiceDetail>): PageStateValue {
  if (query.isPending) return { status: 'loading' };
  if (query.isError) {
    return {
      status: 'error',
      error: getErrorMessage(query.error, 'Rechnungsdetails konnten nicht geladen werden.'),
      retry: () => void query.refetch(),
    };
  }
  return { status: 'ready' };
}

const InvoiceLines: React.FC<{ invoice: Invoice }> = ({ invoice }) => (
  <div className="ui-table-scroll">
    <table className="ui-table invoice-lines">
      <caption className="ui-visually-hidden">Positionen der Rechnung</caption>
      <thead>
        <tr>
          <th scope="col">Beschreibung</th>
          <th scope="col">Typ</th>
          <th scope="col" className="ui-align-end">Menge</th>
          <th scope="col" className="ui-align-end">Einzelpreis (netto)</th>
          <th scope="col" className="ui-align-end">Gesamt (netto)</th>
        </tr>
      </thead>
      <tbody>
        {invoice.line_items.map((item) => (
          <tr key={item.id}>
            <td>{item.description}</td>
            <td>{item.line_type}</td>
            <td className="ui-num ui-align-end">{item.quantity}</td>
            <td className={`ui-num ui-align-end ${MONEY_CLASS}`}>{formatEur(item.unit_price)}</td>
            <td className={`ui-num ui-align-end ${MONEY_CLASS}`}>{formatEur(item.total)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const InvoiceTotals: React.FC<{ invoice: Invoice }> = ({ invoice }) => (
  <dl className="invoice-totals">
    <div className="invoice-totals__row">
      <dt>Zwischensumme (netto)</dt>
      <dd className={`ui-num ${MONEY_CLASS}`}>{formatEur(invoice.subtotal)}</dd>
    </div>
    <div className="invoice-totals__row">
      <dt>MwSt ({invoice.tax_rate}%)</dt>
      <dd className={`ui-num ${MONEY_CLASS}`}>{formatEur(invoice.tax_amount)}</dd>
    </div>
    <div className="invoice-totals__row invoice-totals__row--grand">
      <dt>Gesamtbetrag (brutto)</dt>
      <dd className={`ui-num ${MONEY_CLASS}`}>{formatEur(invoice.total)}</dd>
    </div>
  </dl>
);

const StornoLinks: React.FC<{ invoice: Invoice }> = ({ invoice }) => (
  <>
    {invoice.cancels_invoice_id && (
      <p className="invoice-detail__link">
        Stornorechnung zu{' '}
        <Link to={`?invoice_id=${invoice.cancels_invoice_id}`}>Rechnung #{invoice.cancels_invoice_id}</Link>
      </p>
    )}
    {invoice.cancelled_by_invoice_id && (
      <p className="invoice-detail__link">
        Storniert durch{' '}
        <Link to={`?invoice_id=${invoice.cancelled_by_invoice_id}`}>
          Stornorechnung #{invoice.cancelled_by_invoice_id}
        </Link>
      </p>
    )}
  </>
);

export const InvoiceDetail: React.FC<InvoiceDetailProps> = ({ invoiceId, onSelect, ...actions }) => {
  const query = useInvoiceDetail(invoiceId);
  const invoice = query.data;
  const tone = invoice ? dueTone(invoice.due_date, invoice.status) : 'ok';

  return (
    <section className="invoice-detail-panel" aria-label="Rechnungsdetails">
      <PageState state={detailState(query)} skeleton="detail">
        {invoice && (
          <div data-testid="invoice-detail-panel">
            <header className="invoice-detail__header">
              <h2 className="ui-num">{invoice.invoice_number}</h2>
              <StatusBadge kind="invoice" status={invoice.status} />
            </header>

            <InvoiceActions invoice={invoice} onStornoCreated={onSelect} {...actions} />
            <StornoLinks invoice={invoice} />

            <dl className="invoice-meta">
              <MetaItem label="Ausstellungsdatum">{formatDate(invoice.issue_date)}</MetaItem>
              <MetaItem label="Fälligkeitsdatum">
                {formatDate(invoice.due_date)}
                {DUE_HINT[tone] && <span className={`invoice-due invoice-due--${tone}`}> ({DUE_HINT[tone]})</span>}
              </MetaItem>
              {invoice.paid_date && <MetaItem label="Zahlungseingang">{formatDate(invoice.paid_date)}</MetaItem>}
              {invoice.payment_method && <MetaItem label="Zahlungsart">{invoice.payment_method}</MetaItem>}
              <MetaItem label="Auftrag">
                <Link to={`/orders/${invoice.order_id}`}>#{invoice.order_id}</Link>
              </MetaItem>
            </dl>

            {invoice.notes && (
              <p className="invoice-detail__notes">
                <strong>Anmerkungen:</strong> {invoice.notes}
              </p>
            )}

            {invoice.line_items.length > 0 && <InvoiceLines invoice={invoice} />}
            <InvoiceTotals invoice={invoice} />
          </div>
        )}
      </PageState>
    </section>
  );
};
