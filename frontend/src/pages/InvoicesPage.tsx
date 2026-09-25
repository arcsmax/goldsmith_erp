// Invoices page — Rechnungen (W4-03). List template (playbook 5.1) with the
// selected invoice below the list (`?invoice_id=…`).
//
// ADMIN and GOLDSMITH only (financial data). Voiding a draft, the Storno and
// the accounting exports are ADMIN only, like the backend permissions.
//
// Server state goes through TanStack Query (components/invoices/
// useInvoiceQueries). `/invoices/` is not paged on the server yet, so the
// list keeps the legacy skip/limit call inside useQuery. The backend
// publishes no invoice events; mutations invalidate the ['invoices'] root and
// the order picker rides on the ['orders'] root (realtime `order_updates`).
import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth, useConfirm, useToast } from '../contexts';
import { getErrorMessage } from '../lib/errors';
import { logError } from '../lib/logError';
import type { InvoiceCreateInput, InvoiceListItem, MarkPaidInput } from '../types';
import { Button, PageHeader } from '../ui';
import { CreateInvoiceModal } from '../components/invoices/CreateInvoiceModal';
import { InvoiceDetail } from '../components/invoices/InvoiceDetail';
import { InvoiceList } from '../components/invoices/InvoiceList';
import { MarkPaidModal } from '../components/invoices/MarkPaidModal';
import { downloadAccountingExport, EXPORT_LABELS, type ExportFormat } from '../components/invoices/invoiceExport';
import { useInvoiceMutations, type InvoiceListFilter } from '../components/invoices/useInvoiceQueries';
import '../styles/pages.css';
import '../styles/invoices.css';

const PAGE_SIZE = 25;
const EMPTY_FILTER: InvoiceListFilter = { status: '', from: '', to: '', pageIndex: 0, pageSize: PAGE_SIZE };
const EXPORT_FORMATS: ExportFormat[] = ['datev', 'lexoffice'];

type PayableInvoice = Pick<InvoiceListItem, 'id' | 'invoice_number' | 'total'>;

function parseInvoiceId(value: string | null): number | null {
  const id = Number(value);
  return Number.isInteger(id) && id > 0 ? id : null;
}

export const InvoicesPage: React.FC = () => {
  const { hasRole } = useAuth();
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filter, setFilter] = useState<InvoiceListFilter>(EMPTY_FILTER);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [invoiceToPay, setInvoiceToPay] = useState<PayableInvoice | null>(null);
  const mutations = useInvoiceMutations();

  const selectedId = parseInvoiceId(searchParams.get('invoice_id'));
  const canCancel = hasRole(['ADMIN']);

  // Guard after all hooks so the hook order never changes.
  if (!hasRole(['ADMIN', 'GOLDSMITH'])) {
    return (
      <div className="page-error">
        Keine Berechtigung. Diese Seite ist nur für Goldschmiede und Administratoren zugänglich.
      </div>
    );
  }

  const selectInvoice = (id: number | null) => {
    const next = new URLSearchParams(searchParams);
    if (id) next.set('invoice_id', String(id));
    else next.delete('invoice_id');
    setSearchParams(next, { replace: true });
  };

  // Any filter change starts again at page 1; paging keeps the filter.
  const changeFilter = (next: Partial<InvoiceListFilter>) =>
    setFilter((current) => ({ ...current, pageIndex: 0, ...next }));

  const openCreate = () => {
    setCreateError(null);
    setIsCreateOpen(true);
  };

  const handleCreate = async (data: InvoiceCreateInput) => {
    setCreateError(null);
    try {
      const created = await mutations.create.mutateAsync(data);
      setIsCreateOpen(false);
      showToast('Rechnung erstellt.', 'success');
      selectInvoice(created.id);
    } catch (err) {
      // Inline in the dialog (fixable input) and as a toast (announced).
      logError('invoice.create', err);
      const message = getErrorMessage(err, 'Rechnung konnte nicht erstellt werden.');
      setCreateError(message);
      showToast(message, 'error');
    }
  };

  const handleMarkPaid = async (data: MarkPaidInput) => {
    if (!invoiceToPay) return;
    try {
      await mutations.markPaid.mutateAsync({ id: invoiceToPay.id, data });
      setInvoiceToPay(null);
      showToast('Rechnung als bezahlt markiert.', 'success');
    } catch (err) {
      logError('invoice.markPaid', err);
      showToast(getErrorMessage(err, 'Zahlungsstatus konnte nicht gespeichert werden.'), 'error');
    }
  };

  const handleVoidDraft = async (invoice: Pick<InvoiceListItem, 'id' | 'invoice_number'>) => {
    const confirmed = await showConfirm({
      title: 'Rechnung stornieren',
      message: `Entwurf ${invoice.invoice_number} wirklich stornieren? Er wurde nie versendet und wird ungültig.`,
      confirmLabel: 'Stornieren',
      variant: 'danger',
    });
    if (!confirmed) return;
    try {
      // Status transitions use the action endpoints, not the generic PUT
      // (ADR-2026-09-25 price-semantics, decision 5).
      await mutations.voidDraft.mutateAsync(invoice.id);
      showToast('Rechnung storniert.', 'success');
    } catch (err) {
      logError('invoice.voidDraft', err);
      showToast(getErrorMessage(err, 'Rechnung konnte nicht storniert werden.'), 'error');
    }
  };

  const handleExport = async (format: ExportFormat) => {
    try {
      await downloadAccountingExport(format, filter);
    } catch (err) {
      logError(`invoice.export.${format}`, err);
      showToast('Export fehlgeschlagen. Bitte erneut versuchen.', 'error');
    }
  };

  return (
    <div className="page-container invoices-page">
      <PageHeader
        className="invoice-no-print"
        title="Rechnungen"
        secondaryActions={
          canCancel &&
          EXPORT_FORMATS.map((format) => (
            <Button key={format} variant="secondary" onClick={() => void handleExport(format)}>
              {EXPORT_LABELS[format]}
            </Button>
          ))
        }
        primaryAction={
          <Button icon="plus" onClick={openCreate}>
            Neue Rechnung erstellen
          </Button>
        }
      />

      <InvoiceList
        filter={filter}
        onFilterChange={changeFilter}
        onResetFilter={() => setFilter(EMPTY_FILTER)}
        canCancel={canCancel}
        onMarkPaid={setInvoiceToPay}
        onVoidDraft={(invoice) => void handleVoidDraft(invoice)}
      />

      {selectedId !== null && (
        <InvoiceDetail
          key={selectedId}
          invoiceId={selectedId}
          mutations={mutations}
          canCancel={canCancel}
          onMarkPaid={setInvoiceToPay}
          onVoidDraft={(invoice) => void handleVoidDraft(invoice)}
          onSelect={selectInvoice}
          onClose={() => selectInvoice(null)}
        />
      )}

      <CreateInvoiceModal
        open={isCreateOpen}
        submitError={createError}
        onClose={() => setIsCreateOpen(false)}
        onSubmit={handleCreate}
      />
      <MarkPaidModal invoice={invoiceToPay} onClose={() => setInvoiceToPay(null)} onSubmit={handleMarkPaid} />
    </div>
  );
};
