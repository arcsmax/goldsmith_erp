// KundeninfoTab — customer progress-update history + compose form (V1.2).
//
// Permission model is ROLE-based (not fine-grained): the V1.2 customer-update
// endpoints are ADMIN + GOLDSMITH only. A user without that role must never
// see the compose form and the history GET must never fire (it 403s
// backend-side for VIEWER) — so the fetch itself is gated, not just the UI.
//
// SMTP status: `getEmailConfig()` is ADMIN-only backend-side (a GOLDSMITH
// gets 403), so it is only called for `isAdmin`. For everyone else the
// honest source of truth is the per-send `delivered` flag returned by
// `sendUpdate`/`createUpdate` → `sendUpdate`.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth, useToast } from '../../contexts';
import { customerUpdatesApi } from '../../api/customer-updates';
import type {
  CustomerUpdate,
  CustomerUpdateCreateInput,
  CustomerUpdateKind,
  CustomerUpdateSendResult,
  CustomerUpdateStatus,
} from '../../api/customer-updates';
import { getEmailConfig } from '../../api/admin';
import { logError } from '../../lib/logError';
import { PhotoPicker } from './PhotoPicker';
import './kundeninfo.css';

export interface KundeninfoTabProps {
  orderId: number;
  customerName?: string | null;
}

const KIND_LABELS: Record<CustomerUpdateKind, string> = {
  progress: 'Fortschritt',
  cost_change: 'Kostenänderung',
  ready_for_pickup: 'Abholbereit',
  custom: 'Individuell',
};

const STATUS_LABELS: Record<CustomerUpdateStatus, string> = {
  draft: 'Entwurf',
  sent: 'Gesendet',
  send_failed: 'Fehlgeschlagen',
};

const DELIVERY_METHOD_LABELS: Record<string, string> = {
  email: 'E-Mail',
  pdf_manual: 'PDF (manuell)',
};

const SUBJECT_MAX = 300;
const BODY_MAX = 20000;

interface ComposeForm {
  kind: CustomerUpdateKind;
  subject: string;
  body: string;
  photoIds: string[];
}

const EMPTY_FORM: ComposeForm = {
  kind: 'progress',
  subject: '',
  body: '',
  photoIds: [],
};

function StatusBadge({ status }: { status: CustomerUpdateStatus }) {
  return (
    <span className={`kundeninfo-status-badge status-${status}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function sortNewestFirst(updates: CustomerUpdate[]): CustomerUpdate[] {
  return [...updates].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export function KundeninfoTab({ orderId, customerName }: KundeninfoTabProps) {
  const { hasRole, isAdmin } = useAuth();
  const { showToast } = useToast();
  const canManage = hasRole(['ADMIN', 'GOLDSMITH']);

  const [updates, setUpdates] = useState<CustomerUpdate[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(canManage);
  const [actionLoading, setActionLoading] = useState(false);
  const [smtpConfigured, setSmtpConfigured] = useState<boolean | null>(null);
  const [form, setForm] = useState<ComposeForm>(EMPTY_FORM);

  // Guards against out-of-order responses + setState-after-unmount, mirroring
  // the applyIfCurrent/actionLoading pattern in QuotesPage.tsx: a response
  // for a stale orderId (tab switched away mid-flight) or an unmounted
  // component must never clobber current state.
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
        const data = await customerUpdatesApi.listUpdates(targetOrderId);
        if (isCurrent(targetOrderId)) {
          setUpdates(sortNewestFirst(data));
        }
      } catch (err) {
        logError('KundeninfoTab.loadHistory', err);
        if (isCurrent(targetOrderId)) {
          showToast('Verlauf konnte nicht geladen werden.', 'error');
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
  // 403s CUSTOMER_UPDATE_VIEW for VIEWER, and we must never even attempt it.
  useEffect(() => {
    if (!canManage) {
      setUpdates([]);
      setIsLoadingHistory(false);
      return;
    }
    void loadHistory(orderId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId, canManage]);

  // getEmailConfig is ADMIN-only backend-side — never call it as GOLDSMITH.
  useEffect(() => {
    if (!isAdmin) {
      setSmtpConfigured(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const config = await getEmailConfig();
        if (!cancelled) {
          setSmtpConfigured(
            config.email_notifications_enabled && !!config.smtp_host && config.password_configured
          );
        }
      } catch (err) {
        logError('KundeninfoTab.loadEmailConfig', err);
        if (!cancelled) {
          setSmtpConfigured(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAdmin]);

  const handleSendResult = useCallback(
    async (result: CustomerUpdateSendResult) => {
      if (result.delivered) {
        showToast('Kundeninfo wurde per E-Mail versendet.', 'success');
        return;
      }
      showToast(
        'Als PDF erstellt — bitte manuell an den Kunden übergeben.',
        'info'
      );
      // SMTP is unconfigured, so nothing was actually sent — surface the PDF
      // immediately instead of leaving the goldsmith to dig for the manual
      // "PDF" history-row button (which still exists below as a fallback).
      // A failure here must never break the send flow itself.
      try {
        const blob = await customerUpdatesApi.downloadUpdatePdf(result.update.id);
        downloadBlob(blob, `kundeninfo_${result.update.id}.pdf`);
      } catch (err) {
        logError('KundeninfoTab.autoDownloadPdf', err);
      }
    },
    [showToast]
  );

  const handleDownloadPdf = useCallback(
    async (update: CustomerUpdate) => {
      if (actionLoading) return;
      setActionLoading(true);
      try {
        const blob = await customerUpdatesApi.downloadUpdatePdf(update.id);
        downloadBlob(blob, `kundeninfo_${update.id}.pdf`);
      } catch (err) {
        logError('KundeninfoTab.downloadPdf', err);
        showToast('PDF-Download fehlgeschlagen.', 'error');
      } finally {
        setActionLoading(false);
      }
    },
    [actionLoading, showToast]
  );

  const handleSendExisting = useCallback(
    async (update: CustomerUpdate) => {
      if (actionLoading) return;
      setActionLoading(true);
      try {
        const result = await customerUpdatesApi.sendUpdate(update.id);
        await handleSendResult(result);
        await loadHistory(orderId);
      } catch (err) {
        logError('KundeninfoTab.sendUpdate', err);
        showToast('Update konnte nicht gesendet werden.', 'error');
      } finally {
        setActionLoading(false);
      }
    },
    [actionLoading, handleSendResult, loadHistory, orderId, showToast]
  );

  const handleMarkDelivered = useCallback(
    async (update: CustomerUpdate) => {
      if (actionLoading) return;
      setActionLoading(true);
      try {
        await customerUpdatesApi.markDelivered(update.id);
        showToast('Als übergeben markiert.', 'success');
        await loadHistory(orderId);
      } catch (err) {
        logError('KundeninfoTab.markDelivered', err);
        showToast('Konnte nicht als übergeben markiert werden.', 'error');
      } finally {
        setActionLoading(false);
      }
    },
    [actionLoading, loadHistory, orderId, showToast]
  );

  const buildInput = useCallback(
    (): CustomerUpdateCreateInput => ({
      kind: form.kind,
      subject: form.subject.trim() || undefined,
      body: form.body.trim() || undefined,
      photo_ids: form.photoIds,
    }),
    [form]
  );

  const resetForm = useCallback(() => setForm(EMPTY_FORM), []);

  const handleSaveDraft = useCallback(async () => {
    if (actionLoading) return;
    setActionLoading(true);
    try {
      await customerUpdatesApi.createUpdate(orderId, buildInput());
      showToast('Entwurf gespeichert.', 'success');
      resetForm();
      await loadHistory(orderId);
    } catch (err) {
      logError('KundeninfoTab.createUpdate', err);
      showToast('Entwurf konnte nicht gespeichert werden.', 'error');
    } finally {
      setActionLoading(false);
    }
  }, [actionLoading, buildInput, loadHistory, orderId, resetForm, showToast]);

  const handleCreateAndSend = useCallback(async () => {
    if (actionLoading) return;
    setActionLoading(true);
    try {
      const created = await customerUpdatesApi.createUpdate(orderId, buildInput());
      const result = await customerUpdatesApi.sendUpdate(created.id);
      await handleSendResult(result);
      resetForm();
      await loadHistory(orderId);
    } catch (err) {
      logError('KundeninfoTab.createAndSend', err);
      showToast('Update konnte nicht erstellt oder gesendet werden.', 'error');
    } finally {
      setActionLoading(false);
    }
  }, [actionLoading, buildInput, handleSendResult, loadHistory, orderId, resetForm, showToast]);

  if (!canManage) {
    return (
      <div className="kundeninfo-tab kundeninfo-tab-forbidden">
        <p>
          Keine Berechtigung. Dieser Bereich ist nur für Goldschmiede und Administratoren
          zugänglich.
        </p>
      </div>
    );
  }

  return (
    <div className="kundeninfo-tab">
      <section className="kundeninfo-history">
        <h3>Verlauf{customerName ? ` – ${customerName}` : ''}</h3>
        {isLoadingHistory ? (
          <p>Verlauf wird geladen…</p>
        ) : updates.length === 0 ? (
          <p className="kundeninfo-empty">Noch keine Kundeninfos versendet.</p>
        ) : (
          <ul className="kundeninfo-list">
            {updates.map((update) => (
              <li key={update.id} className="kundeninfo-item">
                <div className="kundeninfo-item-header">
                  <span className="kundeninfo-kind">
                    {KIND_LABELS[update.kind] ?? update.kind}
                  </span>
                  <StatusBadge status={update.status} />
                </div>
                {update.subject && <p className="kundeninfo-subject">{update.subject}</p>}
                <div className="kundeninfo-meta">
                  <span>{new Date(update.created_at).toLocaleString('de-DE')}</span>
                  {update.delivery_method && (
                    <span>
                      {DELIVERY_METHOD_LABELS[update.delivery_method] ?? update.delivery_method}
                    </span>
                  )}
                </div>
                <div className="kundeninfo-item-actions">
                  {update.status === 'sent' && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => void handleDownloadPdf(update)}
                      disabled={actionLoading}
                    >
                      PDF
                    </button>
                  )}
                  {(update.status === 'draft' || update.status === 'send_failed') && (
                    <>
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() => void handleSendExisting(update)}
                        disabled={actionLoading}
                      >
                        Senden
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => void handleMarkDelivered(update)}
                        disabled={actionLoading}
                      >
                        Als übergeben markieren
                      </button>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="kundeninfo-compose">
        <h3>Neue Kundeninfo</h3>

        {isAdmin && smtpConfigured === false && (
          <p className="kundeninfo-smtp-note" role="status">
            E-Mail nicht konfiguriert — Updates werden als PDF erzeugt
          </p>
        )}

        <div className="form-group">
          <label htmlFor="kundeninfo-kind">Art</label>
          <select
            id="kundeninfo-kind"
            value={form.kind}
            onChange={(e) =>
              setForm({ ...form, kind: e.target.value as CustomerUpdateKind })
            }
            disabled={actionLoading}
          >
            {(Object.keys(KIND_LABELS) as CustomerUpdateKind[])
              .filter((kind) => kind !== 'cost_change')
              .map((kind) => (
                <option key={kind} value={kind}>
                  {KIND_LABELS[kind]}
                </option>
              ))}
          </select>
        </div>

        <div className="form-group">
          <label htmlFor="kundeninfo-subject">Betreff</label>
          <input
            id="kundeninfo-subject"
            type="text"
            maxLength={SUBJECT_MAX}
            value={form.subject}
            onChange={(e) => setForm({ ...form, subject: e.target.value })}
            disabled={actionLoading}
          />
        </div>

        <div className="form-group">
          <label htmlFor="kundeninfo-body">Nachricht</label>
          <textarea
            id="kundeninfo-body"
            rows={5}
            maxLength={BODY_MAX}
            value={form.body}
            onChange={(e) => setForm({ ...form, body: e.target.value })}
            disabled={actionLoading}
          />
        </div>

        <PhotoPicker
          orderId={orderId}
          selectedIds={form.photoIds}
          onChange={(ids) => setForm({ ...form, photoIds: ids })}
          disabled={actionLoading}
        />

        <div className="kundeninfo-compose-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void handleSaveDraft()}
            disabled={actionLoading}
          >
            Als Entwurf speichern
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void handleCreateAndSend()}
            disabled={actionLoading}
          >
            Erstellen & senden
          </button>
        </div>
      </section>
    </div>
  );
}

export default KundeninfoTab;
