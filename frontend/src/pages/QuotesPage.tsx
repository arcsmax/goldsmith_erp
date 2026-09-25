// Quotes Page — Kostenvoranschlagsverwaltung
import React, { useEffect, useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast, useConfirm } from '../contexts';
import { quotesApi, QuoteApprovalMethod, QuoteWithDelivery } from '../api/quotes';
import { ordersApi } from '../api/orders';
import {
  QuoteListItem,
  Quote,
  QuoteStatus,
  QuoteCreateInput,
  QuoteLineItem,
  QuoteLineItemInput,
  QuoteLineType,
  OrderType,
} from '../types';
import { logError } from '../lib/logError';
import { SignatureCanvas } from '../components/SignatureCanvas';
import { EstimatorPanel } from '../components/estimator/EstimatorPanel';
import { StatusBadge } from '../ui/StatusBadge';
import { QUOTE_STATUS } from '../design/status';
import { CustomerTypeahead } from '../components/consultation/CustomerTypeahead';
// pages.css: shared .page-header layout (LV-15); consultations.css: the
// .typeahead dropdown styles used by CustomerTypeahead (LV-02).
import '../styles/pages.css';
import '../styles/consultations.css';
import '../styles/quotes.css';

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('de-DE');
}

function formatAmount(amount: number): string {
  return amount.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
}

function validUntilClass(validUntilIso: string, status: QuoteStatus): string {
  if (status === 'approved' || status === 'converted' || status === 'rejected') return '';
  const daysLeft = Math.ceil(
    (new Date(validUntilIso).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
  );
  if (daysLeft < 0) return 'valid-until-expired';
  if (daysLeft <= 3) return 'valid-until-soon';
  return '';
}

/** DOM-11: German toast for the outcome of "Versenden". */
export function sendOutcomeMessage(quote: QuoteWithDelivery): string {
  if (quote.delivery_method === 'email') {
    return 'Kostenvoranschlag per E-Mail versendet.';
  }
  return 'Kostenvoranschlag als versendet vermerkt. Das PDF wurde heruntergeladen, bitte an den Kunden übergeben.';
}

/** DOM-11d: how the customer agreed (backend CostChangeResponseMethod). */
const APPROVAL_METHOD_OPTIONS: { value: QuoteApprovalMethod; label: string }[] = [
  { value: 'in_person', label: 'Persönlich vor Ort' },
  { value: 'email_reply', label: 'Per E-Mail' },
  { value: 'phone', label: 'Telefonisch' },
];

// ---------------------------------------------------------------------------
// Create Quote Modal
// ---------------------------------------------------------------------------

interface CreateQuoteModalProps {
  isOpen: boolean;
  isLoading: boolean;
  onClose: () => void;
  onSubmit: (data: QuoteCreateInput) => Promise<void>;
  /** FE-18: prefill from `/quotes?order_id=…&customer_id=…`. */
  initialCustomerId?: string;
  initialOrderId?: string;
}

const CreateQuoteModal: React.FC<CreateQuoteModalProps> = ({
  isOpen,
  isLoading,
  onClose,
  onSubmit,
  initialCustomerId,
  initialOrderId,
}) => {
  const { showToast } = useToast();
  const [customerId, setCustomerId] = useState<string>('');
  const [customerLabel, setCustomerLabel] = useState<string>('');
  const [orderId, setOrderId] = useState<string>('');
  const [validDays, setValidDays] = useState<string>('14');
  const [taxRate, setTaxRate] = useState<string>('19');
  const [notes, setNotes] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    if (initialCustomerId) {
      setCustomerId(initialCustomerId);
      setCustomerLabel(`Kunde #${initialCustomerId}`);
    }
    if (initialOrderId) setOrderId(initialOrderId);
  }, [isOpen, initialCustomerId, initialOrderId]);

  const reset = () => {
    setCustomerId('');
    setCustomerLabel('');
    setOrderId('');
    setValidDays('14');
    setTaxRate('19');
    setNotes('');
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  // LV2-07: Escape did not close this dialog even though it carries
  // role="dialog" aria-modal="true" — the backdrop only closed on click.
  useEffect(() => {
    if (!isOpen) return undefined;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        handleClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- handleClose/reset/onClose are re-created every render; only isOpen should re-arm the listener.
  }, [isOpen]);

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
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions -- backdrop dismiss is mouse-only by convention; the actual dialog role is on the panel below
    <div className="modal-overlay" onClick={handleClose}>
      {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events -- stops the backdrop's onClose from firing when clicking inside the dialog */}
      <div
        className="modal-content create-quote-modal"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-quote-title"
      >
        <div className="modal-header">
          <h2 id="create-quote-title" className="modal-title">Neues Angebot erstellen</h2>
          <button className="modal-close" onClick={handleClose} aria-label="Schließen">
            &#x2715;
          </button>
        </div>

        <form onSubmit={handleSubmit} className="create-quote-form">
          {/* LV-02: search instead of loading every customer (the list
              endpoint caps limit at 100 and answered 422 to limit=500). */}
          <div className="form-group">
            <label htmlFor="quote-customer">Kunde (Pflichtfeld)</label>
            {customerId ? (
              <div className="quote-customer-selected">
                <span>{customerLabel}</span>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => {
                    setCustomerId('');
                    setCustomerLabel('');
                  }}
                  disabled={isLoading}
                >
                  Kunde ändern
                </button>
              </div>
            ) : (
              <CustomerTypeahead
                inputId="quote-customer"
                onSelect={(customer) => {
                  setCustomerId(String(customer.id));
                  setCustomerLabel(
                    `${customer.first_name} ${customer.last_name}${
                      customer.company_name ? ` — ${customer.company_name}` : ''
                    }`,
                  );
                }}
                onError={() =>
                  showToast('Kundensuche fehlgeschlagen. Bitte erneut versuchen.', 'error')
                }
              />
            )}
          </div>

          <div className="form-group">
            <label htmlFor="quote-order">Auftragsnummer (optional)</label>
            <input
              id="quote-order"
              type="number"
              min="1"
              placeholder="z. B. 42 – leer lassen für ein manuelles Angebot"
              value={orderId}
              onChange={e => setOrderId(e.target.value)}
            />
            <span className="form-hint">
              Wird ein Auftrag angegeben, werden Positionen automatisch berechnet.
            </span>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="quote-valid-days">Gültig für (Tage)</label>
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
              placeholder="Besondere Hinweise oder Konditionen…"
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
              {submitting ? 'Wird erstellt…' : 'Angebot erstellen'}
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
  onApprove: (signatureData: string | null, method: QuoteApprovalMethod) => Promise<void>;
}

const ApproveModal: React.FC<ApproveModalProps> = ({ quote, onClose, onApprove }) => {
  const [signatureData, setSignatureData] = useState<string | null>(null);
  const [method, setMethod] = useState<QuoteApprovalMethod | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!quote) return null;

  const handleApprove = async () => {
    if (!method) return;
    setSubmitting(true);
    try {
      await onApprove(signatureData, method);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions -- backdrop dismiss is mouse-only by convention; the actual dialog role is on the panel below
    <div className="modal-overlay" onClick={onClose}>
      {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events -- stops the backdrop's onClose from firing when clicking inside the dialog */}
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
          <button className="modal-close" onClick={onClose} aria-label="Schließen">
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
            <span className="summary-label">Gültig bis:</span>
            <span className="summary-value">{formatDate(quote.valid_until)}</span>
          </div>
        </div>

        <fieldset className="form-group">
          <legend>Wie hat der Kunde zugestimmt? *</legend>
          {APPROVAL_METHOD_OPTIONS.map((option) => (
            <label key={option.value}>
              <input
                type="radio"
                name="approval-method"
                value={option.value}
                checked={method === option.value}
                onChange={() => setMethod(option.value)}
              />
              {option.label}
            </label>
          ))}
        </fieldset>

        <div className="signature-section">
          {/* eslint-disable-next-line jsx-a11y/label-has-associated-control -- labels a canvas-based signature pad, not a native form control */}
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
            disabled={submitting || !method}
          >
            {submitting ? 'Wird genehmigt…' : 'Angebot genehmigen'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Quote Detail Panel
// ---------------------------------------------------------------------------

const LINE_TYPE_LABELS: Record<QuoteLineType, string> = {
  material: 'Material',
  labor: 'Arbeit',
  gemstone: 'Edelstein',
  other: 'Sonstiges',
};

const EMPTY_LINE_DRAFT: QuoteLineItemInput = {
  line_type: 'labor',
  description: '',
  quantity: 1,
  unit_price: 0,
};

interface LineItemRowProps {
  item: QuoteLineItem;
  index: number;
  disabled: boolean;
  onSave: (itemId: number, data: QuoteLineItemInput) => Promise<void>;
  onRemove: (itemId: number) => Promise<void>;
}

// A single editable line-item row. Local state is seeded from the item and
// committed on blur / select-change, so typing does not round-trip to the API
// on every keystroke. `key={item.id}` keeps the row bound to its DB row but does
// NOT remount on a save (the id is stable), so the useEffect below resyncs the
// draft from the server-canonical item after each save.
function LineItemRow({ item, index, disabled, onSave, onRemove }: LineItemRowProps) {
  const [draft, setDraft] = useState<QuoteLineItemInput>({
    line_type: item.line_type,
    description: item.description,
    quantity: item.quantity,
    unit_price: item.unit_price,
  });
  const [busy, setBusy] = useState(false);

  // Resync when the server-canonical values change (post-save/normalisation),
  // so the row never keeps a stale locally-typed value.
  useEffect(() => {
    setDraft({
      line_type: item.line_type,
      description: item.description,
      quantity: item.quantity,
      unit_price: item.unit_price,
    });
  }, [item.line_type, item.description, item.quantity, item.unit_price]);

  const commit = async (next: QuoteLineItemInput) => {
    if (
      next.line_type === item.line_type &&
      next.description === item.description &&
      next.quantity === item.quantity &&
      next.unit_price === item.unit_price
    ) {
      return; // unchanged — skip the round-trip
    }
    if (!next.description.trim()) return; // never persist an empty description
    // Never send NaN / negative numbers to the API (empty or '-' number inputs
    // read as NaN/negative). Skip silently; the field keeps the typed value for
    // the user to correct, and the stored total stays correct from props.
    if (
      !Number.isFinite(next.quantity) ||
      next.quantity <= 0 ||
      !Number.isFinite(next.unit_price) ||
      next.unit_price < 0
    ) {
      return; // backend requires quantity > 0, unit_price >= 0
    }
    setBusy(true);
    try {
      await onSave(item.id, next);
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async () => {
    setBusy(true);
    try {
      await onRemove(item.id);
    } finally {
      setBusy(false);
    }
  };

  return (
    <tr>
      <td>{index + 1}</td>
      <td>
        <select
          value={draft.line_type}
          disabled={disabled || busy}
          onChange={e => {
            const next = { ...draft, line_type: e.target.value as QuoteLineType };
            setDraft(next);
            void commit(next);
          }}
          aria-label="Art der Position"
        >
          {(Object.keys(LINE_TYPE_LABELS) as QuoteLineType[]).map(t => (
            <option key={t} value={t}>{LINE_TYPE_LABELS[t]}</option>
          ))}
        </select>
      </td>
      <td>
        <input
          type="text"
          value={draft.description}
          disabled={disabled || busy}
          onChange={e => setDraft({ ...draft, description: e.target.value })}
          onBlur={() => void commit(draft)}
          aria-label="Beschreibung"
        />
      </td>
      <td style={{ textAlign: 'right' }}>
        <input
          type="number"
          min={0}
          step="0.01"
          value={draft.quantity}
          disabled={disabled || busy}
          onChange={e => setDraft({ ...draft, quantity: Number(e.target.value) })}
          onBlur={() => void commit(draft)}
          aria-label="Menge"
        />
      </td>
      <td style={{ textAlign: 'right' }}>
        <input
          type="number"
          min={0}
          step="0.01"
          value={draft.unit_price}
          disabled={disabled || busy}
          onChange={e => setDraft({ ...draft, unit_price: Number(e.target.value) })}
          onBlur={() => void commit(draft)}
          aria-label="Einzelpreis"
        />
      </td>
      <td style={{ textAlign: 'right' }}>{formatAmount(item.total)}</td>
      <td style={{ textAlign: 'right' }}>
        <button
          type="button"
          className="btn btn-reject btn-sm"
          disabled={disabled || busy}
          onClick={() => void handleRemove()}
          aria-label={`Position ${index + 1} entfernen`}
          title="Position entfernen"
        >
          <span aria-hidden="true">🗑</span>
        </button>
      </td>
    </tr>
  );
}

interface EditableLineItemsProps {
  items: QuoteLineItem[];
  disabled: boolean;
  onAdd: (data: QuoteLineItemInput) => Promise<void>;
  onSave: (itemId: number, data: QuoteLineItemInput) => Promise<void>;
  onRemove: (itemId: number) => Promise<void>;
}

// Editable line-items table shown for DRAFT quotes. Every add/edit/remove
// persists immediately; the server returns the quote with recomputed totals.
// Exported for unit testing.
export function EditableLineItems({ items, disabled, onAdd, onSave, onRemove }: EditableLineItemsProps) {
  const [draft, setDraft] = useState<QuoteLineItemInput>(EMPTY_LINE_DRAFT);
  const [busy, setBusy] = useState(false);

  const handleAdd = async () => {
    if (!draft.description.trim()) return;
    if (
      !Number.isFinite(draft.quantity) ||
      draft.quantity <= 0 ||
      !Number.isFinite(draft.unit_price) ||
      draft.unit_price < 0
    ) {
      return; // backend requires quantity > 0, unit_price >= 0
    }
    setBusy(true);
    try {
      await onAdd(draft);
      setDraft(EMPTY_LINE_DRAFT);
    } finally {
      setBusy(false);
    }
  };

  return (
    <table className="line-items-table line-items-editable">
      <thead>
        <tr>
          <th>Pos.</th>
          <th>Art</th>
          <th>Beschreibung</th>
          <th style={{ textAlign: 'right' }}>Menge</th>
          <th style={{ textAlign: 'right' }}>Einzelpreis</th>
          <th style={{ textAlign: 'right' }}>Gesamt</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {items.map((item, idx) => (
          <LineItemRow
            key={item.id}
            item={item}
            index={idx}
            disabled={disabled}
            onSave={onSave}
            onRemove={onRemove}
          />
        ))}
        <tr className="line-item-add-row">
          <td>+</td>
          <td>
            <select
              value={draft.line_type}
              disabled={disabled || busy}
              onChange={e => setDraft({ ...draft, line_type: e.target.value as QuoteLineType })}
              aria-label="Art der neuen Position"
            >
              {(Object.keys(LINE_TYPE_LABELS) as QuoteLineType[]).map(t => (
                <option key={t} value={t}>{LINE_TYPE_LABELS[t]}</option>
              ))}
            </select>
          </td>
          <td>
            <input
              type="text"
              placeholder="Neue Position…"
              value={draft.description}
              disabled={disabled || busy}
              onChange={e => setDraft({ ...draft, description: e.target.value })}
              aria-label="Beschreibung der neuen Position"
            />
          </td>
          <td style={{ textAlign: 'right' }}>
            <input
              type="number"
              min={0}
              step="0.01"
              value={draft.quantity}
              disabled={disabled || busy}
              onChange={e => setDraft({ ...draft, quantity: Number(e.target.value) })}
              aria-label="Menge der neuen Position"
            />
          </td>
          <td style={{ textAlign: 'right' }}>
            <input
              type="number"
              min={0}
              step="0.01"
              value={draft.unit_price}
              disabled={disabled || busy}
              onChange={e => setDraft({ ...draft, unit_price: Number(e.target.value) })}
              aria-label="Einzelpreis der neuen Position"
            />
          </td>
          <td style={{ textAlign: 'right' }}>
            {formatAmount(draft.quantity * draft.unit_price)}
          </td>
          <td style={{ textAlign: 'right' }}>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={disabled || busy || !draft.description.trim()}
              onClick={() => void handleAdd()}
            >
              {busy ? '…' : 'Hinzufügen'}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  );
}

interface QuoteDetailPanelProps {
  quote: Quote;
  onSend: () => void;
  onApproveClick: () => void;
  onReject: () => void;
  onConvert: () => void;
  onDownloadPdf: () => void;
  onDeleteQuote: () => void;
  onAddLineItem: (data: QuoteLineItemInput) => Promise<void>;
  onSaveLineItem: (itemId: number, data: QuoteLineItemInput) => Promise<void>;
  onRemoveLineItem: (itemId: number) => Promise<void>;
  isLoading: boolean;
}

const QuoteDetailPanel: React.FC<QuoteDetailPanelProps> = ({
  quote,
  onSend,
  onApproveClick,
  onReject,
  onConvert,
  onDownloadPdf,
  onDeleteQuote,
  onAddLineItem,
  onSaveLineItem,
  onRemoveLineItem,
  isLoading,
}) => {
  const isDraft = quote.status === 'draft';
  const isDeletable = quote.status === 'draft' || quote.status === 'rejected';
  return (
    <div className="quote-detail-panel">
      <div className="detail-header">
        <div>
          <span className="quote-number">{quote.quote_number}</span>
          <StatusBadge kind="quote" status={quote.status} />
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
          {quote.status === 'draft' && (
            <button className="btn btn-primary btn-sm" onClick={onSend} disabled={isLoading}>
              Versenden
            </button>
          )}
          {(quote.status === 'sent' || quote.status === 'draft') && (
            <>
              <button className="btn btn-approve btn-sm" onClick={onApproveClick} disabled={isLoading}>
                Genehmigen
              </button>
              <button className="btn btn-reject btn-sm" onClick={onReject} disabled={isLoading}>
                Ablehnen
              </button>
            </>
          )}
          {quote.status === 'approved' && (
            <button className="btn btn-convert btn-sm" onClick={onConvert} disabled={isLoading}>
              In Auftrag umwandeln
            </button>
          )}
          {isDeletable && (
            <button
              className="btn btn-reject btn-sm"
              onClick={onDeleteQuote}
              disabled={isLoading}
            >
              Löschen
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
          <span className="meta-label">Gültig bis</span>
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

      {isDraft ? (
        <>
          <p className="line-items-hint">
            Entwurf — Positionen und Beträge lassen sich hier anpassen. Der
            Kostenvoranschlag friert erst beim Versenden ein.
          </p>
          <EditableLineItems
            items={quote.line_items}
            disabled={isLoading}
            onAdd={onAddLineItem}
            onSave={onSaveLineItem}
            onRemove={onRemoveLineItem}
          />
          <EstimatorPanel
            quote={quote}
            order={null}
            onPatch={async ({ addLineItem }) => {
              try {
                await onAddLineItem(addLineItem);
                return true;
              } catch {
                return false;
              }
            }}
          />
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
      ) : (
        quote.line_items.length > 0 && (
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
        )
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
  const { showConfirm } = useConfirm();
  const [quotes, setQuotes] = useState<QuoteListItem[]>([]);
  const [selectedQuote, setSelectedQuote] = useState<Quote | null>(null);
  const [statusFilter, setStatusFilter] = useState<QuoteStatus | ''>('');
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isApproveModalOpen, setIsApproveModalOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [linkedOrder, setLinkedOrder] = useState<OrderType | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [prefill, setPrefill] = useState<{ customerId?: string; orderId?: string }>({});

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

  useEffect(() => {
    loadQuotes();
  }, [loadQuotes]);

  // FE-18: `/quotes?order_id=…&customer_id=…` (from the order page) opens the
  // create modal pre-filled; `/quotes?quote_id=…` (from the consultation
  // wizard) opens that quote. The params are consumed once.
  useEffect(() => {
    const orderId = searchParams.get('order_id') ?? undefined;
    const customerId = searchParams.get('customer_id') ?? undefined;
    const quoteId = Number(searchParams.get('quote_id'));
    if (!orderId && !customerId && !quoteId) return;
    setSearchParams({}, { replace: true });
    if (quoteId > 0) {
      quotesApi
        .getQuote(quoteId)
        .then(setSelectedQuote)
        .catch((err) => {
          logError('quote.openFromLink', err);
          showToast('Kostenvoranschlag konnte nicht geladen werden.', 'error');
        });
      return;
    }
    setPrefill({ customerId, orderId });
    setIsCreateModalOpen(true);
  }, [searchParams, setSearchParams, showToast]);

  // ------------------------------------------------------------------
  // Linked order — when the selected quote references an order, fetch
  // it so the EstimatorPanel can pre-fill order_type / surface_finish /
  // alloy. We deliberately swallow 404 here (orphan order_id) — the
  // estimator falls back to empty inputs.
  // ------------------------------------------------------------------

  useEffect(() => {
    const orderId = selectedQuote?.order_id;
    if (!orderId) {
      setLinkedOrder(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const order = await ordersApi.getById(orderId);
        if (!cancelled) setLinkedOrder(order);
      } catch {
        if (!cancelled) setLinkedOrder(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedQuote?.order_id]);

  // ------------------------------------------------------------------
  // Estimator patch — add the LABOR line item suggested by the panel
  // ------------------------------------------------------------------

  const handleEstimatorPatch = useCallback(
    async (patch: { addLineItem: QuoteLineItemInput }): Promise<boolean> => {
      if (!selectedQuote) return false;
      try {
        const updated = await quotesApi.addLineItem(selectedQuote.id, patch.addLineItem);
        setSelectedQuote(updated);
        await loadQuotes();
        showToast('Schätzung wurde übernommen.', 'success');
        return true;
      } catch (err: any) {
        logError('quote.estimatorPatch', err);
        showToast(
          err?.response?.data?.detail ?? 'Schätzung konnte nicht übernommen werden.',
          'error'
        );
        return false;
      }
    },
    [selectedQuote, showToast, loadQuotes]
  );

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
      setPrefill({});
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
      if (updated.delivery_method !== 'email') {
        try {
          await quotesApi.downloadPdf(updated.id, updated.quote_number);
        } catch (downloadErr) {
          logError('quote.sendDownloadPdf', downloadErr);
          showToast('Kostenvoranschlag als versendet vermerkt, aber das PDF konnte nicht heruntergeladen werden.', 'error');
          await loadQuotes();
          return;
        }
      }
      showToast(sendOutcomeMessage(updated), 'success');
      await loadQuotes();
    } catch (err: any) {
      logError('quote.send', err);
      const detail = err?.response?.data?.detail;
      showToast(
        typeof detail === 'string' ? detail : 'Kostenvoranschlag konnte nicht versendet werden.',
        'error'
      );
    } finally {
      setActionLoading(false);
    }
  }, [selectedQuote, showToast, loadQuotes]);

  const handleApprove = useCallback(async (
    signatureData: string | null,
    method: QuoteApprovalMethod
  ) => {
    if (!selectedQuote) return;
    setActionLoading(true);
    try {
      const updated = await quotesApi.approveQuote(selectedQuote.id, {
        response_method: method,
        signature_data: signatureData ?? undefined,
      });
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

  // Guard every line-item mutation against out-of-order responses: a slower
  // response must not clobber a newer selection or resurrect a just-deleted
  // quote. Only apply the result if the panel still shows the same quote.
  const applyIfCurrent = useCallback((quoteId: number, updated: Quote) => {
    setSelectedQuote(prev => (prev && prev.id === quoteId ? updated : prev));
  }, []);

  const handleAddLineItem = useCallback(
    async (data: QuoteLineItemInput) => {
      if (!selectedQuote) return;
      const quoteId = selectedQuote.id;
      setActionLoading(true);
      try {
        const updated = await quotesApi.addLineItem(quoteId, data);
        applyIfCurrent(quoteId, updated);
        await loadQuotes();
      } catch (err) {
        logError('quote.addLineItem', err);
        showToast('Position konnte nicht hinzugefügt werden.', 'error');
      } finally {
        setActionLoading(false);
      }
    },
    [selectedQuote, applyIfCurrent, showToast, loadQuotes]
  );

  const handleSaveLineItem = useCallback(
    async (itemId: number, data: QuoteLineItemInput) => {
      if (!selectedQuote) return;
      const quoteId = selectedQuote.id;
      setActionLoading(true);
      try {
        const updated = await quotesApi.updateLineItem(quoteId, itemId, data);
        applyIfCurrent(quoteId, updated);
        await loadQuotes();
      } catch (err) {
        logError('quote.updateLineItem', err);
        showToast('Position konnte nicht gespeichert werden.', 'error');
      } finally {
        setActionLoading(false);
      }
    },
    [selectedQuote, applyIfCurrent, showToast, loadQuotes]
  );

  const handleRemoveLineItem = useCallback(
    async (itemId: number) => {
      if (!selectedQuote) return;
      const quoteId = selectedQuote.id;
      setActionLoading(true);
      try {
        const updated = await quotesApi.deleteLineItem(quoteId, itemId);
        applyIfCurrent(quoteId, updated);
        await loadQuotes();
      } catch (err) {
        logError('quote.deleteLineItem', err);
        showToast('Position konnte nicht entfernt werden.', 'error');
      } finally {
        setActionLoading(false);
      }
    },
    [selectedQuote, applyIfCurrent, showToast, loadQuotes]
  );

  const handleDeleteQuote = useCallback(async () => {
    if (!selectedQuote) return;
    const ok = await showConfirm({
      title: 'Angebot löschen',
      message: `Angebot ${selectedQuote.quote_number} wirklich löschen?`,
      confirmLabel: 'Löschen',
      variant: 'danger',
    });
    if (!ok) return;
    setActionLoading(true);
    try {
      await quotesApi.deleteQuote(selectedQuote.id);
      setSelectedQuote(null);
      showToast('Angebot gelöscht.', 'success');
      await loadQuotes();
    } catch (err) {
      logError('quote.deleteQuote', err);
      showToast('Angebot konnte nicht gelöscht werden.', 'error');
    } finally {
      setActionLoading(false);
    }
  }, [selectedQuote, showConfirm, showToast, loadQuotes]);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  return (
    <div className="page-container">
      {/* LV-15: same page-header layout as /orders (pages.css). */}
      <header className="page-header">
        <div>
          <h1>Angebote</h1>
          <p className="quotes-page-summary">
            {total} {total === 1 ? 'Kostenvoranschlag' : 'Kostenvoranschläge'}
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setIsCreateModalOpen(true)}
        >
          Neues Angebot
        </button>
      </header>

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
            {(Object.keys(QUOTE_STATUS) as QuoteStatus[]).map((value) => (
              <option key={value} value={value}>
                {QUOTE_STATUS[value].label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="table-container">
        {isLoading ? (
          <div className="loading-state">Angebote werden geladen…</div>
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
                <th>Gültig bis</th>
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
                  <td data-label="Gültig bis">
                    <span className={validUntilClass(q.valid_until, q.status)}>
                      {formatDate(q.valid_until)}
                    </span>
                  </td>
                  <td data-label="Betrag" style={{ textAlign: 'right' }}>
                    <span className="amount-display">{formatAmount(q.total)}</span>
                  </td>
                  <td data-label="Status">
                    <StatusBadge kind="quote" status={q.status} />
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
          onDeleteQuote={handleDeleteQuote}
          onAddLineItem={handleAddLineItem}
          onSaveLineItem={handleSaveLineItem}
          onRemoveLineItem={handleRemoveLineItem}
          isLoading={actionLoading}
        />
      )}

      {/* Estimator — only visible for DRAFT quotes, gated to ADMIN/GOLDSMITH inside the panel */}
      {selectedQuote?.status === 'draft' && (
        <EstimatorPanel
          quote={selectedQuote}
          order={
            linkedOrder
              ? {
                  id: linkedOrder.id,
                  order_type: linkedOrder.order_type ?? null,
                  surface_finish: linkedOrder.surface_finish ?? null,
                  alloy: linkedOrder.alloy ?? null,
                }
              : null
          }
          onPatch={handleEstimatorPatch}
        />
      )}

      {/* Create modal */}
      <CreateQuoteModal
        isOpen={isCreateModalOpen}
        isLoading={isLoading}
        onClose={() => {
          setIsCreateModalOpen(false);
          setPrefill({});
        }}
        onSubmit={handleCreate}
        initialCustomerId={prefill.customerId}
        initialOrderId={prefill.orderId}
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
