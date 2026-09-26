// KundeninfoTab — customer progress-update history + compose form (V1.2).
//
// Permission model is ROLE-based (not fine-grained): the V1.2 customer-update
// endpoints are ADMIN + GOLDSMITH only. A user without that role must never
// see the compose form and the history GET must never fire (it 403s
// backend-side for VIEWER) — so the query itself is gated (`enabled`), not
// just the UI.
//
// SMTP status: `getEmailConfig()` is ADMIN-only backend-side (a GOLDSMITH
// gets 403), so it is only queried for `isAdmin`. For everyone else the
// honest source of truth is the per-send `delivered` flag returned by
// `sendUpdate`/`createUpdate` → `sendUpdate`.
//
// W6 "Update mit Fotos": the composer loads the customer's message context
// (PHOTO_USE consent, email address, Art. 21 opt-out), blocks sending photos
// without the consent (text-only stays possible), previews the email text and
// downloads the same content as PDF for customers without email.
//
// W4-03: server state on TanStack Query. The history and the message context
// are queries nested under the order (queryKeys.orders.*), so an
// `order_updates` hint refreshes them; every change invalidates the order,
// which also refreshes its Verlauf.
import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth, useToast } from '../../contexts';
import { customerUpdatesApi } from '../../api/customer-updates';
import type {
  CustomerMessagePreview,
  CustomerUpdate,
  CustomerUpdateCreateInput,
  CustomerUpdateKind,
  CustomerUpdateSendResult,
} from '../../api/customer-updates';
import { getEmailConfig } from '../../api/admin';
import { extractErrorDetail } from '../../api/consents';
import { queryKeys } from '../../api/queryKeys';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import { Button, PageState, Field, type PageStateValue } from '../../ui';
import { StatusBadge } from '../../ui/StatusBadge';
import { PhotoPicker } from './PhotoPicker';
import { ComposerHints, MessagePreviewBox } from './KundeninfoMessageAids';
import { invalidateOrder } from './orderQueries';
import './kundeninfo.css';

export interface KundeninfoDraftInput {
  kind: CustomerUpdateKind;
  subject: string;
  body: string;
  photoIds: string[];
}

export interface KundeninfoTabProps {
  orderId: number;
  customerName?: string | null;
  /**
   * Pre-fills the compose form (W2-08 milestone prompt, DOM-30). A new
   * object re-applies it. Nothing is sent until the user taps a button.
   */
  initialDraft?: KundeninfoDraftInput | null;
}

const KIND_LABELS: Record<CustomerUpdateKind, string> = {
  progress: 'Fortschritt',
  cost_change: 'Kostenänderung',
  ready_for_pickup: 'Abholbereit',
  custom: 'Individuell',
};

const COMPOSE_KINDS = (Object.keys(KIND_LABELS) as CustomerUpdateKind[]).filter(
  (kind) => kind !== 'cost_change'
);

const DELIVERY_METHOD_LABELS: Record<string, string> = {
  email: 'E-Mail',
  pdf_manual: 'PDF (manuell)',
};

const SUBJECT_MAX = 300;
const BODY_MAX = 20000;

const EMAIL_CONFIG_KEY = queryKeys.admin.emailConfig();

type ComposeForm = KundeninfoDraftInput;

const EMPTY_FORM: ComposeForm = {
  kind: 'progress',
  subject: '',
  body: '',
  photoIds: [],
};

function copyDraft(draft: KundeninfoDraftInput): ComposeForm {
  return { ...draft, photoIds: [...draft.photoIds] };
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

/** Run a request, log failures with context and rethrow (the query shows them). */
async function logged<T>(context: string, request: () => Promise<T>): Promise<T> {
  try {
    return await request();
  } catch (err) {
    logError(context, err);
    throw err;
  }
}

function useKundeninfoQueries(orderId: number, canManage: boolean, isAdmin: boolean) {
  const history = useQuery({
    queryKey: queryKeys.orders.customerUpdates(orderId),
    queryFn: () =>
      logged('KundeninfoTab.loadHistory', async () =>
        sortNewestFirst(await customerUpdatesApi.listUpdates(orderId))
      ),
    // The backend 403s CUSTOMER_UPDATE_VIEW for VIEWER; never even attempt it.
    enabled: canManage,
  });
  // A failure only hides the hints; the backend still enforces the rules.
  const messageContext = useQuery({
    queryKey: queryKeys.orders.messageContext(orderId),
    queryFn: () =>
      logged('KundeninfoTab.loadMessageContext', async () =>
        (await customerUpdatesApi.getMessageContext(orderId)) ?? null
      ),
    enabled: canManage,
  });
  // getEmailConfig is ADMIN-only backend-side — never call it as GOLDSMITH.
  const emailConfig = useQuery({
    queryKey: EMAIL_CONFIG_KEY,
    queryFn: () => logged('KundeninfoTab.loadEmailConfig', getEmailConfig),
    enabled: isAdmin,
  });
  const smtpConfigured = emailConfig.data
    ? emailConfig.data.email_notifications_enabled &&
      !!emailConfig.data.smtp_host &&
      emailConfig.data.password_configured
    : null;
  return {
    history,
    messageContext: messageContext.data ?? null,
    smtpConfigured,
  };
}

function historyState(history: ReturnType<typeof useKundeninfoQueries>['history']): PageStateValue {
  if (history.isPending) return { status: 'loading' };
  if (history.isError) {
    return {
      status: 'error',
      error: getErrorMessage(history.error, 'Verlauf konnte nicht geladen werden.'),
      retry: () => void history.refetch(),
    };
  }
  return { status: history.data.length === 0 ? 'empty' : 'ready' };
}

interface HistoryItemProps {
  update: CustomerUpdate;
  isBusy: boolean;
  onDownloadPdf: (update: CustomerUpdate) => void;
  onSend: (update: CustomerUpdate) => void;
  onMarkDelivered: (update: CustomerUpdate) => void;
}

function HistoryItem({ update, isBusy, onDownloadPdf, onSend, onMarkDelivered }: HistoryItemProps) {
  const isOpen = update.status === 'draft' || update.status === 'send_failed';
  return (
    <li className="kundeninfo-item">
      <div className="kundeninfo-item-header">
        <span className="kundeninfo-kind">{KIND_LABELS[update.kind] ?? update.kind}</span>
        <StatusBadge kind="customerUpdate" status={update.status} />
      </div>
      {update.subject && <p className="kundeninfo-subject">{update.subject}</p>}
      <div className="kundeninfo-meta">
        <span>{new Date(update.created_at).toLocaleString('de-DE')}</span>
        {update.delivery_method && (
          <span>{DELIVERY_METHOD_LABELS[update.delivery_method] ?? update.delivery_method}</span>
        )}
      </div>
      <div className="kundeninfo-item-actions">
        {update.status === 'sent' && (
          <Button variant="secondary" icon="file-text" onClick={() => onDownloadPdf(update)} disabled={isBusy}>
            PDF laden
          </Button>
        )}
        {isOpen && (
          <>
            <Button icon="send" onClick={() => onSend(update)} disabled={isBusy}>
              Senden
            </Button>
            <Button variant="secondary" onClick={() => onMarkDelivered(update)} disabled={isBusy}>
              Als übergeben markieren
            </Button>
          </>
        )}
      </div>
    </li>
  );
}

export function KundeninfoTab({ orderId, customerName, initialDraft }: KundeninfoTabProps) {
  const { hasRole, isAdmin } = useAuth();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const canManage = hasRole(['ADMIN', 'GOLDSMITH']);
  const subjectRef = useRef<HTMLInputElement>(null);

  const [form, setForm] = useState<ComposeForm>(() =>
    initialDraft ? copyDraft(initialDraft) : EMPTY_FORM
  );
  const [preview, setPreview] = useState<CustomerMessagePreview | null>(null);
  // W6 "Statusbericht anhängen" — transient, applies to the next send only
  // (there is no DB column for it; see AttachStatusReportRequest docstring).
  const [attachStatusReport, setAttachStatusReport] = useState(false);

  // A new initialDraft object re-applies the pre-fill (adjusting state during
  // render instead of an effect; React re-renders before painting).
  const [appliedDraft, setAppliedDraft] = useState(initialDraft);
  if (initialDraft !== appliedDraft) {
    setAppliedDraft(initialDraft);
    if (initialDraft) {
      setForm(copyDraft(initialDraft));
      setPreview(null);
    }
  }

  const { history, messageContext, smtpConfigured } = useKundeninfoQueries(
    orderId,
    canManage,
    isAdmin
  );

  // A preview describes one exact form state; any edit makes it stale.
  const updateForm = (patch: Partial<ComposeForm>) => {
    setForm((current) => ({ ...current, ...patch }));
    setPreview(null);
  };

  const resetForm = () => {
    setForm(EMPTY_FORM);
    setPreview(null);
    setAttachStatusReport(false);
  };

  const buildInput = (): CustomerUpdateCreateInput => ({
    kind: form.kind,
    subject: form.subject.trim() || undefined,
    body: form.body.trim() || undefined,
    photo_ids: form.photoIds,
  });

  const refreshOrder = () => invalidateOrder(queryClient, orderId);

  const handleSendResult = async (result: CustomerUpdateSendResult) => {
    if (result.delivered) {
      showToast('Kundeninfo wurde per E-Mail versendet.', 'success');
      return;
    }
    showToast(
      result.reason === 'opted_out'
        ? 'Kunde wünscht keine E-Mail-Updates — PDF erstellt, bitte manuell übergeben.'
        : 'Als PDF erstellt — bitte manuell an den Kunden übergeben.',
      'info'
    );
    // SMTP is unconfigured, so nothing was actually sent — surface the PDF
    // immediately instead of leaving the goldsmith to dig for the manual
    // "PDF laden" history-row button (still there as a fallback). A failure
    // here must never break the send flow itself.
    try {
      const blob = await customerUpdatesApi.downloadUpdatePdf(result.update.id);
      downloadBlob(blob, `kundeninfo_${result.update.id}.pdf`);
    } catch (err) {
      logError('KundeninfoTab.autoDownloadPdf', err);
    }
  };

  /** Log with context, then toast the backend detail or the fallback text. */
  const failWith = (context: string, fallback: string, useDetail = false) => (err: unknown) => {
    logError(context, err);
    showToast((useDetail && extractErrorDetail(err)) || fallback, 'error');
  };

  const downloadPdf = useMutation({
    mutationFn: async (update: CustomerUpdate) => {
      downloadBlob(await customerUpdatesApi.downloadUpdatePdf(update.id), `kundeninfo_${update.id}.pdf`);
    },
    onError: failWith('KundeninfoTab.downloadPdf', 'PDF-Download fehlgeschlagen.'),
  });

  const sendExisting = useMutation({
    mutationFn: (update: CustomerUpdate) => customerUpdatesApi.sendUpdate(update.id),
    onSuccess: async (result) => {
      await handleSendResult(result);
      await refreshOrder();
    },
    onError: failWith('KundeninfoTab.sendUpdate', 'Update konnte nicht gesendet werden.'),
  });

  const markDelivered = useMutation({
    mutationFn: (update: CustomerUpdate) => customerUpdatesApi.markDelivered(update.id),
    onSuccess: async () => {
      showToast('Als übergeben markiert.', 'success');
      await refreshOrder();
    },
    onError: failWith('KundeninfoTab.markDelivered', 'Konnte nicht als übergeben markiert werden.'),
  });

  const statusReport = useMutation({
    mutationFn: async () => {
      const blob = await customerUpdatesApi.downloadOrderStatusReportPdf(orderId);
      downloadBlob(blob, `statusbericht_auftrag_${orderId}.pdf`);
    },
    onError: failWith('KundeninfoTab.downloadStatusReport', 'Statusbericht konnte nicht erstellt werden.'),
  });

  const saveDraft = useMutation({
    mutationFn: (input: CustomerUpdateCreateInput) => customerUpdatesApi.createUpdate(orderId, input),
    onSuccess: async () => {
      showToast('Entwurf gespeichert.', 'success');
      resetForm();
      await refreshOrder();
    },
    onError: failWith('KundeninfoTab.createUpdate', 'Entwurf konnte nicht gespeichert werden.', true),
  });

  const createAndSend = useMutation({
    mutationFn: async ({ input, attach }: { input: CustomerUpdateCreateInput; attach: boolean }) => {
      const created = await customerUpdatesApi.createUpdate(orderId, input);
      return customerUpdatesApi.sendUpdate(created.id, attach);
    },
    onSuccess: async (result) => {
      await handleSendResult(result);
      resetForm();
      await refreshOrder();
    },
    onError: failWith(
      'KundeninfoTab.createAndSend',
      'Update konnte nicht erstellt oder gesendet werden.',
      true
    ),
  });

  const loadPreview = useMutation({
    mutationFn: (input: CustomerUpdateCreateInput) => customerUpdatesApi.previewUpdate(orderId, input),
    onSuccess: (data) => setPreview(data),
    onError: failWith('KundeninfoTab.previewUpdate', 'Vorschau konnte nicht erstellt werden.', true),
  });

  const previewPdf = useMutation({
    mutationFn: async (input: CustomerUpdateCreateInput) => {
      const blob = await customerUpdatesApi.previewUpdatePdf(orderId, input);
      downloadBlob(blob, `kundeninfo_vorschau_${orderId}.pdf`);
    },
    onError: failWith('KundeninfoTab.previewUpdatePdf', 'PDF-Vorschau konnte nicht erstellt werden.', true),
  });

  const isBusy = [
    downloadPdf,
    sendExisting,
    markDelivered,
    statusReport,
    saveDraft,
    createAndSend,
    loadPreview,
    previewPdf,
  ].some((mutation) => mutation.isPending);

  // Photos without PHOTO_USE consent are refused server-side (422); block
  // the buttons up front. Unknown context (null) leaves it to the backend.
  const photosBlocked =
    form.photoIds.length > 0 && messageContext !== null && !messageContext.photo_consent;

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
        <PageState
          state={historyState(history)}
          skeletonCount={2}
          empty={{
            icon: 'mail',
            title: 'Noch keine Kundeninfos versendet',
            body: 'Schreiben Sie unten die erste Kundeninfo zu diesem Auftrag.',
            headingLevel: 3,
            action: (
              <Button variant="secondary" icon="pencil" onClick={() => subjectRef.current?.focus()}>
                Kundeninfo schreiben
              </Button>
            ),
          }}
        >
          <ul className="kundeninfo-list">
            {(history.data ?? []).map((update) => (
              <HistoryItem
                key={update.id}
                update={update}
                isBusy={isBusy}
                onDownloadPdf={(u) => downloadPdf.mutate(u)}
                onSend={(u) => sendExisting.mutate(u)}
                onMarkDelivered={(u) => markDelivered.mutate(u)}
              />
            ))}
          </ul>
        </PageState>
      </section>

      <section className="kundeninfo-compose">
        <div className="kundeninfo-item-header">
          <h3>Neue Kundeninfo</h3>
          <Button
            variant="secondary"
            icon="file-text"
            onClick={() => statusReport.mutate()}
            disabled={isBusy}
            loading={statusReport.isPending}
          >
            Statusbericht (PDF)
          </Button>
        </div>

        {isAdmin && smtpConfigured === false && (
          <p className="kundeninfo-smtp-note" role="status">
            E-Mail nicht konfiguriert — Updates werden als PDF erzeugt
          </p>
        )}

        <Field label="Art" name="kind">
          <select
            id="kundeninfo-kind"
            value={form.kind}
            onChange={(e) => updateForm({ kind: e.target.value as CustomerUpdateKind })}
            disabled={isBusy}
          >
            {COMPOSE_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {KIND_LABELS[kind]}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Betreff" name="subject">
          <input
            ref={subjectRef}
            id="kundeninfo-subject"
            type="text"
            maxLength={SUBJECT_MAX}
            value={form.subject}
            onChange={(e) => updateForm({ subject: e.target.value })}
            disabled={isBusy}
          />
        </Field>

        <Field label="Nachricht" name="body">
          <textarea
            id="kundeninfo-body"
            rows={5}
            maxLength={BODY_MAX}
            value={form.body}
            onChange={(e) => updateForm({ body: e.target.value })}
            disabled={isBusy}
          />
        </Field>

        <PhotoPicker
          orderId={orderId}
          selectedIds={form.photoIds}
          onChange={(ids) => updateForm({ photoIds: ids })}
          disabled={isBusy}
        />

        <ComposerHints
          context={messageContext}
          photosSelected={form.photoIds.length > 0}
          onRemovePhotos={() => updateForm({ photoIds: [] })}
          disabled={isBusy}
        />

        {preview && <MessagePreviewBox preview={preview} onClose={() => setPreview(null)} />}

        <label className="kundeninfo-checkbox" htmlFor="kundeninfo-attach-status-report">
          <input
            id="kundeninfo-attach-status-report"
            type="checkbox"
            checked={attachStatusReport}
            onChange={(e) => setAttachStatusReport(e.target.checked)}
            disabled={isBusy}
          />
          Statusbericht anhängen
        </label>

        <div className="kundeninfo-compose-actions">
          <Button
            variant="secondary"
            onClick={() => loadPreview.mutate(buildInput())}
            disabled={isBusy}
            loading={loadPreview.isPending}
          >
            Vorschau anzeigen
          </Button>
          <Button
            variant="secondary"
            onClick={() => previewPdf.mutate(buildInput())}
            disabled={isBusy || photosBlocked}
            loading={previewPdf.isPending}
          >
            Vorschau als PDF
          </Button>
          <Button
            variant="secondary"
            onClick={() => saveDraft.mutate(buildInput())}
            disabled={isBusy || photosBlocked}
            loading={saveDraft.isPending}
          >
            Als Entwurf speichern
          </Button>
          <Button
            icon="send"
            onClick={() => createAndSend.mutate({ input: buildInput(), attach: attachStatusReport })}
            disabled={isBusy || photosBlocked}
            loading={createAndSend.isPending}
          >
            Erstellen & senden
          </Button>
        </div>
      </section>
    </div>
  );
}

export default KundeninfoTab;
