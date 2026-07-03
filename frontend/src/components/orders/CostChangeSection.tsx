// CostChangeSection — §649 cost-change history, create-form & record-response
// modal (V1.2 Task 5). Mounted in the order-detail `kosten` tab beside
// CostBreakdownCard.
//
// Permission model mirrors KundeninfoTab / CostAlertBanner: listCostChanges
// is COST_CHANGE_VIEW and every write is COST_CHANGE_MANAGE, both ADMIN +
// GOLDSMITH only. A VIEWER must never trigger the GET (it 403s backend-side)
// and never see any write action — so the fetch itself is gated on the role,
// not just the rendered UI.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth, useConfirm, useToast } from '../../contexts';
import { customerUpdatesApi } from '../../api/customer-updates';
import type {
  CostChange,
  CostChangeCreateInput,
  CostChangeRecordResponseInput,
  CostChangeResponseMethod,
  CostChangeStatus,
} from '../../api/customer-updates';
import { logError } from '../../lib/logError';
import { formatCurrency, formatPercentage } from '../../utils/formatters';
import { CostChangeForm } from './CostChangeForm';
import './cost-change.css';

export interface CostChangeSectionProps {
  orderId: number;
  onChanged?: () => void;
}

const STATUS_LABELS: Record<CostChangeStatus, string> = {
  draft: 'Entwurf',
  sent: 'Gesendet',
  approved: 'Genehmigt',
  declined: 'Abgelehnt',
  superseded: 'Ersetzt',
};

const RESPONSE_METHOD_LABELS: Record<CostChangeResponseMethod, string> = {
  email_reply: 'E-Mail-Antwort',
  in_person: 'Persönlich',
  phone: 'Telefon',
};

const RESPONSE_EVIDENCE_MIN = 5;
const RESPONSE_EVIDENCE_MAX = 2000;

function sortNewestFirst(costChanges: CostChange[]): CostChange[] {
  return [...costChanges].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
}

function StatusBadge({ status }: { status: CostChangeStatus }) {
  return (
    <span className={`cost-change-status-badge status-${status}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Record-response modal
// ---------------------------------------------------------------------------

interface RecordResponseModalProps {
  costChange: CostChange | null;
  onClose: () => void;
  onSubmit: (input: CostChangeRecordResponseInput) => Promise<void>;
}

function RecordResponseModal({ costChange, onClose, onSubmit }: RecordResponseModalProps) {
  const [status, setStatus] = useState<'approved' | 'declined'>('approved');
  const [responseMethod, setResponseMethod] = useState<CostChangeResponseMethod>('email_reply');
  const [evidence, setEvidence] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Reset the draft whenever a different (or no) cost-change is targeted, so
  // a stale evidence text never leaks into the next row's response.
  useEffect(() => {
    setStatus('approved');
    setResponseMethod('email_reply');
    setEvidence('');
    setError(null);
  }, [costChange]);

  if (!costChange) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;

    const trimmed = evidence.trim();
    if (trimmed.length < RESPONSE_EVIDENCE_MIN || trimmed.length > RESPONSE_EVIDENCE_MAX) {
      setError(
        `Nachweis muss zwischen ${RESPONSE_EVIDENCE_MIN} und ${RESPONSE_EVIDENCE_MAX} Zeichen lang sein.`
      );
      return;
    }
    setError(null);

    setSubmitting(true);
    try {
      await onSubmit({ status, response_method: responseMethod, response_evidence: trimmed });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="cost-change-modal-overlay" onClick={onClose}>
      <div
        className="cost-change-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="cost-change-response-title"
      >
        <div className="cost-change-modal-header">
          <h3 id="cost-change-response-title">Antwort erfassen</h3>
          <button
            type="button"
            className="cost-change-modal-close"
            onClick={onClose}
            aria-label="Schließen"
          >
            &#x2715;
          </button>
        </div>

        <form noValidate onSubmit={(e) => void handleSubmit(e)}>
          <div className="form-group">
            <label htmlFor="cost-change-response-status">Antwort des Kunden</label>
            <select
              id="cost-change-response-status"
              value={status}
              onChange={(e) => setStatus(e.target.value as 'approved' | 'declined')}
              disabled={submitting}
            >
              <option value="approved">Genehmigt</option>
              <option value="declined">Abgelehnt</option>
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="cost-change-response-method">Art der Rückmeldung</label>
            <select
              id="cost-change-response-method"
              value={responseMethod}
              onChange={(e) => setResponseMethod(e.target.value as CostChangeResponseMethod)}
              disabled={submitting}
            >
              {(Object.keys(RESPONSE_METHOD_LABELS) as CostChangeResponseMethod[]).map(
                (method) => (
                  <option key={method} value={method}>
                    {RESPONSE_METHOD_LABELS[method]}
                  </option>
                )
              )}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="cost-change-response-evidence">Nachweis / Notiz</label>
            <textarea
              id="cost-change-response-evidence"
              rows={4}
              maxLength={RESPONSE_EVIDENCE_MAX}
              value={evidence}
              onChange={(e) => setEvidence(e.target.value)}
              disabled={submitting}
            />
            {error && <p className="cost-change-error">{error}</p>}
          </div>

          <div className="cost-change-modal-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
              disabled={submitting}
            >
              Abbrechen
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              Antwort speichern
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CostChangeSection
// ---------------------------------------------------------------------------

export function CostChangeSection({ orderId, onChanged }: CostChangeSectionProps) {
  const { hasRole } = useAuth();
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const canManage = hasRole(['ADMIN', 'GOLDSMITH']);

  const [costChanges, setCostChanges] = useState<CostChange[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(canManage);
  const [actionLoading, setActionLoading] = useState(false);
  const [responseModalTarget, setResponseModalTarget] = useState<CostChange | null>(null);

  // Guards against out-of-order responses + setState-after-unmount, mirroring
  // the applyIfCurrent/actionLoading pattern in QuotesPage.tsx and
  // KundeninfoTab: a response for a stale orderId or an unmounted component
  // must never clobber current state.
  const mountedRef = useRef(true);
  const currentOrderIdRef = useRef(orderId);

  useEffect(() => {
    currentOrderIdRef.current = orderId;
  }, [orderId]);

  useEffect(
    () => () => {
      mountedRef.current = false;
    },
    []
  );

  const isCurrent = useCallback(
    (targetOrderId: number) => mountedRef.current && currentOrderIdRef.current === targetOrderId,
    []
  );

  const loadHistory = useCallback(
    async (targetOrderId: number) => {
      setIsLoadingHistory(true);
      try {
        const data = await customerUpdatesApi.listCostChanges(targetOrderId);
        if (isCurrent(targetOrderId)) {
          setCostChanges(sortNewestFirst(data));
        }
      } catch (err) {
        logError('CostChangeSection.loadHistory', err);
        if (isCurrent(targetOrderId)) {
          showToast('Verlauf der Kostenänderungen konnte nicht geladen werden.', 'error');
        }
      } finally {
        if (isCurrent(targetOrderId)) {
          setIsLoadingHistory(false);
        }
      }
    },
    [isCurrent, showToast]
  );

  // Skip the GET entirely for a user without the manage role — the backend
  // 403s COST_CHANGE_VIEW for VIEWER, and we must never even attempt it.
  useEffect(() => {
    if (!canManage) {
      setCostChanges([]);
      setIsLoadingHistory(false);
      return;
    }
    void loadHistory(orderId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId, canManage]);

  const handleCreate = useCallback(
    async (input: CostChangeCreateInput) => {
      try {
        await customerUpdatesApi.createCostChange(orderId, input);
        showToast('Kostenänderung wurde angelegt.', 'success');
        await loadHistory(orderId);
        onChanged?.();
      } catch (err) {
        logError('CostChangeSection.createCostChange', err);
        showToast('Kostenänderung konnte nicht angelegt werden.', 'error');
      }
    },
    [orderId, loadHistory, onChanged, showToast]
  );

  const handleSend = useCallback(
    async (costChange: CostChange) => {
      if (actionLoading) return;
      const ok = await showConfirm({
        title: '§649 Kostenänderung senden',
        message: `Kostenänderung über ${formatCurrency(costChange.new_amount)} (netto) an den Kunden senden?`,
        confirmLabel: 'Senden',
      });
      if (!ok) return;

      setActionLoading(true);
      try {
        const result = await customerUpdatesApi.sendCostChange(costChange.id);
        if (result.delivered) {
          showToast('Kostenänderung wurde per E-Mail versendet.', 'success');
        } else {
          showToast(
            'Als PDF erstellt — bitte manuell an den Kunden übergeben.',
            'info'
          );
        }
        await loadHistory(orderId);
        onChanged?.();
      } catch (err) {
        logError('CostChangeSection.sendCostChange', err);
        showToast('Kostenänderung konnte nicht gesendet werden.', 'error');
      } finally {
        setActionLoading(false);
      }
    },
    [actionLoading, showConfirm, loadHistory, orderId, onChanged, showToast]
  );

  const handleRecordResponse = useCallback(
    async (costChangeId: number, input: CostChangeRecordResponseInput) => {
      if (actionLoading) return;
      setActionLoading(true);
      try {
        await customerUpdatesApi.recordCostChangeResponse(costChangeId, input);
        showToast('Antwort wurde erfasst.', 'success');
        setResponseModalTarget(null);
        await loadHistory(orderId);
        onChanged?.();
      } catch (err) {
        logError('CostChangeSection.recordCostChangeResponse', err);
        showToast('Antwort konnte nicht erfasst werden.', 'error');
      } finally {
        setActionLoading(false);
      }
    },
    [actionLoading, loadHistory, orderId, onChanged, showToast]
  );

  const handleModalSubmit = useCallback(
    async (input: CostChangeRecordResponseInput) => {
      if (!responseModalTarget) return;
      await handleRecordResponse(responseModalTarget.id, input);
    },
    [responseModalTarget, handleRecordResponse]
  );

  if (!canManage) {
    return (
      <div className="cost-change-section cost-change-section-forbidden">
        <p>
          Keine Berechtigung. Dieser Bereich ist nur für Goldschmiede und Administratoren
          zugänglich.
        </p>
      </div>
    );
  }

  return (
    <div className="cost-change-section">
      <section className="cost-change-history">
        <h3>§649 Kostenänderungen</h3>
        {isLoadingHistory ? (
          <p>Verlauf wird geladen…</p>
        ) : costChanges.length === 0 ? (
          <p className="cost-change-empty">Noch keine Kostenänderungen angelegt.</p>
        ) : (
          <ul className="cost-change-list">
            {costChanges.map((costChange) => (
              <li key={costChange.id} className="cost-change-item">
                <div className="cost-change-item-header">
                  <span className="cost-change-amounts">
                    {formatCurrency(costChange.original_amount)} →{' '}
                    {formatCurrency(costChange.new_amount)} (netto)
                  </span>
                  <StatusBadge status={costChange.status} />
                </div>
                <p className="cost-change-delta">
                  {formatPercentage(costChange.delta_percent)}
                </p>
                <p className="cost-change-reason">{costChange.reason}</p>
                <div className="cost-change-item-actions">
                  {costChange.status === 'draft' && (
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={() => void handleSend(costChange)}
                      disabled={actionLoading}
                    >
                      Senden
                    </button>
                  )}
                  {costChange.status === 'sent' && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setResponseModalTarget(costChange)}
                      disabled={actionLoading}
                    >
                      Antwort erfassen
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="cost-change-compose">
        <h3>Neue Kostenänderung</h3>
        <CostChangeForm onSubmit={handleCreate} disabled={actionLoading} />
      </section>

      <RecordResponseModal
        costChange={responseModalTarget}
        onClose={() => setResponseModalTarget(null)}
        onSubmit={handleModalSubmit}
      />
    </div>
  );
}

export default CostChangeSection;
