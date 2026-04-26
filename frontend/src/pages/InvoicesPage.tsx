// Invoice Management Page — Rechnungsverwaltung
import React, { useEffect, useState, useCallback } from 'react';
import { useAuth, useToast, useConfirm } from '../contexts';
import apiClient from '../api/client';
import { invoicesApi } from '../api/invoices';
import { ordersApi } from '../api/orders';
import {
  InvoiceListItem,
  Invoice,
  InvoiceStatus,
  InvoiceCreateInput,
  MarkPaidInput,
  OrderType,
} from '../types';
import '../styles/pages.css';
import '../styles/invoices.css';

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

// Status keys are the backend's lowercase enum values (see types.ts).
const STATUS_LABELS: Record<InvoiceStatus, string> = {
  draft: 'Entwurf',
  sent: 'Versendet',
  paid: 'Bezahlt',
  overdue: 'Überfällig',
  cancelled: 'Storniert',
};

// Colorblind-safe: label text carries the semantic meaning, color is secondary.
function StatusBadge({ status }: { status: InvoiceStatus }) {
  return (
    <span className={`invoice-status-badge status-${status}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Date helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('de-DE');
}

function formatAmount(amount: number): string {
  return amount.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
}

/**
 * Extracts a human-readable error message from an Axios error.
 *
 * FastAPI error shapes we have to handle:
 *   - `{detail: "string"}` from explicit `HTTPException(status_code=4xx, detail="...")`
 *   - `{detail: [{loc, msg, type}]}` from Pydantic validation (422)
 *
 * Without this normalization, rendering the array shape via JSX throws
 * "Objects are not valid as a React child", which is exactly how previous
 * invoice errors became invisible: the explicit-string case was masked by
 * the `|| 'Fehler beim Erstellen ...'` fallback after a render crash.
 */
function extractBackendErrorMessage(
  err: unknown,
  fallback: string
): string {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const detail = (err as any)?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    // Pydantic validation: stitch together the human-readable msgs
    return detail
      .map((d: { msg?: string; loc?: unknown[] }) =>
        d?.msg ? d.msg : JSON.stringify(d)
      )
      .join('; ');
  }
  return fallback;
}

function dueDateClass(dueIso: string, status: InvoiceStatus): string {
  if (status === 'paid' || status === 'cancelled') return '';
  const daysLeft = Math.ceil(
    (new Date(dueIso).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
  );
  if (daysLeft < 0) return 'due-date-overdue';
  if (daysLeft <= 7) return 'due-date-soon';
  return '';
}

// ---------------------------------------------------------------------------
// Create Invoice Modal
// ---------------------------------------------------------------------------

interface CreateInvoiceModalProps {
  isOpen: boolean;
  orders: OrderType[];
  isLoading: boolean;
  submitError: string | null;
  onClose: () => void;
  onSubmit: (data: InvoiceCreateInput) => Promise<void>;
}

/**
 * Statuses for which the backend allows invoice creation.
 *
 * Mirrors the guard in `InvoiceService.create_invoice_from_order`:
 *   if order.status not in (OrderStatusEnum.COMPLETED, OrderStatusEnum.DELIVERED): 422
 *
 * Filtering the dropdown client-side gives the user immediate feedback
 * (no failing round-trip) and prevents the previous "generic error"
 * dead-end where users picked a draft / in_progress order and got a
 * surprise 422.
 */
const INVOICEABLE_ORDER_STATUSES: ReadonlyArray<OrderType['status']> = [
  'completed',
  'delivered',
];

const CreateInvoiceModal: React.FC<CreateInvoiceModalProps> = ({
  isOpen,
  orders,
  isLoading,
  submitError,
  onClose,
  onSubmit,
}) => {
  const [orderId, setOrderId] = useState<string>('');
  const [dueDate, setDueDate] = useState<string>('');
  const [taxRate, setTaxRate] = useState<string>('19');
  const [notes, setNotes] = useState<string>('');
  const [paymentMethod, setPaymentMethod] = useState<string>('');

  // Default due date = today + 14 days
  useEffect(() => {
    if (isOpen) {
      const d = new Date();
      d.setDate(d.getDate() + 14);
      setDueDate(d.toISOString().substring(0, 10));
      setOrderId('');
      setTaxRate('19');
      setNotes('');
      setPaymentMethod('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  // Only show orders the backend will actually accept. The full list is
  // still fetched (for audit completeness in availableOrders), but we hide
  // ineligible ones from the picker so the user can't fall into the trap.
  const eligibleOrders = orders.filter((o) =>
    INVOICEABLE_ORDER_STATUSES.includes(o.status)
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!orderId || !dueDate) return;
    await onSubmit({
      order_id: Number(orderId),
      due_date: new Date(dueDate).toISOString(),
      tax_rate: Number(taxRate),
      notes: notes || undefined,
      payment_method: paymentMethod || undefined,
    });
  };

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-invoice-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal create-invoice-modal" style={{ maxWidth: 520 }}>
        <div className="modal-header">
          <h2 id="create-invoice-title">Rechnung erstellen</h2>
          <button
            className="modal-close"
            onClick={onClose}
            aria-label="Modal schließen"
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {/*
              Inline error banner — shows the backend's `detail` string when
              the API rejects creation (e.g. order status not eligible, or
              an active invoice already exists). The modal stays open so the
              user can fix the input rather than starting over.
            */}
            {submitError && (
              <div
                role="alert"
                className="invoice-create-error"
                data-testid="invoice-create-error"
              >
                {submitError}
              </div>
            )}

            <div className="form-group">
              <label htmlFor="invoice-order-select">
                Auftrag <span style={{ color: '#ef4444' }}>*</span>
              </label>
              <select
                id="invoice-order-select"
                value={orderId}
                onChange={(e) => setOrderId(e.target.value)}
                required
              >
                <option value="">-- Auftrag wählen --</option>
                {eligibleOrders.map((o) => (
                  <option key={o.id} value={o.id}>
                    #{o.id} — {o.title}
                  </option>
                ))}
              </select>
              {eligibleOrders.length === 0 && (
                <p className="form-helper-text" style={{ color: '#6b7280', fontSize: '0.85rem', marginTop: '0.25rem' }}>
                  Keine abrechenbaren Aufträge vorhanden. Aufträge müssen den
                  Status "Abgeschlossen" oder "Ausgeliefert" haben.
                </p>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="invoice-due-date">
                Fälligkeitsdatum <span style={{ color: '#ef4444' }}>*</span>
              </label>
              <input
                id="invoice-due-date"
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                required
                min={new Date().toISOString().substring(0, 10)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="invoice-tax-rate">MwSt-Satz (%)</label>
              <select
                id="invoice-tax-rate"
                value={taxRate}
                onChange={(e) => setTaxRate(e.target.value)}
              >
                <option value="19">19% (Standard)</option>
                <option value="7">7% (Ermäßigt)</option>
                <option value="0">0% (Steuerfrei)</option>
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="invoice-payment-method">Zahlungsart</label>
              <select
                id="invoice-payment-method"
                value={paymentMethod}
                onChange={(e) => setPaymentMethod(e.target.value)}
              >
                <option value="">-- optional --</option>
                <option value="Ueberweisung">Überweisung</option>
                <option value="Bar">Barzahlung</option>
                <option value="Karte">Kartenzahlung</option>
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="invoice-notes">Anmerkungen</label>
              <textarea
                id="invoice-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
                maxLength={2000}
                placeholder="Optionale Hinweise zur Rechnung..."
              />
            </div>
          </div>

          <div className="modal-footer">
            <button
              type="button"
              className="btn-secondary"
              onClick={onClose}
              disabled={isLoading}
            >
              Abbrechen
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={isLoading || !orderId || !dueDate}
            >
              {isLoading ? 'Erstelle...' : 'Rechnung erstellen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Mark as Paid Modal
// ---------------------------------------------------------------------------

interface MarkPaidModalProps {
  invoice: InvoiceListItem | null;
  isLoading: boolean;
  onClose: () => void;
  onSubmit: (data: MarkPaidInput) => Promise<void>;
}

const MarkPaidModal: React.FC<MarkPaidModalProps> = ({
  invoice,
  isLoading,
  onClose,
  onSubmit,
}) => {
  const today = new Date().toISOString().substring(0, 10);
  const [paidDate, setPaidDate] = useState(today);
  const [paymentMethod, setPaymentMethod] = useState('');

  useEffect(() => {
    if (invoice) {
      setPaidDate(today);
      setPaymentMethod(invoice ? '' : '');
    }
  }, [invoice]);

  if (!invoice) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSubmit({
      paid_date: paidDate ? new Date(paidDate).toISOString() : null,
      payment_method: paymentMethod || undefined,
    });
  };

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="mark-paid-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal mark-paid-modal" style={{ maxWidth: 440 }}>
        <div className="modal-header">
          <h2 id="mark-paid-title">Als bezahlt markieren</h2>
          <button
            className="modal-close"
            onClick={onClose}
            aria-label="Modal schließen"
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="payment-summary">
              <div style={{ fontSize: '0.85rem', color: '#374151', marginBottom: '0.25rem' }}>
                Rechnungsnummer
              </div>
              <div style={{ fontWeight: 700, color: '#1e40af', fontFamily: 'monospace', marginBottom: '0.75rem' }}>
                {invoice.invoice_number}
              </div>
              <div style={{ fontSize: '0.85rem', color: '#374151', marginBottom: '0.25rem' }}>
                Gesamtbetrag
              </div>
              <div className="summary-amount">{formatAmount(invoice.total)}</div>
            </div>

            <div className="form-group">
              <label htmlFor="paid-date">Zahlungsdatum</label>
              <input
                id="paid-date"
                type="date"
                value={paidDate}
                onChange={(e) => setPaidDate(e.target.value)}
                max={today}
              />
            </div>

            <div className="form-group">
              <label htmlFor="paid-method">Zahlungsart</label>
              <select
                id="paid-method"
                value={paymentMethod}
                onChange={(e) => setPaymentMethod(e.target.value)}
              >
                <option value="">-- optional --</option>
                <option value="Ueberweisung">Überweisung</option>
                <option value="Bar">Barzahlung</option>
                <option value="Karte">Kartenzahlung</option>
              </select>
            </div>
          </div>

          <div className="modal-footer">
            <button
              type="button"
              className="btn-secondary"
              onClick={onClose}
              disabled={isLoading}
            >
              Abbrechen
            </button>
            <button
              type="submit"
              className="btn-mark-paid"
              disabled={isLoading}
            >
              {isLoading ? 'Speichere...' : 'Als bezahlt markieren'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Invoice Detail Panel (inline expand)
// ---------------------------------------------------------------------------

interface InvoiceDetailPanelProps {
  invoiceId: number;
  onClose: () => void;
}

/**
 * Inline detail panel for a single invoice.
 *
 * IMPORTANT — rendering outside the table:
 *   The panel used to render as `<tr><td colspan=7>` inside the invoices
 *   table, but that constrained its width to the natural width of the
 *   wider 7-column table (~1018px on desktop) which overflowed the
 *   `.table-container` (`overflow: hidden`, ~880px). The right-aligned
 *   totals values were therefore clipped off-screen — exactly the symptom
 *   reported. Rendering as a regular block sibling tracks the container
 *   width and removes the print-CSS contortions that the previous fix
 *   needed (no more `:not(:has(...))` selector required for the print
 *   page either).
 *
 * The panel is rendered by the parent page below the table, keyed to
 * `expandedInvoiceId`, so it still appears immediately under the row in
 * the natural reading order even though it's no longer DOM-nested inside
 * the row.
 */
const InvoiceDetailPanel: React.FC<InvoiceDetailPanelProps> = ({ invoiceId, onClose }) => {
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const data = await invoicesApi.getInvoice(invoiceId);
        setInvoice(data);
      } catch {
        setError('Rechnungsdetails konnten nicht geladen werden.');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, [invoiceId]);

  if (isLoading) {
    return (
      <div className="invoice-detail-panel" data-testid="invoice-detail-loading">
        <div style={{ padding: '1rem', textAlign: 'center', color: '#666' }}>
          Lade Details...
        </div>
      </div>
    );
  }

  if (error || !invoice) {
    return (
      <div className="invoice-detail-panel" role="alert">
        <div style={{ padding: '1rem', color: '#dc2626' }}>{error}</div>
      </div>
    );
  }

  return (
    <div className="invoice-detail-panel" data-testid="invoice-detail-panel">
      <div className="detail-header">
        <div>
          <span className="invoice-number" style={{ fontSize: '1.1rem' }}>
            {invoice.invoice_number}
          </span>
          <StatusBadge status={invoice.status} />
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <button
            className="btn-secondary btn-print"
            onClick={() => window.print()}
            style={{ minHeight: 44, padding: '0.5rem 1rem' }}
            title="Rechnung drucken"
          >
            Drucken
          </button>
          <button
            className="btn-secondary btn-close-detail"
            onClick={onClose}
            style={{ minHeight: 44, padding: '0.5rem 1rem' }}
          >
            Schließen
          </button>
        </div>
      </div>

      <div className="detail-meta">
        <div className="detail-meta-item">
          <span className="meta-label">Ausstellungsdatum</span>
          <span className="meta-value">{formatDate(invoice.issue_date)}</span>
        </div>
        <div className="detail-meta-item">
          <span className="meta-label">Fälligkeitsdatum</span>
          <span className={`meta-value ${dueDateClass(invoice.due_date, invoice.status)}`}>
            {formatDate(invoice.due_date)}
          </span>
        </div>
        {invoice.paid_date && (
          <div className="detail-meta-item">
            <span className="meta-label">Zahlungseingang</span>
            <span className="meta-value">{formatDate(invoice.paid_date)}</span>
          </div>
        )}
        {invoice.payment_method && (
          <div className="detail-meta-item">
            <span className="meta-label">Zahlungsart</span>
            <span className="meta-value">{invoice.payment_method}</span>
          </div>
        )}
        <div className="detail-meta-item">
          <span className="meta-label">Auftrag</span>
          <span className="meta-value">#{invoice.order_id}</span>
        </div>
      </div>

      {invoice.notes && (
        <div style={{ marginBottom: '1rem', color: '#374151', fontSize: '0.9rem' }}>
          <strong>Anmerkungen:</strong> {invoice.notes}
        </div>
      )}

      {/* Line items */}
      {invoice.line_items.length > 0 && (
        <div className="table-container" style={{ marginBottom: '1rem' }}>
          <table className="line-items-table">
            <thead>
              <tr>
                <th>Beschreibung</th>
                <th>Typ</th>
                <th style={{ textAlign: 'right' }}>Menge</th>
                <th style={{ textAlign: 'right' }}>Einzelpreis (netto)</th>
                <th style={{ textAlign: 'right' }}>Gesamt (netto)</th>
              </tr>
            </thead>
            <tbody>
              {invoice.line_items.map((item) => (
                <tr key={item.id}>
                  <td>{item.description}</td>
                  <td>{item.line_type}</td>
                  <td style={{ textAlign: 'right' }}>{item.quantity}</td>
                  <td style={{ textAlign: 'right' }}>{formatAmount(item.unit_price)}</td>
                  <td style={{ textAlign: 'right' }}>{formatAmount(item.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Totals */}
      <div className="invoice-totals">
        <div className="totals-row">
          <span className="totals-label">Zwischensumme (netto)</span>
          <span className="totals-value">{formatAmount(invoice.subtotal)}</span>
        </div>
        <div className="totals-row">
          <span className="totals-label">MwSt ({invoice.tax_rate}%)</span>
          <span className="totals-value">{formatAmount(invoice.tax_amount)}</span>
        </div>
        <div className="totals-row totals-grand">
          <span className="totals-label">Gesamtbetrag (brutto)</span>
          <span className="totals-value">{formatAmount(invoice.total)}</span>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export const InvoicesPage: React.FC = () => {
  const { hasRole } = useAuth();
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();

  const [invoices, setInvoices] = useState<InvoiceListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [filterStatus, setFilterStatus] = useState<InvoiceStatus | ''>('');
  const [filterFrom, setFilterFrom] = useState('');
  const [filterTo, setFilterTo] = useState('');

  // Pagination
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 25;

  // Create modal
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [availableOrders, setAvailableOrders] = useState<OrderType[]>([]);
  const [isCreateLoading, setIsCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Mark as paid modal
  const [invoiceToMarkPaid, setInvoiceToMarkPaid] = useState<InvoiceListItem | null>(null);
  const [isMarkPaidLoading, setIsMarkPaidLoading] = useState(false);

  // Inline detail expand
  const [expandedInvoiceId, setExpandedInvoiceId] = useState<number | null>(null);

  // Export dropdown
  const [isExportMenuOpen, setIsExportMenuOpen] = useState(false);

  const fetchInvoices = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await invoicesApi.getInvoices({
        status: filterStatus || undefined,
        from: filterFrom || undefined,
        to: filterTo || undefined,
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      setInvoices(data.items);
      setTotal(data.total);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Rechnungen.');
    } finally {
      setIsLoading(false);
    }
  }, [filterStatus, filterFrom, filterTo, page]);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  // Guard — this page is for ADMIN and GOLDSMITH only.
  // Placed after all hooks so React's hook call order is always consistent.
  if (!hasRole(['ADMIN', 'GOLDSMITH'])) {
    return (
      <div className="page-error">
        Keine Berechtigung. Diese Seite ist nur für Goldschmiede und Administratoren zugänglich.
      </div>
    );
  }

  const openCreateModal = async () => {
    setCreateError(null);
    try {
      const orders = await ordersApi.getAll({ limit: 500 });
      setAvailableOrders(orders);
    } catch {
      setAvailableOrders([]);
    }
    setIsCreateModalOpen(true);
  };

  const closeCreateModal = () => {
    setIsCreateModalOpen(false);
    setCreateError(null);
  };

  const handleCreateInvoice = async (data: InvoiceCreateInput) => {
    try {
      setIsCreateLoading(true);
      setCreateError(null);
      await invoicesApi.createFromOrder(data);
      setIsCreateModalOpen(false);
      await fetchInvoices();
      showToast('Rechnung erfolgreich erstellt!', 'success');
    } catch (err) {
      const message = extractBackendErrorMessage(
        err,
        'Fehler beim Erstellen der Rechnung.'
      );
      // Surface inline in the modal so the user can fix the input. Also
      // emit a toast so the error is announced to assistive tech and is
      // visible if the modal is dismissed before the user reads it.
      setCreateError(message);
      showToast(message, 'error');
    } finally {
      setIsCreateLoading(false);
    }
  };

  const handleMarkPaid = async (data: MarkPaidInput) => {
    if (!invoiceToMarkPaid) return;
    try {
      setIsMarkPaidLoading(true);
      await invoicesApi.markAsPaid(invoiceToMarkPaid.id, data);
      setInvoiceToMarkPaid(null);
      await fetchInvoices();
      showToast('Rechnung als bezahlt markiert.', 'success');
    } catch (err) {
      showToast(
        extractBackendErrorMessage(
          err,
          'Fehler beim Aktualisieren des Zahlungsstatus.'
        ),
        'error'
      );
    } finally {
      setIsMarkPaidLoading(false);
    }
  };

  const handleCancelInvoice = async (invoice: InvoiceListItem, e: React.MouseEvent) => {
    e.stopPropagation();
    const confirmed = await showConfirm({
      title: 'Rechnung stornieren',
      message: `Rechnung ${invoice.invoice_number} wirklich stornieren?`,
      confirmLabel: 'Stornieren',
      variant: 'danger',
    });
    if (!confirmed) return;
    try {
      await invoicesApi.updateInvoice(invoice.id, { status: 'cancelled' });
      await fetchInvoices();
    } catch (err) {
      showToast(
        extractBackendErrorMessage(err, 'Fehler beim Stornieren der Rechnung.'),
        'error'
      );
    }
  };

  const handleRowClick = (id: number) => {
    setExpandedInvoiceId((prev) => (prev === id ? null : id));
  };

  const resetFilters = () => {
    setFilterStatus('');
    setFilterFrom('');
    setFilterTo('');
    setPage(0);
  };

  /**
   * Trigger a browser download for the given accounting export format.
   *
   * Uses the Fetch API with the stored JWT token in the Authorization header
   * (the same token that the Axios client uses for all other requests).
   * Once the response arrives, a temporary blob URL is created and a hidden
   * anchor element is clicked to trigger the browser's native file-save dialog.
   *
   * This avoids the need to pass the token as a query parameter — which would
   * expose it in server access logs and browser history.
   */
  const handleExport = async (format: 'datev' | 'lexoffice') => {
    setIsExportMenuOpen(false);

    const params = new URLSearchParams();
    if (filterFrom) params.set('date_from', new Date(filterFrom).toISOString());
    if (filterTo) params.set('date_to', new Date(filterTo).toISOString());
    if (filterStatus && format === 'datev') params.set('status', filterStatus);

    const url = `/invoices/export/${format}?${params.toString()}`;

    try {
      const response = await apiClient.get(url, { responseType: 'blob' });
      const blob = response.data;
      const blobUrl = URL.createObjectURL(blob);
      const today = new Date().toISOString().substring(0, 10).replace(/-/g, '');
      const filename = `${format}_export_${today}.csv`;

      const anchor = document.createElement('a');
      anchor.href = blobUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(blobUrl);
    } catch {
      showToast('Export fehlgeschlagen. Bitte versuchen Sie es erneut.', 'error');
    }
  };

  // Summary stats from current page
  const totalAmount = invoices.reduce((sum, inv) => sum + inv.total, 0);
  const overdueCount = invoices.filter((inv) => inv.status === 'overdue').length;
  const paidCount = invoices.filter((inv) => inv.status === 'paid').length;

  const totalPages = Math.ceil(total / PAGE_SIZE);

  if (error) {
    return (
      <div className="page-error">
        <span>{error}</span>
        <button className="btn-secondary" onClick={fetchInvoices}>
          Erneut versuchen
        </button>
      </div>
    );
  }

  return (
    <div className="page-container">
      <header className="page-header">
        <div>
          <h1>Rechnungen</h1>
          <p style={{ color: '#666', margin: '0.5rem 0 0 0' }}>
            {total} Rechnungen gesamt
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          {/* Export dropdown — ADMIN only */}
          {hasRole(['ADMIN']) && (
            <div style={{ position: 'relative' }}>
              <button
                className="btn-secondary"
                onClick={() => setIsExportMenuOpen((prev) => !prev)}
                aria-haspopup="true"
                aria-expanded={isExportMenuOpen}
                style={{ minHeight: 44 }}
              >
                Export ▾
              </button>
              {isExportMenuOpen && (
                <div
                  role="menu"
                  style={{
                    position: 'absolute',
                    right: 0,
                    top: 'calc(100% + 4px)',
                    background: '#ffffff',
                    border: '2px solid #e5e7eb',
                    borderRadius: 8,
                    boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
                    minWidth: 200,
                    zIndex: 100,
                    overflow: 'hidden',
                  }}
                >
                  <button
                    role="menuitem"
                    onClick={() => handleExport('datev')}
                    style={{
                      display: 'block',
                      width: '100%',
                      textAlign: 'left',
                      padding: '0.875rem 1.25rem',
                      background: 'none',
                      border: 'none',
                      borderBottom: '1px solid #f3f4f6',
                      cursor: 'pointer',
                      fontSize: '0.95rem',
                      color: '#111827',
                      minHeight: 44,
                    }}
                    onMouseEnter={(e) => ((e.target as HTMLElement).style.background = '#f3f4f6')}
                    onMouseLeave={(e) => ((e.target as HTMLElement).style.background = 'none')}
                  >
                    DATEV Export
                  </button>
                  <button
                    role="menuitem"
                    onClick={() => handleExport('lexoffice')}
                    style={{
                      display: 'block',
                      width: '100%',
                      textAlign: 'left',
                      padding: '0.875rem 1.25rem',
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      fontSize: '0.95rem',
                      color: '#111827',
                      minHeight: 44,
                    }}
                    onMouseEnter={(e) => ((e.target as HTMLElement).style.background = '#f3f4f6')}
                    onMouseLeave={(e) => ((e.target as HTMLElement).style.background = 'none')}
                  >
                    Lexoffice Export
                  </button>
                </div>
              )}
            </div>
          )}
          <button className="btn-primary" onClick={openCreateModal}>
            + Rechnung erstellen
          </button>
        </div>
      </header>

      {/* Summary bar */}
      <div className="invoice-summary-bar">
        <div className="invoice-summary-card">
          <span className="summary-label">Gesamt (Seite)</span>
          <span className="summary-value">{formatAmount(totalAmount)}</span>
        </div>
        <div className="invoice-summary-card card-overdue">
          <span className="summary-label">Überfällig</span>
          <span className="summary-value">{overdueCount}</span>
        </div>
        <div className="invoice-summary-card card-paid">
          <span className="summary-label">Bezahlt</span>
          <span className="summary-value">{paidCount}</span>
        </div>
        <div className="invoice-summary-card">
          <span className="summary-label">Einträge</span>
          <span className="summary-value">{invoices.length}</span>
        </div>
      </div>

      {/* Filters */}
      <div className="invoices-controls">
        <div className="filter-group">
          <label>Status:</label>
          <select
            value={filterStatus}
            onChange={(e) => {
              setFilterStatus(e.target.value as InvoiceStatus | '');
              setPage(0);
            }}
          >
            <option value="">Alle Status</option>
            <option value="draft">Entwurf</option>
            <option value="sent">Versendet</option>
            <option value="paid">Bezahlt</option>
            <option value="overdue">Überfällig</option>
            <option value="cancelled">Storniert</option>
          </select>
        </div>

        <div className="filter-group">
          <label>Von:</label>
          <input
            type="date"
            value={filterFrom}
            onChange={(e) => {
              setFilterFrom(e.target.value);
              setPage(0);
            }}
            style={{ padding: '0.75rem 1rem', border: '2px solid #e5e7eb', borderRadius: 8, fontSize: '1rem', minHeight: 44 }}
          />
        </div>

        <div className="filter-group">
          <label>Bis:</label>
          <input
            type="date"
            value={filterTo}
            onChange={(e) => {
              setFilterTo(e.target.value);
              setPage(0);
            }}
            style={{ padding: '0.75rem 1rem', border: '2px solid #e5e7eb', borderRadius: 8, fontSize: '1rem', minHeight: 44 }}
          />
        </div>

        {(filterStatus || filterFrom || filterTo) && (
          <div className="filter-group">
            <label>&nbsp;</label>
            <button
              className="btn-secondary"
              onClick={resetFilters}
              style={{ minHeight: 44 }}
            >
              Filter zurücksetzen
            </button>
          </div>
        )}
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="page-loading">Lade Rechnungen...</div>
      ) : invoices.length === 0 ? (
        <div className="empty-state">
          <p>
            {filterStatus || filterFrom || filterTo
              ? 'Keine Rechnungen für diese Filter gefunden.'
              : 'Noch keine Rechnungen vorhanden.'}
          </p>
        </div>
      ) : (
        <>
          <div className="table-container">
            <table className="invoices-table">
              <thead>
                <tr>
                  <th>Rechnungsnummer</th>
                  <th>Auftrag</th>
                  <th>Ausstelldatum</th>
                  <th>Fälligkeitsdatum</th>
                  <th>Gesamtbetrag</th>
                  <th>Status</th>
                  <th>Aktionen</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((invoice) => (
                  <tr
                    key={invoice.id}
                    onClick={() => handleRowClick(invoice.id)}
                    aria-expanded={expandedInvoiceId === invoice.id}
                  >
                    <td data-label="Rechnungsnummer">
                      <span className="invoice-number">{invoice.invoice_number}</span>
                    </td>
                    <td data-label="Auftrag">#{invoice.order_id}</td>
                    <td data-label="Ausstelldatum">
                      {formatDate(invoice.issue_date)}
                    </td>
                    <td data-label="Fälligkeitsdatum">
                      <span className={dueDateClass(invoice.due_date, invoice.status)}>
                        {formatDate(invoice.due_date)}
                      </span>
                    </td>
                    <td data-label="Gesamtbetrag">
                      <span
                        className={
                          invoice.status === 'overdue'
                            ? 'amount-overdue'
                            : 'amount-display'
                        }
                      >
                        {formatAmount(invoice.total)}
                      </span>
                    </td>
                    <td data-label="Status">
                      <StatusBadge status={invoice.status} />
                    </td>
                    <td data-label="Aktionen">
                      <div
                        className="invoice-actions"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {/* "Als bezahlt markieren" — only for SENT/OVERDUE invoices */}
                        {(invoice.status === 'sent' || invoice.status === 'overdue') && (
                          <button
                            className="btn-mark-paid"
                            onClick={(e) => {
                              e.stopPropagation();
                              setInvoiceToMarkPaid(invoice);
                            }}
                            title="Als bezahlt markieren"
                          >
                            Bezahlt
                          </button>
                        )}

                        {/* "Stornieren" — only for DRAFT invoices */}
                        {invoice.status === 'draft' && (
                          <button
                            className="btn-cancel-invoice"
                            onClick={(e) => handleCancelInvoice(invoice, e)}
                            title="Rechnung stornieren"
                          >
                            Stornieren
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/*
            Detail panel is rendered OUTSIDE the table so its width tracks
            the page container, not the natural width of the wider 7-column
            invoices-table. See InvoiceDetailPanel JSDoc for context.
          */}
          {expandedInvoiceId !== null && (
            <InvoiceDetailPanel
              key={expandedInvoiceId}
              invoiceId={expandedInvoiceId}
              onClose={() => setExpandedInvoiceId(null)}
            />
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="pagination-controls">
              <div className="pagination-info">
                Seite {page + 1} von {totalPages} &bull; {total} Rechnungen
              </div>
              <div className="pagination-buttons">
                <button onClick={() => setPage(0)} disabled={page === 0}>
                  &laquo; Erste
                </button>
                <button onClick={() => setPage(page - 1)} disabled={page === 0}>
                  &lsaquo; Zurück
                </button>
                <button
                  onClick={() => setPage(page + 1)}
                  disabled={page >= totalPages - 1}
                >
                  Weiter &rsaquo;
                </button>
                <button
                  onClick={() => setPage(totalPages - 1)}
                  disabled={page >= totalPages - 1}
                >
                  Letzte &raquo;
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Create Invoice Modal */}
      <CreateInvoiceModal
        isOpen={isCreateModalOpen}
        orders={availableOrders}
        isLoading={isCreateLoading}
        submitError={createError}
        onClose={closeCreateModal}
        onSubmit={handleCreateInvoice}
      />

      {/* Mark as Paid Modal */}
      <MarkPaidModal
        invoice={invoiceToMarkPaid}
        isLoading={isMarkPaidLoading}
        onClose={() => setInvoiceToMarkPaid(null)}
        onSubmit={handleMarkPaid}
      />
    </div>
  );
};
