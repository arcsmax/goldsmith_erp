// HandoffTab — Übergabe-Verwaltung im Auftragsdetail
import React, { useEffect, useState, useCallback } from 'react';
import { handoffsApi, HandoffCreateInput } from '../../api/handoffs';
import { usersApi } from '../../api';
import { useAuth, useToast } from '../../contexts';
import { UserType } from '../../types';

// ============================================================
// Types
// ============================================================

export interface Handoff {
  id: number;
  order_id: number;
  from_user_id: number;
  to_user_id: number;
  from_user?: { id: number; full_name: string; email: string };
  to_user?: { id: number; full_name: string; email: string };
  handoff_type: string;
  status: 'PENDING' | 'ACCEPTED' | 'DECLINED';
  notes?: string;
  response_notes?: string;
  created_at: string;
  responded_at?: string;
}

// ============================================================
// Constants
// ============================================================

const HANDOFF_TYPES = [
  { value: 'WEITERGABE', label: 'Weitergabe' },
  { value: 'PRUEFUNG', label: 'Prüfung anfordern' },
  { value: 'NACHARBEIT', label: 'Zurück zur Nacharbeit' },
  { value: 'FERTIGMELDUNG', label: 'Fertigmeldung' },
];

// ============================================================
// Helpers
// ============================================================

const getStatusLabel = (status: string): string => {
  const labels: Record<string, string> = {
    PENDING: 'Ausstehend',
    ACCEPTED: 'Angenommen',
    DECLINED: 'Abgelehnt',
  };
  return labels[status] || status;
};

const getStatusClass = (status: string): string => {
  const classes: Record<string, string> = {
    PENDING: 'handoff-status--pending',
    ACCEPTED: 'handoff-status--accepted',
    DECLINED: 'handoff-status--declined',
  };
  return classes[status] || '';
};

const formatDateTime = (dt?: string): string => {
  if (!dt) return '—';
  return new Date(dt).toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

// ============================================================
// Sub-components
// ============================================================

interface HandoffCardProps {
  handoff: Handoff;
  currentUserId: number;
  onAccept: (id: number) => Promise<void>;
  onDecline: (id: number, notes: string) => Promise<void>;
}

const HandoffCard: React.FC<HandoffCardProps> = ({
  handoff,
  currentUserId,
  onAccept,
  onDecline,
}) => {
  const [declineNotes, setDeclineNotes] = useState('');
  const [showDeclineForm, setShowDeclineForm] = useState(false);
  const [isActing, setIsActing] = useState(false);

  const isAddressedToMe = handoff.to_user_id === currentUserId;
  const isPending = handoff.status === 'PENDING';
  const canAct = isAddressedToMe && isPending;

  const handleAccept = async () => {
    setIsActing(true);
    try {
      await onAccept(handoff.id);
    } finally {
      setIsActing(false);
    }
  };

  const handleDecline = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!declineNotes.trim()) return;
    setIsActing(true);
    try {
      await onDecline(handoff.id, declineNotes.trim());
      setShowDeclineForm(false);
    } finally {
      setIsActing(false);
    }
  };

  const typeLabel =
    HANDOFF_TYPES.find((t) => t.value === handoff.handoff_type)?.label ||
    handoff.handoff_type;

  return (
    <div className={`handoff-card ${getStatusClass(handoff.status)}`}>
      <div className="handoff-card__header">
        <div className="handoff-card__route">
          <span className="handoff-card__user">
            {handoff.from_user?.full_name || `#${handoff.from_user_id}`}
          </span>
          <span className="handoff-card__arrow">→</span>
          <span className="handoff-card__user">
            {handoff.to_user?.full_name || `#${handoff.to_user_id}`}
          </span>
        </div>
        <div className="handoff-card__meta">
          <span className="handoff-card__type">{typeLabel}</span>
          <span className={`handoff-status-badge ${getStatusClass(handoff.status)}`}>
            {getStatusLabel(handoff.status)}
          </span>
        </div>
      </div>

      {handoff.notes && (
        <p className="handoff-card__notes">{handoff.notes}</p>
      )}

      <div className="handoff-card__footer">
        <span className="handoff-card__date">{formatDateTime(handoff.created_at)}</span>
        {handoff.responded_at && (
          <span className="handoff-card__date">
            Beantwortet: {formatDateTime(handoff.responded_at)}
          </span>
        )}
      </div>

      {handoff.response_notes && (
        <p className="handoff-card__response-notes">
          Antwort: {handoff.response_notes}
        </p>
      )}

      {/* Accept / Decline actions for the addressed user on PENDING handoffs */}
      {canAct && (
        <div className="handoff-card__actions">
          {!showDeclineForm ? (
            <>
              <button
                className="btn-handoff-accept"
                onClick={handleAccept}
                disabled={isActing}
              >
                Annehmen
              </button>
              <button
                className="btn-handoff-decline-trigger"
                onClick={() => setShowDeclineForm(true)}
                disabled={isActing}
              >
                Ablehnen
              </button>
            </>
          ) : (
            <form className="handoff-decline-form" onSubmit={handleDecline}>
              <textarea
                className="handoff-decline-textarea"
                value={declineNotes}
                onChange={(e) => setDeclineNotes(e.target.value)}
                placeholder="Begründung für die Ablehnung..."
                rows={3}
                required
                autoFocus
              />
              <div className="handoff-decline-form__actions">
                <button
                  type="submit"
                  className="btn-handoff-decline"
                  disabled={isActing || !declineNotes.trim()}
                >
                  {isActing ? 'Wird abgelehnt...' : 'Ablehnen bestätigen'}
                </button>
                <button
                  type="button"
                  className="btn-handoff-cancel"
                  onClick={() => setShowDeclineForm(false)}
                  disabled={isActing}
                >
                  Abbrechen
                </button>
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  );
};

// ============================================================
// Main HandoffTab Component
// ============================================================

interface HandoffTabProps {
  orderId: number;
}

const HandoffTab: React.FC<HandoffTabProps> = ({ orderId }) => {
  const { user: currentUser } = useAuth();
  const { showToast } = useToast();
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [users, setUsers] = useState<UserType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [toUserId, setToUserId] = useState<string>('');
  const [handoffType, setHandoffType] = useState<string>('WEITERGABE');
  const [notes, setNotes] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  const loadHandoffs = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const resp = await handoffsApi.getForOrder(orderId);
      setHandoffs(Array.isArray(resp.data) ? resp.data : []);
    } catch (err: any) {
      setError(
        err.response?.data?.detail || 'Fehler beim Laden der Übergaben'
      );
      setHandoffs([]);
    } finally {
      setIsLoading(false);
    }
  }, [orderId]);

  useEffect(() => {
    loadHandoffs();
  }, [loadHandoffs]);

  // Load users for the dropdown
  useEffect(() => {
    usersApi.getAll(0, 100)
      .then((data) => {
        // Exclude self from dropdown
        const others = data.filter((u) => u.id !== currentUser?.id);
        setUsers(others);
      })
      .catch(() => setUsers([]));
  }, [currentUser?.id]);

  const handleCreateHandoff = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!toUserId) return;
    setIsSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(false);
    try {
      const payload: HandoffCreateInput = {
        to_user_id: parseInt(toUserId),
        handoff_type: handoffType,
        notes: notes.trim() || undefined,
      };
      await handoffsApi.create(orderId, payload);
      setToUserId('');
      setHandoffType('WEITERGABE');
      setNotes('');
      setSubmitSuccess(true);
      await loadHandoffs();
      setTimeout(() => setSubmitSuccess(false), 3000);
    } catch (err: any) {
      setSubmitError(
        err.response?.data?.detail || 'Fehler beim Erstellen der Übergabe'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAccept = async (id: number) => {
    try {
      await handoffsApi.accept(id);
      await loadHandoffs();
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Fehler beim Annehmen der Übergabe', 'error');
    }
  };

  const handleDecline = async (id: number, notes: string) => {
    try {
      await handoffsApi.decline(id, { response_notes: notes });
      await loadHandoffs();
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Fehler beim Ablehnen der Übergabe', 'error');
    }
  };

  return (
    <div className="handoff-tab tab-panel">
      {/* ── Create Handoff Form ── */}
      <section className="handoff-form-section">
        <h3 className="handoff-section-title">Neue Übergabe erstellen</h3>
        <form className="handoff-form" onSubmit={handleCreateHandoff}>
          <div className="handoff-form__fields">
            <div className="form-group">
              <label htmlFor="handoff-to-user">Goldschmied / Empfänger</label>
              <select
                id="handoff-to-user"
                value={toUserId}
                onChange={(e) => setToUserId(e.target.value)}
                required
              >
                <option value="">— Bitte wählen —</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name || u.email} ({u.role})
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="handoff-type">Übergabetyp</label>
              <select
                id="handoff-type"
                value={handoffType}
                onChange={(e) => setHandoffType(e.target.value)}
              >
                {HANDOFF_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group form-group--full">
              <label htmlFor="handoff-notes">Notizen (optional)</label>
              <textarea
                id="handoff-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
                placeholder="Besondere Hinweise für den Empfänger..."
              />
            </div>
          </div>

          {submitError && (
            <p className="handoff-form__error">{submitError}</p>
          )}
          {submitSuccess && (
            <p className="handoff-form__success">Übergabe erfolgreich erstellt.</p>
          )}

          <div className="handoff-form__submit">
            <button
              type="submit"
              className="btn-handoff-submit"
              disabled={isSubmitting || !toUserId}
            >
              {isSubmitting ? 'Wird erstellt...' : 'Übergabe erstellen'}
            </button>
          </div>
        </form>
      </section>

      {/* ── Handoff History ── */}
      <section className="handoff-history-section">
        <h3 className="handoff-section-title">
          Übergabehistorie ({handoffs.length})
        </h3>

        {isLoading ? (
          <div className="handoff-loading">Lade Übergaben...</div>
        ) : error ? (
          <div className="handoff-error">{error}</div>
        ) : handoffs.length === 0 ? (
          <div className="handoff-empty">
            <p>Noch keine Übergaben für diesen Auftrag vorhanden.</p>
          </div>
        ) : (
          <div className="handoff-list">
            {handoffs.map((h) => (
              <HandoffCard
                key={h.id}
                handoff={h}
                currentUserId={currentUser?.id ?? -1}
                onAccept={handleAccept}
                onDecline={handleDecline}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
};

export default HandoffTab;
