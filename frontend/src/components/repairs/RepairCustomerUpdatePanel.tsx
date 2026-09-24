// RepairCustomerUpdatePanel — pickup-ready Kundeninfo draft on
// RepairDetailPage (DOM-12 / W2-02).
//
// Reaching READY creates a DRAFT CustomerUpdate server-side (see
// RepairService.complete_repair) — nothing is sent to the customer yet.
// This panel shows that draft and lets staff send it with one tap. It
// reuses the SAME CustomerUpdate draft/send mechanism the order-scoped
// Kundeninfo flow uses (api/customer-updates.ts), not a second path.
//
// Only rendered for repairs that could have a draft (status ready or
// picked_up — see _VALID_TRANSITIONS in repair_service.py: READY is only
// reachable once and never reverts, so no earlier status can have one).
//
// Styling: no src/ui primitives exist yet (CLAUDE.md, Wave 4) — reuses the
// existing .intake-checklist card + .status-badge + .btn classes rather
// than introducing new ones (styles are out of scope for this fix).
import React, { useCallback, useEffect, useState } from 'react';
import { customerUpdatesApi } from '../../api/customer-updates';
import type { CustomerUpdate, CustomerUpdateStatus } from '../../api/customer-updates';
import type { RepairJob } from '../../types';
import { useToast } from '../../contexts';
import { logError } from '../../lib/logError';

const STATUS_LABELS: Record<CustomerUpdateStatus, string> = {
  draft: 'Entwurf',
  sent: 'Verschickt',
  send_failed: 'Versand fehlgeschlagen',
};

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

interface RepairCustomerUpdatePanelProps {
  repair: RepairJob;
  /** Called with the fresh RepairJob after a send — customer_notified_at
   *  only ever changes server-side on an actual delivered send, so the
   *  parent must refetch rather than have this panel guess the value. */
  onRepairRefresh: () => void;
}

export function RepairCustomerUpdatePanel({
  repair,
  onRepairRefresh,
}: RepairCustomerUpdatePanelProps) {
  const { showToast } = useToast();
  const [update, setUpdate] = useState<CustomerUpdate | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  const canHaveDraft = repair.status === 'ready' || repair.status === 'picked_up';

  const loadUpdate = useCallback(async () => {
    setLoading(true);
    try {
      const updates = await customerUpdatesApi.listRepairUpdates(repair.id);
      setUpdate(updates[0] ?? null);
    } catch (err) {
      logError('Kundeninfo-Entwurf laden fehlgeschlagen', err);
    } finally {
      setLoading(false);
    }
  }, [repair.id]);

  useEffect(() => {
    if (canHaveDraft) loadUpdate();
  }, [canHaveDraft, loadUpdate]);

  if (!canHaveDraft) return null;

  const handleSend = async () => {
    setSending(true);
    try {
      const result = await customerUpdatesApi.sendRepairUpdate(repair.id);
      setUpdate(result.update);
      showToast(
        result.delivered
          ? 'Kunde wurde benachrichtigt'
          : 'Email-Versand nicht möglich — Entwurf bleibt erhalten (PDF-Fallback über Kundeninfo)',
        result.delivered ? 'success' : 'error'
      );
      // customer_notified_at on the repair changes ONLY when this send was
      // delivered — refetch from the parent rather than duplicating that
      // rule here (see RepairService.send_customer_update).
      onRepairRefresh();
    } catch (err: unknown) {
      logError('Kundeninfo-Update senden fehlgeschlagen', err);
      showToast('Versand fehlgeschlagen', 'error');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="intake-checklist">
      <div className="intake-checklist-header">
        <h3>Kundeninfo — Abholbereit</h3>
        {update && (
          <span className={`status-badge ${update.status}`}>
            {STATUS_LABELS[update.status]}
          </span>
        )}
      </div>

      {loading && <p style={{ color: 'var(--color-text-muted)' }}>Wird geladen…</p>}

      {!loading && !update && (
        <p style={{ color: 'var(--color-text-muted)' }}>
          Noch kein Kundeninfo-Entwurf vorhanden.
        </p>
      )}

      {!loading && update && (
        <>
          <p style={{ fontWeight: 600, margin: '0 0 0.5rem' }}>{update.subject}</p>
          {update.status === 'sent' ? (
            <p style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
              Verschickt am {formatDateTime(update.sent_at)}
              {update.delivery_method === 'email' ? ' per Email' : ''}.
            </p>
          ) : (
            <button
              type="button"
              className="btn btn-success"
              disabled={sending}
              onClick={handleSend}
            >
              {sending ? 'Wird verschickt…' : 'Kunde benachrichtigen'}
            </button>
          )}
        </>
      )}
    </div>
  );
}
