// Quotes Page — Kostenvoranschlagsverwaltung
import React, { useEffect, useState, useCallback } from 'react';
import { useToast } from '../contexts';
import { quotesApi } from '../api/quotes';
import { customersApi } from '../api/customers';
import {
  QuoteListItem,
  Quote,
  QuoteStatus,
  QuoteCreateInput,
  ApproveQuoteInput,
  Customer,
} from '../types';
import { SignatureCanvas } from '../components/SignatureCanvas';
import '../styles/quotes.css';

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

const STATUS_LABELS: Record<QuoteStatus, string> = {
  DRAFT: 'Entwurf',
  SENT: 'Gesendet',
  APPROVED: 'Genehmigt',
  REJECTED: 'Abgelehnt',
  EXPIRED: 'Abgelaufen',
  CONVERTED: 'Umgewandelt',
};

function StatusBadge({ status }: { status: QuoteStatus }) {
  return (
    <span className={`quote-status-badge status-${status}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('de-DE');
}

function formatAmount(amount: number): string {
  return amount.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
}

function validUntilClass(validUntilIso: string, status: QuoteStatus): string {
  if (status === 'APPROVED' || status === 'CONVERTED' || status === 'REJECTED') return '';
  const daysLeft = Math.ceil(
    (new Date(validUntilIso).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
  );
  if (daysLeft < 0) return 'valid-until-expired';
  if (daysLeft <= 3) return 'valid-until-soon';
  return '';
}

// ---------------------------------------------------------------------------
// Create Quote Modal
// ---------------------------------------------------------------------------

interface CreateQuoteModalProps {
  isOpen: boolean;
  customers: Customer[];
  isLoading: boolean;
  onClose: () => void;
  onSubmit: (data: QuoteCreateInput) => Promise<void>;
}

const CreateQuoteModal: React.FC<CreateQuoteModalProps> = ({
  isOpen,
  customers,
  isLoading,
  onClose,
  onSubmit,
}) => {
  const [customerId, setCustomerId] = useState<string>('');
  const [orderId, setOrderId] = useState<string>('');
  const [validDays, setValidDays] = useState<string>('14');
  const [taxRate, setTaxRate] = useState<string>('19');
  const [notes, setNotes] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setCustomerId('');
    setOrderId('');
    setValidDays('14');
    setTaxRate('19');
    setNotes('');
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customerId) return;
    setSubmitting(true);
    try {
      await onSubmit({
        customer_id: parseInt(customerId),
        order_id: orderId ? parseInt(orderId) : undefined,
        valid_days: parseInt(validDays) || 14,
        tax_rate: parseFloat(taxRate) || 19.0,
        notes: notes.trim() || undefined,
      });
      reset();
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div
        className="modal-content create-quote-modal"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-quote-title"
      >
        <div className="modal-header">
          <h2 id="create-quote-title" className="modal-title">Neues Angebot erstellen</h2>
          <button className="modal-close" onClick={handleClose} aria-label="Schliessen">
            &#x2715;
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="quote-customer">Kunde *</label>
            <select
              id="quote-customer"
              value={customerId}
              onChange={e => setCustomerId(e.target.value)}
              required
              disabled={isLoading}
            >
              <option value="">Kunde auswaehlen...</option>
              {customers.map(c => (
                <option key={c.id} value={c.id}>
                  {c.first_name} {c.last_name}
                  {c.company_name ? ` — ${c.company_name}` : ''}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="quote-order">Auftragsnummer (optional)</label>
            <input
              id="quote-order"
              type="number"
              min="1"
              placeholder="z.B. 42 — leer lassen fuer manuelles Angebot"
              value={orderId}
              onChange={e => setOrderId(e.target.value)}
            />
            <span className="form-hint">
              Wird ein Auftrag angegeben, werden Positionen automatisch berechnet.
            </span>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="quote-valid-days">Gueltig fuer (Tage)</label>
              <input
                id="quote-valid-days"
                type="number"
                min="1"
                max="365"
                value={validDays}
                onChange={e => setValidDays(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label htmlFor="quote-tax">MwSt-Satz (%)</label>
              <input
                id="quote-tax"
                type="number"
                min="0"
                max="100"
                step="0.1"
                value={taxRate}
                onChange={e => setTaxRate(e.target.value)}
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="quote-notes">Anmerkungen</label>
            <textarea
              id="quote-notes"
              rows={3}
              maxLength={2000}
              placeholder="Besondere Hinweise oder Konditionen..."
              value={notes}
              onChange={e => setNotes(e.target.value)}
            />
          </div>

          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={handleClose}>
              Abbrechen
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || !customerId}
            >
              {submitting ? 'Wird erstellt...' : 'Angebot erstellen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Approve Quote Modal (with SignatureCanvas)
// ---------------------------------------------------------------------------

interface ApproveModalProps {
  quote: Quote | null;
  onClose: () => void;
  onApprove: (signatureData: string | null) => Promise<void>;
}

const ApproveModal: React.FC<ApproveModalProps> = ({ quote, onClose, onApprove }) => {
  const [signatureData, setSignatureData] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!quote) return null;

  const handleApprove = async () => {
    setSubmitting(true);
    try {
      await onApprove(signatureData);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content approve-quote-modal"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="approve-quote-title"
      >
        <div className="modal-header">
          <h2 id="approve-quote-title" className="modal-title">
            Angebot genehmigen
          </h2>
          <button className="modal-close" onClick={onClose} aria-label="Schliessen">
            &#x2715;
          </button>
        </div>

        <div className="approve-quote-summary">
          <div className="summary-row">
            <span className="summary-label">KV-Nummer:</span>
            <span className="summary-value quote-number">{quote.quote_number}</span>
          </div>
          <div className="summary-row">
            <span className="summary-label">Gesamtbetrag:</span>
            <span className="summary-value summary-total">{formatAmount(quote.total)}</span>
          </div>
          <div className="summary-row">
            <span className="summary-label">Gueltig bis:</span>
            <span className="summary-value">{formatDate(quote.valid_until)}</span>
          </div>
        </div>

        <div className="signature-section">
          <label className="signature-label">
            Unterschrift des Kunden (optional)
          </label>
          <SignatureCanvas
            onSave={(data) => setSignatureData(data)}
            width={500}
            height={160}
          />
          {signatureData && (
            <p className="signature-hint signature-captured">
              Unterschrift erfasst
            </p>
          )}
          {!signatureData && (
            <p className="signature-hint">
              Feld leer lassen, falls keine Unterschrift vorhanden.
            </p>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Abbrechen
          </button>
          <button
            type="button"
            className="btn btn-approve"
            onClick={handleApprove}
            disabled={submitting}
          >
            {submitting ? 'Wird genehmigt...' : 'Angebot genehmigen'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Quote Detail Panel
// ---------------------------------------------------------------------------

interface QuoteDetailPanelProps {
  quote: Quote;
  onSend: () => void;
  onApproveClick: () => void;
  onReject: () => void;
  onConvert: () => void;
  onDownloadPdf: () => void;
  isLoading: boolean;
}

const QuoteDetailPanel: React.FC<QuoteDetailPanelProps> = ({
  quote,
  onSend,
  onApproveClick,
  onReject,
  onConvert,
  onDownloadPdf,
  isLoading,
}) => {
  return (
    <div className="quote-detail-panel">
      <div className="detail-header">
        <div>
          <span className="quote-number">{quote.quote_number}</span>
          <StatusBadge status={quote.status} />
        </div>
        <div className="quote-actions">
          <button
            className="btn btn-secondary btn-sm"
            onClick={onDownloadPdf}
            disabled={isLoading}
            aria-label="PDF herunterladen"
          >
            PDF
          </button>
          {quote.status === 'DRAFT' && (
            <button className="btn btn-primary btn-sm" onClick={onSend} disabled={isLoading}>
              Versenden
            </button>
          )}
          {(quote.status === 'SENT' || quote.status === 'DRAFT') && (
            <>
              <button className="btn btn-approve btn-sm" onClick={onApproveClick} disabled={isLoading}>
                Genehmigen
              </button>
              <button className="btn btn-reject btn-sm" onClick={onReject} disabled={isLoading}>
                Ablehnen
              </button>
            </>
          )}
          {quote.status === 'APPROVED' && (
            <button className="btn btn-convert btn-sm" onClick={onConvert} disabled={isLoading}>
              In Auftrag umwandeln
            </button>
          )}
        </div>
      </div>

      <div className="detail-meta">
        <div className="detail-meta-item">
          <span className="meta-label">Erstellt am</span>
          <span className="meta-value">{formatDate(quote.created_at)}</span>
        </div>
        <div className="detail-meta-item">
          <span className="meta-label">Gueltig bis</span>
          <span className={`meta-value ${validUntilClass(quote.valid_until, quote.status)}`}>
            {formatDate(quote.valid_until)}
          </span>
        </div>
        {quote.order_id && (
          <div className="detail-meta-item">
            <span className="meta-label">Auftragsnr.</span>
            <span className="meta-value">#{quote.order_id}</span>
          </div>
        )}
        {quote.approved_at && (
          <div className="detail-meta-item">
            <span className="meta-label">Genehmigt am</span>
            <span className="meta-value">{formatDate(quote.approved_at)}</span>
          </div>
        )}
        {quote.converted_at && (
          <div className="detail-meta-item">
            <span className="meta-label">Umgewandelt am</span>
            <span className="meta-value">{formatDate(quote.converted_at)}</span>
          </div>
        )}
      </div>

      {quote.line_items.length > 0 && (
        <>
          <table className="line-items-table">
            <thead>
              <tr>
                <th>Pos.</th>
                <th>Beschreibung</th>
                <th style={{ textAlign: 'right' }}>Menge</th>
                <th style={{ textAlign: 'right' }}>Einzelpreis</th>
                <th style={{ textAlign: 'right' }}>Gesamt</th>
              </tr>
            </thead>
            <tbody>
              {quote.line_items.map((item, idx) => (
                <tr key={item.id}>
                  <td>{idx + 1}</td>
                  <td>{item.description}</td>
                  <td style={{ textAlign: 'right' }}>{item.quantity}</td>
                  <td style={{ textAlign: 'right' }}>{formatAmount(item.unit_price)}</td>
                  <td style={{ textAlign: 'right' }}>{formatAmount(item.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="quote-totals">
            <div className="totals-row">
              <span className="totals-label">Zwischensumme:</span>
              <span className="totals-value">{formatAmount(quote.subtotal)}</span>
            </div>
            <div className="totals-row">
              <span className="totals-label">MwSt {quote.tax_rate}%:</span>
              <span className="totals-value">{formatAmount(quote.tax_amount)}</span>
            </div>
            <div className="totals-row totals-grand">
              <span className="totals-label">Gesamtbetrag:</span>
              <span className="totals-value">{formatAmount(quote.total)}</span>
            </div>
          </div>
        </>
      )}

      {quote.notes && (
        <div className="detail-notes">
          <span className="notes-label">Anmerkungen</span>
          <p className="notes-text">{quote.notes}</p>
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main QuotesPage component
// ---------------------------------------------------------------------------

export const QuotesPage: React.FC = () => {
  const { showToast } = useToast();
  const [quotes, setQuotes] = useState<QuoteListItem[]>([]);
  const [selectedQuote, setSelectedQuote] = useState<Quote | null>(null);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [statusFilter, setStatusFilter] = useState<QuoteStatus | ''>('');
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isApproveModalOpen, setIsApproveModalOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  // ------------------------------------------------------------------
  // Data loading
  // ------------------------------------------------------------------

  const loadQuotes = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = statusFilter ? { status: statusFilter } : undefined;
      const resp = await quotesApi.getQuotes(params);
      setQuotes(resp.items);
      setTotal(resp.total);
    } catch {
      showToast('Angebote konnten nicht geladen werden.', 'error');
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter, showToast]);

  const loadCustomers = useCallback(async () => {
    try {
      const resp = await customersApi.getAll({ limit: 500 });
      setCustomers(resp as Customer[]);
    } catch {
      // customers is optional for the filter — fail silently
    }
  }, []);

  useEffect(() => {
    loadQuotes();
  }, [loadQuotes]);

  useEffect(() => {
    loadCustomers();
  }, [loadCustomers]);

  // ------------------------------------------------------------------
  // Row selection — load full quote with line items
  // ------------------------------------------------------------------

  const handleRowClick = useCallback(async (item: QuoteListItem) => {
    if (selectedQuote?.id === item.id) {
      setSelectedQuote(null);
      return;
    }
    try {
      const full = await quotesApi.getQuote(item.id);
      setSelectedQuote(full);
    } catch {
      showToast('Angebot konnte nicht geladen werden.', 'error');
    }
  }, [selectedQuote, showToast]);

  // ------------------------------------------------------------------
  // Create
  // ------------------------------------------------------------------

  const handleCreate = useCallback(async (data: QuoteCreateInput) => {
    try {
      await quotesApi.createQuote(data);
      showToast('Angebot wurde erstellt.', 'success');
      setIsCreateModalOpen(false);
      await loadQuotes();
    } catch (err: any) {
      const detail = err?.response?.data?.detail ?? 'Angebot konnte nicht erstellt werden.';
      showToast(detail, 'error');
      throw err;
    }
  }, [showToast, loadQuotes]);

  // ------------------------------------------------------------------
  // Status transitions
  // ------------------------------------------------------------------

  const handleSend = useCallback(async () => {
    if (!selectedQuote) return;
    setActionLoading(true);
    try {
      const updated = await quotesApi.sendQuote(selectedQuote.id);
      setSelectedQuote(updated);
      showToast('Angebot wurde als "Gesendet" markiert.', 'success');
      await loadQuotes();
    } catch (err: any) {
      showToast(err?.response?.data?.detail ?? 'Fehler beim Versenden.', 'error');
    } finally {
      setActionLoading(false);
    }
  }, [selectedQuote, showToast, loadQuotes]);

  const handleApprove = useCallback(async (signatureData: string | null) => {
    if (!selectedQuote) return;
    setActionLoading(true);
    try {
      const payload: ApproveQuoteInput = { signature_data: signatureData ?? undefined };
      const updated = await quotesApi.approveQuote(selectedQuote.id, payload);
      setSelectedQuote(updated);
      setIsApproveModalOpen(false);
      showToast('Angebot wurde genehmigt.', 'success');
      await loadQuotes();
    } catch (err: any) {
      showToast(err?.response?.data?.detail ?? 'Fehler beim Genehmigen.', 'error');
    } finally {
      setActionLoading(false);
    }
  }, [selectedQuote, showToast, loadQuotes]);

  const handleReject = useCallback(async () => {
    if (!selectedQuote) return;
    const reason = window.prompt('Ablehnungsgrund (optional):');
    if (reason === null) return; // cancelled
    setActionLoading(true);
    try {
      const updated = await quotesApi.rejectQuote(selectedQuote.id, { reason: reason || undefined });
      setSelectedQuote(updated);
      showToast('Angebot wurde abgelehnt.', 'success');
      await loadQuotes();
    } catch (err: any) {
      showToast(err?.response?.data?.detail ?? 'Fehler beim Ablehnen.', 'error');
    } finally {
      setActionLoading(false);
    }
  }, [selectedQuote, showToast, loadQuotes]);

  const handleConvert = useCallback(async () => {
    if (!selectedQuote) return;
    if (!window.confirm(`Angebot ${selectedQuote.quote_number} in einen Auftrag umwandeln?`)) return;
    setActionLoading(true);
    try {
      const updated = await quotesApi.convertQuote(selectedQuote.id);
      setSelectedQuote(updated);
      showToast('Angebot wurde in einen Auftrag umgewandelt.', 'success');
      await loadQuotes();
    } catch (err: any) {
      showToast(err?.response?.data?.detail ?? 'Fehler beim Umwandeln.', 'error');
    } finally {
      setActionLoading(false);
    }
  }, [selectedQuote, showToast, loadQuotes]);

  const handleDownloadPdf = useCallback(async () => {
    if (!selectedQuote) return;
    try {
      await quotesApi.downloadPdf(selectedQuote.id, selectedQuote.quote_number);
    } catch {
      showToast('PDF-Download fehlgeschlagen.', 'error');
    }
  }, [selectedQuote, showToast]);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">Angebote</h1>
          <p className="page-subtitle">{total} Kostenvoranschlag{total !== 1 ? 'e' : ''}</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setIsCreateModalOpen(true)}
        >
          Neues Angebot
        </button>
      </div>

      {/* Status filter */}
      <div className="quotes-controls">
        <div className="form-group form-group-inline">
          <label htmlFor="status-filter">Status</label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value as QuoteStatus | '')}
          >
            <option value="">Alle</option>
            <option value="DRAFT">Entwurf</option>
            <option value="SENT">Gesendet</option>
            <option value="APPROVED">Genehmigt</option>
            <option value="REJECTED">Abgelehnt</option>
            <option value="EXPIRED">Abgelaufen</option>
            <option value="CONVERTED">Umgewandelt</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="table-container">
        {isLoading ? (
          <div className="loading-state">Angebote werden geladen...</div>
        ) : quotes.length === 0 ? (
          <div className="empty-state">
            <p>Keine Angebote gefunden.</p>
            <button className="btn btn-primary" onClick={() => setIsCreateModalOpen(true)}>
              Erstes Angebot erstellen
            </button>
          </div>
        ) : (
          <table className="quotes-table">
            <thead>
              <tr>
                <th>KV-Nummer</th>
                <th>Kunde (ID)</th>
                <th>Erstellt</th>
                <th>Gueltig bis</th>
                <th style={{ textAlign: 'right' }}>Betrag</th>
                <th>Status</th>
                <th>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {quotes.map(q => (
                <tr
                  key={q.id}
                  onClick={() => handleRowClick(q)}
                  className={selectedQuote?.id === q.id ? 'row-selected' : ''}
                >
                  <td data-label="KV-Nummer">
                    <span className="quote-number">{q.quote_number}</span>
                  </td>
                  <td data-label="Kunde">#{q.customer_id}</td>
                  <td data-label="Erstellt">{formatDate(q.created_at)}</td>
                  <td data-label="Gueltig bis">
                    <span className={validUntilClass(q.valid_until, q.status)}>
                      {formatDate(q.valid_until)}
                    </span>
                  </td>
                  <td data-label="Betrag" style={{ textAlign: 'right' }}>
                    <span className="amount-display">{formatAmount(q.total)}</span>
                  </td>
                  <td data-label="Status">
                    <StatusBadge status={q.status} />
                  </td>
                  <td data-label="Aktionen" onClick={e => e.stopPropagation()}>
                    <div className="quote-row-actions">
                      <button
                        className="btn btn-secondary btn-xs"
                        onClick={async () => {
                          try {
                            await quotesApi.downloadPdf(q.id, q.quote_number);
                          } catch {
                            showToast('PDF-Download fehlgeschlagen.', 'error');
                          }
                        }}
                        aria-label="PDF herunterladen"
                        title="PDF herunterladen"
                      >
                        PDF
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Detail panel */}
      {selectedQuote && (
        <QuoteDetailPanel
          quote={selectedQuote}
          onSend={handleSend}
          onApproveClick={() => setIsApproveModalOpen(true)}
          onReject={handleReject}
          onConvert={handleConvert}
          onDownloadPdf={handleDownloadPdf}
          isLoading={actionLoading}
        />
      )}

      {/* Create modal */}
      <CreateQuoteModal
        isOpen={isCreateModalOpen}
        customers={customers}
        isLoading={isLoading}
        onClose={() => setIsCreateModalOpen(false)}
        onSubmit={handleCreate}
      />

      {/* Approve modal */}
      <ApproveModal
        quote={isApproveModalOpen ? selectedQuote : null}
        onClose={() => setIsApproveModalOpen(false)}
        onApprove={handleApprove}
      />
    </div>
  );
};
